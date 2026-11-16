# Lưới ảnh và chỉnh màu: kế hoạch xây

> **Cho agent làm việc:** dùng superpowers:subagent-driven-development hoặc superpowers:executing-plans để làm từng task. Bước dùng
> ô `- [ ]` để đánh dấu.

**Mục tiêu:** hộp Image setups như CVAT (lưới, độ sáng, tương phản, bão hoà, gamma) cộng phần đo của EyePin (lưới xuống 1 px, toạ độ và
khoảng cách dưới con trỏ, thước theo trục mắt), và EyePin vẽ pixel đúng chỗ CVAT vẽ.

**Kiến trúc:** mọi phép tính thuần (màu, bước lưới, vẽ lưới, thước, chữ đo) nằm trong module mới `eyepin/imagefx.py`, không đụng Tk,
test được không cần cửa sổ. `render.Look` giữ các giá trị; `render.render_base` gọi màu và lưới khi dựng ảnh nền (lưới xoay theo ảnh vì
`gui` xoay ảnh nền sau đó); `render.draw_overlay` vẽ thước; `gui.py` chỉ thêm hộp, phím, dòng đo.

**Công nghệ:** Python 3.12, numpy, OpenCV, Tkinter, unittest. Không thêm thư viện.

**Thiết kế:** `design/2026-11-16-grid-color-design.md` (đã duyệt 2026-11-16). Đọc cùng kế hoạch này.

## Ràng buộc chung

- Không model học máy; ảnh không rời máy; chỉ CVAT local (`http://localhost:8080`), được ghi và điều khiển trình duyệt ở đó.
- Thang và mặc định như CVAT: Brightness 50–200 (100), Contrast 50–200 (100), Saturation 0–300 (100), Gamma 0,2–2,6 bước 0,01 (1),
  lưới Size **1**–1000 (100; CVAT 5–1000), màu White/Black/Red/Green/Blue (White), Opacity 0–100 (100).
- Chỉ để nhìn: không đổi ảnh gốc, không đổi toạ độ nhãn, không hút điểm.
- Chữ hiện cho người dùng bằng tiếng Việt; số thập phân dùng dấu phẩy.
- Chạy test: `python -m unittest discover -s tests -p "<file>"` (không chạy được dạng `tests.<module>`); cả bộ:
  `python -m unittest discover -s tests`.
- Không có git: thay bước commit bằng chạy cả bộ test. Xong mỗi task thì tick hoặc thêm việc trong `TASKS.md` (quy tắc dự án).

## Điểm cần soi khi review

1. `settings.json` cũ có `brightness: 30` (thang cộng) không được hiểu thành 30% (ảnh tối đen): phải về 100 kèm thông báo. Test ở Task 2.
2. Thu nhỏ hết cỡ với Size 1: lưới không được phủ xám ảnh. Test ở Task 4.
3. Ảnh đang xoay 90°/270°: chữ đo phải là toạ độ ảnh đúng, không phải toạ độ màn hình. Test ở Task 6.
4. Frame chưa có nhãn, chỉ có một mắt, hoặc con trỏ ngoài ảnh: chữ đo không lỗi. Test ở Task 6.
5. Giá trị màu ở hai đầu thang (bão hoà 300, độ sáng 200, gamma 0,2): kẹp 0–255, không bị tràn số uint8. Test ở Task 2.

---

### Task 1: Kiểm quy ước pixel trên CVAT local, đo tốc độ trước khi sửa

Không đổi mã sản phẩm. Kết quả quyết định Task 3.

**Files:**
- Create: `spike/pixel_convention_check.py` (dùng một lần), `spike/perf_view.py` (đo tốc độ, dùng lại ở Task 8)
- Modify: `design/cvat-api-notes.md` (thêm mục "Quy ước pixel")

- [ ] **Bước 1: Dựng job thử trên CVAT local.** `spike/pixel_convention_check.py` tạo ảnh PNG 64×48 nền đen, pixel (10, 10) và (30, 20)
  trắng; tạo task mới trên `http://localhost:8080` với nhãn kiểu `points` tên `probe` (khoá đọc từ `~\.cvat_token`, header
  `Authorization: Token …`, không in khoá ra); import file CVAT 1.1 có hai shape `points` trên ảnh 0: `10.00,10.00` và `10.50,10.50`.
  In ra id task và id job.
- [ ] **Bước 2: Xem trên trình duyệt** (Claude in Chrome, tab mới, chỉ localhost): mở job, phóng to tối đa vào pixel (10, 10), bật Image
  grid Size 5, chụp màn hình. Ghi lại: điểm nào nằm giữa pixel trắng; đường lưới có trùng mép pixel không.
- [ ] **Bước 3: Xác nhận công thức gamma** của fabric 5.x (bản CVAT dùng, `cvat-ui` khai báo `fabric ^5.2.1`) từ mã nguồn
  `src/filters/gamma_filter.class.js` của gói `fabric@5.2.1` trên unpkg: ghi lại công thức bảng tra (mong đợi `pow(i/255, 1/gamma)*255`).
- [ ] **Bước 4: Ghi kết quả** vào `design/cvat-api-notes.md` mục "Quy ước pixel" (ảnh chụp lưu trong `spike/out/`, không lưu ảnh mặt người).
  Kết luận một dòng: "CVAT: pixel i phủ [i, i+1] → làm Task 3" hoặc "không lệch → bỏ Task 3".
- [ ] **Bước 5: Đo tốc độ trước khi sửa.** `spike/perf_view.py` mở `App` trên `C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che`
  với `--pins spike/out/pins_case01_ai.json`, khung 1900×980, đo (a) sang frame 20 lần, (b) kéo một điểm 30 lần di chuột (`on_press`,
  `on_motion`, `on_release` như `tests/test_mouse_speed.py`), in trung vị và p90 (ms). Chạy và ghi số vào `TASKS.md` dòng việc này.
  Mốc cũ để so: kéo điểm 20–31 ms, sang frame 134–149 ms.

### Task 2: Màu theo thang và cách tính của CVAT, thêm gamma, đổi thang cũ

**Files:**
- Create: `eyepin/imagefx.py`, `tests/test_imagefx.py`
- Modify: `eyepin/render.py` (`Look`), `eyepin/gui.py` (`DISPLAY_KEYS`, `_apply_settings_to_look`, `reset_adjust`, lưu khi đóng, thanh trượt
  hộp "Chỉnh hiển thị"), `tests/test_gui.py::test_image_adjust_and_layer_order`

**Interfaces:**
- Produces: `imagefx.COLOR_DEFAULTS = {"brightness": 100.0, "contrast": 100.0, "saturation": 100.0, "gamma": 1.0}`;
  `imagefx.COLOR_RANGES = {"brightness": (50, 200), "contrast": (50, 200), "saturation": (0, 300), "gamma": (0.2, 2.6)}`;
  `imagefx.apply_color(img: np.ndarray, brightness: float, contrast: float, saturation: float, gamma: float) -> np.ndarray`;
  `imagefx.migrate_display(display: dict) -> bool`.
- `Look` đổi mặc định `brightness=100.0, contrast=100.0, saturation=100.0`, thêm `gamma: float = 1.0`; `Look.adjust(img)` gọi `apply_color`.

- [ ] **Bước 1: Viết test hỏng** trong `tests/test_imagefx.py` (ảnh BGR uint8 2×2):
  - `test_defaults_return_the_same_array`: `apply_color(a, 100, 100, 100, 1.0) is a`.
  - `test_brightness_multiplies_and_clips`: xám 100, độ sáng 150 → 150; xám 200, độ sáng 200 → 255.
  - `test_contrast_around_mid_gray`: xám 100, tương phản 200 → 72.
  - `test_saturation_zero_is_gray_by_luminance`: đỏ thuần (B0, G0, R200), bão hoà 0 → cả ba kênh 43.
  - `test_saturation_max_clips_both_ends`: (B50, G50, R200), bão hoà 300 → R 255, G 0.
  - `test_gamma_uses_one_over_gamma`: 64 với gamma 2 → 128; 128 với gamma 0,5 → 64.
  - `test_gamma_runs_before_brightness`: 64, gamma 2, độ sáng 50 → 64.
  - `test_migrate_drops_old_scale`: `{"brightness": 30, "contrast": 1.2, "saturation": 1.0, "size": 1.5}` → trả `True`, dict thành
    `{"size": 1.5, "color_scale": "cvat"}`; `{"brightness": 150, "color_scale": "cvat"}` → `False`, không đổi; `{}` → `False`, thêm
    `"color_scale": "cvat"`.
- [ ] **Bước 2: Chạy** `python -m unittest discover -s tests -p "test_imagefx.py"`. Mong đợi: lỗi import `eyepin.imagefx`.
- [ ] **Bước 3: Viết `imagefx.apply_color`.** Thứ tự như CVAT: gamma, rồi brightness (nhân b/100), contrast ((v − 127,5)·c/100 + 127,5), cùng
  gộp vào một bảng tra 256 giá trị (`np.rint`, kẹp 0–255, `cv2.LUT`); rồi saturate bằng `cv2.transform` với ma trận Filter Effects
  (s = saturation/100; viết theo RGB, đổi sang thứ tự BGR của OpenCV), kẹp 0–255:
  ```
  R' = (0.213+0.787s)R + (0.715-0.715s)G + (0.072-0.072s)B
  G' = (0.213-0.213s)R + (0.715+0.285s)G + (0.072-0.072s)B
  B' = (0.213-0.213s)R + (0.715-0.715s)G + (0.072+0.928s)B
  ```
  Nếu Task 1 bước 3 cho công thức gamma khác thì dùng công thức đó và sửa test gamma theo.
- [ ] **Bước 4: Viết `imagefx.migrate_display`**: nếu `display.get("color_scale") != "cvat"` thì bỏ `brightness`, `contrast`, `saturation`
  (nếu có); luôn đặt `color_scale = "cvat"`; trả `True` khi có bỏ ít nhất một khoá.
- [ ] **Bước 5: Nối vào `Look` và `gui`.** `Look.adjust` gọi `apply_color`. `DISPLAY_KEYS` thêm `"gamma"`. `_apply_settings_to_look` gọi
  `migrate_display(self.settings["display"])` trước khi áp; trả `True` thì `self.notice = "Độ sáng, tương phản, bão hoà đã về mặc định vì
  EyePin đổi sang thang của CVAT (50–200%)."` và `self.save_settings()`. Lưu khi đóng ghi thêm `"color_scale": "cvat"`. `reset_adjust` đặt
  bốn giá trị về `COLOR_DEFAULTS` (không đụng lưới). Thanh trượt hộp "Chỉnh hiển thị" đổi sang thang mới, thêm gamma (Task 5 sẽ chuyển
  chúng sang hộp mới). Khoá dựng lại ảnh nền trong `_refresh` thêm `look.gamma`.
- [ ] **Bước 6: Sửa test cũ** `test_image_adjust_and_layer_order`: `Look(brightness=150)` làm sáng hơn; `Look(contrast=200.0)` cho 72;
  `Look(saturation=0)` xám; `reset_adjust` đưa `brightness` về `100.0`.
- [ ] **Bước 7: Thêm test GUI** vào `tests/test_gui.py`: `test_old_display_scale_is_reset`: đặt `app.settings["workspace"]["remember_display"] =
  True`, `app.settings["display"] = {"brightness": 30}`, gọi `app._apply_settings_to_look()` → `app.look.brightness == 100.0`,
  `"thang của CVAT" in app.notice`, `app.settings["display"]["color_scale"] == "cvat"`.
- [ ] **Bước 8: Chạy** hai file test trên rồi cả bộ. Mong đợi: OK.

### Task 3: Vẽ ảnh để pixel i phủ [i, i+1] như CVAT (chỉ làm nếu Task 1 xác nhận lệch)

**Files:**
- Modify: `eyepin/render.py` (`render_base`)
- Test: `tests/test_render.py`

**Interfaces:**
- Produces: `render.warp_image(src: np.ndarray, view: View, size: tuple[int, int], smooth: bool, bg: tuple) -> np.ndarray`; `render_base` dùng
  hàm này.

- [ ] **Bước 1: Viết test hỏng** `test_image_pixel_covers_i_to_i_plus_1`: ảnh 40×40 đen, pixel (10, 10) trắng, `View(0, 0, 8, 40, 40)`, khung
  (320, 320), không làm mịn → các cột trắng ở hàng 84 đúng là 80…87, các hàng trắng ở cột 84 đúng là 80…87; `View.to_frame(80, 80) ==
  (10.0, 10.0)`. Thêm `test_smoothed_pixel_peak_is_centered`: làm mịn → cột sáng nhất ở hàng 84 là 83 hoặc 84.
- [ ] **Bước 2: Chạy** `python -m unittest discover -s tests -p "test_render.py"`. Mong đợi: hỏng (hiện các cột 76…84).
- [ ] **Bước 3: Viết `warp_image`** với ma trận bù nửa pixel:
  `M = [[k, 0, k*(0.5 - x0) - 0.5], [0, k, k*(0.5 - y0) - 0.5]]`, nội suy `INTER_NEAREST` hoặc `INTER_CUBIC` theo `smooth`. Ảnh thu nhỏ
  (`render.py`, `INTER_AREA`) giữ nguyên.
- [ ] **Bước 4: Chạy** test render rồi cả bộ. Test cũ nào hỏng vì lệch nửa pixel thì sửa số trong test, ghi lý do trong tên hoặc chú thích.
- [ ] **Bước 5:** Thêm vào `TASKS.md` việc chờ người dùng quyết: "Nhãn làm bằng EyePin trước ngày sửa lệch nửa pixel nằm lệch (−0,5; −0,5) px
  so với ảnh trên CVAT; có cần dời lại không".

### Task 4: Lưới ảnh

**Files:**
- Modify: `eyepin/imagefx.py`, `eyepin/render.py` (`Look`, `render_base`), `eyepin/gui.py` (khoá dựng lại ảnh nền, `DISPLAY_KEYS`)
- Test: `tests/test_imagefx.py`

**Interfaces:**
- Produces: `imagefx.GRID_COLORS = {"White": (255, 255, 255), "Black": (0, 0, 0), "Red": (0, 0, 255), "Green": (0, 255, 0), "Blue": (255, 0, 0)}`
  (BGR); `imagefx.GRID_SIZE_RANGE = (1, 1000)`; `imagefx.grid_step(size: int, k: float, min_px: float = 8.0) -> int` (thiết kế ghi 4 px;
  đổi thành 8 px vì nét 1 px cách 4 px vẫn phủ khoảng 40% ảnh, trái phản mục tiêu "lưới phủ xám ảnh"; người dùng đã được báo);
  `imagefx.draw_grid(img: np.ndarray, view: View, img_w: int, img_h: int, size: int, color: str, opacity: float) -> int` (vẽ tại chỗ, trả
  bước đã dùng).
- `Look` thêm `grid: bool = False`, `grid_size: int = 100`, `grid_color: str = "White"`, `grid_opacity: float = 100.0`.

- [ ] **Bước 1: Viết test hỏng:**
  - `test_grid_step_thins_out`: `grid_step(100, 1.0) == 100`, `grid_step(1, 8.0) == 1`, `grid_step(1, 1.0) == 10`, `grid_step(1, 0.2) == 50`,
    `grid_step(5, 0.5) == 25` (nhân lần lượt ×1, ×5, ×10, ×50, ×100, ×500… tới khi bước × k ≥ 8).
  - `test_grid_lines_on_pixel_edges`: ảnh màn hình đen 400×300, `View(0, 0, 8, …)`, ảnh 40×30, Size 5, White, 100 → cột 40 trắng ở hàng 0…239,
    cột 41 đen; hàng 40 trắng; điểm (350, 100) và (100, 260) vẫn đen (ngoài ảnh); trả 5. Cột của đường tại toạ độ u là
    `floor((u − x0)·k)` (với `x0 = 0.3`, u = 5 rơi vào cột 37).
  - `test_grid_opacity_blends`: Opacity 50 → cột 40 có giá trị 127 hoặc 128.
  - `test_zoomed_out_size_one_does_not_gray_the_image` (điểm soi 2): `View(0, 0, 0.2, …)`, ảnh 1024×576, Size 1 → trả 50, và dưới 25% số
    pixel trong vùng ảnh bị đổi màu (đường cách nhau 10 px màn hình phủ khoảng 19%).
  - `test_tiny_grid_turns_off_smoothing`: `Look(grid=True, grid_size=2, smooth=True)` qua `render_base` cho cùng ảnh với `smooth=False`, ngoại
    trừ các pixel thuộc đường lưới. Phiên thử: `Session` trên thư mục ảnh tạm như `tests/test_gui.py` (`GuiTests.setUpClass` ghi
    `test_tracking.render(t)` ra PNG).
- [ ] **Bước 2: Chạy** `test_imagefx.py`. Mong đợi: thiếu `grid_step`.
- [ ] **Bước 3: Viết** `grid_step`, `draw_grid` (đường dọc và ngang 1 px, trộn màu theo Opacity bằng numpy, chỉ trong khung ảnh
  `[0, img_w] × [0, img_h]` đổi sang màn hình). `render_base`: làm mịn chỉ khi `look.smooth and not (look.grid and look.grid_size <= 2)`;
  sau khi dựng ảnh, `if look.grid: draw_grid(...)`. `DISPLAY_KEYS` thêm bốn khoá lưới; khoá dựng lại ảnh nền trong `_refresh` thêm bốn
  trường lưới.
- [ ] **Bước 4: Chạy** `test_imagefx.py`, `test_render.py`, rồi cả bộ. Mong đợi: OK.

### Task 5: Hộp Image setups, phím, nút `^`

**Files:**
- Modify: `eyepin/gui.py`, `eyepin/shortcuts.py`, `HUONG_DAN.md`, `design/shortcuts.md` (sinh lại)
- Create: `tests/test_image_setups.py` (dùng lại `test_gui` như `tests/test_mouse_speed.py`)

**Interfaces:**
- Consumes: `COLOR_DEFAULTS`, `COLOR_RANGES`, `GRID_COLORS`, `GRID_SIZE_RANGE` (Task 2, 4).
- Produces: `App.show_image_setups()`, `App.toggle_grid()`, `App._apply_setup(name: str, value) -> None` (kẹp theo thang, đặt vào `Look`,
  vẽ lại), `App._setup_vars: dict[str, tk.Variable]` (khoá là tên trường `Look`). Hành động mới trong `shortcuts.ACTIONS` nhóm `G_VIEW`:
  `Action("image_setups", G_VIEW, "Mở Image setups (lưới, độ sáng, tương phản, bão hoà, gamma)", ("<Control-g>",), "", "CVAT: nút ^ giữa mép dưới khung ảnh")`,
  `Action("grid", G_VIEW, "Bật/tắt lưới ảnh", ("g",), "", "CVAT: ô Image grid trong Image setups")`.

- [ ] **Bước 1: Viết test hỏng** trong `tests/test_image_setups.py`:
  - `test_g_toggles_grid_and_redraws_the_base`: `app.handlers["grid"](None)` → `app.look.grid is True`, `app._base_raw` khác trước.
  - `test_apply_setup_clamps`: `_apply_setup("grid_size", 0)` → 1; `_apply_setup("gamma", 5)` → 2.6; `_apply_setup("brightness", 150)` → 150.0.
  - `test_reset_color_keeps_grid`: bật lưới, độ sáng 150, gamma 2 → `reset_adjust()` → độ sáng 100, tương phản 100, bão hoà 100, gamma 1;
    lưới vẫn bật.
  - `test_box_opens_and_vars_follow_look`: `show_image_setups()` → `_setup_vars["grid_size"].get() == app.look.grid_size`; sau `toggle_grid()`
    thì `_setup_vars["grid"].get()` đổi theo.
  - `test_shortcuts_guide_lists_new_actions`: `"image_setups"` và `"grid"` có trong `shortcuts.BY_ID`, không trùng phím với hành động khác.
- [ ] **Bước 2: Chạy** `python -m unittest discover -s tests -p "test_image_setups.py"`. Mong đợi: thiếu `show_image_setups`.
- [ ] **Bước 3: Làm hộp.** Toplevel ẩn/hiện như hộp "Chỉnh hiển thị". Phần "Image grid": ô bật, Size (Spinbox 1–1000), Color (Combobox năm
  màu), Opacity (thanh 0–100), ô "Thước theo trục mắt" (Task 7 nối vào; ở task này chỉ lưu `look.axis_guide`). Phần "Color settings":
  bốn thanh theo `COLOR_RANGES`, nút "Reset color settings" gọi `reset_adjust`. Nút `^` nhỏ đặt giữa mép dưới khung ảnh mở hộp, cạnh nút.
  Menu Xem thêm mục "Image setups (lưới, màu)…". Bỏ ba thanh độ sáng, tương phản, bão hoà (và gamma) khỏi hộp "Chỉnh hiển thị".
  `Look` thêm `axis_guide: bool = False`; `DISPLAY_KEYS` thêm `"axis_guide"`.
- [ ] **Bước 4: Chạy** test của task, `test_gui.py`, `test_keys_focus.py`, rồi cả bộ. Mong đợi: OK.
- [ ] **Bước 5: Tài liệu.** `python -m eyepin shortcuts --out design/shortcuts.md`. `HUONG_DAN.md`: một đoạn "Lưới và màu ảnh" (phím `g`,
  `Ctrl+G`, nút `^`, thang như CVAT, Size 1 là lưới từng pixel).

### Task 6: Toạ độ và khoảng cách dưới con trỏ

**Files:**
- Modify: `eyepin/imagefx.py`, `eyepin/gui.py` (hàng trạng thái, `on_hover`)
- Test: `tests/test_imagefx.py`, `tests/test_image_setups.py`

**Interfaces:**
- Produces: `imagefx.readout(u: Point, img_w: int, img_h: int, pts: dict[int, Point] | None) -> str`; `App.measure_var: tk.StringVar`.

- [ ] **Bước 1: Viết test hỏng:**
  - `test_readout_coordinates`: `readout((412.371, 288.049), 1024, 576, None) == "x 412,37 · y 288,05"`.
  - `test_readout_outside_image` (điểm soi 4): `readout((-3, 10), 1024, 576, None) == "ngoài ảnh"`.
  - `test_readout_nearest_point_and_eye_width`: điểm 14 (100, 100), 18 (160, 100), 16 (130, 90); con trỏ (130, 93.2) →
    `"x 130,00 · y 93,20 · tới điểm 16: 3,2 px (5% bề rộng mắt)"`.
  - `test_readout_without_both_corners` (điểm soi 4): chỉ có điểm 16 (130, 90) → `"x 130,00 · y 93,20 · tới điểm 16: 3,2 px"`.
  - `test_hover_readout_under_rotation` (điểm soi 3, trong `test_image_setups.py`): xoay ảnh 90° bằng `app.rotate(1)`, đổi toạ độ điểm 16
    sang màn hình đã xoay (ngược với `App._unrot`),
    gọi `app.on_hover(Ev(x, y))` ở toạ độ màn hình của điểm 16 → `app.measure_var.get()` có `"tới điểm 16: 0,0 px"` (sai số làm tròn
    màn hình cho phép tới 0,2 px: so bằng số đọc ra từ chuỗi).
- [ ] **Bước 2: Chạy.** Mong đợi: thiếu `readout`.
- [ ] **Bước 3: Viết `readout`** (khoảng cách 1 chữ số lẻ, phần trăm làm tròn số nguyên, bề rộng mắt = khoảng cách hai khoé của mắt chứa điểm
  đó theo `geometry.EYES`) và nối vào `gui`: hàng trạng thái thành một khung gồm nhãn trạng thái cũ (bên trái, giãn) và nhãn
  `measure_var` (bên phải); `on_hover` đặt `measure_var` từ `self.view.to_frame(*self.hover)` và `self.s.points_at(self.f)`. Chỉ đổi
  chữ, không gọi `refresh`.
- [ ] **Bước 4: Chạy** hai file test rồi cả bộ. Mong đợi: OK.

### Task 7: Thước theo trục mắt

**Files:**
- Modify: `eyepin/imagefx.py`, `eyepin/render.py` (`draw_overlay`), `eyepin/gui.py` (ô bật trong hộp)
- Test: `tests/test_imagefx.py`, `tests/test_image_setups.py`

**Interfaces:**
- Produces: `imagefx.axis_guides(spec: EyeSpec, pts: dict[int, Point]) -> list[tuple[Point, Point]] | None` (toạ độ ảnh; đoạn đầu là trục
  khoé–khoé, rồi một vạch cho mỗi tỉ lệ; `None` khi thiếu khoé hoặc hai khoé trùng nhau).

- [ ] **Bước 1: Viết test hỏng:**
  - `test_axis_guides_ticks_at_guideline_ratios`: mattrai 14 (100, 100), 18 (160, 100), 16 (130, 90), 20 (130, 110) → 7 đoạn; đoạn đầu
    ((100, 100), (160, 100)); vạch mí trên tại 0,48 từ (128.8, 100) tới (128.8, 79); vạch mí dưới tại 0,50 từ (130, 100) tới (130, 121)
    (dài 0,35 bề rộng mắt; mí trên về phía điểm `up`). Tỉ lệ lấy từ `EyeSpec` (`up_mid`, `lo_mid`, `derived`), không chép số tay.
  - `test_axis_guides_follow_a_slanted_eye`: khoé (100, 100) và (160, 130) → mọi vạch vuông góc với trục (tích vô hướng < 1e-6).
  - `test_axis_guides_degenerate`: hai khoé trùng nhau → `None`; thiếu điểm 18 → `None`.
  - `test_guides_drawn_only_when_on_and_eye_selected` (trong `test_image_setups.py`): dùng `render.CvPainter` qua `render_main` với
    `Look(axis_guide=True)` và `selected="mattrai"` → ảnh khác so với `axis_guide=False`; `selected=None` → không khác.
- [ ] **Bước 2: Chạy.** Mong đợi: thiếu `axis_guides`.
- [ ] **Bước 3: Viết `axis_guides`** và vẽ trong `draw_overlay` (sau nhãn, trước tay cầm) khi `look.axis_guide` và `selected` là một mắt đủ
  hai khoé: `p.line` cho từng đoạn (đổi sang màn hình bằng `view.to_screen`), dùng điểm sau `override` để thước đi theo khi kéo. Màu và nét
  do người xây chọn, khác màu mắt.
- [ ] **Bước 4: Chạy** hai file test rồi cả bộ. Mong đợi: OK.

### Task 8: Đo tốc độ sau khi sửa, cập nhật tài liệu dự án

**Files:**
- Modify: `TASKS.md`, `CLAUDE.md`, `.archify/` (thư mục sơ đồ mới)

- [ ] **Bước 1: Chạy** `spike/perf_view.py` như Task 1 bước 5, thêm hai lượt: lưới bật Size 100, và lưới bật Size 1 ở mức phóng ×8. Mong đợi:
  kéo điểm và sang frame không chậm hơn mốc Task 1 quá 10% khi lưới tắt; ghi cả bốn bộ số vào `TASKS.md`.
- [ ] **Bước 2: Cả bộ test:** `python -m unittest discover -s tests`. Mong đợi: OK.
- [ ] **Bước 3: `TASKS.md`:** tick các việc của tính năng này; thêm việc còn mở (nếu có).
- [ ] **Bước 4: Module mới `imagefx.py`** (quy tắc dự án): thêm một dòng vào mục "Mã trong dự án" của `CLAUDE.md`, chạy `/archify` vẽ lại sơ đồ
  vào `.archify/architecture-eyepin-<chủ đề>-<ngày-giờ>/` mới và sửa đường dẫn sơ đồ hiện tại trong `CLAUDE.md`.
