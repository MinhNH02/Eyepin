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


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def username(user) -> str:
    """Tên đăng nhập trong trường `owner`/`assignee` CVAT trả (dict có `username`); `None` (chưa giao, tài khoản đã xoá) hoặc dạng lạ thì `""`."""
    name = user.get("username") if isinstance(user, dict) else None
    return name if isinstance(name, str) else ""


def task_row(raw: dict) -> dict:
    """Một dòng task của báo cáo; `jobs` là tổng số job của task (`jobs.count`), `None` nếu CVAT không cho biết."""
    jobs, name, size = raw.get("jobs"), raw.get("name"), raw.get("size")
    count = jobs.get("count") if isinstance(jobs, dict) else None
    return {"id": raw["id"], "name": name if isinstance(name, str) else "", "size": size if _is_int(size) else 0,
            "jobs": count if _is_int(count) else None}


def job_row(raw: dict) -> dict:
    """Một dòng job của báo cáo; `issues` là số issue CVAT đã đếm sẵn cho job (`issues.count`), `None` nếu không có."""
    issues, kind = raw.get("issues"), raw.get("type")
    count = issues.get("count") if isinstance(issues, dict) else None
    return {"id": raw["id"], "type": kind if isinstance(kind, str) and kind else "annotation", "assignee": username(raw.get("assignee")),
            "issues": count if _is_int(count) else None}


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
        try:
            data = r.json()
        except ValueError as e:                      # 200 nhưng không phải JSON (trang HTML của proxy...): không để "Expecting value" lọt ra giao diện
            raise CvatError("CVAT trả dữ liệu không đọc được khi đăng nhập (không phải JSON). Kiểm tra lại địa chỉ CVAT.") from e
        key = data.get("key") if isinstance(data, dict) else None
        if not key:
            raise CvatError("CVAT không trả khoá đăng nhập.")
        self._s.headers["Authorization"] = "Token " + key

    @property
    def token(self) -> str | None:
        """Khoá đăng nhập đang dùng (sau `login` hoặc `use_token`), hoặc None. Chỉ để `eyepin.cvatlogin` nhớ qua lần mở tool; không in ra, không ghi log."""
        auth = self._s.headers.get("Authorization") or ""
        return auth[len("Token "):] if auth.startswith("Token ") and len(auth) > len("Token ") else None

    def use_token(self, token: str) -> None:
        """Dùng một khoá đã có (đã nhớ từ lần trước) thay cho đăng nhập bằng mật khẩu. Chưa biết khoá còn hiệu lực không: gọi `whoami()` để thử."""
        if not isinstance(token, str) or not token.strip() or any(c.isspace() for c in token):
            raise ValueError("Khoá đăng nhập không hợp lệ.")
        self._s.headers["Authorization"] = "Token " + token

    def whoami(self) -> str:
        """Tên người dùng đang đăng nhập (`GET /api/users/self`): cách nhẹ nhất để biết khoá còn dùng được không. Khoá hết hạn hoặc bị huỷ → `LoginNeeded`."""
        d = self._json("GET", "/api/users/self")
        name = d.get("username") if isinstance(d, dict) else None
        if not isinstance(name, str) or not name:
            raise CvatError("CVAT không cho biết tên người dùng đang đăng nhập.")
        return name

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

    # ---- báo cáo issue (chỉ đọc: chỉ GET) ----
    def _all(self, path: str, params: dict, what: str) -> list[dict]:
        """Lấy MỘT danh sách phân trang của CVAT trong đúng một phản hồi (`page_size=all`) và kiểm là trọn vẹn: `count` khớp số mục, không còn
        trang sau, mọi mục là dict có `id` số nguyên không trùng. Sai điều nào cũng là lỗi, không đoán và không trả danh sách thiếu. `what` là tên loại mục
        trong thông điệp lỗi."""
        d = self._json("GET", path, params=dict(params, page_size="all"))
        results = d.get("results") if isinstance(d, dict) else None
        ok = (isinstance(d, dict) and isinstance(results, list) and _is_int(d.get("count")) and not d.get("next") and len(results) == d["count"]
              and all(isinstance(r, dict) and _is_int(r.get("id")) for r in results) and len({r["id"] for r in results}) == len(results))
        if not ok:
            raise CvatError("CVAT trả danh sách %s không trọn vẹn (có thể dữ liệu vừa thay đổi). Hãy bấm Làm mới." % what)
        return results

    def report_tasks(self) -> list[dict]:
        """Mọi task tài khoản xem được, dạng `task_row`, `id` tăng dần."""
        return sorted((task_row(t) for t in self._all("/api/tasks", {}, "task")), key=lambda r: r["id"])

    def report_jobs(self, task_id: int) -> list[dict]:
        """Các job của một task, dạng `job_row` (kèm số issue CVAT đếm sẵn), `id` tăng dần."""
        return sorted((job_row(j) for j in self._all("/api/jobs", {"task_id": task_id}, "job")), key=lambda r: r["id"])

    def issues(self, task_id: int) -> list[dict]:
        """Mọi issue của một task, dict nguyên dạng CVAT trả, đúng thứ tự CVAT trả (`id` giảm dần)."""
        return self._all("/api/issues", {"task_id": task_id}, "issue")

    def comments(self, job_id: int) -> list[dict]:
        """Mọi bình luận của một job, dict nguyên dạng CVAT trả (`id` giảm dần). Chỉ lọc theo job: `task_id` bị CVAT bỏ qua và trả mọi bình luận."""
        return self._all("/api/comments", {"job_id": job_id}, "bình luận")
