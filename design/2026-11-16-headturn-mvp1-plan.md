# Kế hoạch xây MVP 1: phát hiện đoạn quay đầu

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Mục tiêu:** EyePin tự báo "người lái quay đầu từ frame nào tới frame nào" trên dải thời gian, tab Issues và dòng lệnh `turns`.

**Kiến trúc:** Module mới `eyepin/headturn.py` chỉ nhận toạ độ và độ khớp (không đọc ảnh), nên kiểm được bằng dãy số dựng sẵn. `Session.recompute()` gọi nó sau mỗi lần tính lại nhãn và giữ kết quả ở `Session.turns` (mỗi người một báo cáo). `render.py`, `gui_objects.py` và `__main__.py` chỉ đọc `Session.turns`.

**Công nghệ:** Python 3.12, `unittest`, OpenCV, Tkinter. Không thêm thư viện.

**Spec:** `design/2026-11-15-headturn-mvp-design.md` (bản 2), mục 3.1, 8 "MVP 1", 9, 10, 11. Mục 15 (đo model) **không** thuộc kế hoạch này.

## Ràng buộc chung

- Không dùng model học máy. Chỉ toạ độ, độ khớp của bộ bám và hình học.
- Không đổi `Session.labels`, file xuất, hay quy tắc "ghim frame N không làm đổi frame trước N".
- Ảnh chỉ đọc vào RAM. Không đặt ảnh vào thư mục dự án.
- 139 test hiện có phải còn qua: `python -m unittest discover -s tests -v`.
- Dự án không có git: không có bước commit. Mỗi task kết thúc bằng chạy cả bộ test.
- Chữ hiện cho người dùng viết tiếng Việt. Màu theo `eyepin/theme.py` (cam #FF6600 = BGR `(0, 102, 255)`).
- Hằng số lấy nguyên từ spec: vào đoạn `0.86`, ra đoạn `0.90`, dài tối thiểu `5` frame, độ khớp tin được `0.85`, bề rộng xác nhận `0.75`, tối thiểu `3` frame ghim đủ hai mắt, mức co `< 0.20` nhẹ / `< 0.30` vừa / còn lại mạnh.
- Mọi con số in ra kèm số frame ghim, khoảng cách ghim trung vị và nguồn điểm ghim (spec mục 5).
- Hạn: demo chiều 2026-11-16. Thứ tự cắt khi thiếu giờ: bỏ Task 4 (giao diện) trước; Task 3 phần lệnh `turns` không cắt.

## Trọng tâm rà soát

Các tình huống spec có hàm ý nhưng dễ bị bỏ sót; mỗi dòng đã có test ở task ghi trong ngoặc.

1. Bộ bám mất mắt giữa đoạn quay (độ khớp < 0,85, khoảng cách hai mắt vô nghĩa): không được tạo hay kết thúc đoạn, không được làm mức co thành 99% (Task 1, test 4 và 5).
2. Người dùng mới ghim một mắt, hoặc chưa đủ 3 frame ghim hai mắt: phải báo "chưa đủ ghim", không báo cả clip là quay đầu (Task 1, test 8).
3. Hai mắt trùng tâm hoặc mốc bằng 0: không chia cho 0 (Task 1, test 10).
4. Job nhiều người có một người chưa ghim gì: `Session.turns` vẫn đủ một phần tử mỗi người, giao diện không lỗi (Task 2, test 3).
5. File `--pins` sai (frame ngoài phạm vi, mắt thiếu điểm): báo lỗi tiếng Việt, không in traceback (Task 2, test 4; Task 3, test 2).
6. Mở cửa sổ bằng `--pins` rồi tự lưu: không được ghi đè file phiên 3 ghim đang có của case 01 (Task 3, test 3).
7. Hoàn tác / làm lại / khôi phục phiên: `Session.turns` phải theo kịp (Task 2, test 2).

---

### Task 1: Bộ phát hiện thuần toạ độ `eyepin/headturn.py`

**Files:**
- Create: `eyepin/headturn.py`
- Test: `tests/test_headturn.py`

**Interfaces:**
- Consumes: `eyepin.geometry.EYES` (`EyeSpec.ids`, `.first`, `.last`), `eyepin.geometry.Point`.
- Produces:

```python
ENTER, LEAVE, MIN_LEN, TRUST, CONFIRM_WIDTH, MIN_PINS = 0.86, 0.90, 5, 0.85, 0.75, 3

@dataclass(frozen=True)
class Turn:
    first: int; last: int
    peak: int | None        # frame co mạnh nhất; None nếu đoạn chỉ gồm frame một mắt
    shrink: float | None    # 1 - min(d/mốc) trên frame tin được có đủ hai mắt; None như trên
    level: str              # "nhẹ" | "vừa" | "mạnh" | "một mắt"
    far_eye: str | None     # "mattrai" | "matphai" | None
    confirmed: int          # số frame ghim trong đoạn có bề rộng mắt hẹp / mắt rộng <= 0.75
    unsure: int             # frame trong đoạn không tin được hoặc không còn mắt nào
    one_eye: int            # frame trong đoạn chỉ còn một mắt
    need_pin: int           # frame "cần ghim" trong [first, last]
    def message(self, index: int) -> str: ...

@dataclass(frozen=True)
class TurnReport:
    status: str             # "ok" | "few_pins"
    baseline: float | None  # mốc (px); None khi few_pins
    turns: tuple[Turn, ...]
    untrusted: int          # số frame có nhãn nhưng không tin được, cả clip
    both_pins: int          # số frame ghim đủ hai mắt

def level_of(shrink: float | None) -> str
def detect(n_frames: int, points: dict[int, dict[int, Point]], scores: dict[int, dict[str, float]],
           keys: dict[str, set[int]], need_pin=(), skip=()) -> TurnReport
```

`points[f]` chỉ chứa điểm không Outside; mắt vắng mặt thì không có id nào của nó. `keys[label]` là tập frame ghim của mắt đó. `skip` là frame đã xoá.

- [ ] **Bước 0: Sao lưu** (làm một lần trước khi sửa mã)

```powershell
Copy-Item eyepin, tests -Destination ..\eye_label_tool_backup_20261116 -Recurse
```
Đạt khi `..\eye_label_tool_backup_20261116\eyepin\session.py` tồn tại.

- [ ] **Bước 1: Viết test (chưa có mã nên phải đỏ)**

Hàm dựng dữ liệu trong `tests/test_headturn.py`: `eye(spec, cx, width)` trả 8 điểm của một mắt (hai khoé ở `cx ∓ width/2`, các điểm còn lại rải đều giữa hai khoé, lệch y ±5); `clip(ratios, far=1.0, pins=..., low=())` trả `(n, points, scores, keys)` với mattrai tâm `(100, 100)` rộng `60·far` ở frame có `ratio < 0.86`, matphai tâm `(100 + 150·ratio, 100)` rộng 60, độ khớp `0.95` (frame trong `low`: `0.5`), frame ghim có độ khớp `1.0`.

| # | Tên test | Dựng | Khẳng định |
|---|---|---|---|
| 1 | `test_straight_clip_has_no_turn` | 60 frame, ratio 1,0, ghim 0/20/40 | `status == "ok"`, `turns == ()`, `baseline ≈ 150` |
| 2 | `test_shrink_for_thirty_frames` | ratio 0,68 ở frame 20–49 (không dùng 0,70 vì mức co rơi đúng ranh giới 0,30 và lệch do làm tròn), `far=0.5`, ghim mỗi 10 frame | đúng 1 đoạn: `first=20, last=49`, `shrink ≈ 0.32` (±0,005), `level == "mạnh"`, `confirmed == 3`, `far_eye == "mattrai"`, `unsure == 0`, `peak` trong 20–49 |
| 3 | `test_dip_shorter_than_five_frames_is_dropped` | ratio 0,68 ở frame 20–23 | `turns == ()` |
| 4 | `test_untrusted_frames_hold_the_turn_and_do_not_set_shrink` | như test 2, frame 31–39 có ratio 0,01 và nằm trong `low` | 1 đoạn 20–49, `unsure == 9`, `shrink ≈ 0.32` |
| 5 | `test_untrusted_frames_never_start_a_turn` | clip thẳng, frame 31–39 ratio 0,5 và trong `low` | `turns == ()`, `untrusted == 9` |
| 6 | `test_one_eye_frames_count_as_turning` | clip thẳng, frame 20–39 bỏ hết điểm mattrai | 1 đoạn 20–39, `one_eye == 20`, `shrink is None`, `level == "một mắt"`, `far_eye == "mattrai"` |
| 7 | `test_ratio_above_one_is_not_a_turn` | ratio dao động 0,95–1,05 | `turns == ()` |
| 8 | `test_fewer_than_three_two_eye_pins` | (a) ghim 0/20; (b) mattrai ghim 0/10/20/30, matphai chỉ ghim 0 | cả hai: `status == "few_pins"`, `turns == ()`, `baseline is None` |
| 9 | `test_levels` | `level_of` | `0.19 → "nhẹ"`, `0.20 → "vừa"`, `0.299 → "vừa"`, `0.30 → "mạnh"`, `None → "một mắt"` |
| 10 | `test_zero_baseline_does_not_divide` | mọi frame hai mắt trùng tâm | `status == "few_pins"`, không ném lỗi |
| 11 | `test_frames_without_any_eye_hold_state` | như test 2, frame 30–34 không có điểm nào, không ghim ở 30 | 1 đoạn 20–49, `unsure == 5` |
| 12 | `test_turn_open_at_clip_end` | 60 frame, ratio 0,68 từ frame 40 tới hết | 1 đoạn `first=40, last=59` |
| 13 | `test_deleted_frames_are_skipped` | như test 2, `skip={30, 31}` (không ghim ở 30) | 1 đoạn 20–49, `unsure == 0` |
| 14 | `test_unconfirmed_turn_says_so` | như test 2 nhưng `far=1.0` | `confirmed == 0`, `far_eye is None`, `"chưa xác nhận (có thể do tiến/lùi)" in turn.message(1)` |
| 15 | `test_message_format` | đoạn của test 2 kèm `need_pin=[25, 26]` | `message(1)` bắt đầu bằng `"Quay đầu  #1  frame 20–49  co 32% (mạnh)  mắt xa: mattrai  xác nhận tại 3 ghim"` và chứa `"2 frame cần ghim"` |

- [ ] **Bước 2: Chạy, xác nhận đỏ**

Run: `python -m unittest tests.test_headturn -v`
Expected: lỗi `ModuleNotFoundError: No module named 'eyepin.headturn'`.

- [ ] **Bước 3: Viết `eyepin/headturn.py`**

Các quyết định mà chữ ký và test chưa cố định:

- Tâm một mắt = trung bình các điểm của mắt đó có trong `points[f]`. Mắt "có mặt" khi còn ít nhất một điểm.
- Mốc: sắp tăng dần `d` tại các frame thuộc cả `keys["mattrai"]` lẫn `keys["matphai"]` và có đủ hai mắt; lấy phần tử thứ `min(n - 1, int(0.9 * n))`. Ít hơn `MIN_PINS` frame như vậy, hoặc mốc `<= 0`: trả `TurnReport("few_pins", None, (), 0, n)`.
- Frame tin được: có đủ hai mắt, và với từng mắt thì `f in keys[label]` hoặc `scores[f][label] >= TRUST`.
- Máy trạng thái, duyệt `f` tăng dần qua `range(n_frames)` trừ `skip` (đây là phần phải khớp với số đo trong spec mục 2, nên ghi rõ):

```python
for f in frames:
    eyes = present(f)                                  # tập mắt còn điểm ở frame f
    if len(eyes) == 1:                                 # một mắt: coi là đang quay
        if not inside: open_turn(f)
        cur.one_eye += 1; cur.missing[the_absent_eye] += 1
    elif len(eyes) == 2 and trusted(f):
        r = d(f) / baseline
        if not inside and r <= ENTER: open_turn(f); cur.low, cur.peak = r, f
        elif inside and r >= LEAVE: close_turn(last=f - 1)        # giữ nếu f - first >= MIN_LEN
        elif inside and r < cur.low: cur.low, cur.peak = r, f     # cur.low khởi đầu là +inf
    elif inside:                                       # không tin được, hoặc không còn mắt nào
        cur.unsure += 1
if inside: close_turn(last=frames[-1])                 # giữ nếu last - first + 1 >= MIN_LEN
```

- `untrusted` của báo cáo: số frame có đủ hai mắt nhưng không tin được, đếm trên cả clip. `both_pins`: số frame thuộc cả hai tập `keys` và còn đủ hai mắt (chính là các frame dùng để tính mốc).
- Xác nhận: với mỗi frame ghim đủ hai mắt nằm trong `[first, last]` mà cả bốn khoé (`spec.first`, `spec.last` của hai mắt) đều có trong `points[f]`, tính bề rộng hai mắt; `min/max <= CONFIRM_WIDTH` thì `confirmed += 1` và mắt hẹp được một phiếu. `far_eye` = mắt nhiều phiếu nhất; không có phiếu nào thì lấy mắt vắng mặt nhiều nhất trong các frame một mắt; vẫn không có thì `None`.
- `message(index)`: các phần nối bằng hai dấu cách, theo thứ tự: `Quay đầu`, `#<index>`, `frame <first>–<last>` (dấu gạch `–`), `co <N>% (<mức>)` hoặc `mất một mắt` khi `shrink is None`, `mắt xa: <nhãn>` (bỏ khi `None`), `xác nhận tại <n> ghim` hoặc `chưa xác nhận (có thể do tiến/lùi)` khi `confirmed == 0`, rồi chỉ khi lớn hơn 0: `<n> frame không chắc`, `<n> frame một mắt`, `<n> frame cần ghim`.

- [ ] **Bước 4: Chạy, xác nhận xanh**

Run: `python -m unittest tests.test_headturn -v`
Expected: 15 test qua.

- [ ] **Bước 5: Chạy cả bộ**

Run: `python -m unittest discover -s tests`
Expected: `OK`, 154 test (139 + 15).

---

### Task 2: Nối vào `Session`, nạp điểm ghim từ JSON, kiểm trên dữ liệu thật

**Files:**
- Modify: `eyepin/headturn.py` (thêm `for_session`)
- Modify: `eyepin/session.py:82` (thuộc tính `turns`), `eyepin/session.py:554-562` (`recompute`), thêm `load_pins`
- Modify: `eyepin/__main__.py:63-69` (`_preview` dùng `load_pins`)
- Test: `tests/test_headturn.py` (thêm lớp `SessionTurnTests`, `RealDataTests`)

**Interfaces:**
- Consumes: `detect`, `TurnReport` của Task 1; `Session.layer_ctx(i)`, `Session.eye_keyframes(label)`, `Session.flags_at(f)`, `Session.labels`, `Session.need_pin`, `Session.deleted`.
- Produces:

```python
# eyepin/headturn.py
def for_session(session) -> list[TurnReport]      # một phần tử mỗi Layer, cùng thứ tự session.layers

# eyepin/session.py
Session.turns: list[TurnReport]                    # luôn dài bằng len(session.layers) sau recompute()
def load_pins(self, data: dict) -> int             # trả số frame đã ghim; ném ValueError tiếng Việt khi dữ liệu sai
```

Định dạng `data` (giống file `spike/out/pins_case01_ai.json` đã `json.load`): `{"<frame>": {"<id điểm>": [x, y], ...}, ...}`; khoá bắt đầu bằng `_` bị bỏ qua; ở mỗi frame, mắt nào có đủ 4 điểm ghim (`spec.pins`) thì được ghim bằng `add_pin`, mắt không có điểm nào thì bỏ qua.

- [ ] **Bước 1: Viết test**

`SessionTurnTests` dùng ảnh tổng hợp như `tests/test_session.py` (`setUpClass` ghi `T.render(t)` cho `t in range(T.N)`, hàm `pin_both`).

| # | Tên test | Khẳng định |
|---|---|---|
| 1 | `test_turns_follow_recompute` | phiên mới: `len(s.turns) == 1` và `s.turns[0].status == "few_pins"`; sau khi ghim hai mắt ở frame 0, 20, 40: `status == "ok"`, `both_pins == 3`, `turns == ()` (cảnh tổng hợp không quay đầu) |
| 2 | `test_turns_follow_undo` | sau 3 lần ghim như trên rồi `s.undo()`: `s.turns[0].both_pins == 2` và `status == "few_pins"`; `s.redo()` trả lại `"ok"` |
| 3 | `test_one_report_per_layer` | ghim 3 frame ở người 1, `s.add_layer()` rồi `s.recompute()`: `len(s.turns) == 2`, `s.turns[1].status == "few_pins"` |
| 4 | `test_load_pins` | `load_pins` với 3 frame hợp lệ trả `3` và `sorted(s.pins) == [0, 20, 40]`; khoá `"_note"` bị bỏ qua; frame `"999"` ném `ValueError` có chữ `"ngoài phạm vi"`; mắt chỉ có 3 trong 4 điểm ghim ném `ValueError` có chữ `"thiếu điểm"`; khoá `"abc"` ném `ValueError` |
| 5 | `test_outside_points_are_left_out` | ghim hai mắt ở frame 0, 10, 20, 40 (frame 20 mất mattrai nên cần 3 frame ghim khác còn đủ hai mắt), `s.toggle_flag(20, i, "outside")` cho cả 8 điểm của mattrai: `for_session(s)[0]` có `both_pins == 3` và một đoạn bắt đầu ở frame 20 với `one_eye > 0` |

`RealDataTests` (bỏ qua bằng `unittest.skipUnless` khi thiếu thư mục ảnh hoặc file ghim):

| # | Tên test | Dựng | Khẳng định |
|---|---|---|---|
| 6 | `test_case01_two_turns` | `C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che`, ghim từ `spike/out/pins_case01_ai.json`, chỉ giữ frame chia hết cho 10 và frame 209 | đúng 2 đoạn; đoạn 1: `first <= 30`, `last >= 65`, `abs(first - 21) <= 10`, `abs(last - 79) <= 10`; đoạn 2: `first <= 105`, `last >= 145`, `abs(first - 100) <= 10`, `abs(last - 160) <= 10`; cả hai `far_eye == "mattrai"` và `confirmed >= 1` |
| 7 | `test_frontal_clip_has_no_turn` | `C:\Users\minhf\Downloads\dms_build\physdrive_seg`, ghim từ `spike/out/pins_ai.json` | `status == "ok"`, `turns == ()` |

- [ ] **Bước 2: Chạy, xác nhận đỏ**

Run: `python -m unittest tests.test_headturn -v`
Expected: các test mới lỗi `AttributeError` (`turns`, `load_pins`, `for_session`).

- [ ] **Bước 3: Viết mã**

- `for_session(session)`: với từng `i`, trong `with session.layer_ctx(i)`: `keys = {l: set(session.eye_keyframes(l)) for l in EYES}`; `points[f]` = `session.labels[f].points` bỏ các id có cờ `"outside"` trong `session.flags_at(f)`; `scores[f] = session.labels[f].scores`; gọi `detect(session.n_frames, points, scores, keys, session.need_pin, session.deleted)`.
- `Session.__init__`: `self.turns = []` cạnh `self.findings`. `Session.recompute()`: sau khối `try/finally`, gán `self.turns = headturn.for_session(self)` (import `headturn` ở đầu file; `headturn` không được import `session`).
- `Session.load_pins(data)`: kiểm toàn bộ dữ liệu trước rồi mới ghim (sai thì không ghim gì). Thông báo lỗi: `f"frame {k} ngoài phạm vi 0–{self.n_frames - 1}"`, `f"frame {k}: mắt {label} thiếu điểm ghim (cần {list(spec.pins)})"`, `f"khoá frame không phải số: {k!r}"`.
- `__main__._preview`: thay vòng lặp ở dòng 64–69 bằng `s.load_pins(json.load(open(a.pins, encoding="utf-8")))`.

- [ ] **Bước 4: Chạy, xác nhận xanh**

Run: `python -m unittest tests.test_headturn -v`
Expected: 22 test qua (hoặc 20 qua, 2 bỏ qua nếu máy thiếu thư mục ảnh). Trên máy này thư mục ảnh có sẵn nên test 6 và 7 phải **chạy và qua**; nếu test 6 trượt vì ranh giới, in `s.turns[0]` ra và dừng lại báo người dùng, không nới ngưỡng.

- [ ] **Bước 5: Chạy cả bộ**

Run: `python -m unittest discover -s tests`
Expected: `OK`, 161 test.

---

### Task 3: Dòng lệnh `turns` và mở cửa sổ với `--pins`

**Files:**
- Modify: `eyepin/headturn.py` (thêm `format_report`)
- Modify: `eyepin/__main__.py` (lệnh con `turns`; tham số `--pins` cho `gui`)
- Modify: `eyepin/gui.py:837-847` (`load`), `eyepin/gui.py:449-461` (`save_work`), `eyepin/gui.py:1671-1675` (`run`)
- Test: `tests/test_headturn.py` (lớp `CliTests`), `tests/test_gui.py` (1 test)

**Interfaces:**
- Consumes: `Session.load_pins`, `Session.turns`, `Turn.message` (Task 1, 2).
- Produces:

```python
# eyepin/headturn.py
def format_report(session, source: str) -> str     # văn bản in ra của lệnh turns; source = tên file điểm ghim

# eyepin/gui.py
App.load(self, frames_dir: str, xml: str | None, pins: dict | None = None)
App.scratch: bool                                   # True khi mở bằng --pins: không khôi phục, không ghi file phiên
def run(frames_dir, xml, selftest=False, pins: str | None = None) -> int
```

Lệnh: `python -m eyepin turns <thư_mục_ảnh> --pins <file.json>` (mã thoát 0; `--pins` bắt buộc) và `python -m eyepin gui <thư_mục_ảnh> --pins <file.json>`.

Văn bản của `format_report` (mỗi người một khối; dòng đầu và dòng cuối in một lần):

```
<tên thư mục ảnh>: 210 frame, 22 frame ghim, khoảng cách ghim trung vị 10 frame (nguồn điểm ghim: pins_case01_ai.json)
Người 1 (đối tượng #1, #10): mốc khoảng cách hai mắt 152.3 px, 59/210 frame không tin được
  Quay đầu  #1  frame 21–79  co 28% (vừa)  mắt xa: mattrai  xác nhận tại 6 ghim  13 frame không chắc
  Quay đầu  #2  frame 100–160  ...
Giới hạn: ranh giới chỉ chính xác khi các frame ghim trong đoạn quay cách nhau không quá khoảng 20 frame; không phát hiện cúi/ngửa đầu.
```

Người có `status == "few_pins"`: `  Chưa đủ ghim để phát hiện (cần ít nhất 3 frame ghim đủ hai mắt, đang có <both_pins>).` Người có `status == "ok"` mà không có đoạn: `  Không có đoạn quay đầu.` Số frame ghim và khoảng cách trung vị tính trên hợp các frame ghim của mọi người.

- [ ] **Bước 1: Viết test**

| # | Tên test | Khẳng định |
|---|---|---|
| 1 | `CliTests.test_turns_prints_report` | ảnh tổng hợp + file ghim tạm (3 frame): `main(["turns", dir, "--pins", path])` trả `0`; stdout (bắt bằng `contextlib.redirect_stdout`) chứa `"3 frame ghim"`, `"nguồn điểm ghim:"`, `"Không có đoạn quay đầu."`, `"Giới hạn:"` |
| 2 | `CliTests.test_turns_reports_bad_pins_file` | file ghim có frame `"999"`: `main([...])` trả `2`, stdout chứa `"ngoài phạm vi"`, không ném ngoại lệ; file không tồn tại: trả `2` |
| 3 | `GuiTests.test_pins_mode_never_touches_the_saved_session` (trong `tests/test_gui.py`) | `app, seq = self.make_app()`; ghim frame 0 bằng `self.click_pins`, `app.save_work()`, đọc nội dung `app.state_path()`; tạo `app2 = App(self.root)` với `app2.ask_restore` ném `AssertionError`, gọi `app2.load(self.dir, None, pins=<3 frame>)`: `app2.scratch is True`, `sorted(app2.s.pins) == [0, 20, 40]`; `app2.save_work()` và `app2.save_work(auto=True)` không đổi nội dung file phiên; `app2.notice` chứa `"--pins"` |

- [ ] **Bước 2: Chạy, xác nhận đỏ**

Run: `python -m unittest tests.test_headturn.CliTests tests.test_gui.GuiTests.test_pins_mode_never_touches_the_saved_session -v`
Expected: test 1, 2 lỗi vì `argparse` không biết lệnh `turns` (`SystemExit`); test 3 lỗi `TypeError` (tham số `pins`).

- [ ] **Bước 3: Viết mã**

- `__main__.main`: thêm lệnh con `turns` (`frames_dir`, `--pins` bắt buộc) và `--pins` cho `gui`. Nhánh `turns`: mở `Session`, `load_pins`, in `format_report(s, os.path.basename(a.pins))`, trả `0`; bắt `(OSError, ValueError)` thì in `f"Lỗi: {err}"` và trả `2`. Nhánh `gui`: truyền `pins=a.pins` cho `run`.
- `App.__init__`: `self.scratch = False`. `App.load(..., pins=None)`: đặt `self.scratch = pins is not None`; khi có `pins` thì gọi `self.s.load_pins(pins)` **thay cho** `self.try_restore()`.
- `App.save_work`: khi `self.scratch`, không ghi gì, đặt `self.notice = "Đang mở bằng --pins: không ghi file phiên (xuất file import vẫn dùng được)."` và trả về; với `auto=True` thì trả về im lặng, không đổi `notice`. Test 3 kiểm `notice` sau lần gọi không `auto`.
- `run(..., pins=None)`: đọc JSON từ đường dẫn `pins` rồi gọi `app.load(frames_dir, xml, pins=data)`.

- [ ] **Bước 4: Chạy, xác nhận xanh**

Run: `python -m unittest tests.test_headturn tests.test_gui -v`
Expected: mọi test qua.

- [ ] **Bước 5: Chạy thật trên case 01 và cả bộ test**

Run: `python -m eyepin turns "C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che" --pins spike\out\pins_case01_ai.json`
Expected: hai dòng `Quay đầu`, đoạn 1 chứa frame 30–65, đoạn 2 chứa 105–145 (file đủ 24 frame ghim nên ranh giới có thể lệch vài frame so với 21–79 và 100–160).

Run: `python -m unittest discover -s tests`
Expected: `OK`, 164 test.

---

### Task 4: Dải quay đầu trên dải thời gian và trong tab Issues

**Files:**
- Modify: `eyepin/render.py:307-333` (`render_timeline`)
- Modify: `eyepin/gui_objects.py:403-440` (`_fill_issues`, `issue_step`, `issue_resolve`)
- Modify: `eyepin/gui.py:837-847` (`load`), `eyepin/gui.py:1564` (`refresh`)
- Test: `tests/test_render.py` (1 test), `tests/test_parity.py` (1 test)

**Interfaces:**
- Consumes: `Session.turns`, `Session.cur`, `Turn.first/last/confirmed/message` (Task 1, 2).
- Produces: `TURN_BGR = (0, 102, 255)` và `TURN_UNSURE_BGR = (150, 200, 255)` trong `render.py`; `App._turn_rows() -> list[tuple[int, int, Turn]]` (chỉ số người, số thứ tự đoạn tính từ 1 trong người đó, đoạn) theo thứ tự người rồi frame đầu.

- [ ] **Bước 1: Viết test**

Cả hai test gán thẳng `s.turns = [TurnReport("ok", 150.0, (Turn(20, 39, 30, 0.3, "mạnh", "mattrai", 2, 0, 0, 0), Turn(50, 55, 52, 0.15, "nhẹ", None, 0, 0, 0, 0)), 0, 3)]` sau khi ghim, để không phụ thuộc vào ảnh.

| # | Tên test | Khẳng định |
|---|---|---|
| 1 | `test_render.…test_timeline_shows_turn_band` | `render_timeline(s, 0, width=600)`: điểm ảnh ở hàng `y=3`, cột giữa frame 25 bằng `TURN_BGR`; cột giữa frame 52 bằng `TURN_UNSURE_BGR`; cột giữa frame 45 bằng `(235, 235, 235)`; với `s.turns = []` hàm không lỗi và hàng `y=3` toàn `(235, 235, 235)` trừ vạch frame hiện tại |
| 2 | `test_parity.…test_issues_tab_lists_turns_first` | `app.s.findings = [Finding("yellow", "jump", "matphai", 30, 30, (), "nhảy", 20.0, [30])]`; `app._fill_issues()`: `app.issues_var.get() == "Items: 3"`; `app.listbox.get(0)` bắt đầu bằng `"Quay đầu  #1  frame 20–39"`; `app.items == [20, 50, 30]`; từ frame 0, `app.issue_step(1)` ba lần đưa `app.f` qua `20, 30, 50`; chọn dòng 0 rồi `app.issue_resolve()`: `len(app.s.turns[0].turns) == 2`, `len(app.s.findings) == 1`, `app.notice` chứa `"tính lại từ điểm ghim"`; chọn dòng 2 rồi `app.issue_resolve()`: `app.s.findings == []` |

- [ ] **Bước 2: Chạy, xác nhận đỏ**

Run: `python -m unittest tests.test_render tests.test_parity -v`
Expected: hai test mới trượt (`ImportError: TURN_BGR`; `Items: 1`).

- [ ] **Bước 3: Viết mã**

- `render_timeline`: với các đoạn của người đang chọn (`session.turns[session.cur].turns`, bỏ qua khi `session.turns` ngắn hơn), tô hình chữ nhật từ `y=0` tới `y=6` trên các cột của `[first, last]`: `TURN_BGR` khi `confirmed > 0`, ngược lại `TURN_UNSURE_BGR`. Vẽ trước vạch frame hiện tại. Cập nhật docstring: "dải cam phía trên = đoạn quay đầu (cam nhạt = chưa xác nhận)".
- `_fill_issues`: dòng đoạn quay đầu đứng trước dòng quét; `self.items` = frame đầu của từng đoạn rồi tới `fd.frame`. Chữ của dòng: `turn.message(k)`; khi `len(self.s.layers) > 1` thêm tiền tố `f"Người {i + 1}: "`. `issues_var` đếm cả hai loại. Dòng "Không có frame nào cần chú ý." chỉ hiện khi cả hai rỗng.
- `issue_step`: ứng viên gồm frame đầu các đoạn quay đầu (thông báo `turn.message(k)`) và `fd.frame` (thông báo cũ), sắp theo frame.
- `issue_resolve`: gọi `rows = self._turn_rows()`; nếu dòng chọn `< len(rows)` thì không xoá gì, đặt `self.notice = "Đoạn quay đầu không bỏ được: nó được tính lại từ điểm ghim."`; ngược lại bỏ `self.s.findings[sel - len(rows)]` như cũ.
- Tự cập nhật: `App.load` đặt `self._turns_sig = ()`; trong `refresh` khi `light` là `False`, tính `sig = tuple((i, t.first, t.last, t.confirmed) for i, _, t in self._turn_rows())`; khác `self._turns_sig` thì gọi `self._fill_issues()` và lưu `sig`. (Nhờ vậy danh sách không bị dựng lại ở mỗi lần vẽ, và sau `load` danh sách vẫn trống như hiện nay cho tới khi có đoạn quay đầu hoặc bấm Quét.)

- [ ] **Bước 4: Chạy, xác nhận xanh**

Run: `python -m unittest tests.test_render tests.test_parity tests.test_gui -v`
Expected: mọi test qua, kể cả `test_issues_tab_count_navigation_resolve_and_timeline` cũ.

- [ ] **Bước 5: Nghiệm thu MVP 1**

Run: `python -m unittest discover -s tests`
Expected: `OK`, 166 test.

Run: `python -m eyepin gui "C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che" --pins spike\out\pins_case01_ai.json --selftest`
Expected: `gui selftest: OK`. (Lệnh `gui --selftest` phải nhận `--pins`; thêm khi sửa `run` ở Task 3.)

Run (cần Docker CVAT đang chạy và job 5 trống; nếu CVAT không chạy thì ghi "chưa chạy" vào báo cáo, không coi là qua): `python tests\verify_vs_cvat.py 5`
Expected: 11/11.

Sau đó: tick dòng "MVP 1" trong `TASKS.md` nhóm 7, sửa trạng thái ở đầu spec thành "MVP 1 đã xây", và cập nhật mục "Mã trong dự án" của `CLAUDE.md` thêm `headturn.py`, lệnh `turns` và `gui --pins`. Vẽ lại `/archify` để sau khi đóng băng mã (spec mục 6).
