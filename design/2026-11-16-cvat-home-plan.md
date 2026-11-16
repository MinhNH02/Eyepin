# Trang chủ CVAT, nhớ đăng nhập, Đăng xuất dọn máy — kế hoạch thực hiện

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mở EyePin với `--cvat` là vào trang chủ kiểu CVAT (thẻ task có ảnh, danh sách job có trạng thái CVAT + prelabeled), đi lại job ↔ trang chủ không đăng nhập lại, nhớ khoá đăng nhập có hạn (DPAPI), Đăng xuất xoá dữ liệu CVAT trên máy.

**Architecture:** API mới trong `CvatClient` (chỉ đọc) + `FakeCvat`; quy tắc "có nhãn mắt" dùng chung ở `qc.py`; khoá đăng nhập mã hoá trong `eyepin/cvatlogin.py`; trang chủ là mixin mới `eyepin/gui_home.py` thay vùng thân cửa sổ; hộp đăng nhập cũ thu lại thành hộp nhỏ chỉ dùng khi hết phiên giữa job.

**Tech Stack:** Python 3.12, Tkinter/ttk, requests (đã có trong `cvatapi.py`), Pillow, `ctypes` (DPAPI `crypt32`), unittest.

**Spec:** `design/2026-11-16-cvat-home-design.md` (mục 4.1–4.7, 4.5b, 4.6b, 8).

**Phụ thuộc:** làm sau kế hoạch `design/2026-11-16-cvat-sidebar-icons-plan.md` (dùng icon `home`, `logout`, `upload` và `IconButton` mới).

## Global Constraints
- Chỉ CVAT localhost (`CvatClient` đã chặn địa chỉ khác, `trust_env=False`, không redirect) — giữ nguyên.
- Ảnh (preview, frame) chỉ trong bộ nhớ, không ghi đĩa, không cache ra file.
- **Không bao giờ gọi `POST /api/auth/logout`.** Mật khẩu không bao giờ lưu.
- Hạn nhớ đăng nhập mặc định **8 giờ**, Cài đặt "Nhớ đăng nhập CVAT (giờ)", 0 = không nhớ.
- Mọi lệnh mạng chạy nền (`_run_bg`), cửa sổ không đứng.
- Không git: sao lưu `eyepin/`, `tests/` sang `..\eye_label_tool_backup_home\` trước Task 1. Test chạy từng file: `python -m unittest discover -s tests -p "<file>.py"`, `PYTHONIOENCODING=utf-8`.
- Thử trên server thật chỉ là CVAT local, chỉ đọc (GET), trừ khi người dùng cho phép khác.
- Văn bản cho người dùng bằng tiếng Việt.

## Review Focus
1. CVAT tắt hoặc 502 khi đang ở trang chủ: trang chủ báo lỗi và có nút Làm mới, không treo, không văng ra màn đăng nhập (test Task 5).
2. Khoá đã nhớ nhưng CVAT đã huỷ (401): xoá file khoá, về màn đăng nhập, không lặp vô hạn (test Task 3 và 5).
3. File khoá hỏng hoặc của tài khoản Windows khác: coi như không có, xoá, không sập (test Task 3).
4. Bấm job khác trong khi job trước còn đang tải: chỉ job bấm sau cùng được mở (test Task 5).
5. Đăng xuất khi một file phiên đang bị khoá/không xoá được: báo tên file, không nói "đã sạch" (test Task 7).

---

### Task 1: API CVAT cho trang chủ (chỉ đọc) và kiểm trên CVAT local

**Files:**
- Modify: `eyepin/cvatapi.py` (~121–140), `tests/fake_cvat.py`, `design/cvat-api-notes.md`
- Test: `tests/test_cvatapi.py`

**Interfaces:**
- Produces: `CvatClient.tasks() -> list[dict]` có thêm `project_id: int|None`, `updated_date: str`, `jobs: int` (số job; từ `jobs.count` nếu có, không thì `None`).
- Produces: `CvatClient.projects() -> dict[int, str]`.
- Produces: `CvatClient.jobs(task_id)` thêm `assignee: str|None` (username), `updated_date: str`, `type: str`.
- Produces: `CvatClient.preview(kind: Literal["task","job"], obj_id: int) -> bytes | None` (`GET /api/{kind}s/{id}/preview`; 404/không có → `None`; lỗi mạng khác vẫn ném `CvatError`).
- Produces: `CvatClient.whoami() -> str` (`GET /api/users/self` → username; 401 → `LoginNeeded`).
- Produces: `CvatClient.token -> str | None` (property, khoá hiện dùng) và `CvatClient.use_token(token: str) -> None` (đặt header `Authorization: Token <token>`).
- `FakeCvat` có `projects`, `assignee`, `preview` (bytes PNG nhỏ hoặc thiếu), `users/self`.

- [ ] **Step 0: Sao lưu.**
- [ ] **Step 1: Kiểm trên CVAT local (chỉ GET, qua phiên Chrome đã đăng nhập của người dùng hoặc `curl` với khoá người dùng cung cấp):** `/api/tasks?page_size=1` có `jobs.count` không; `/api/tasks/4/preview` và `/api/jobs/4/preview` trả gì (mã, `Content-Type`); `/api/users/self` có `username`. Ghi kết quả vào `design/cvat-api-notes.md` mục mới "Trang chủ (2.75, thử ngày …)". Không ghi được thì ghi "chưa thử" và làm theo mã nguồn CVAT.
- [ ] **Step 2: Test** thêm vào `tests/test_cvatapi.py`: `test_tasks_have_project_updated_jobs`, `test_projects_map`, `test_jobs_have_assignee_and_updated`, `test_preview_bytes_and_missing_is_none`, `test_whoami_and_401_raises_login_needed`, `test_use_token_sets_header_and_token_property` (header đúng `Token <t>`), `test_preview_still_localhost_only` (client tạo với địa chỉ không phải localhost vẫn bị từ chối như cũ).
- [ ] **Step 3:** chạy → FAIL; **Step 4:** implement; **Step 5:** chạy → PASS.

### Task 2: Một quy tắc "có nhãn mắt" cho trang chủ và lúc mở job

**Files:**
- Modify: `eyepin/qc.py`, `eyepin/cvatsource.py` (`_has_eyes` ~107, `open_job` ~111)
- Test: `tests/test_qc.py`, `tests/test_cvatsource.py`

**Interfaces:**
- Produces: `qc.json_has_eyes(annotations_json: dict) -> bool` — True nếu có **bất kỳ** shape hoặc track nào (kể cả track rỗng, toàn Outside, ngoài khoảng frame) thuộc label `mattrai`/`matphai` (nhận theo cách `cvatsource._is_eye` đang nhận). `cvatsource._has_eyes` gọi hàm này (hoặc bị thay hẳn).
- Hành vi mới của `open_job`: `session.qc = qc.has_eye_labels(xml_ann) or qc.json_has_eyes(aj)`.

- [ ] **Step 1: Test:** `test_json_has_eyes_shape_track_empty_outside` (các dạng trên đều True; chỉ nhãn khác → False; `{}` → False); trong `test_cvatsource.py`: `test_open_job_qc_when_only_json_has_eyes` (FakeJob có track mắt toàn Outside mà XML sau parse không còn mắt → `session.qc is True`).
- [ ] **Step 2–4:** FAIL → implement → PASS; chạy lại toàn bộ `test_cvatsource.py`, `test_gui_cvat.py`.

### Task 3: Khoá đăng nhập mã hoá có hạn (`cvatlogin.py`)

**Files:**
- Create: `eyepin/cvatlogin.py`
- Modify: `eyepin/shortcuts.py` (`DEFAULT_SETTINGS["cvat"]["remember_hours"] = 8`; sửa chú thích "mật khẩu và khoá không bao giờ lưu" → "mật khẩu không bao giờ lưu; khoá lưu mã hoá có hạn ở cvat_login.bin")
- Test: `tests/test_cvatlogin.py`

**Interfaces:**
- Produces: `login_path() -> Path` (= `shortcuts.settings_path().parent / "cvat_login.bin"`).
- Produces: `protect(data: bytes) -> bytes`, `unprotect(blob: bytes) -> bytes` (DPAPI `CryptProtectData`/`CryptUnprotectData` qua `ctypes`, phạm vi người dùng hiện tại; lỗi → `ValueError`).
- Produces: `save_login(url: str, user: str, token: str, hours: float, now: float | None = None) -> bool` (hours ≤ 0 → không ghi, xoá file cũ, trả False).
- Produces: `load_login(url: str, now: float | None = None) -> tuple[str, str] | None` → `(user, token)`; hết hạn / khác url / hỏng / không giải mã được → xoá file và trả `None`.
- Produces: `forget_login() -> str | None` (xoá file; trả tên file nếu không xoá được).

- [ ] **Step 1: Test** `tests/test_cvatlogin.py` (đặt `EYEPIN_HOME` tạm): `test_roundtrip`, `test_file_does_not_contain_token_or_user_in_plain` (bytes file không chứa token, user, url dạng UTF-8/UTF-16), `test_expired_is_deleted` (now = lưu + 8 giờ + 1 s), `test_other_url_returns_none_and_deletes`, `test_corrupt_file_returns_none_and_deletes`, `test_zero_hours_does_not_save`, `test_forget_removes_file`. Bỏ qua cả file nếu không phải Windows.
- [ ] **Step 2–4:** FAIL → implement → PASS.

### Task 4: Cờ "chưa gửi" và chỗ để file phiên CVAT

**Files:**
- Modify: `eyepin/session.py` (`_push_undo` ~625, `state` ~651), `eyepin/cvatsync.py` (`send` thành công, `mark_synced`), `eyepin/gui.py` (`state_path` ~536, khôi phục phiên)
- Test: `tests/test_session.py`, `tests/test_cvatsync.py`

**Interfaces:**
- Produces: `Session.unsent: bool` — False khi mở job; True sau mọi thay đổi nhãn (`_push_undo`) và sau khi khôi phục phiên đã lưu có ghim; False sau `send` thành công. Chỉ có nghĩa khi `session.cvat` khác None.
- Produces: `Session.state()` thêm `"source_key"` và `"unsent"`; `load_state` đọc lại `unsent` (thiếu → False).
- Produces: `App.state_path()` — phiên CVAT (`s.cvat` khác None) nằm ở `sessions/cvat/<hash>.json`; phiên thư mục ảnh vẫn `sessions/<hash>.json`. Khi mở job CVAT mà file cũ ở `sessions/<hash>.json` tồn tại thì chuyển nó sang `sessions/cvat/`.
- Produces: `cvat_session_files() -> list[Path]` trong `eyepin/cvatlogin.py` (mọi file trong `sessions/cvat/` + file `sessions/*.json` có `source_key` bắt đầu bằng `cvat:`), và `unsent_sessions() -> list[tuple[Path, str, int]]` → `(file, source_key, số frame ghim)` cho file có `unsent=True`.

- [ ] **Step 1: Test:** `test_unsent_after_edit_cleared_after_send` (FakeCvat), `test_unsent_roundtrips_in_state`, `test_cvat_session_goes_to_cvat_subfolder`, `test_legacy_cvat_session_is_moved`, `test_unsent_sessions_lists_only_unsent_cvat`.
- [ ] **Step 2–4:** FAIL → implement → PASS; chạy lại `test_gui.py`, `test_gui_cvat.py`, `test_close_confirm.py`.

### Task 5: Trang chủ (màn đăng nhập, lưới task, danh sách job)

**Files:**
- Create: `eyepin/gui_home.py`
- Modify: `eyepin/gui.py` (thêm `HomeMixin` vào `App`; `_build` để thân cửa sổ đổi được giữa "trang chủ" và "job"), `eyepin/gui_cvat.py` (`open_cvat` → `show_home`; hộp cũ thu lại thành `_relogin_dialog`), `eyepin/__main__.py` / `run(...)` (`--cvat` không `--job` → trang chủ)
- Test: `tests/test_gui_home.py`

**Interfaces:**
- Consumes: Task 1 (API), Task 2 (`json_has_eyes`), Task 3 (`load_login`/`save_login`), icon `home`/`logout`/`upload`.
- Produces: `App.show_home(url: str | None = None) -> None`, `App.home_visible() -> bool`, `App.show_job_view() -> None`.
- Produces: `App.home_open_task(task_id: int)`, `App.home_back_to_tasks()`, `App.home_open_job(job_id: int)` (→ `load_cvat` hiện có; bấm job mới khi job cũ đang tải thì kết quả cũ bị bỏ — dùng số thứ tự yêu cầu), `App.home_refresh()`.
- Produces: `App.job_badge(job_id: int) -> str` ∈ `{"prelabeled", "chưa có nhãn mắt", "đang kiểm…", "chưa rõ"}`; cache `{(job_id, updated_date): bool}`; sau gửi thành công đặt job đó là prelabeled.
- Màn đăng nhập: địa chỉ, tên, mật khẩu, ô "Ghi nhớ đăng nhập" (mặc định bật), nút Đăng nhập. Mở trang chủ: có khoá nhớ còn hạn → `use_token` + `whoami()` nền → được thì vào lưới task; 401 → `forget_login()` rồi màn đăng nhập. Đăng nhập thành công + ô ghi nhớ bật + `remember_hours > 0` → `save_login`.
- Lưới task: thẻ có ảnh preview (thu nhỏ, `PhotoImage` trong bộ nhớ, tải nền, thiếu → khung xám), `#id tên`, tên project, số frame, số job; ô lọc project (`Tất cả` + tên) và ô tìm (tên hoặc số). Danh sách job: ảnh, `Job #id`, `frame a–b`, `state / stage`, nhãn EyePin, người được giao, ngày sửa (`dd/mm HH:MM` giờ máy), nút Mở; bấm đúp = Mở. Bố cục theo phác thảo spec 4.2.
- Job mà `cvatsource` sẽ từ chối mở và biết được từ dữ liệu đã tải (ví dụ `type` là ground truth) hiện mờ kèm lý do ngắn; các lý do chỉ biết lúc mở thì để lỗi hiện như hiện nay.
- Lỗi mạng/502 ở trang chủ: dòng báo lỗi + nút Làm mới; không xoá khoá đã nhớ (chỉ 401 mới xoá).

- [ ] **Step 1: Test** `tests/test_gui_home.py` (FakeCvat như `tests/test_gui_cvat.py`, `_run_bg` chạy đồng bộ trong test): `test_cvat_without_job_shows_home_login`, `test_remembered_token_skips_login`, `test_revoked_token_forgets_and_shows_login`, `test_login_with_remember_saves_token`, `test_login_without_remember_does_not_save`, `test_task_grid_filters_by_project_and_search`, `test_job_badges_prelabeled_and_empty` (job có track mắt → "prelabeled"; trống → "chưa có nhãn mắt"; lỗi annotations → "chưa rõ"), `test_badge_cache_follows_updated_date`, `test_open_job_from_home_then_back_without_login`, `test_last_clicked_job_wins`, `test_server_down_shows_retry_and_keeps_token`, `test_previews_never_written_to_disk` (patch `open`/`Image.save` để báo nếu ghi ảnh).
- [ ] **Step 2–4:** FAIL → implement → PASS; chạy lại `test_gui_cvat.py`.

### Task 6: Rời job về trang chủ; hết phiên giữa job

**Files:**
- Modify: `eyepin/gui_home.py`, `eyepin/gui_cvat.py` (`_login_again`), `eyepin/gui.py` (nút "← Trang chủ" trên thanh trên khi đang mở job CVAT)
- Test: `tests/test_gui_home.py`

**Interfaces:**
- Produces: `App.leave_job() -> bool` — `s.unsent` False → về trang chủ; True → hỏi `ask_leave_job() -> "send" | "leave" | "cancel"` (mặc định `cancel`): `send` chạy `send_cvat` và chỉ về trang chủ khi gửi thành công; `leave` tự lưu phiên (`save_work(auto=True)`) rồi về; `cancel` ở lại. Không bao giờ tự gửi, không xoá file phiên.
- Produces: `App._relogin_dialog()` — hộp nhỏ nổi trên job (địa chỉ cố định, tên, mật khẩu, ô ghi nhớ); đăng nhập xong gọi `retry` như `_login_again` hiện nay.
- Thư mục ảnh đang mở mà chọn "Mở từ CVAT…": giữ hành vi hiện tại (`_save_outgoing`) rồi `show_home`.

- [ ] **Step 1: Test:** `test_leave_without_changes_goes_home`, `test_leave_with_unsent_cancel_stays`, `test_leave_with_unsent_leave_saves_session_and_goes_home`, `test_leave_with_unsent_send_failure_stays`, `test_401_mid_job_shows_small_dialog_and_retries` (job vẫn hiện, không về trang chủ).
- [ ] **Step 2–4:** FAIL → implement → PASS.

### Task 7: Đăng xuất = dọn dữ liệu CVAT trên máy

**Files:**
- Modify: `eyepin/gui_home.py`, `eyepin/cvatlogin.py`, `eyepin/gui.py` (Cài đặt: "Nhớ đăng nhập CVAT (giờ)")
- Test: `tests/test_logout.py`

**Interfaces:**
- Produces: `cvatlogin.wipe_local(settings: dict) -> list[str]` — xoá `cvat_login.bin`, mọi `cvat_session_files()`, đặt `settings["cvat"]["user"] = ""` (giữ `url`), lưu settings; trả danh sách file **không** xoá được (rỗng = sạch).
- Produces: `App.logout() -> None` theo spec 4.6b: (1) job đang mở có `unsent` → `ask_logout_open_job() -> "send" | "discard" | "cancel"` (mặc định `cancel`; `send` lỗi hoặc huỷ → dừng, không xoá); (2) `unsent_sessions()` khác rỗng (trừ job đang mở) → `ask_logout_others(list) -> "wipe" | "cancel"`; (3) `wipe_local`; đóng job, `cvat_client = None`, về màn đăng nhập; (4) danh sách lỗi khác rỗng → báo tên file, không báo "đã sạch".
- Phiên thư mục ảnh (`sessions/<hash>.json` không phải CVAT) và file người dùng tự lưu qua hộp "Lưu…" **không** bị xoá.

- [ ] **Step 1: Test** `tests/test_logout.py`: `test_logout_clean_removes_token_sessions_and_user` (url còn), `test_logout_keeps_folder_sessions`, `test_logout_with_unsent_open_job_cancel_keeps_everything`, `test_logout_send_failure_keeps_everything`, `test_logout_discard_wipes`, `test_logout_lists_other_unsent_jobs_and_cancel_keeps`, `test_locked_file_is_reported_not_claimed_clean` (patch `Path.unlink` ném `PermissionError` cho một file), `test_logout_never_calls_server_logout` (FakeCvat ghi mọi request; không có `/api/auth/logout`), `test_remember_hours_setting_zero_disables_saving`.
- [ ] **Step 2–4:** FAIL → implement → PASS.

### Task 8: Tài liệu và thử thật trên CVAT local

**Files:**
- Modify: `HUONG_DAN.md` (mục 5: trang chủ, trạng thái job, nhớ đăng nhập 8 giờ là của EyePin trên máy này, khoá vẫn còn trên CVAT tới khi đăng xuất trên web, Đăng xuất xoá gì/không xoá gì, khuyên bấm Đăng xuất trước khi về), `TASKS.md`, `CLAUDE.md` (module `gui_home.py`, `cvatlogin.py`; lệnh `--cvat` không `--job` mở trang chủ), `design/2026-11-16-cvat-home-design.md` mục 7 (đánh dấu đã kiểm).

- [ ] **Step 1:** Cập nhật tài liệu.
- [ ] **Step 2:** Chạy `python -m eyepin gui --cvat http://localhost:8080`; người dùng tự đăng nhập; kiểm: thấy 8 task có ảnh, job có track mắt (#3, #4, #6 có track — kiểm đúng là nhãn mắt) hiện "prelabeled", #5 "chưa có nhãn mắt", mở job rồi "← Trang chủ" không hỏi đăng nhập, đóng mở lại tool không hỏi đăng nhập, Đăng xuất xong thư mục `sessions\cvat\` trống và không còn `cvat_login.bin`.
- [ ] **Step 3:** Chạy lần lượt mọi file test và báo kết quả từng file.
