# Trang chủ CVAT, đăng nhập lại có ghi nhớ, Đăng xuất về màn đăng nhập: kế hoạch thực hiện (bản 2, cập nhật 2026-11-17)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đóng các lỗ an toàn còn mở (job có nhãn mắt mà vào chế độ gán mới; 401 giữa job không đụng tới khoá đã nhớ), cho Đăng xuất quay về màn đăng nhập thay vì đóng EyePin, rồi xây trang chủ kiểu CVAT (thẻ task có ảnh, danh sách job có trạng thái CVAT + nhãn prelabeled) và đường "← Trang chủ" từ job.

**Architecture:** Quy tắc "có nhãn mắt" dùng chung nằm ở `qc.py` (`open_job` và trang chủ cùng gọi). Khung nhập đăng nhập tách khỏi `LoginScreen` thành `LoginForm` dùng chung cho màn đăng nhập, hộp đăng nhập lại giữa job và trang chủ. Trang chủ là mixin mới `eyepin/gui_home.py` của `App`, thay vùng thân cửa sổ, có bộ chạy nền riêng `HomeRunner` (không đặt `App.busy`, có số thứ tự yêu cầu). Đăng xuất gỡ `App` khỏi cửa sổ gốc (`App.teardown`) rồi dựng lại `FrontDoor` trong cùng cửa sổ.

**Tech Stack:** Python 3.12, Tkinter/ttk, requests (trong `cvatapi.py`), Pillow (`ImageTk`), `ctypes` (DPAPI, đã có), unittest.

**Spec:** `design/2026-11-16-cvat-home-design.md` (mục 4.1–4.7, 4.5b, 4.6b, 9, 9b; dòng 170: người dùng chốt Đăng xuất về màn đăng nhập). Báo cáo đối chiếu mã: `.superpowers/sdd/bugfix/PLAN2-check.md`.

## Đã có — đừng làm lại

Ba task của bản kế hoạch 16/11 đã xây xong (2026-11-17), khớp spec mục 9 và 9b (không khớp văn bản task gốc; spec thắng):

- **Khoá đăng nhập mã hoá có hạn:** `eyepin/cvatlogin.py`: `login_path`, `remember_hours(settings)` (đọc `settings["workspace"]["remember_login_hours"]`, kẹp 0–72, hỏng thì 8; **không** phải `settings["cvat"]["remember_hours"]`), `protect`/`unprotect` (DPAPI + entropy `_ENTROPY`), `save_login(url, user, token, hours, now=None) -> bool`, `load_login(url, now=None) -> (user, token) | None`, `forget_login() -> str | None`. Test: `tests/test_cvatlogin.py` (30).
- **Cờ chưa gửi:** `Session.unsent` (`session.py` 107; bật ở 716/728/738 trong `_push_undo`/`undo`/`redo`; ghi vào `state()` 752 chỉ với job CVAT; `load_state` 796: thiếu cờ mà có ghim → True). Tắt **chỉ** trong `cvatsync.send` (346) khi gửi xong và đối chiếu khớp; `mark_synced` không tắt. Không có thư mục `sessions/cvat/`: file phiên CVAT nhận ra bằng khoá `cvat` trong nội dung (`cvatlogin._cvat_sessions`, `cvat_session_files()`, `unsent_sessions() -> list[UnsentSession(path, job, pins, known)]`).
- **Đăng xuất dọn máy:** `gui_login.LoginMixin.logout` (321) → `_logout_after_send` → `_logout_continue` → `_logout_wipe` (364); `cvatlogin.wipe_local(settings) -> list[str]` (225); hộp `ask_logout`, `ask_logout_open_job -> "send"|"discard"|"cancel"`, `ask_logout_others -> bool`; nút `logout` trên thanh cam (`gui.py` 267), mục menu (`gui_cvat.py` 92), Cài đặt giờ nhớ (F2 > Workspace). Test: `tests/test_logout.py` (38), `tests/test_gui_login.py` lớp `TestLogout`.
- **Màn đăng nhập là cửa trước:** `gui_login.LoginScreen` (29), `FrontDoor` (242); `gui.run` (2555) dựng `FrontDoor` khi không có thư mục ảnh và không `--selftest`. Test: `tests/test_gui_login.py` (40).
- **API đã có:** `CvatClient.token` (125), `use_token` (131), `whoami` (137); `FakeCvat` trả `GET /api/users/self`.
- **Hạ tầng dùng lại:** `App._cancel_all_after` (gui.py 1206, B13: huỷ MỌI hẹn giờ `after` của trình thông dịch), `App._on_root_destroy` (1202), `CvatMixin._run_bg` (gui_cvat.py 189), `_save_outgoing` (493), `_after_send`/`_send_finished` (566), `_login_again` (458).

## Global Constraints

- Git: làm trên nhánh `feature/cvat-home` tách từ `develop` (`git switch develop && git switch -c feature/cvat-home`); commit theo Conventional Commits của `CLAUDE.md` (`<type>(<phạm vi>): <mô tả tiếng Việt có dấu>`, ≤ 72 ký tự, mỗi commit một mục đích); không `--no-verify`; PR vào `develop`, không đụng `main`. Không còn bước sao lưu thư mục.
- Test chạy **từng file** (máy thiếu bộ nhớ ảo): `PYTHONIOENCODING=utf-8 python -m unittest discover -s tests -p test_xxx.py` (PowerShell: `$env:PYTHONIOENCODING='utf-8'; python -m unittest discover -s tests -p test_xxx.py`).
- Chỉ CVAT localhost (`cvatapi._check_local`, `trust_env=False`, `allow_redirects=False`, không nhận cookie) — giữ nguyên.
- Ảnh (preview, frame) chỉ trong RAM: không ghi đĩa, không cache ra file.
- Mật khẩu không bao giờ lưu, và bị xoá khỏi ô nhập sau mỗi lần thử. Khoá chỉ ở `cvat_login.bin` (DPAPI) và trong RAM.
- **Không bao giờ gọi `POST /api/auth/logout`.**
- Gặp 401 (dù ở màn đăng nhập, trang chủ hay giữa job) → `cvatlogin.forget_login()`. Lỗi mạng / 5xx → **giữ** khoá.
- Mọi lệnh mạng chạy nền; cửa sổ không đứng. Luồng nền không đụng Tk.
- Mọi chuỗi giao diện bằng tiếng Việt. Không dùng model học máy.
- Thử trên CVAT local: chỉ GET, trừ khi người dùng cho phép khác. Không điều khiển trình duyệt vào server công ty.

## Review Focus

1. **CVAT tắt hoặc 502 khi đang ở trang chủ:** trang chủ hiện dòng lỗi + nút Làm mới, không treo, không văng về màn đăng nhập, không xoá khoá đã nhớ. → `test_server_down_shows_retry_and_keeps_token` (Task 5).
2. **Bấm job khác khi job trước còn đang tải:** chỉ job bấm sau cùng được mở; kết quả cũ bị bỏ, không thành hai phiên chồng nhau. → `test_last_clicked_job_wins` (Task 5).
3. **Đăng xuất khi một hẹn giờ (tự lưu, vẽ, tooltip, poll `_run_bg`) còn chờ:** không có "invalid command name" sau khi dựng lại màn đăng nhập; đăng nhập lại lần hai chạy bình thường. → `test_logout_leaves_no_orphan_timer_and_second_login_works` (Task 2).
4. **401 giữa job rồi đăng nhập lại:** khoá cũ trong `cvat_login.bin` bị xoá ngay, khoá mới được lưu nếu ô ghi nhớ bật; mở lại tool không hỏi mật khẩu. → `test_401_mid_job_forgets_then_relogin_saves_new_key` (Task 4).
5. **JSON của job có track mắt toàn Outside mà XML không còn mắt:** job vào QC, trang chủ hiện "prelabeled". → `test_open_job_qc_when_only_json_has_eyes` (Task 1), `test_job_badges_prelabeled_and_empty` (Task 6).

Đã có test (không phải thêm): khoá bị huỷ (`test_a_revoked_key_is_forgotten_and_the_form_stays`), file khoá hỏng (`test_cvatlogin.py`), xoá file bị khoá (`test_a_key_file_that_cannot_be_deleted_is_named_and_logout_stops`, `test_logout.py`).

---

### Task 1: Một quy tắc "có nhãn mắt" (`qc.json_has_eyes`) cho lúc mở job — sửa an toàn, làm trước

**Files:**
- Modify: `eyepin/qc.py` (thêm hàm), `eyepin/cvatsource.py` (`_is_eye` 88, `_has_eyes` 107, `open_job` 111–132, dòng 131)
- Test: `tests/test_qc.py`, `tests/test_cvatsource.py`

**Interfaces:**
- Consumes: không.
- Produces: `qc.is_eye_obj(obj: dict, eye_ids: set[int] | None) -> bool` (chuyển nguyên logic `cvatsource._is_eye` sang `qc.py`; `EYE_POINTS = 8` đi theo; `cvatsource._is_eye` gọi nó hoặc bị thay hẳn — `qc.py` không được import `cvatsource`, tránh vòng import).
- Produces: `qc.json_has_eyes(annotations_json: dict, eye_ids: set[int] | None = None) -> bool` — True nếu **bất kỳ** phần tử nào trong `shapes` hoặc `tracks` là mắt theo `is_eye_obj` (kể cả track rỗng, toàn Outside, ngoài khoảng frame). `{}`/thiếu khoá → False. `cvatsource._has_eyes` bị thay bằng hàm này.
- Hành vi mới: `open_job` đặt `session.qc = qc.has_eye_labels(ann) or qc.json_has_eyes(aj, eye_ids)`.

- [ ] **Step 1: Tạo nhánh** `feature/cvat-home` từ `develop` (Global Constraints).
- [ ] **Step 2: Viết test hỏng**

```python
# tests/test_qc.py
def test_json_has_eyes_shape_track_empty_outside(self):
    ids = {14, 22}
    self.assertTrue(qc.json_has_eyes({"shapes": [{"label_id": 14, "elements": []}]}, ids))
    self.assertTrue(qc.json_has_eyes({"tracks": [{"label_id": 22, "shapes": [], "elements": []}]}, ids))          # track rỗng
    self.assertTrue(qc.json_has_eyes({"tracks": [{"label_id": 14, "shapes": [{"outside": True}]}]}, ids))      # toàn Outside
    self.assertFalse(qc.json_has_eyes({"shapes": [{"label_id": 1}], "tracks": [{"label_id": 2}]}, ids))
    self.assertFalse(qc.json_has_eyes({}, ids))

def test_json_has_eyes_without_ids_uses_eight_point_skeleton(self):
    sk = {"label_id": 99, "elements": [{}] * 8}
    self.assertTrue(qc.json_has_eyes({"tracks": [sk]}))
    self.assertFalse(qc.json_has_eyes({"tracks": [dict(sk, elements=[{}] * 5)]}))
```

```python
# tests/test_cvatsource.py, cạnh test_eye_tracks_show_with_keyframes_and_turn_qc_on (253)
def test_open_job_qc_when_only_json_has_eyes(self):
    job = self.serve()                              # XML rỗng: parse không thấy mắt
    job.annotations_json = ann_json(tracks=[{"label_id": 14, "frame": 0, "shapes": [{"frame": 0, "outside": True}], "elements": []}])
    s = open_job(self.cl, 7)
    self.assertTrue(s.qc)
```

- [ ] **Step 3: Chạy → FAIL** `PYTHONIOENCODING=utf-8 python -m unittest discover -s tests -p test_qc.py` (AttributeError `json_has_eyes`), rồi `-p test_cvatsource.py` (`s.qc` False).
- [ ] **Step 4: Cài `is_eye_obj`, `json_has_eyes` trong `qc.py`; sửa `cvatsource` như Interfaces.**
- [ ] **Step 5: Chạy → PASS** `test_qc.py`, `test_cvatsource.py`, rồi chạy lại `test_gui_cvat.py` (`test_open_job_with_eyes_goes_to_qc_and_scans`).
- [ ] **Step 6: Commit** `fix(cvat): vào chế độ QC khi JSON của job có nhãn mắt dù XML không có`

### Task 2: Đăng xuất về màn đăng nhập thay vì đóng EyePin (người dùng chốt 2026-11-17)

**Files:**
- Modify: `eyepin/gui.py` (`App.__init__` 179–187 giữ id các bind; thêm `teardown`, `back_to_login`; tooltip `logout_btn` 267; `run` 2555–2591), `eyepin/gui_login.py` (`FrontDoor` 242–269 gắn `to_login` vào `App`; `_logout_wipe` 377 gọi `back_to_login` thay `shutdown`; `logout_text` 281 bỏ "Xong thì EyePin đóng"; docstring đầu file và `LoginMixin.logout` 322)
- Test: `tests/test_gui_login.py` (lớp mới `TestLogoutToLogin`; sửa `TestLogout`), `tests/test_logout.py` (patch `back_to_login` thay `shutdown`: 18 chỗ `self.shut`, 143)

**Interfaces:**
- Consumes: `App._cancel_all_after()` (B13), `App._bound` (`_bind_keys` 484), `FrontDoor(root, *, url, job, new_client, app_factory, settings)`.
- Produces: `App.teardown() -> None` — gỡ `App` khỏi `root` mà **không** huỷ `root`: dừng phát, `_cancel_all_after()`, `root.unbind` mọi seq trong `self._bound`, gỡ `bind_all("<ButtonPress>")` (`root.unbind_all("<ButtonPress>")`) và bind `<Destroy>` của root (giữ funcid lúc bind ở `__init__`), tắt `-fullscreen`, huỷ mọi `self._dialogs`, huỷ mọi con của `root` (`for w in root.winfo_children(): w.destroy()`), `root.protocol("WM_DELETE_WINDOW", root.destroy)`, `cvat_client.close()` rồi `cvat_client = None`, `self.s = None`. Gọi hai lần không lỗi.
- Produces: `App.to_login: Callable[[tk.Tk], object]` — mặc định `lambda root: FrontDoor(root)` (nạp muộn); `FrontDoor._build_app` gán `app.to_login = lambda root: FrontDoor(root, new_client=..., app_factory=..., settings=...)` (cùng tham số, **không** truyền `job`).
- Produces: `App.back_to_login() -> None` — lưu cài đặt như `shutdown` (`settings["display"]`), `teardown()`, rồi `self.to_login(self.root)`. `_logout_wipe` gọi nó khi `wipe_local` trả rỗng; xoá lỗi thì giữ nguyên hành vi hiện tại (báo tên file, không rời cửa sổ).
- Không đổi: `on_close` → `shutdown` (đóng cửa sổ là thoát tiến trình). Không gọi `POST /api/auth/logout`.

- [ ] **Step 1: Viết test hỏng** trong `tests/test_gui_login.py`, lớp `TestLogoutToLogin(G.CvatGuiCase)` dùng `FrontDoor` thật (như `TestFrontDoor.door`, 308):

```python
def test_logout_returns_to_the_login_screen_in_the_same_window(self):
    d = self.door(); self.log_in(d); self.wait(d.app)
    app = d.app
    app.ask_logout = lambda: True
    app.logout()
    self.root.update()
    self.assertTrue(self.root.winfo_exists())
    self.assertEqual(self.root.title(), "EyePin — đăng nhập")
    self.assertIsNone(app.cvat_client)
    self.assertFalse(cvatlogin.login_path().exists())
    self.assertEqual(sc.load_settings()["cvat"]["user"], "")
    self.assertNotIn("/api/auth/logout", " ".join(self.srv.calls))

def test_logout_leaves_no_orphan_timer_and_second_login_works(self):
    d = self.door(); self.log_in(d); self.wait(d.app)
    made = []
    d.app.to_login = lambda r, f=d.app.to_login: made.append(f(r)) or made[-1]   # giữ FrontDoor mới
    d.app.ask_logout = lambda: True
    d.app.logout()
    self.assertEqual(self.root.tk.splitlist(self.root.tk.call("after", "info")), ())
    errors = []
    self.root.report_callback_exception = lambda *a: errors.append(a)
    for _ in range(20): self.root.update(); time.sleep(0.01)
    self.assertEqual(errors, [])
    self.assertEqual(self.root.bind(), ())                       # không còn phím của App cũ trên root
    self.log_in(made[0])
    self.assertIsNot(made[0].app, d.app)
    self.assertEqual(made[0].app.cvat_client.token, "k1")
    self.wait(made[0].app)

def test_logout_with_failed_wipe_stays_in_the_job(self):
    # mock.patch.object(cvatlogin, "wipe_local", return_value=["x.json"]) → App còn nguyên (d.app.root có con), lỗi hiện có "x.json",
    # root.title() khác "EyePin — đăng nhập", tự lưu được hẹn lại (_autosave_job không None)

def test_closing_the_window_after_logout_exits(self):
    # sau logout: root.protocol("WM_DELETE_WINDOW") không còn là lệnh của App cũ; gọi nó thì root bị huỷ (winfo_exists ném TclError)
    # dùng một Tk riêng cho test này, không phải root dùng chung
```

- [ ] **Step 2: Sửa test cũ:** `tests/test_logout.py` (143) và `TestLogout` trong `test_gui_login.py` (385) patch `app.back_to_login` thay `app.shutdown`; các assert `self.shut == [1]` giữ nghĩa "đã rời job sau khi dọn". Thêm vào `TestLogout`: `test_logout_does_not_shut_the_window` (`app.shutdown` bị patch để ghi lại; sau logout sạch, `shutdown` không được gọi, `back_to_login` được gọi một lần).
- [ ] **Step 3: Chạy → FAIL** `-p test_gui_login.py`, `-p test_logout.py`.
- [ ] **Step 4: Cài `teardown`, `to_login`, `back_to_login`** như Interfaces; sửa `_logout_wipe`, `logout_text`, tooltip nút (bỏ "rồi đóng EyePin", thay "rồi về màn đăng nhập"); `run` khi mở bằng thư mục ảnh vẫn dùng `to_login` mặc định (Đăng xuất từ phiên thư mục ảnh cũng về màn đăng nhập).
- [ ] **Step 5: Chạy → PASS** `test_gui_login.py`, `test_logout.py`, `test_bugfix_b13.py`, `test_close_confirm.py`, `test_gui.py`.
- [ ] **Step 6: Commit** `feat(gui): đăng xuất quay về màn đăng nhập, chỉ đóng cửa sổ mới thoát`

### Task 3: API CVAT còn thiếu cho trang chủ (chỉ đọc) và kiểm trên CVAT 2.75 local

**Files:**
- Modify: `eyepin/cvatapi.py` (`tasks` 145, `jobs` 148; thêm `projects`, `task_labels`, `preview`; docstring dòng 3 "Khoá đăng nhập chỉ giữ trong đối tượng này" → "khoá nằm trong đối tượng này; `eyepin.cvatlogin` có thể nhớ nó mã hoá"), `tests/fake_cvat.py` (`FakeJob` thêm `project_id`, `assignee`, `type`, `preview`; `_route` 203: `/api/projects`, `/api/tasks/{id}/preview`, `/api/jobs/{id}/preview`, `/api/labels?task_id=`; trả thêm trường ở `/api/tasks`, `/api/jobs`), `design/cvat-api-notes.md` (mục mới)
- Test: `tests/test_cvatapi.py`

**Interfaces:**
- Produces: `CvatClient.tasks() -> list[dict]` có thêm `project_id: int | None`, `updated_date: str`, `jobs: int | None` (từ `jobs.count`; không có → `None`), `mode: str` (`"annotation"` | `"interpolation"`). Giữ `id, name, size`.
- Produces: `CvatClient.projects() -> dict[int, str]` (`GET /api/projects`, phân trang `_paged`).
- Produces: `CvatClient.jobs(task_id)` thêm `assignee: str | None` (`assignee.username`), `updated_date: str`, `type: str` (`"annotation"` | `"ground_truth"` …).
- Produces: `CvatClient.task_labels(task_id: int) -> list[dict]` (`GET /api/labels?task_id=`), để trang chủ lấy `eye_ids` một lần mỗi task.
- Produces: `CvatClient.preview(kind: Literal["task", "job"], obj_id: int) -> bytes | None` (`GET /api/{kind}s/{id}/preview`; 404 → `None`; 401 → `LoginNeeded`; lỗi khác → `CvatError`). `kind` khác hai giá trị → `ValueError`.

- [ ] **Step 1: Kiểm trên CVAT local (chỉ GET).** Dùng khoá trong `~\.cvat_token` (tiền tố `Token`) bằng `curl --noproxy '*' -H "Authorization: Token <khoá>"`, không in khoá ra log. Kiểm: `/api/tasks?page_size=1` có `jobs.count`, `project_id`, `updated_date`, `mode`; `/api/jobs?task_id=4` có `assignee`, `updated_date`, `type`; `/api/projects`; `/api/labels?task_id=4`; `/api/tasks/4/preview` và `/api/jobs/4/preview` (mã, `Content-Type`, cỡ); `/api/users/self` có `username` (TASKS 160). Ghi vào `design/cvat-api-notes.md` mục "Trang chủ (2.75, thử 2026-11-…)". Không có khoá dùng được → ghi "chưa thử", làm theo mã nguồn CVAT, và báo lại người điều phối.
- [ ] **Step 2: Viết test hỏng** trong `tests/test_cvatapi.py`:

```python
def test_tasks_have_project_updated_jobs_mode(self):      # FakeJob(project_id=2), 2 job cùng task
    t = self.cl.tasks()[0]
    self.assertEqual((t["project_id"], t["jobs"], t["mode"]), (2, 2, "annotation"))
    self.assertTrue(t["updated_date"])
def test_projects_map(self):            self.assertEqual(self.cl.projects(), {2: "eyes_label"})
def test_jobs_have_assignee_updated_type(self):
    j = self.cl.jobs(1)[0]
    self.assertEqual((j["assignee"], j["type"]), ("minh", "annotation")); self.assertTrue(j["updated_date"])
def test_job_without_assignee_is_none(self):  ...  # assignee None trong JSON → None
def test_task_labels(self):             self.assertEqual({l["name"] for l in self.cl.task_labels(1)}, {"mattrai", "matphai"})
def test_preview_bytes_and_missing_is_none(self):
    self.assertTrue(self.cl.preview("job", 7).startswith(b"\x89PNG"))
    self.assertIsNone(self.cl.preview("task", 999))
    with self.assertRaises(ValueError): self.cl.preview("project", 1)
def test_preview_401_raises_login_needed(self): ...
def test_preview_still_localhost_only(self):
    with self.assertRaises(CvatError): CvatClient("http://example.com").preview("job", 1)
```

- [ ] **Step 3: Chạy → FAIL** `-p test_cvatapi.py`.
- [ ] **Step 4: Cài** các hàm như Interfaces và mở rộng `FakeCvat` (preview là PNG nhỏ dựng bằng `cv2.imencode` trong RAM; `FakeJob.preview = None` → 404).
- [ ] **Step 5: Chạy → PASS** `test_cvatapi.py`, rồi `test_cvatsource.py`, `test_gui_cvat.py` (FakeCvat đổi).
- [ ] **Step 6: Commit** hai commit: `feat(cvat): thêm project, preview, nhãn task và trường job cho trang chủ`; `docs(cvat): ghi kết quả kiểm endpoint trang chủ trên CVAT 2.75`.

### Task 4: Khung đăng nhập dùng chung; 401 giữa job xoá khoá đã nhớ, đăng nhập lại có ghi nhớ

**Files:**
- Modify: `eyepin/gui_login.py` (tách `LoginForm` từ `LoginScreen._build` 51–92, `_try_remembered` 141–177, `submit` 180–217, `_bg` 117–138), `eyepin/gui_cvat.py` (`_login_again` 458 → `_relogin_dialog`; `_frame_read_failed` 245, `_edit_net_failed` 253, `load_cvat` 469, `_after_prepare` 577, `_do_send` 593 đều đi qua `_login_again`)
- Test: `tests/test_gui_login.py`, `tests/test_gui_cvat.py` (sửa `test_frame_read_needing_login_opens_the_login_box` 465, `test_login_needed_while_pinning_opens_the_login_box_and_recomputes_after` 534, `test_login_needed_reopens_login_and_keeps_the_pins` 796: đang điền `app._cvat_ui[...]` + `cvat_login()`, đổi sang điền `app._relogin.form`)

**Interfaces:**
- Produces: `gui_login.LoginForm(parent: tk.Widget, *, root: tk.Tk, on_login: Callable[[CvatClient, str], None], url: str | None, settings: dict, new_client=CvatClient, fixed_url: bool = False, try_remembered: bool = True)` — ô địa chỉ (chỉ đọc khi `fixed_url`), tên, mật khẩu, ô "Ghi nhớ đăng nhập trên máy này (N giờ)", nút Đăng nhập, dòng trạng thái; thuộc tính `url_var, user_var, password_var, remember_var, status_var, busy`; phương thức `submit()`, `destroy()`, `alive() -> bool`. Mọi quy tắc hiện có của `LoginScreen` đi theo (xoá mật khẩu sau mỗi lần thử, ghi nhớ → `save_login`, bỏ ghi nhớ → `forget_login`, 401/khoá hỏng khi thử khoá đã nhớ → `forget_login`, lỗi mạng giữ khoá, kết quả muộn bị bỏ khi khung đã đóng, `notice` khi không lưu được khoá).
- `LoginScreen` giữ nguyên giao diện công khai (test `test_gui_login.py` hiện có phải qua không sửa, trừ chỗ truy cập widget con nếu đổi tên), nay chứa một `LoginForm` + liên kết "Làm việc không cần CVAT".
- Produces: `CvatMixin._relogin_dialog(retry: Callable[[], None]) -> None` — Toplevel nhỏ `transient` trên job, chứa `LoginForm(fixed_url=True, url=self.cvat_client.url, try_remembered=False)`; lưu ở `self._relogin` (một hộp mỗi lúc; gọi lại khi đang mở thì chỉ đổi `retry`). Đăng nhập được → khoá mới vào **chính** `self.cvat_client` (`use_token(client.token)`, để `CvatSource` đang giữ client này dùng được), đóng hộp, gọi `retry()`. Đóng hộp không đăng nhập → bỏ `_cvat_after_login` và `_after_send` như `_cvat_dialog_closed` (338).
- Hành vi mới của `_login_again(retry)`: `cvatlogin.forget_login()` **trước**, rồi `_relogin_dialog(retry)`. Không đổi sang trang chủ; phiên và ghim không bị đụng.

- [ ] **Step 1: Viết test hỏng**

```python
# tests/test_gui_cvat.py
@win_only
def test_401_mid_job_forgets_then_relogin_saves_new_key(self):
    cvatlogin.save_login(self.srv.url, "minh", "old", 8)
    app = self.open_job_app()                     # job 7 đang mở
    self.srv.fail_401 = True
    app.send_cvat(); self.wait(app)
    self.assertFalse(cvatlogin.login_path().exists())          # khoá cũ đi ngay khi gặp 401
    self.assertIsNotNone(app.s)                                 # vẫn ở job
    self.srv.fail_401 = False
    f = app._relogin.form
    self.assertEqual(f.url_var.get(), self.srv.url)
    self.assertTrue(f.remember_var.get())
    f.user_var.set("minh"); f.password_var.set("pw"); f.submit(); self.wait(app)
    self.assertEqual(f.password_var.get(), "")
    self.assertEqual(cvatlogin.load_login(self.srv.url), ("minh", "k1"))
    self.assertEqual(app.cvat_client.token, "k1")

def test_relogin_without_remember_saves_nothing(self): ...
def test_closing_the_relogin_box_drops_the_pending_retry_and_send_hook(self): ...
```

Trong `test_gui_login.py`: `test_login_form_is_shared_by_screen_and_relogin_box` (cả hai có `remember_var`, cùng chữ trên ô ghi nhớ).

- [ ] **Step 2: Chạy → FAIL** `-p test_gui_cvat.py`, `-p test_gui_login.py`.
- [ ] **Step 3: Cài `LoginForm`, `_relogin_dialog`, sửa `_login_again`**; sửa ba test cũ của `test_gui_cvat.py` (465, 534, 796) sang hộp mới. Hộp "Mở từ CVAT…" cũ (`open_cvat`) **giữ nguyên** trong task này (Task 5 thay).
- [ ] **Step 4: Chạy → PASS** `test_gui_login.py`, `test_gui_cvat.py`, `test_logout.py` (gửi rồi đăng xuất qua 401), `test_cvatlogin.py`.
- [ ] **Step 5: Commit** `refactor(gui): tách khung đăng nhập dùng chung LoginForm` và `fix(gui): gặp 401 giữa job thì quên khoá cũ, đăng nhập lại có ghi nhớ`.

### Task 5: Trang chủ: khung, bộ chạy nền riêng, lưới task, danh sách job, mở job

**Files:**
- Create: `eyepin/gui_home.py` (`HomeRunner`, `HomeMixin`)
- Modify: `eyepin/gui.py` (`App` thêm `HomeMixin` vào danh sách mixin dòng 117; `_build` 190: vùng thân `body` 271 đổi được giữa trang chủ và job; nút điều hướng frame ẩn khi ở trang chủ), `eyepin/gui_cvat.py` (`open_cvat` 287 → `show_home`; **xoá** `_build_cvat_dialog`, `cvat_login`, `_fill_cvat_tasks`, `_cvat_list_tasks`, `cvat_pick_task`, `cvat_open_selected`, `_cvat_dialog_*`; tách phần `done` của `load_cvat` 468–474 thành `_cvat_opened(client, job_id, session, err)`), `eyepin/gui_login.py` (`FrontDoor._login` 266: `app.show_home()` thay `app.open_cvat(url=...)`), `eyepin/gui.py` `run` 2574 (`--cvat --selftest` → `show_home(url=cvat)`)
- Test: Create `tests/test_gui_home.py`; Modify `tests/test_gui_cvat.py` (`TestDialog` 615–705: 5 test dựa vào hộp cũ — chuyển ý sang `test_gui_home.py` rồi xoá; tổng 23 chỗ `_cvat_ui`/`cvat_login`/`open_cvat`/`cvat_pick_task`/`cvat_open_selected`, phần 401 đã đổi ở Task 4), `tests/test_gui_login.py` (`test_login_opens_the_main_window_with_the_task_list` 337 và `test_remembered_key_goes_straight_to_the_main_window` 364: assert `app.home_visible()` và lưới có task "clip" thay cho `_cvat_ui["tasks_lb"]`)

**Interfaces:**
- Consumes: Task 3 (`tasks`, `projects`, `jobs`), Task 4 (`LoginForm`), `CvatMixin._install_cvat`, `_save_outgoing`.
- Produces: `gui_home.HomeRunner(root: tk.Tk, alive: Callable[[], bool])` với `submit(key: str, fn: Callable[[], T], done: Callable[[T | None, BaseException | None], None]) -> int` — chạy `fn` trên luồng daemon, lấy kết quả bằng `root.after(40, poll)`; mỗi `key` có số thứ tự, `done` chỉ được gọi cho yêu cầu **mới nhất** của key đó và khi `alive()`; **không** đặt `App.busy`, không khoá sửa nhãn; `cancel_all()` làm mọi kết quả đang chờ bị bỏ. Hẹn giờ của nó bị `_cancel_all_after` dọn khi teardown.
- Produces: `App.show_home(url: str | None = None) -> None` (đã có `cvat_client` → lưới task; không có → `LoginForm` nhúng trong trang chủ với `try_remembered=True`, nên đường "Làm việc không cần CVAT → Mở từ CVAT…" thử khoá đã nhớ trước khi hỏi mật khẩu), `App.home_visible() -> bool`, `App.show_job_view() -> None`.
- Produces: `App.home_open_task(task_id: int)`, `App.home_back_to_tasks()`, `App.home_refresh()`, `App.home_open_job(job_id: int)` — mở job qua `HomeRunner.submit("open", lambda: open_job(client, job_id), …)` rồi `_cvat_opened`; bấm job khác khi job trước còn tải thì job trước bị bỏ (số thứ tự).
- Produces: dữ liệu trang chủ trong `self._home: dict` (`tasks`, `projects`, `jobs`, `task_id`, `query`, `project`) và hàm thuần `gui_home.filter_tasks(tasks: list[dict], projects: dict[int, str], project: int | None, query: str) -> list[dict]` (tìm theo tên không phân biệt hoa thường, hoặc theo số `#id`).
- Lỗi ở trang chủ: `LoginNeeded` → `forget_login()`, hiện `LoginForm`; `CvatError` khác → dòng lỗi + nút "Làm mới", giữ khoá.
- Giao diện: thanh cam giữ menu, Làm mới, Đăng xuất; ẩn các nút frame. Lưới thẻ task (`#id tên`, project, số frame, số job; ảnh để Task 6), ô lọc project ("Tất cả" + tên) và ô tìm. Danh sách job: `Job #id`, `frame a–b`, `state / stage`, người được giao, ngày sửa `dd/mm HH:MM` giờ máy, nút "Mở"; bấm đúp = Mở. Job `type == "ground_truth"` hoặc task `mode == "interpolation"` → dòng mờ kèm lý do ("job thưa", "task video"), nút Mở tắt. Màu theo `theme.py`. Số cột tự theo bề rộng; trăm task không đứng cửa sổ (dựng thẻ trong một `Canvas` cuộn).

- [ ] **Step 1: Viết test hỏng** `tests/test_gui_home.py` (dùng `CvatGuiCase` của `test_gui_cvat.py`, FakeCvat):

```python
def test_runner_drops_all_but_the_latest_result_per_key(self):   # HomeRunner thuần, không App
def test_runner_does_not_set_busy(self):                          # app.busy vẫn None trong lúc tải
def test_login_shows_the_task_grid(self):                         # FrontDoor → show_home → thấy task "clip"
def test_task_grid_filters_by_project_and_search(self):
    self.assertEqual([t["id"] for t in filter_tasks(T, P, 2, "")], [1])
    self.assertEqual([t["id"] for t in filter_tasks(T, P, None, "#3")], [3])
def test_open_task_lists_jobs_with_state_and_assignee(self):
def test_ground_truth_job_is_greyed_with_a_reason(self):
def test_open_job_from_home(self):                                # home_open_job(7) → app.s.cvat["job"] == 7, không còn trang chủ
def test_last_clicked_job_wins(self):                             # home_open_job(7); home_open_job(8) trước khi 7 xong → app.s.cvat["job"] == 8, chỉ một _install_cvat
def test_server_down_shows_retry_and_keeps_token(self):           # srv.fail_500 → dòng lỗi + nút Làm mới; login_path() còn; không về màn đăng nhập
def test_401_on_home_forgets_key_and_shows_the_form(self):
def test_open_cvat_from_a_folder_session_tries_the_remembered_key(self):   # đi "không cần CVAT", mở thư mục, menu Mở từ CVAT… → có khoá nhớ → lưới task không hỏi mật khẩu
```

- [ ] **Step 2: Chạy → FAIL** `-p test_gui_home.py`.
- [ ] **Step 3: Cài `gui_home.py`, nối vào `App`, `FrontDoor`, `run`**; xoá hộp cũ; sửa/xoá test cũ như ở mục Files (ghi trong commit test nào bị chuyển sang `test_gui_home.py`).
- [ ] **Step 4: Chạy → PASS** từng file: `test_gui_home.py`, `test_gui_cvat.py`, `test_gui_login.py`, `test_logout.py`, `test_gui.py`, `test_bugfix_b13.py`.
- [ ] **Step 5: Commit** `feat(gui): thêm trang chủ CVAT thay hộp Mở từ CVAT` (mã) và `test(gui): chuyển test hộp Mở từ CVAT sang trang chủ`.

### Task 6: Nhãn prelabeled và ảnh xem trước trên trang chủ

**Files:**
- Modify: `eyepin/gui_home.py`, `eyepin/gui_cvat.py` (`_do_send` 598–600: gửi khớp → báo trang chủ)
- Test: `tests/test_gui_home.py`

**Interfaces:**
- Consumes: Task 1 `qc.json_has_eyes(aj, eye_ids)`, Task 3 `task_labels`, `preview`, `HomeRunner`.
- Produces: `App.job_badge(job_id: int) -> str` ∈ `{"prelabeled", "chưa có nhãn mắt", "đang kiểm…", "chưa rõ"}`. Khi mở một task: `task_labels(task_id)` **một lần** → `eye_ids = {id của mattrai, matphai}`; rồi mỗi job `annotations(job_id)` qua `HomeRunner.submit(f"badge:{job_id}", …)` → `json_has_eyes(aj, eye_ids)`. Lỗi → "chưa rõ" (không đoán). Không có nhãn mắt trong task → mọi job "chưa rõ".
- Produces: `self._badge_cache: dict[tuple[int, str], bool]` theo `(job_id, updated_date)`; `updated_date` đổi thì kiểm lại. `App.home_mark_sent(job_id: int, updated: str) -> None` (gọi sau gửi khớp với `s.cvat["updated"]`) đặt `(job_id, updated) → True`.
- Produces: ảnh xem trước: `preview("task"|"job", id)` qua `HomeRunner` → `PIL.Image.open(io.BytesIO(b))` → `thumbnail((160, 120))` → `ImageTk.PhotoImage` giữ trong `self._home_imgs` (xoá khi rời trang/làm mới); `None`/lỗi → khung xám. Không ghi file.

- [ ] **Step 1: Viết test hỏng**

```python
def test_job_badges_prelabeled_and_empty(self):     # job 7 track mắt toàn Outside → "prelabeled"; job 8 trống → "chưa có nhãn mắt"; job 9 annotations 500 → "chưa rõ"
def test_badge_shows_checking_while_loading(self):  # trước khi runner trả: "đang kiểm…"
def test_badge_cache_follows_updated_date(self):    # mở lại task: không gọi lại annotations; tăng FakeJob.version → gọi lại
def test_labels_fetched_once_per_task(self):        # srv.calls["GET /api/labels"] == 1 cho task 3 job
def test_sent_job_becomes_prelabeled(self):
def test_previews_never_written_to_disk(self):
    with mock.patch("PIL.Image.Image.save", side_effect=AssertionError("ghi ảnh")), \
         mock.patch("cv2.imwrite", side_effect=AssertionError("ghi ảnh")):
        app.home_open_task(1); self.wait_home(app)
    self.assertTrue(app._home_imgs)                  # ảnh có trong RAM
def test_missing_preview_is_a_grey_box(self):
```

- [ ] **Step 2: Chạy → FAIL** `-p test_gui_home.py`.
- [ ] **Step 3: Cài** như Interfaces.
- [ ] **Step 4: Chạy → PASS** `test_gui_home.py`, `test_gui_cvat.py`.
- [ ] **Step 5: Commit** `feat(gui): hiện nhãn prelabeled và ảnh xem trước trên trang chủ`

### Task 7: Rời job về trang chủ ("← Trang chủ")

**Files:**
- Modify: `eyepin/gui_home.py`, `eyepin/gui.py` (thanh cam: nút "Trang chủ" — dùng chung nút icon `home` hiện là `cvat_open_btn` của `_cvat_buttons`, gui_cvat.py 97: bấm khi đang mở job CVAT = `leave_job`, khi không = `show_home`), `eyepin/gui_cvat.py` (`open_cvat` khi đang ở job CVAT → `leave_job`)
- Test: `tests/test_gui_home.py`

**Interfaces:**
- Consumes: `Session.unsent`, `send_cvat`, `_after_send`/`_send_finished`, `save_work(auto=True)`.
- Produces: `App.ask_leave_job(job: int | None, pins: int) -> Literal["send", "leave", "cancel"]` (hộp Có/Không/Huỷ như `ask_logout_open_job`, mặc định `cancel`; chữ: "Gửi lên CVAT rồi về trang chủ / Về trang chủ (công vẫn lưu trên máy, mở lại job sẽ hỏi khôi phục) / Ở lại").
- Produces: `App.leave_job() -> None` — `s.unsent` False → `save_work(auto=True)`, về trang chủ (danh sách job của task vừa làm, làm mới); True → hỏi: `send` đặt `_after_send = lambda ok: ok and not s.unsent and self._go_home_from_job()` rồi `send_cvat()`; `leave` → `save_work(auto=True)` rồi về; `cancel` ở lại. Không bao giờ tự gửi, không xoá file phiên. Về trang chủ thì `self.s = None`, `show_home()`.
- Đang mở thư mục ảnh mà bấm "Mở từ CVAT…"/nút Trang chủ: `_save_outgoing()` rồi `show_home()` (như hiện nay).

- [ ] **Step 1: Viết test hỏng:** `test_leave_without_changes_goes_home_without_login` (không gọi `POST /api/auth/login`, `home_visible()` True, đang xem task của job), `test_leave_with_unsent_cancel_stays`, `test_leave_with_unsent_leave_saves_session_and_goes_home` (file `state_path` có `unsent: true`), `test_leave_with_unsent_send_failure_stays` (`fail_import` → vẫn ở job), `test_leave_with_unsent_send_ok_goes_home_and_badge_prelabeled`, `test_folder_session_saves_then_shows_home`.
- [ ] **Step 2: Chạy → FAIL** `-p test_gui_home.py`.
- [ ] **Step 3: Cài** như Interfaces.
- [ ] **Step 4: Chạy → PASS** `test_gui_home.py`, `test_gui_cvat.py`, `test_logout.py`, `test_close_confirm.py`.
- [ ] **Step 5: Commit** `feat(gui): thêm nút về trang chủ từ job, hỏi khi còn công chưa gửi`

### Task 8: Tài liệu, sơ đồ kiến trúc và thử thật trên CVAT local

**Files:**
- Modify: `HUONG_DAN.md` (dòng 6–7 và mục 5 dòng 47–58: trang chủ, nhãn prelabeled, nút Trang chủ; Đăng xuất **về màn đăng nhập**, không đóng tool; nhớ đăng nhập 8 giờ là của EyePin trên máy này, khoá vẫn còn trên CVAT), `TASKS.md` (tick 109, 163, 179; thêm việc phát sinh), `CLAUDE.md` (module `gui_home.py`, `LoginForm`, `App.teardown/back_to_login`; lệnh `--cvat` không `--job` mở màn đăng nhập rồi trang chủ; đường dẫn sơ đồ mới), `design/2026-11-16-cvat-home-design.md` mục 7 (đánh dấu đã kiểm, dẫn sang `cvat-api-notes.md`)

- [ ] **Step 1: Cập nhật tài liệu** như Files.
- [ ] **Step 2: Vẽ lại sơ đồ** bằng `/archify` vào `.archify/architecture-eyepin-home-<ngày-giờ>/` (quy tắc `CLAUDE.md`: thêm `gui_home.py` và đổi luồng khởi động/đăng xuất là thay đổi module lớn; gộp luôn việc TASKS 179 về `cvatlogin.py`, `gui_login.py`); cập nhật đường dẫn trong `CLAUDE.md`.
- [ ] **Step 3: Kiểm trạng thái nhãn job 3–9 trước khi khẳng định** (chỉ GET `/api/jobs/{id}/annotations` với khoá ở `~\.cvat_token`): ghi lại job nào có shape/track `mattrai`/`matphai` — `verify_vs_cvat.py` và `cvat_roundtrip.py` từng import rồi xoá trên job 5 và 9, nên không giả định "#5 chưa có nhãn mắt".
- [ ] **Step 4: Thử thật cùng người dùng** (người dùng tự gõ mật khẩu): `python -m eyepin gui --cvat http://localhost:8080`; kiểm: đăng nhập có ghi nhớ; thấy 8 task (ảnh nếu preview có); nhãn từng job khớp kết quả Step 3; mở một job rồi Trang chủ không hỏi đăng nhập; đóng rồi mở lại tool không hỏi đăng nhập; Đăng xuất → về màn đăng nhập, cửa sổ còn; sau đó trong `%USERPROFILE%\.eyepin\` không còn `cvat_login.bin` và không còn file `sessions\*.json` nào có khoá `cvat`; đóng cửa sổ ở màn đăng nhập thì tiến trình thoát. Ghi kết quả vào `TASKS.md` (dòng 160, 164).
- [ ] **Step 5: Chạy lần lượt mọi file test** `tests/test_*.py` (mỗi file một lệnh) và báo số test qua/hỏng từng file.
- [ ] **Step 6: Commit** `docs: cập nhật hướng dẫn, danh sách việc và CLAUDE.md cho trang chủ`; rồi mở PR `feature/cvat-home` → `develop`.

---

## Quyết định người dùng / quyết định của Claude

**Người dùng chốt 2026-11-17 (sau khi duyệt bản viết lại):**
- EyePin là tool bên ngoài CVAT: nút Đăng xuất chỉ đăng xuất khỏi EyePin (dọn dữ liệu cục bộ, về màn đăng nhập), KHÔNG bao giờ đăng xuất CVAT. Giữ nút ở mọi chế độ (kể cả phiên thư mục ảnh).
- Xoá hẳn hộp "Mở từ CVAT…" cũ (trang chủ thay thế).
- Sau Đăng xuất KHÔNG tự mở lại job (kể cả job truyền bằng `--job`): phải đăng nhập lại, rồi vào trang chủ.
- Tách hai nút (người dùng 2026-11-17): **Đăng xuất** (dọn dữ liệu cục bộ, về màn đăng nhập) và **Thoát EyePin** (như đóng cửa sổ: hỏi lưu rồi tắt tiến trình, không dọn dữ liệu). Làm trong vòng sửa 1 của Task 2.
- Chưa trả lời: lối tắt Desktop `Eyepin.lnk` có đổi sang `EyePin.bat` không; mật khẩu cho lần thử thật ở Task 8 (người dùng tự nhập).


**Người dùng đã chốt**
- Trang chủ nằm trong cửa sổ chính (spec 3a, cách A); nhớ đăng nhập bằng khoá, không lưu mật khẩu, mã hoá DPAPI (3b, cách A); hạn mặc định 8 giờ, chỉnh trong Cài đặt, 0 = không nhớ.
- "prelabeled" = job đã có nhãn mắt (mở sẽ vào QC).
- Không bao giờ gọi `POST /api/auth/logout` ("chỉ đăng xuất ở máy cá nhân").
- Đăng xuất = dọn dữ liệu CVAT trên máy (4.6b), có nút nhìn thấy được (9b).
- Màn đăng nhập là cửa trước, có liên kết "Làm việc không cần CVAT" (mục 9, cách A).
- **2026-11-17: Đăng xuất (sau khi dọn) chỉ quay về màn đăng nhập; chỉ đóng cửa sổ mới thoát tiến trình** (spec dòng 170) → Task 2.
- Dự án dùng git với nhánh `develop` và quy ước commit trong `CLAUDE.md`.

**Claude đề xuất (chưa được duyệt từng điểm)**
- Thứ tự: sửa an toàn trước (Task 1 QC, Task 4 khoá khi 401) rồi mới trang chủ; Task 2 đứng thứ hai vì người dùng vừa chốt và nó độc lập.
- `qc.json_has_eyes(aj, eye_ids=None)` nhận id nhãn; trang chủ lấy `task_labels` một lần mỗi task để khỏi báo "prelabeled" giả cho skeleton 8 điểm khác.
- Đăng xuất từ phiên thư mục ảnh (mở bằng `gui <thư_mục>`) cũng về màn đăng nhập, cùng đường.
- `teardown` gỡ `App` rồi dựng `FrontDoor` mới trong cùng `root` (không tạo `Tk` mới); sau Đăng xuất không tự mở lại `--job` đã truyền lúc đầu.
- Trang chủ có `HomeRunner` riêng, không dùng `_run_bg` (không khoá sửa nhãn, "bấm sau cùng thắng").
- Hộp "Mở từ CVAT…" cũ bị xoá hẳn khi có trang chủ (spec 4.1 bước 3); test của nó chuyển sang `test_gui_home.py`. `--cvat --selftest` mở trang chủ thay hộp cũ.
- Hộp đăng nhập lại giữa job khoá ô địa chỉ (cùng CVAT), ô ghi nhớ mặc định bật, và gắn khoá mới vào chính client đang mở.
- Nút "Trang chủ" dùng chung nút icon `home` đang có (thay vì thêm nút thứ hai).
- Job `ground_truth` và task `mode == "interpolation"` hiện mờ ở trang chủ (chỉ khi Task 3 Step 1 xác nhận trường này có trên 2.75).
- Kiểm endpoint bằng khoá trong `~\.cvat_token` (CVAT local, chỉ GET).

**Còn chờ người dùng**
- Đổi lối tắt Desktop `Eyepin.lnk` sang `EyePin.bat` (TASKS 161).
- Mật khẩu để thử thật (Task 8 Step 4).
- Có muốn giữ nút Đăng xuất khi đang làm việc không cần CVAT (hiện vẫn hiện và vẫn dọn phiên CVAT cũ trên máy) hay ẩn đi.
