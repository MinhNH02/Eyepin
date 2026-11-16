# Kế hoạch: EyePin nối thẳng CVAT local, chế độ QC cho job đã có nhãn, cảnh báo khi gửi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Mục tiêu:** Mở một job của CVAT local ngay trong EyePin (ảnh chỉ trong RAM). Job chưa có nhãn mắt thì gán bằng EyePin rồi gửi thẳng vào job bằng import (có cảnh báo, chống ghi đè, đối chiếu). Job đã có nhãn mắt thì vào chế độ QC; muốn sửa thì xoá nhãn mắt cũ rồi gán lại.

**Kiến trúc:** `Session` đọc ảnh qua một nguồn ảnh (thư mục như cũ, hoặc CVAT). Client API mỏng `cvatapi.py` (requests) lo đăng nhập, liệt kê, ảnh, xuất, import. `qc.py` đếm nhãn mắt có sẵn và bỏ chúng khỏi nhãn nền. `cvatsync.py` ghép các bước gửi. `gui.py` thêm hộp "Mở từ CVAT…", chế độ QC, lệnh "Xoá nhãn mắt cũ và gán lại", "Gửi lên CVAT"; việc mạng chạy trên luồng nền.

**Công nghệ:** Python 3.12, requests 2.34, OpenCV, Tkinter, unittest. Không thêm thư viện.

**Spec:** `design/2026-11-16-cvat-direct-design.md`

## Ràng buộc chung
- Chỉ host `localhost`, `127.0.0.1`, `::1`; host khác ném `CvatError("Lần này chỉ nối với CVAT trên máy (localhost). Server công ty chưa được bật.")`.
- Ảnh không bao giờ ghi ra đĩa (kể cả file tạm). XML toạ độ được phép ghi file tạm.
- Ghi vào CVAT chỉ bằng import (`POST /api/jobs/{id}/annotations?format=CVAT 1.1`). Không PATCH/PUT nhãn.
- Header: `Authorization: Token <key>`; không gửi `Accept: application/json`.
- Khoá đăng nhập chỉ trong RAM; không lưu mật khẩu; nhớ `{url, user}` trong `~/.eyepin/settings.json` khoá `cvat`.
- Mở bằng thư mục (kể cả `--xml`) phải y như cũ: 208 test hiện có còn qua.
- Dự án không có git: thay bước commit bằng chạy cả bộ test `python -m unittest discover -s tests`; trước Task 1 sao lưu `eyepin\` và `tests\` sang `..\eye_label_tool_backup_<giờ>`.
- Chữ hiện cho người dùng bằng tiếng Việt.

## Trọng tâm rà soát
1. Job không bắt đầu từ frame 0: ghim, xuất và đối chiếu dùng đúng số frame của job (Task 3, `test_frame_numbers_of_a_job_that_starts_at_10`).
2. Mạng rớt sau khi gửi lệnh import, trước khi biết kết quả: báo "chưa rõ đã import chưa", không báo thành công (Task 5, `test_lost_connection_while_waiting_for_import`).
3. Khoá hết hạn (401) giữa chừng: hỏi đăng nhập lại, không mất ghim (Task 2 `test_401_raises_login_needed`; Task 6 `test_login_needed_reopens_login`).
4. Ở chế độ QC, mọi đường sửa nhãn đều bị chặn, kể cả phím tắt và kéo chuột (Task 4 chặn trong `Session`; Task 6 `test_qc_blocks_every_edit_path`).
5. Job dài (hàng nghìn frame): mở job không tải hết ảnh (Task 3, `test_open_job_downloads_no_frame_until_asked`).

---

### Task 0: Thử trên CVAT local thật (XONG 2026-11-16, kết quả ở `design/cvat-api-notes.md`)

**Kết luận đã chốt (các task sau dùng đúng những điều này):** import một lần không gửi `filename`; "CVAT for images" trải track thành shape ở mọi frame, "CVAT for video" đổi shape thành track một frame; định dạng nền chọn theo loại đối tượng không phải mắt (đọc `GET /api/jobs/{id}/annotations`); số frame XML = số frame của task = `meta.start_frame + i` (**sửa 2026-11-16 sau review toàn nhánh:** chỉ số EyePin `i` ↔ `job.start_frame + i` lấy từ `GET /api/jobs/{id}`; `meta.start_frame` là số tuyệt đối của media, chỉ trùng khi task không đặt start_frame/frame_step; job video, job thưa và task đặt start_frame/frame_step bị từ chối; xem `design/cvat-api-notes.md`).

**Files:** Create `spike/cvat_api_probe.py` (dùng một lần), `design/cvat-api-notes.md` (kết quả).

- [ ] **Bước 1:** Bật CVAT local (`cd C:\Users\minhf\cvat; $env:CVAT_VERSION='v2.75.0'; docker compose up -d`, chờ hết 502; cổng 8080 trả rỗng thì `docker restart traefik`). Đăng nhập lấy khoá. Chỉ dùng job trống hoặc job thử; xoá sạch nhãn thử khi xong.
- [ ] **Bước 2:** Trên job có một track `mattrai` (3 keyframe, một điểm Outside, một điểm Occluded) và một shape `matphai`: xuất "CVAT for images 1.1" và "CVAT for video 1.1" bằng `POST /api/jobs/{id}/dataset/export?format=...&save_images=False` → `GET /api/requests/{rq_id}` → tải `result_url`. Ghi lại: track còn là `<track>` hay thành shape mỗi frame ở từng định dạng; số frame trong XML là số của task hay tính từ đầu job; `cvatxml.parse` + `points_at` hiển thị được ở định dạng nào.
- [ ] **Bước 3:** Import `POST .../annotations?format=CVAT 1.1&filename=x.xml` (multipart `annotation_file`) một file có cả `<track>` và `<image>` shape; ghi mã trả về và thân `requests/{rq_id}` khi `finished` và khi `failed` (gửi file hỏng).
- [ ] **Bước 4:** Với task nhiều job (hoặc tạo task thử 30 ảnh, job 10 frame): `data/meta` và ảnh frame đầu của job thứ hai; xoá một frame trên giao diện CVAT rồi xem `data?type=frame` của frame đó và file export.
- [ ] **Bước 5:** Ghi vào `design/cvat-api-notes.md`: định dạng nền khi gửi, định dạng để hiện nhãn ở chế độ QC, cách đổi số frame XML ↔ chỉ số EyePin, hành vi frame đã xoá. Chỗ nào khác giả định trong kế hoạch thì sửa kế hoạch trước khi làm task sau.

---

### Task 1: Nguồn ảnh, `Session` không còn gắn cứng với thư mục

**Files:**
- Create: `eyepin/frames.py`
- Modify: `eyepin/session.py` (`__init__`, `bgr`, `gray`), `eyepin/headturn.py` (`format_report` dùng `session.title`), `eyepin/gui.py` (`state_path` dùng `session.source_key`)
- Test: `tests/test_frames.py`

**Interfaces:**
- Produces:
```python
# eyepin/frames.py
class DirSource:
    def __init__(self, folder: str): ...
    names: list[str]; width: int; height: int; deleted: set[int]
    key: str            # os.path.abspath(folder).lower(): khoá file phiên như cũ
    title: str          # tên thư mục
    def read(self, i: int) -> np.ndarray   # BGR
# eyepin/session.py
Session(frames_dir: str | None = None, xml_path: str | None = None, *, source=None, ann: Annotations | None = None)
Session.source; Session.source_key: str; Session.title: str
```
`Session(frames_dir)` giữ nguyên nghĩa (tạo `DirSource`); `Session.deleted` khởi tạo từ `source.deleted`; `frames_dir` là `None` với nguồn khác.

- [ ] **Bước 1: Test:** `test_dir_source_matches_old_reading` (ảnh tổng hợp như `tests/test_session.py`: `DirSource(d).read(3)` bằng `cv2.imread` của tệp thứ 4; `names` sắp xếp; cỡ ảnh đúng); `test_session_accepts_any_source` (nguồn giả trong RAM 60 ảnh `T.render(t)`: `Session(source=fake)`, ghim frame 0, `labels[10]` lệch < 1 px); `test_state_key_for_folder_unchanged` (`App.state_path()` cho một thư mục bằng đúng giá trị của bản cũ: băm sha1 12 ký tự của `os.path.abspath(d).lower()`).
- [ ] **Bước 2:** `python -m unittest discover -s tests -p test_frames.py` đỏ (`ModuleNotFoundError: eyepin.frames`).
- [ ] **Bước 3:** Viết `frames.py`; `Session.bgr`/`gray` dùng `self.source.read(i)`.
- [ ] **Bước 4:** Xanh; cả bộ `OK` (208 + 3).

---

### Task 2: Client API CVAT và server CVAT giả

**Files:** Create `eyepin/cvatapi.py`, `tests/fake_cvat.py`; Test `tests/test_cvatapi.py`.

**Interfaces:**
- Produces:
```python
class CvatError(Exception): ...         # thông điệp tiếng Việt, hiện thẳng cho người dùng
class LoginNeeded(CvatError): ...       # 401
class CvatClient:
    def __init__(self, url: str, timeout: float = 30): ...      # kiểm host
    url: str
    def login(self, user: str, password: str) -> None
    def tasks(self) -> list[dict]                 # [{id, name, size}]
    def jobs(self, task_id: int) -> list[dict]    # [{id, start_frame, stop_frame, state, stage}]
    def job(self, job_id: int) -> dict            # có updated_date, task_id
    def meta(self, job_id: int) -> dict           # data/meta nguyên văn
    def frame(self, job_id: int, number: int) -> bytes
    def export_xml(self, job_id: int, fmt: str) -> bytes        # annotations.xml giải nén trong RAM
    def import_xml(self, job_id: int, xml: bytes) -> None       # chờ finished; failed -> CvatError kèm thông điệp server
    def eye_labels_ok(self, job_id: int) -> str | None          # None nếu có skeleton mattrai/matphai đủ 8 điểm, không thì lý do
    def annotations(self, job_id: int) -> dict                  # GET /api/jobs/{id}/annotations (JSON: shapes, tracks đúng loại)
```
- `tests/fake_cvat.py`: `FakeCvat` (http.server trong luồng, 127.0.0.1, cổng ngẫu nhiên) giữ một hoặc vài job trong RAM (ảnh tổng hợp `T.render`, XML nhãn, `updated_date`, `start_frame`, `deleted_frames`), làm đúng các đường ở spec mục 5: `202 {rq_id}`, `requests/{rq_id}` trả `queued` một lần rồi `finished`; công tắc: 401, 500, `failed`, ngắt khi hỏi trạng thái, dời một điểm khi import; ghi lại header và số lần gọi từng đường.

- [ ] **Bước 1: Test** (`FakeCvat`):
  - `test_refuses_non_local_host`: `CvatClient("https://cvat-dc.vantixapps.net")` ném `CvatError` có chữ "localhost".
  - `test_login_sends_token_header_and_no_accept_json`: sau `login`, header `Authorization == "Token k1"`, không có `Accept: application/json`.
  - `test_401_raises_login_needed`.
  - `test_export_waits_for_the_request_and_unzips_in_memory`: trả đúng bytes XML; `requests/{rq_id}` được hỏi ít nhất 2 lần.
  - `test_import_replaces_and_reports_server_failure`.
  - `test_frame_bytes_never_touch_disk`: `unittest.mock.patch("builtins.open")` ném lỗi nếu mở để ghi trong lúc `frame()`; bytes giải mã được bằng `cv2.imdecode`.
  - `test_connection_refused_gives_a_helpful_message`: cổng không ai nghe → `CvatError` có "Docker Desktop" và "docker restart traefik".
- [ ] **Bước 2:** Đỏ (`ModuleNotFoundError`). **Bước 3:** Viết (`requests.Session`; hỏi trạng thái mỗi 0,5 s, tối đa 300 s). **Bước 4:** Xanh; cả bộ.
- [x] **Vòng sửa theo CVAT thật (2026-11-16):** `import_xml` KHÔNG gửi `filename` trên URL (server báo 400 `No such file were uploaded`); thêm `annotations(job_id)`; server giả phải từ chối import có `filename` và cho test cấp XML riêng theo từng định dạng xuất.

---

### Task 3: Nguồn ảnh CVAT và mở một job

**Files:** Create `eyepin/cvatsource.py`; Modify `eyepin/cvatxml.py` (thêm `parse_bytes(data: bytes) -> Annotations`; đổi số frame theo Task 0); Test `tests/test_cvatsource.py`.

**Interfaces:**
- Consumes: `CvatClient` (Task 2), giao diện nguồn ảnh (Task 1).
- Produces:
```python
def base_format(annotations_json: dict) -> tuple[str, str]   # (định dạng nền khi gửi, định dạng hiện nhãn mắt) theo cvat-api-notes.md; nền: chỉ shape/không có → "CVAT for images 1.1", chỉ track hoặc cả hai → "CVAT for video 1.1"; hiện nhãn mắt: có track mắt → video, không → images
class CvatSource:                    # names, width, height, deleted, key, title, read(i) như DirSource
    def __init__(self, client: CvatClient, job_id: int): ...
    job_id: int
    frame_numbers: list[int]         # chỉ số EyePin i -> số frame của job
    key: str                         # f"cvat:{client.url}|job{job_id}"
    title: str                       # f"CVAT job #{job_id} ({tên task})"
def open_job(client: CvatClient, job_id: int) -> Session
    # eye_labels_ok; CvatSource; xuất nhãn nền theo định dạng Task 0 chọn; Session(source=..., ann=...);
    # session.cvat = {"job": job_id, "updated": updated_date}; session.qc = qc.has_eye_labels(ann) (Task 4)
```
`read(i)` tải `client.frame(job, frame_numbers[i])`, giải mã `cv2.imdecode` trong RAM.

- [ ] **Bước 1: Test:** `test_open_job_downloads_no_frame_until_asked` (≤ 1 lần gọi `data?type=frame` khi mở); `test_frames_come_from_cvat_in_ram` (`session.bgr(5)` bằng ảnh frame thứ 6 của server giả); `test_frame_numbers_of_a_job_that_starts_at_10` (job `start_frame=10`; ghim ở chỉ số 2 → `session.export` ra XML có frame đúng theo cách đánh số Task 0 ghi lại); `test_deleted_frames_are_read_only` (`deleted_frames=[3]` → `3 in session.deleted`); `test_job_without_eye_skeletons_is_refused` (`CvatError` có chữ "mattrai").
- [ ] **Bước 2:** Đỏ. **Bước 3:** Viết; `session.qc` tạm đặt `False` nếu Task 4 chưa xong (đợt 2 làm song song). **Bước 4:** Xanh; cả bộ.

---

### Task 4: Chế độ QC và "Xoá nhãn mắt cũ và gán lại" (lõi)

**Files:** Create `eyepin/qc.py`; Modify `eyepin/session.py` (cờ `qc`, chặn sửa trong `_push_undo`, `clear_old_eyes`/`restore_old_eyes`); Test `tests/test_qc.py`.

**Interfaces:**
- Produces:
```python
# eyepin/qc.py
@dataclass
class EyeLabels:
    tracks: list[tuple[str, int, int, int]]   # (nhãn, id track, frame đầu, frame cuối)
    shapes: dict[str, int]                    # nhãn -> số shape
    def empty(self) -> bool
    def message(self) -> str   # "" khi rỗng; ví dụ "1 track mắt #37 (mattrai, frame 0–120) và 30 shape mắt"
def eye_labels(ann: Annotations) -> EyeLabels
def has_eye_labels(ann: Annotations) -> bool
def without_eyes(ann: Annotations) -> Annotations    # bản sao: bỏ mọi <track> và <skeleton> mắt khỏi cây và khỏi tracks/shapes; nhãn khác giữ nguyên
# eyepin/session.py
Session.qc: bool                      # True: mọi thay đổi ghim ném ValueError(QC_MSG)
QC_MSG = "Job đã có nhãn mắt: đang ở chế độ QC. Muốn sửa thì bấm 'Xoá nhãn mắt cũ và gán lại'."
def clear_old_eyes(self) -> EyeLabels      # self.ann = without_eyes(...); giữ bản cũ; qc = False; trả cái đã bỏ
def restore_old_eyes(self) -> bool         # chỉ khi chưa có ghim nào sau lúc xoá; trả về ann cũ, qc = True
```
Chặn sửa: `Session._push_undo` ném `ValueError(QC_MSG)` khi `self.qc` (mọi thao tác sửa ghim đều gọi nó trước khi đổi gì).

- [ ] **Bước 1: Test** (XML dựng sẵn trong test, ảnh tổng hợp):
  - `test_counts_tracks_and_shapes`: 1 track `mattrai` id 37 frame 0–120 + 30 shape `matphai` → `message() == "1 track mắt #37 (mattrai, frame 0–120) và 30 shape mắt"`.
  - `test_without_eyes_keeps_other_labels`: XML có thêm một `<box label="face">` → sau `without_eyes`, `eye_labels(...).empty()` và cây vẫn còn thẻ box; `other_objects` không đổi.
  - `test_qc_blocks_edits`: `Session(source=..., ann=ann_có_mắt)` với `qc=True` → `add_pin`, `toggle_flag`, `drag_points`, `pin_eye` đều ném `ValueError` có "chế độ QC", không đổi `pins`/`flags`.
  - `test_clear_then_label_then_export_has_only_new_eyes`: `clear_old_eyes()` trả `EyeLabels` không rỗng, `qc` False; ghim 2 frame; `export` → chỉ có track mắt mới, box còn.
  - `test_restore_old_eyes_only_before_new_pins`: ngay sau `clear_old_eyes` → `restore_old_eyes()` True và `qc` True; sau khi đã ghim → False và giữ nguyên ghim.
- [ ] **Bước 2:** Đỏ. **Bước 3:** Viết. **Bước 4:** Xanh; cả bộ (mở thư mục với `--xml` không đặt `qc`, nên các test cũ không đổi).

---

### Task 5: Gửi lên CVAT (`cvatsync`)

**Files:** Create `eyepin/cvatsync.py`; Modify `eyepin/session.py` (khai báo mặc định `self.cvat = None`, `self.base_format = None`, `self.display_format = None` trong `__init__`; `state()`/`load_state()` thêm trường tuỳ chọn `"cvat": {"job", "updated"}`, file phiên cũ không có trường này vẫn mở được); Test `tests/test_cvatsync.py`.

**Facts đã thử trên CVAT thật (`design/cvat-api-notes.md`, bắt buộc đọc):** "CVAT for images" trải track thành shape ở mọi frame; "CVAT for video" đổi shape thành track một frame. Vì vậy nhãn mắt CVAT đang có phải đếm từ JSON `client.annotations(job)` (đúng loại), không đếm từ XML nền. Import không gửi `filename`.

**Interfaces:**
- Consumes: `CvatClient` (`job`, `annotations`, `labels`, `export_xml`, `import_xml`), `cvatsource.base_format(annotations_json, eye_label_ids)`, `cvatxml.parse_bytes(data, frame_numbers)`, `qc.EyeLabels`, `qc.without_eyes`, `Session.export(path)` (đã đổi ngược chỉ số về số frame job qua `ann.frame_numbers`), `session.source.frame_numbers`, `session.cvat`.
- Produces:
```python
@dataclass
class SendPlan:
    changed_on_server: bool          # job.updated_date khác session.cvat["updated"]
    replaced: EyeLabels              # nhãn mắt đang có trên CVAT (đếm từ JSON; frame ghi theo số frame của job) sẽ bị thay
    mixed_types: bool                # job có cả shape lẫn track không phải mắt: shape sẽ thành track một frame (nền = video)
    keyframes: int                   # số keyframe EyePin sẽ gửi
    base_format: str
    def needs_warning(self) -> bool  # changed_on_server or not replaced.empty() or mixed_types
    def text(self) -> str            # luôn có "thay toàn bộ nhãn của job"; thêm replaced.message() ("sẽ xoá ..."), cảnh báo shape thành track một frame, cảnh báo job đã bị sửa trên CVAT
@dataclass
class SendResult:
    ok: bool; message: str; mismatches: list[str]; snapshot: bytes | None
def prepare(session, client) -> SendPlan
    # đọc job (updated_date), annotations JSON, labels; base_format(...); xuất nền mới nhất theo base_format, parse_bytes(.., frame_numbers), ann = qc.without_eyes(...); giữ ann và bản XML nền gốc (bytes) trong plan (trường riêng, không in ra)
def send(session, client, plan: SendPlan) -> SendResult
    # tạm đặt session.ann = nền (đã without_eyes), session.export(file tạm .xml: toạ độ, được phép), đọc bytes, trả session.ann về như cũ (try/finally), client.import_xml(job, bytes);
    # rồi xuất lại "CVAT for video 1.1" và đối chiếu V1–V3 như tests/verify_vs_cvat.py (vị trí trong 2 px + làm tròn, cờ Occluded/Outside, keyframe) trên các frame không xoá;
    # thành công thì cập nhật session.cvat["updated"] bằng job.updated_date mới; snapshot = bản XML nền gốc (bytes) chụp trước khi gửi
def restore(client, job_id: int, snapshot: bytes) -> None   # client.import_xml(job_id, snapshot)
```
Giới hạn đã chọn: bản chụp là bản xuất nền trước khi gửi; nhãn mắt cũ chỉ được khôi phục đúng loại khi định dạng nền cũng là định dạng hiện nhãn mắt (người dùng đã xác nhận xoá nhãn mắt cũ khi gửi). Ghi giới hạn này vào docstring của `restore`.

- [ ] **Bước 1: Test** (FakeCvat với `export_xml_by_format`, `annotations_json`; ảnh tổng hợp):
  - `test_send_roundtrip_ok`: job trống → ghim 3 frame bằng `Session.pin_eye` → `prepare`, `send` → `ok`; XML server giữ 2 track mắt đúng keyframe; nhãn không phải mắt của nền còn nguyên.
  - `test_replaced_counts_come_from_json_not_from_the_images_export`: server có 1 track mắt id 37 (frame 5–120) và 30 shape mắt trong `annotations_json`, trong khi XML xuất "images" có 210 shape mắt → `plan.replaced.message()` ghi "1 track mắt #37 ..." và "30 shape mắt" (không phải 210).
  - `test_mixed_non_eye_types_warn`: JSON có box không phải mắt dạng shape và polygon dạng track → `plan.mixed_types` và `base_format == "CVAT for video 1.1"`, `plan.text()` nói shape sẽ thành track một frame.
  - `test_changed_on_server_is_detected_and_saved_in_session`: đổi `updated_date` trên server sau khi mở → `plan.changed_on_server`; sau `send` thành công `session.state()["cvat"]["updated"]` là giá trị mới; `load_state` của file phiên cũ (không có `cvat`) vẫn chạy.
  - `test_mismatch_is_reported_and_restore_puts_the_snapshot_back`: server giả dời một điểm khi import (`shift_on_import`) → `ok is False`, `mismatches` nêu frame và điểm; `restore` đưa XML server về đúng snapshot.
  - `test_lost_connection_while_waiting_for_import`: ngắt khi hỏi trạng thái (`drop_on_poll`) → `ok is False`, `message` có "chưa rõ"; đã đọc lại `updated_date` và ghi vào `message`.
  - `test_deleted_frames_are_skipped_in_comparison`: job có `deleted_frames=[3]`, XML xuất không có frame 3 → không báo lệch giả.
  - `test_job_start_frame_10_sends_job_frame_numbers`: job `start_frame=10`; XML import chứa frame 12.. (số frame của job), không phải chỉ số.
- [ ] **Bước 2:** Đỏ. **Bước 3:** Viết. **Bước 4:** Xanh; cả bộ.

---

### Task 6: Giao diện

**Files:** Modify `eyepin/gui.py`, `eyepin/gui_frames.py` (tắt xoá frame khi nguồn là CVAT), `eyepin/__main__.py` (`gui --cvat URL --job ID`), `eyepin/shortcuts.py` (ba hành động mới không phím mặc định: `open_cvat`, `send_cvat`, `qc_clear`); Test `tests/test_gui.py` (lớp mới dùng FakeCvat).

**Interfaces:**
- Consumes: `CvatClient`, `open_job`, `prepare`, `send`, `restore`, `Session.qc`, `clear_old_eyes`, `restore_old_eyes`.
- Produces: `App.open_cvat()` (hộp: địa chỉ, tên, mật khẩu, Đăng nhập, danh sách task, danh sách job, Mở); `App.load_cvat(client, job_id)`; `App.send_cvat()`; `App.qc_clear()`; `App._run_bg(fn, done)` (chạy `fn` trên luồng nền, `done` qua `root.after`; trong lúc chạy chặn sửa nhãn, hiện "Đang …").
- Sau khi gửi: `SendResult.ok` → `notice` có số keyframe và "đối chiếu khớp"; không `ok` → hộp báo `message` và `mismatches`, có nút "Khôi phục job về bản trước khi gửi" (gọi `restore` với `snapshot`) và "Lưu bản chụp…" (ghi XML ra file người dùng chọn).
- Mở job đã có nhãn mắt mà người dùng chọn khôi phục phiên đã lưu cho job đó → gọi `clear_old_eyes()` trước khi `load_state` (spec mục 8).
- Hộp "Mở từ CVAT…" nhớ `{url, user}` vào `settings["cvat"]` sau khi đăng nhập được.
- Chế độ QC: khi `s.qc`: tiêu đề và dòng trạng thái có "QC"; tự chạy Quét và mở tab Issues; mọi lệnh sửa hiện `QC_MSG` (bắt `ValueError` từ `Session`, cộng chặn sớm ở `start_draw`, `start_pin`, `on_press` để không vào chế độ vẽ); nút "Gửi lên CVAT" tắt; nút "Xoá nhãn mắt cũ và gán lại" hiện (hộp xác nhận có `EyeLabels.message()`).

- [ ] **Bước 1: Test:**
  - `test_open_empty_job_is_normal_labeling` (FakeCvat job trống → `app.s.qc is False`, tiêu đề có "CVAT job #7").
  - `test_open_job_with_eyes_goes_to_qc_and_scans` (job có track mắt → `app.s.qc`, `issues_var` đã cập nhật, trạng thái có "QC").
  - `test_qc_blocks_every_edit_path`: ở QC, gọi lần lượt `start_draw`, `begin_draw`+bấm 4 điểm, kéo một điểm (`on_press/on_motion/on_release`), `toggle_flag`, `toggle_pin_here`, `rotate_eye`, `handlers["paste"]` → `pins` và `flags` không đổi, `notice` có "chế độ QC", không có ngoại lệ lọt ra.
  - `test_qc_clear_then_label_then_send` (giả `askyesno` trả True: `qc_clear` → `qc` False → vẽ một mắt, Apply → `send_cvat` → `notice` có số keyframe và "đối chiếu").
  - `test_send_asks_first_and_warns` (giả `askyesno` ghi chữ và trả False: không gửi; chữ có "thay toàn bộ nhãn của job").
  - `test_delete_frame_is_disabled_for_cvat`; `test_session_file_is_keyed_by_job`; `test_login_needed_reopens_login` (401 khi gửi → hộp đăng nhập mở lại, ghim còn nguyên).
- [ ] **Bước 2:** Đỏ. **Bước 3:** Viết. **Bước 4:** Xanh; cả bộ; `python -m eyepin gui <case01> --selftest` vẫn OK.

**Cập nhật sau Task 0–5 (bắt buộc đọc, đè lên chỗ khác trong task này):**
- Frame và nhãn: `Session.frames_dir` là `None` với nguồn CVAT; các chỗ còn đọc nó phải xử lý: `App.load`/`run()` (chỉ dựng Session từ thư mục), hộp Thông tin (`gui.py` ~625), nạp lại file nhãn (`gui.py` ~958), `gui_frames.py` ~48, `gui_objects.py` ~183. Dùng `session.title`/`session.source_key`.
- `open_job` đặt `session.cvat`, `session.base_format`, `session.display_format`, `session.qc`. Mở job: nếu `session.qc` thì tự `run_scan()`, mở tab Issues, tiêu đề và trạng thái có "QC".
- Khôi phục phiên đã lưu cho một job đang ở QC (phiên có ghim): gọi `session.clear_old_eyes()` trước `load_state` (spec mục 8), kèm thông báo.
- Hộp xác nhận gửi: dùng `SendPlan.text()`; thêm một dòng cảnh báo về tag chú thích khi nền là video (tag có thể mất, chưa kiểm). Nếu `prepare`/`send` ném `LoginNeeded` thì mở lại hộp đăng nhập, không mất ghim.
- Sau `restore(...)` thành công phải gọi `cvatsync.mark_synced(session, client)` (nếu không lần `prepare` kế báo giả là job bị sửa trên server).
- Kết quả `send`: `ok` → `notice` có số keyframe và "đối chiếu khớp"; không ok → hộp báo `message` và `mismatches`, có nút "Khôi phục job về bản trước khi gửi" (gọi `restore` với `snapshot`, rồi `mark_synced`) và "Lưu bản chụp…" (ghi XML ra file người dùng chọn). Ghi chú giới hạn khôi phục nhãn mắt cũ trong hộp.
- Ở chế độ CVAT tắt lệnh xoá/khôi phục frame (`Session.delete_frame`/`restore_frame` vẫn thêm được frame xoá cục bộ; frame xoá từ CVAT chỉ đọc).
- Đăng nhập: nhớ `{url, user}` vào `settings["cvat"]` sau khi đăng nhập được; mật khẩu và khoá chỉ trong RAM. Việc mạng chạy luồng nền (`App._run_bg`); trong lúc chạy chặn sửa nhãn.
- Server giả để test: `tests/fake_cvat.py` (đọc docstring).

---

### Task 7: Kiểm trên CVAT local thật, tài liệu

**Files:** Create `tests/cvat_direct_check.py` (chạy tay, cần job trống); Modify `TASKS.md`, `CLAUDE.md`, `HUONG_DAN.md`, `design/shortcuts.md` (sinh lại).

- [ ] **Bước 1:** Script: đăng nhập; `open_job` job trống (phải là gán nhãn bình thường); ghim 3 frame bằng `pin_eye`; `prepare` + `send`; in kết quả đối chiếu; mở lại job (phải vào QC, Quét không có lỗi đỏ); `clear_old_eyes` + ghim lại + gửi; cuối cùng xoá sạch nhãn thử.
- [ ] **Bước 2:** Chạy trên job trống của CVAT local; đạt khi in `ĐẠT` cho: gửi, đối chiếu, mở lại vào QC, xoá và gửi lại.
- [ ] **Bước 3:** Tài liệu: `HUONG_DAN.md` mục "Làm thẳng với CVAT local" (mở, QC, xoá và gán lại, gửi); `CLAUDE.md` thêm `frames.py`, `cvatapi.py`, `cvatsource.py`, `qc.py`, `cvatsync.py`; `TASKS.md` tick, thêm "áp dụng chế độ QC cho mở thư mục với `--xml`"; ghi việc `/archify` (luồng dữ liệu đổi) để làm khi đóng băng mã.

## Chạy song song
Không có git, nên hai việc không được sửa cùng một file trong cùng một đợt.
- **Đợt 1:** Task 0 (chỉ đọc/ghi CVAT local và `design/cvat-api-notes.md`) ∥ Task 1 (`frames.py`, `session.py` phần ảnh, `headturn.py`, `gui.py` `state_path`) ∥ Task 2 (`cvatapi.py`, `tests/fake_cvat.py`).
- **Đợt 2:** Task 3 (`cvatsource.py`, `cvatxml.py`) ∥ Task 4 (`qc.py`, `session.py` phần QC). Task 3 cần kết luận của Task 0.
- **Đợt 3:** Task 5 → Task 6 → Task 7.
