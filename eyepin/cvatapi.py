"""Client API CVAT mỏng cho EyePin: mở job trên CVAT local và gửi nhãn về bằng import.

Chỉ nối với localhost. Ảnh frame trả về dạng bytes trong RAM, không ghi đĩa. Khoá đăng nhập chỉ giữ trong đối tượng này.
Mọi thông điệp lỗi là tiếng Việt, hiện thẳng cho người dùng.
"""
import http.cookiejar
import io
import time
import zipfile
from urllib.parse import urlsplit

import requests

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
EYES = ("mattrai", "matphai")
POLL_INTERVAL = 0.5
MAX_WAIT = 300.0


class CvatError(Exception):
    """Lỗi khi làm việc với CVAT; thông điệp tiếng Việt. `status` là mã HTTP nếu lỗi đến từ một phản hồi của server."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class LoginNeeded(CvatError):
    """CVAT trả 401: chưa đăng nhập hoặc khoá hết hạn."""


def _check_local(url: str) -> str:
    if "://" not in url:
        url = "http://" + url
    host = urlsplit(url).hostname
    if host not in LOCAL_HOSTS:
        raise CvatError("Lần này chỉ nối với CVAT trên máy (localhost). Server công ty chưa được bật.")
    return url.rstrip("/")


class CvatClient:
    def __init__(self, url: str, timeout: float = 30):
        self.url = _check_local(url)
        self.timeout = timeout
        self.poll_interval = POLL_INTERVAL
        self.max_wait = MAX_WAIT
        self._s = requests.Session()
        self._s.trust_env = False  # không đi qua proxy hệ thống: khoá và ảnh chỉ nằm trên máy
        self._s.headers["Accept"] = "*/*"  # không bao giờ application/json (server công ty trả 406)
        # Không nhận cookie nào. Đăng nhập, CVAT trả khoá VÀ đặt cookie phiên; lúc không có khoá (đăng nhập lại, sau một lần đăng nhập hỏng)
        # CVAT xác thực bằng cookie đó và đòi CSRF cho mọi POST: 403 "CSRF Failed: CSRF token missing." (log CVAT 2.75, 2026-11-16).
        self._s.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))

    def close(self):
        self._s.close()

    # ---- nền ----
    def _request(self, method, path_or_url, **kw):
        url = path_or_url if "://" in path_or_url else self.url + path_or_url
        _check_local(url)
        try:
            r = self._s.request(method, url, timeout=self.timeout, allow_redirects=False, **kw)
        except requests.ConnectionError as e:
            raise CvatError("Không nối được CVAT (%s). Hãy bật Docker Desktop và chờ CVAT chạy; nếu CVAT đã chạy mà vẫn lỗi, "
                            "chạy `docker restart traefik`." % self.url) from e
        except requests.Timeout as e:
            raise CvatError("CVAT không trả lời kịp (quá %g giây)." % self.timeout) from e
        except requests.RequestException as e:
            raise CvatError("Lỗi khi gọi CVAT: %s" % e) from e
        if r.status_code == 401:
            raise LoginNeeded("CVAT báo chưa đăng nhập hoặc phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.", 401)
        if 300 <= r.status_code < 400:
            raise CvatError("CVAT chuyển hướng sang nơi khác (%d); EyePin không đi theo." % r.status_code, r.status_code)
        if r.status_code >= 400:
            detail = r.text.strip()[:300]
            raise CvatError("CVAT báo lỗi %d khi gọi %s%s" % (r.status_code, urlsplit(url).path, ": " + detail if detail else ""), r.status_code)
        return r

    def _json(self, method, path, **kw):
        try:
            return self._request(method, path, **kw).json()
        except ValueError as e:
            raise CvatError("CVAT trả dữ liệu không đọc được.") from e

    def _paged(self, path, params):
        out, url, params = [], path, dict(params, page_size=100)
        while url:
            d = self._json("GET", url, params=params)
            out.extend(d.get("results", []))
            url, params = d.get("next"), None
        return out

    def _wait(self, rq_id) -> dict:
        """Hỏi `requests/{rq_id}` tới khi xong; trả về dict trạng thái `finished`."""
        deadline = time.monotonic() + self.max_wait
        while True:
            d = self._json("GET", "/api/requests/%s" % rq_id)
            status = d.get("status")
            if status == "finished":
                return d
            if status == "failed":
                raise CvatError("CVAT báo thất bại: %s" % (d.get("message") or "không rõ lý do"))
            if time.monotonic() >= deadline:
                raise CvatError("CVAT xử lý quá lâu (hơn %g giây), đã ngừng chờ." % self.max_wait)
            time.sleep(self.poll_interval)

    # ---- API ----
    def login(self, user: str, password: str) -> None:
        self._s.headers.pop("Authorization", None)  # khoá cũ (hết hạn) làm server từ chối cả lúc đăng nhập
        try:
            r = self._request("POST", "/api/auth/login", json={"username": user, "password": password})
        except CvatError as e:
            if e.status == 400:
                raise CvatError("Sai tên đăng nhập hoặc mật khẩu.", 400) from e
            raise
        key = r.json().get("key")
        if not key:
            raise CvatError("CVAT không trả khoá đăng nhập.")
        self._s.headers["Authorization"] = "Token " + key

    def tasks(self) -> list[dict]:
        return [{"id": t["id"], "name": t.get("name", ""), "size": t.get("size", 0)} for t in self._paged("/api/tasks", {})]

    def jobs(self, task_id: int) -> list[dict]:
        keys = ("id", "start_frame", "stop_frame", "state", "stage")
        return [{k: j.get(k) for k in keys} for j in self._paged("/api/jobs", {"task_id": task_id})]

    def job(self, job_id: int) -> dict:
        return self._json("GET", "/api/jobs/%d" % job_id)

    def meta(self, job_id: int) -> dict:
        return self._json("GET", "/api/jobs/%d/data/meta" % job_id)

    def frame(self, job_id: int, number: int) -> bytes:
        return self._request("GET", "/api/jobs/%d/data" % job_id,
                             params={"type": "frame", "number": number, "quality": "original"}).content

    def annotations(self, job_id: int) -> dict:
        """Nhãn hiện có của job dạng JSON (`version, tags, shapes, tracks`); phân biệt đúng shape và track."""
        return self._json("GET", "/api/jobs/%d/annotations" % job_id)

    def export_xml(self, job_id: int, fmt: str) -> bytes:
        rq = self._json("POST", "/api/jobs/%d/dataset/export" % job_id, params={"format": fmt, "save_images": "False"})
        done = self._wait(rq["rq_id"])
        url = done.get("result_url")
        if not url:
            raise CvatError("CVAT báo xuất xong nhưng không đưa đường tải file.")
        data = self._request("GET", url).content
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return z.read("annotations.xml")
        except (zipfile.BadZipFile, KeyError) as e:
            raise CvatError("File CVAT xuất ra không có annotations.xml.") from e

    def import_xml(self, job_id: int, xml: bytes) -> None:
        rq = self._json("POST", "/api/jobs/%d/annotations" % job_id,
                        params={"format": "CVAT 1.1"},  # không gửi `filename`: CVAT hiểu là mã file TUS (400)
                        files={"annotation_file": ("eyepin.xml", xml, "text/xml")})
        self._wait(rq["rq_id"])

    def labels(self, job_id: int) -> list[dict]:
        """Nhãn của job (`id, name, type, sublabels`)."""
        return self._paged("/api/labels", {"job_id": job_id})

    def eye_labels_ok(self, job_id: int) -> str | None:
        labels = {lb.get("name"): lb for lb in self.labels(job_id)}
        for name in EYES:
            lb = labels.get(name)
            if lb is None:
                return "Job chưa có nhãn '%s'." % name
            if lb.get("type") != "skeleton":
                return "Nhãn '%s' của job không phải kiểu skeleton." % name
            if len(lb.get("sublabels") or []) != 8:
                return "Nhãn '%s' không đủ 8 điểm (có %d)." % (name, len(lb.get("sublabels") or []))
        return None
