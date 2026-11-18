"""Server CVAT giả (http.server trong luồng, chỉ 127.0.0.1, cổng ngẫu nhiên) để test mà không cần Docker.

Dùng:
    srv = FakeCvat([FakeJob(7, task_id=3, task_name="clip", n_frames=5, start_frame=10, xml=b"...")])
    srv.start(); self.addCleanup(srv.stop)
    client = CvatClient(srv.url)

FakeJob(id, task_id=1, task_name="task", n_frames=3, start_frame=0, xml=XML_EMPTY, deleted_frames=(), labels=None, state="in progress", stage="annotation",
        data_start_frame=0, frame_step=1, media="images", included_frames=None, assignee=None, type="annotation", issue_count=None, listed=True)
    Như CVAT thật (cvat/apps/engine/views.py, data/meta của job): `start_frame`/`stop_frame` của job là số frame TƯƠNG ĐỐI của task (cũng là số
    dùng trong `data?type=frame&number=`, `deleted_frames` và JSON annotations); `GET /api/jobs/{id}/data/meta` trả `start_frame`/`stop_frame`
    TUYỆT ĐỐI của media (`data_start_frame + start_frame*frame_step`), `size` = số frame của job, `frames` một phần tử mỗi frame với
    media="images" nhưng chỉ MỘT phần tử với media="video", `included_frames` (job thưa) như đã đặt. `.meta_overrides` (dict) ghi đè trường của meta.
    .xml (bytes) là nhãn hiện tại của job; .export_xml_by_format {định dạng: bytes} cho export khác nhau theo định dạng (vắng thì dùng .xml);
    .annotations_json là JSON của GET /api/jobs/{id}/annotations (mặc định rỗng); .updated_date đổi mỗi lần import; .labels mặc định là hai skeleton mattrai (14-21) và matphai (22-29)
    (FakeJob.default_labels()); ảnh frame số k (k = start_frame..start_frame+n_frames-1) là test_tracking.render(k) mã hoá JPEG.

    Thêm cho đường báo cáo issue: `assignee` (tên người được giao hoặc None), `type` (loại job, mặc định "annotation"), `issue_count` (số ép vào
    `issues.count` của job khi liệt kê; None = tự đếm trong FakeCvat.issues, tính cả issue ẩn), `listed` (False: job vắng ở GET /api/jobs
    nhưng vẫn được đếm vào `jobs.count` của task, như job tài khoản không xem được).

FakeCvat.jobs: dict id -> FakeJob (thêm/bớt được sau khi tạo).
Issue và bình luận (dạng dữ liệu chép từ design/cvat-api-notes.md, mục "Issue và bình luận"):
    fake_user(name), fake_issue(id, job, frame, resolved=, owner=, created=, comments=), fake_comment(id, issue, message, owner=, created=)
    FakeCvat.issues, .comments   list dict như hàm trên tạo (gán thẳng, đổi được giữa chừng)
    GET /api/issues     lọc `task_id` (task của job chứa issue) và `job_id`, xếp `id` GIẢM dần, bỏ issue có mã trong .hidden_issues; issue có
                        `comments` None thì trả `{"count": số bình luận trong .comments, "url"}` (bản sao, không sửa dict đang lưu)
    GET /api/comments   lọc `job_id` (job của issue chứa bình luận) và `issue_id`, xếp `id` giảm dần; BỎ QUA `task_id` như CVAT thật
    GET /api/jobs       chỉ job `listed`; mỗi dòng thêm `type`, `assignee`, `issues: {url, count}`; GET /api/jobs/{id} không đổi
    GET /api/tasks      mỗi task thêm `jobs: {count}` (số FakeJob của task, tính cả job không `listed`)
    page_size=all       trả toàn bộ danh sách trong một trang (không bị .page_size giới hạn)
    PATCH, PUT, DELETE  được ghi vào requests/calls rồi trả 405 (đường báo cáo chỉ được GET)
Công tắc (thuộc tính, đổi được giữa chừng):
    fail_401            mọi đường trừ đăng nhập trả 401
    fail_500            mọi đường trừ đăng nhập trả 500
    fail_import         chuỗi: import kết thúc `failed` với thông điệp đó (job giữ nguyên nhãn cũ)
    drop_on_poll        True: ngắt kết nối (không trả lời) khi hỏi GET /api/requests/{rq_id}
    shift_on_import     số px: dời toạ độ x của điểm đầu tiên trong XML đã import (mô phỏng CVAT đổi nhãn)
    polls_before_finish số lần hỏi trạng thái còn trả `queued` trước khi `finished` (mặc định 1; rất lớn = không bao giờ xong)
    page_size           số mục mỗi trang của /api/tasks, /api/jobs, /api/labels, /api/issues, /api/comments (mặc định 100)
    hidden_issues       tập mã issue tài khoản "không xem được": vắng ở GET /api/issues nhưng vẫn được đếm vào `issues.count` của job
    tamper              dict `đường dẫn -> hàm(payload) -> payload`, áp vào phản hồi DANH SÁCH ngay trước khi gửi (giả lập phản hồi hỏng)
    reject_login_with_auth  True: đăng nhập có kèm header Authorization (khoá cũ) bị trả 401
    redirect_job        True: GET /api/jobs/{id} trả 302 sang http://example.com/ (kiểm client không đi theo)
    lose_non_eye_on_import  True: import xong thì JSON annotations của job mất một đối tượng không phải mắt (shape trước, rồi track)
    password            mật khẩu đúng (mặc định "pw"; sai -> 400); key trả về là `token` (mặc định "k1")
    username            tên trả về ở GET /api/users/self (mặc định "minh"; "" = server trả dữ liệu thiếu tên)
Xác thực như CVAT thật (cvat/settings/base.py, DEFAULT_AUTHENTICATION_CLASSES: Token rồi Session): đăng nhập đúng trả `key` VÀ đặt cookie
    `sessionid`, `csrftoken` (dj-rest-auth SESSION_LOGIN mặc định bật). Có header Authorization thì chỉ xét khoá (sai -> 401). Không có header
    mà có cookie phiên hợp lệ thì yêu cầu được xác thực bằng phiên; khi đó POST (kể cả POST /api/auth/login) phải kèm header X-CSRFToken
    trùng cookie csrftoken, không thì 403 {"detail": "CSRF Failed: CSRF token missing."} (đúng 45 byte như log CVAT 2.75 ngày 2026-11-16).
Ghi lại:
    requests            list {"method", "path" (không query), "query" (dict), "headers" (dict)}, theo thứ tự
    calls               Counter "METHOD /path" -> số lần gọi (ví dụ "GET /api/requests/rq1")
    export_formats / export_query, import_formats, frame_query: tham số các lần gọi tương ứng
"""
import gc
import io
import json
import re
import threading
import zipfile
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import cv2

import test_tracking as T

XML_EMPTY = b'<?xml version="1.0" encoding="utf-8"?><annotations><version>1.1</version></annotations>'


def fake_user(name):
    """`owner`/`assignee` dạng CVAT trả; `name` None thì trả None (tài khoản đã xoá / chưa giao)."""
    return None if name is None else {"url": "http://localhost:8080/api/users/7", "id": 7, "username": name, "first_name": "", "last_name": ""}


def fake_issue(id, job, frame, resolved=False, owner="qa_01", created="2026-11-18T07:05:00.000000Z", comments=None):
    """Issue dạng CVAT trả. `comments` None: server giả tự đếm bình luận của issue khi trả; số nguyên: ép `comments.count` đúng số đó."""
    count = None if comments is None else {"count": comments, "url": "http://localhost:8080/api/comments?issue_id=%d" % id}
    return {"id": id, "frame": frame, "position": [10.0, 10.0, 50.0, 50.0], "job": job, "owner": fake_user(owner), "assignee": None,
            "created_date": created, "updated_date": created, "resolved": resolved, "comments": count}


def fake_comment(id, issue, message, owner="qa_01", created="2026-11-18T07:05:00.000000Z"):
    return {"id": id, "issue": issue, "owner": fake_user(owner), "message": message, "created_date": created, "updated_date": created}


class FakeJob:
    def __init__(self, id, task_id=1, task_name="task", n_frames=3, start_frame=0, xml=XML_EMPTY,
                 deleted_frames=(), labels=None, state="in progress", stage="annotation",
                 data_start_frame=0, frame_step=1, media="images", included_frames=None,
                 assignee=None, type="annotation", issue_count=None, listed=True):
        self.id, self.task_id, self.task_name = id, task_id, task_name
        self.assignee, self.type, self.issue_count, self.listed = assignee, type, issue_count, listed
        self.n_frames, self.start_frame = n_frames, start_frame
        self.data_start_frame, self.frame_step, self.media = data_start_frame, frame_step, media
        self.included_frames = list(included_frames) if included_frames is not None else None
        self.meta_overrides = {}
        self.xml = xml
        self.deleted_frames = list(deleted_frames)
        self.labels = labels if labels is not None else self.default_labels()
        self.state, self.stage = state, stage
        self.export_xml_by_format = {}  # {"CVAT for images 1.1": bytes, ...}; format vắng mặt thì dùng .xml
        self.annotations_json = {"version": 0, "tags": [], "shapes": [], "tracks": []}  # trả về bởi GET /annotations
        self.version = 0

    @staticmethod
    def default_labels():
        def sk(name, first):
            return {"id": first, "name": name, "type": "skeleton",
                    "sublabels": [{"id": first + i, "name": str(first + i), "type": "points"} for i in range(8)]}
        return [sk("mattrai", 14), sk("matphai", 22)]

    @property
    def stop_frame(self):
        return self.start_frame + self.n_frames - 1

    @property
    def updated_date(self):
        return "2026-11-16T10:00:%02d.000000Z" % self.version


class FakeCvat:
    token = "k1"

    def __init__(self, jobs=()):
        self.jobs = {j.id: j for j in jobs}
        self.fail_401 = self.fail_500 = False
        self.fail_import = None
        self.drop_on_poll = False
        self.reject_login_with_auth = False
        self.redirect_job = False
        self.lose_non_eye_on_import = False
        self.shift_on_import = 0.0
        self.polls_before_finish = 1
        self.page_size = 100
        self.issues, self.comments = [], []
        self.hidden_issues = set()
        self.tamper = {}
        self.password = "pw"
        self.username = "minh"
        self._sessions: dict[str, str] = {}   # sessionid -> csrftoken của các lần đăng nhập thành công
        self.requests, self.calls = [], Counter()
        self.export_formats, self.export_query, self.import_formats, self.frame_query = [], [], [], []
        self._rqs = {}
        self._lock = threading.Lock()
        self._httpd = None

    # ---- vòng đời ----
    def start(self):
        # Rác Tk của test GUI chạy trước (biến Tk) phải được dọn ở luồng chính: nếu GC chạy trong luồng của server giả thì Variable.__del__
        # gọi Tk từ sai luồng, chờ cả giây cho mỗi biến và làm client hết thời gian chờ (test_cvatapi chạy ngay sau test_close_confirm).
        gc.collect()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer._handle(self, "GET")

            def do_POST(self):
                outer._handle(self, "POST")

            def do_PATCH(self):
                outer._handle(self, "PATCH")

            def do_PUT(self):
                outer._handle(self, "PUT")

            def do_DELETE(self):
                outer._handle(self, "DELETE")

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self.url = "http://127.0.0.1:%d" % self.port
        self._thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._thread.join(5)
            self._httpd = None

    # ---- xử lý ----
    def _handle(self, h, method):
        parts = urlsplit(h.path)
        path = parts.path
        query = {k: v[-1] for k, v in parse_qs(parts.query).items()}
        length = int(h.headers.get("Content-Length") or 0)
        body = h.rfile.read(length) if length else b""
        with self._lock:
            self.requests.append({"method": method, "path": path, "query": query, "headers": dict(h.headers)})
            self.calls["%s %s" % (method, path)] += 1
        login = path == "/api/auth/login" and method == "POST"
        auth = h.headers.get("Authorization")
        if login and self.reject_login_with_auth and auth:
            return self._send(h, 401, {"detail": "Invalid token."})
        if auth is not None:                                  # TokenAuthentication đứng đầu: có header thì chỉ xét khoá
            if auth != "Token " + self.token:
                return self._send(h, 401, {"detail": "Invalid token."})
            authed = True
        else:                                                 # SessionAuthentication: cookie phiên hợp lệ, POST phải kèm CSRF
            cookies = self._cookies(h)
            csrf = self._sessions.get(cookies.get("sessionid", ""))
            authed = csrf is not None
            if authed and method == "POST" and h.headers.get("X-CSRFToken") != csrf:
                return self._send(h, 403, {"detail": "CSRF Failed: CSRF token missing."})
        if login:
            return self._login(h, body)
        if self.fail_401:
            return self._send(h, 401, {"detail": "Invalid token."})
        if self.fail_500:
            return self._send(h, 500, {"detail": "boom"})
        if not authed:
            return self._send(h, 401, {"detail": "Authentication credentials were not provided."})
        try:
            return self._route(h, method, path, query, body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    @staticmethod
    def _cookies(h) -> dict:
        out = {}
        for part in (h.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                out[k] = v
        return out

    def _login(self, h, body):
        d = json.loads(body or b"{}")
        if d.get("password") != self.password:
            return self._send(h, 400, {"non_field_errors": ["Unable to log in with provided credentials."]})
        with self._lock:
            n = len(self._sessions) + 1
            sid, csrf = "s%d" % n, "c%d" % n
            self._sessions[sid] = csrf
        return self._send(h, 200, {"key": self.token},
                          cookies=("sessionid=%s; Path=/; HttpOnly; SameSite=Lax" % sid, "csrftoken=%s; Path=/; SameSite=Lax" % csrf))

    def _route(self, h, method, path, q, body):
        if method in ("PATCH", "PUT", "DELETE"):
            return self._send(h, 405, {"detail": "method not allowed"})
        if path == "/api/users/self":
            return self._send(h, 200, {"id": 1, "username": self.username})
        if path == "/api/tasks":
            tasks = {}
            for j in self.jobs.values():
                t = tasks.setdefault(j.task_id, {"id": j.task_id, "name": j.task_name, "size": 0, "jobs": {"count": 0}})
                t["size"] += j.n_frames
                t["jobs"]["count"] += 1
            return self._page(h, q, path, sorted(tasks.values(), key=lambda t: t["id"]))
        if path == "/api/jobs":
            tid = int(q["task_id"]) if "task_id" in q else None
            rows = [self._job_row(j) for j in self.jobs.values() if j.listed and (tid is None or j.task_id == tid)]
            return self._page(h, q, path, sorted(rows, key=lambda r: r["id"]))
        if path == "/api/issues":
            return self._page(h, q, path, self._issue_rows(q))
        if path == "/api/comments":
            return self._page(h, q, path, self._comment_rows(q))
        if path == "/api/labels":
            j = self.jobs.get(int(q.get("job_id", -1)))
            return self._page(h, q, path, j.labels) if j else self._send(h, 404, {})
        if path.startswith("/api/requests/") and method == "GET":
            return self._poll(h, path.rsplit("/", 1)[1])
        m = re.fullmatch(r"/api/jobs/(\d+)(/.*)?", path)
        if m:
            j = self.jobs.get(int(m.group(1)))
            if j is None:
                return self._send(h, 404, {"detail": "no such job"})
            return self._job_route(h, method, j, m.group(2) or "", q, body)
        return self._send(h, 404, {"detail": "unknown path " + path})

    def _job_route(self, h, method, j, sub, q, body):
        if sub == "" and method == "GET" and self.redirect_job:
            h.send_response(302)
            h.send_header("Location", "http://example.com/")
            h.send_header("Content-Length", "0")
            h.end_headers()
            return
        if sub == "" and method == "GET":
            return self._send(h, 200, self._job_json(j))
        if sub == "/data/meta":
            first = j.data_start_frame + j.start_frame * j.frame_step          # tuyệt đối, như CVAT thật
            if j.media == "video":
                frames = [{"name": "video.mp4", "width": T.W, "height": T.H}] if j.n_frames else []
            else:
                frames = [{"name": "frame_%06d.jpg" % (first + i * j.frame_step), "width": T.W, "height": T.H} for i in range(j.n_frames)]
            meta = {"start_frame": first, "stop_frame": j.data_start_frame + j.stop_frame * j.frame_step, "size": j.n_frames,
                    "frame_filter": "step=%d" % j.frame_step if j.frame_step != 1 else "", "included_frames": j.included_frames,
                    "deleted_frames": j.deleted_frames, "frames": frames}
            meta.update(j.meta_overrides)
            return self._send(h, 200, meta)
        if sub == "/data" and method == "GET":
            self.frame_query.append(q)
            n = int(q.get("number", -1))
            if not j.start_frame <= n <= j.stop_frame:
                return self._send(h, 404, {"detail": "no such frame"})
            ok, buf = cv2.imencode(".jpg", T.render(n))
            return self._send(h, 200, buf.tobytes(), "image/jpeg")
        if sub == "/dataset/export" and method == "POST":
            self.export_formats.append(q.get("format"))
            self.export_query.append(q)
            return self._new_rq(h, {"kind": "export", "job": j, "fmt": q.get("format")})
        if sub == "/annotations" and method == "GET":
            return self._send(h, 200, j.annotations_json)
        if sub == "/annotations" and method == "POST":
            if "filename" in q:  # CVAT thật hiểu filename là mã file TUS
                return self._send(h, 400, ["No such file were uploaded"])
            self.import_formats.append(q.get("format"))
            xml = self._multipart_file(h.headers.get("Content-Type", ""), body)
            return self._new_rq(h, {"kind": "import", "job": j, "xml": xml})
        if sub == "/dataset/download" and method == "GET":
            fmt = (self._rqs.get(q.get("rq_id")) or {}).get("fmt")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("annotations.xml", j.export_xml_by_format.get(fmt, j.xml))
            return self._send(h, 200, buf.getvalue(), "application/zip")
        return self._send(h, 404, {"detail": "unknown job path " + sub})

    @staticmethod
    def _job_json(j):
        return {"id": j.id, "task_id": j.task_id, "start_frame": j.start_frame, "stop_frame": j.stop_frame,
                "state": j.state, "stage": j.stage, "updated_date": j.updated_date}

    def _job_row(self, j):
        """Một dòng của GET /api/jobs: `_job_json` (không đổi) cộng `type`, `assignee`, `issues` như CVAT thật."""
        n = j.issue_count if j.issue_count is not None else sum(1 for i in self.issues if i["job"] == j.id)  # tính cả issue ẩn
        return dict(self._job_json(j), type=j.type, assignee=fake_user(j.assignee),
                    issues={"url": "%s/api/issues?job_id=%d" % (self.url, j.id), "count": n})

    def _issue_rows(self, q):
        rows = [i for i in self.issues if i["id"] not in self.hidden_issues]
        if "task_id" in q:
            rows = [i for i in rows if self.jobs[i["job"]].task_id == int(q["task_id"])]
        if "job_id" in q:
            rows = [i for i in rows if i["job"] == int(q["job_id"])]
        out = []
        for i in sorted(rows, key=lambda r: r["id"], reverse=True):
            i = dict(i)                                         # bản sao: không sửa dict đang lưu trong self.issues
            if i["comments"] is None:
                i["comments"] = {"count": sum(1 for c in self.comments if c["issue"] == i["id"]),
                                 "url": "%s/api/comments?issue_id=%d" % (self.url, i["id"])}
            out.append(i)
        return out

    def _comment_rows(self, q):
        """`task_id` bị bỏ qua như CVAT thật: tham số lạ không lọc gì."""
        job_of = {i["id"]: i["job"] for i in self.issues}
        rows = self.comments
        if "job_id" in q:
            rows = [c for c in rows if job_of.get(c["issue"]) == int(q["job_id"])]
        if "issue_id" in q:
            rows = [c for c in rows if c["issue"] == int(q["issue_id"])]
        return sorted(rows, key=lambda r: r["id"], reverse=True)

    @staticmethod
    def _multipart_file(ctype, body):
        m = re.search(r"boundary=([^;]+)", ctype)
        if not m:
            return body
        for part in body.split(b"--" + m.group(1).strip('"').encode()):
            if b'name="annotation_file"' in part:
                head, _, data = part.partition(b"\r\n\r\n")
                return data[:-2] if data.endswith(b"\r\n") else data
        return b""

    def _new_rq(self, h, info):
        with self._lock:
            rq_id = "rq%d" % (len(self._rqs) + 1)
            info["polls"] = 0
            self._rqs[rq_id] = info
        return self._send(h, 202, {"rq_id": rq_id})

    def _poll(self, h, rq_id):
        if self.drop_on_poll:
            h.close_connection = True
            h.connection.close()
            return
        info = self._rqs.get(rq_id)
        if info is None:
            return self._send(h, 404, {"detail": "no such request"})
        with self._lock:
            info["polls"] += 1
            done = info["polls"] > self.polls_before_finish
        if not done:
            return self._send(h, 200, {"status": "queued", "message": ""})
        j = info["job"]
        if info["kind"] == "export":
            url = "%s/api/jobs/%d/dataset/download?rq_id=%s" % (self.url, j.id, rq_id)
            return self._send(h, 200, {"status": "finished", "message": "", "result_url": url})
        if self.fail_import:
            return self._send(h, 200, {"status": "failed", "message": self.fail_import})
        with self._lock:
            if not info.get("applied"):
                info["applied"] = True
                xml = info["xml"]
                if self.shift_on_import:
                    xml = re.sub(rb'points="([-\d.]+),', lambda m: b'points="%s,' % repr(float(m.group(1)) + self.shift_on_import).encode(),
                                 xml, count=1)
                j.xml = xml
                j.version += 1
                if self.lose_non_eye_on_import:
                    self._lose_one_non_eye(j)
        return self._send(h, 200, {"status": "finished", "message": ""})

    @staticmethod
    def _lose_one_non_eye(j):
        eye_ids = {lb["id"] for lb in j.labels if lb.get("name") in ("mattrai", "matphai")}
        aj = j.annotations_json = json.loads(json.dumps(j.annotations_json))
        for kind in ("shapes", "tracks"):
            for k, o in enumerate(aj.get(kind) or []):
                if o.get("label_id") not in eye_ids:
                    del aj[kind][k]
                    return

    def _page(self, h, q, path, rows):
        page = int(q.get("page", 1))
        if q.get("page_size") == "all":                       # như CVAT thật (pagination.py): toàn bộ danh sách trong một trang
            size = max(len(rows), 1)
        else:
            size = min(int(q.get("page_size", self.page_size)), self.page_size)
        chunk = rows[(page - 1) * size: page * size]
        nxt = None
        if page * size < len(rows):
            qq = dict(q, page=page + 1)
            nxt = self.url + path + "?" + "&".join("%s=%s" % kv for kv in qq.items())
        payload = {"count": len(rows), "next": nxt, "previous": None, "results": chunk}
        if path in self.tamper:
            payload = self.tamper[path](payload)
        return self._send(h, 200, payload)

    @staticmethod
    def _send(h, code, payload, ctype="application/json", cookies=()):
        data = json.dumps(payload).encode() if ctype == "application/json" else payload
        h.send_response(code)
        h.send_header("Content-Type", ctype)
        h.send_header("Content-Length", str(len(data)))
        for c in cookies:
            h.send_header("Set-Cookie", c)
        h.end_headers()
        h.wfile.write(data)
