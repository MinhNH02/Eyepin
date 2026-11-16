# Thanh bên phải giống CVAT + bộ icon CVAT — kế hoạch thực hiện

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tab Objects thành danh sách thẻ theo đúng CVAT 2.75, mọi nút dùng icon gốc của CVAT/Ant Design, chỉ hiện chữ khi trỏ chuột; Hidden/Lock trên thẻ theo từng đối tượng; tab Frame lân cận bật/tắt được.

**Architecture:** Icon SVG được đổi một lần sang PNG mặt nạ alpha (`tools/build_icons.py`, dùng PyMuPDF có sẵn) và tô màu lúc chạy (`icons.py`). Thẻ đối tượng là widget mới `ObjectList` (`eyepin/gui_sidebar.py`) có **API giống `ttk.Treeview`** (iid `eye:<label>[@layer]`, `pt:<id>[@layer]`, cột `vai`/`sao`/`trang`) để `refresh_objects`, `_selected` và ~50 chỗ trong test chỉ đổi tối thiểu; thẻ được dựng lại chỉ khi danh sách iid đổi, còn lại cập nhật tại chỗ.

**Tech Stack:** Python 3.12, Tkinter/ttk 8.6, Pillow (ImageTk), PyMuPDF (`fitz`, chỉ lúc build icon), unittest.

**Spec:** `design/2026-11-16-cvat-sidebar-icons-design.md` (đọc cả mục 4, 7b).

## Global Constraints
- Không git: trước Task 1 sao lưu `eyepin/` và `tests/` sang `..\eye_label_tool_backup_sidebar\`; review bằng diff với bản đó.
- Test: `python -m unittest discover -s tests -p "<file>.py"` (chạy từng file; máy thiếu bộ nhớ ảo, cả bộ có thể `MemoryError` ngẫu nhiên — test lỗi kiểu đó thì chạy lại riêng). Đặt `PYTHONIOENCODING=utf-8`.
- Không thêm thư viện chạy lúc dùng tool; PyMuPDF chỉ dùng trong `tools/build_icons.py`.
- Không chữ cố định cạnh icon; chữ khi trỏ chuột = tiếng Việt + phím tắt hiện hành (`self.kl(id)`).
- Nguồn icon: `scratchpad/icons_dl/{cvat,ant}/*.svg` + `LICENSE` (CVAT v2.75.0, `@ant-design/icons-svg@4.4.2`, MIT). Đường dẫn đầy đủ: `C:\Users\minhf\AppData\Local\Temp\claude\3fbc9c6e4df64d61\1f1916e9-6806-45d3-a8eb-10d604afb9d2\scratchpad\icons_dl\`. Thiếu icon thì tải thêm từ cùng nguồn, cùng phiên bản.
- Bố cục và thứ tự nút: theo mục 4 của spec (chép từ mã nguồn CVAT v2.75.0, `scratchpad\cvat_src\`).
- Không đổi phím tắt; phím `Del`/`q`/`o` theo con trỏ (tests/test_keys_focus.py) phải giữ.
- Văn bản cho người dùng bằng tiếng Việt.

## Review Focus
1. Phát (Space) / kéo điểm gọi `refresh` mỗi frame: `ObjectList` không được huỷ-dựng lại thẻ khi iid không đổi (test ở Task 4).
2. Job ở chế độ QC hoặc đang bận: nút sửa trên thẻ (Outside, Occluded, Keyframe, Pinned, đổi label, DETAILS) không được sửa nhãn (test ở Task 5).
3. Nhiều người (layer ≥ 2): thẻ của người 2 tác động đúng người 2 (iid hậu tố `@1`), kể cả Hidden/Lock (test ở Task 3 và 5).
4. Thiếu file PNG của một icon: nút rơi về chữ thay thế, không sập (test ở Task 2).
5. Bấm ô chọn label trên thẻ xong, phím tắt vẫn chạy (focus trả về ảnh) (test ở Task 5).

---

### Task 1: Bộ icon PNG + ghi chú bản quyền

**Files:**
- Create: `tools/build_icons.py`, `tools/icon_src/cvat/*.svg`, `tools/icon_src/ant/*.svg` (chép nguồn đã tải để build lại được), `eyepin/assets/icons/*.png`, `eyepin/assets/icons/NOTICE.md`
- Test: `tests/test_icon_assets.py`

**Interfaces:**
- Produces: file `eyepin/assets/icons/<name>-<px>.png` với `px ∈ {16, 20, 24}`, RGBA, màu trắng, hình ở kênh alpha; `name` là khoá của `ICON_SOURCES`.
- Produces: `tools/build_icons.py` có hằng `ICON_SOURCES: dict[str, str]` (tên EyePin → đường dẫn SVG tương đối trong `tools/icon_src/`) và `SIZES = (16, 20, 24)`; `python tools/build_icons.py` dựng lại toàn bộ.

`ICON_SOURCES` tối thiểu (theo spec 4.1–4.6): `menu=cvat/main-menu-icon`, `save`, `undo`, `redo`, `first`, `last`, `prev=cvat/previous-icon`, `next`, `prev_filtered`, `next_filtered`, `back10=cvat/back-jump-icon`, `fwd10=cvat/forward-jump-icon`, `play`, `pause`, `fullscreen`, `filter`, `outside=cvat/object-outside-icon`, `inside=ant/outlined_select`, `occluded=ant/outlined_team`, `not_occluded=ant/outlined_user`, `lock=ant/filled_lock`, `unlock=ant/outlined_unlock`, `eye=ant/outlined_eye`, `eye_off=ant/filled_eye-invisible`, `star=ant/filled_star`, `star_off=ant/outlined_star`, `pinned=ant/filled_pushpin`, `unpinned=ant/outlined_pushpin`, `caret_down=ant/outlined_caret-down`, `caret_up=ant/filled_caret-up`, `more=ant/outlined_more`, `info=ant/outlined_info-circle`, `cursor`, `hand=cvat/move-icon`, `rotate=cvat/rotate-icon`, `fit=cvat/fit-to-window-icon`, `zoom=cvat/zoom-icon`, `skeleton=cvat/skeleton-icon`, `point=cvat/point-icon`, `display=cvat/colorize-icon`, `add=cvat/plus-icon`, `trash=ant/outlined_delete`, `copy`, `link`, `check=ant/outlined_check`, `scan`, `export`, `settings=ant/outlined_setting`, `keyboard=ant/outlined_question-circle`, `layer_up=cvat/next-layer-icon`, `layer_down=cvat/previous-layer-icon`, `foreground`, `background`, `upload=ant/outlined_cloud-upload`, `home`, `logout`.

- [ ] **Step 0: Sao lưu** `eyepin/` và `tests/` sang `..\eye_label_tool_backup_sidebar\`.
- [ ] **Step 1: Write the failing test** `tests/test_icon_assets.py`:
  - `test_every_icon_has_all_sizes`: với mỗi `name` trong `build_icons.ICON_SOURCES`, mỗi `px` trong `SIZES`, file tồn tại, `Image.open(...).mode == "RGBA"`, `size == (px, px)`, kênh alpha có ít nhất 5% điểm > 128 và ít nhất 5% điểm == 0 (có hình, không phải ô vuông đặc).
  - `test_icons_are_white_masks`: mọi điểm có alpha > 0 có RGB ≥ (240, 240, 240).
  - `test_notice_has_both_mit_licenses`: `NOTICE.md` chứa `"cvat-ai/cvat"`, `"v2.75.0"`, `"@ant-design/icons-svg"`, `"4.4.2"`, và chữ `"MIT"` ít nhất 2 lần, chứa nguyên văn dòng bản quyền của hai file LICENSE.
  - Import `tools/build_icons.py` qua `importlib.util.spec_from_file_location`.
- [ ] **Step 2: Chạy** `python -m unittest discover -s tests -p "test_icon_assets.py"` → FAIL (thiếu file).
- [ ] **Step 3: Implement** `tools/build_icons.py`: `render(svg_path: Path, px: int) -> PIL.Image` dùng `fitz.open(svg)` → `page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=True)` với `s = px / page.rect.width`, rồi lấy độ phủ làm alpha (alpha của pixmap; nếu SVG vẽ bằng `stroke`/`currentColor` mà alpha rỗng thì dùng `255 - độ sáng` của bản nền trắng) và đặt RGB = 255. Ghi `NOTICE.md` từ hai `LICENSE`. Chạy script.
- [ ] **Step 4: Chạy lại test** → PASS. Mở vài PNG phóng to (ví dụ `outside-24`, `occluded-24`, `skeleton-24`) để nhìn bằng mắt rằng hình đúng, không bị ô đặc.

### Task 2: `icons.py` vẽ icon PNG, chỉ chữ khi trỏ chuột

**Files:**
- Modify: `eyepin/icons.py` (thay `GLYPHS` bằng ảnh, giữ chữ thay thế)
- Test: `tests/test_icons.py`

**Interfaces:**
- Consumes: PNG của Task 1.
- Produces: `icon_image(widget: tk.Misc, name: str, px: int, color: str) -> ImageTk.PhotoImage | None` (cache theo `(name, px, color)`; `None` khi thiếu file).
- Produces: `IconButton(parent, name, command, *, tip="", kind="tool", size=16, caption=...)` — tham số `caption` vẫn nhận (để code cũ không vỡ) nhưng **không vẽ chữ**; `set_icon(name)`, `set_active(on)` giữ nghĩa; thêm `set_enabled(on: bool)` (mờ + bỏ qua bấm).
- Produces: `Tooltip` hiện sau **150 ms** (CVAT dùng ~100 ms), mất khi rời.
- Màu: thường `theme.INK`; nền thanh cam giữ như nay; bật (`active`) dùng màu nhấn hiện có; mờ dùng `theme.MUTED` (hoặc màu xám tương đương có sẵn trong `theme.py`).

- [ ] **Step 1: Test** `tests/test_icons.py` (cửa sổ Tk ẩn, bỏ qua nếu không có màn hình):
  - `test_button_shows_image_not_text`: `b = IconButton(root, "lock", None, tip="Khoá (l)", caption="Khoá")` → `b.icon.cget("image") != ""`, `b.cap is None`, không có `Label` con nào có `text` khác rỗng.
  - `test_set_icon_swaps_image`: `set_icon("unlock")` đổi `cget("image")`.
  - `test_missing_png_falls_back_to_text`: tạm đổi thư mục icon sang thư mục rỗng (hằng `ICON_DIR` patch được) → nút vẫn tạo được, `icon.cget("text")` khác rỗng.
  - `test_disabled_ignores_click`: `set_enabled(False)` rồi gọi `b._click(None)` → command không chạy.
  - `test_tooltip_delay_is_short`: `Tooltip.DELAY_MS <= 200`.
- [ ] **Step 2:** chạy → FAIL.
- [ ] **Step 3: Implement** trong `eyepin/icons.py` (đổi docstring đầu file cho đúng: icon CVAT/Ant, MIT). Giữ tên cũ còn được gọi trong code (`kf_prev`, `kf_next`, `rot_ccw`, `rot_cw`, `zoom_in`, `zoom_out`, `pin`, `pin_hidden`, `keyframe`, `collapse`, `open`, `search`, `window`) bằng bảng bí danh sang tên ở Task 1 (ví dụ `kf_prev→prev`, `rot_ccw→rotate` lật ngang, `zoom_in→zoom`, `pin→skeleton`, `pin_hidden→point`, `keyframe→star`, `collapse→caret_down`, `window→fullscreen`).
- [ ] **Step 4:** chạy `test_icons.py` → PASS; chạy `test_gui.py` → PASS (nút cũ vẫn tạo được).

### Task 3: Hidden và Lock theo từng đối tượng

**Files:**
- Modify: `eyepin/render.py` (`draw_overlay`, `render_main` nếu nó gọi `draw_overlay`), `eyepin/gui.py` (`toggle_eye_hidden`, `toggle_lock`, chỗ gọi `draw_overlay`, điều kiện chặn kéo ~1442), `eyepin/gui_objects.py` (`LayerSet`, tab Labels)
- Test: `tests/test_object_hide_lock.py`

**Interfaces:**
- Produces: `draw_overlay(..., hidden: frozenset[tuple[int, str]] = frozenset())` — bỏ qua mắt `(layer, label)` có trong `hidden` (layer của bộ đang chọn = `session.cur`, của bộ khác = `v["layer"]`). `look.eyes` vẫn là ẩn theo label cho mọi người.
- Produces: `App.hidden_objs: set[tuple[int, str]]`; `App._obj_hidden(layer: int, label: str) -> bool` (= `(layer,label) in hidden_objs or not look.eyes[label]`).
- Produces: `LayerSet.set_all(x, on: bool, layers: int)` — thêm/bỏ `x` ở mọi bộ `0..layers-1`.
- Hành vi: phím `h` và nút Hidden trên thẻ đảo `(s.cur, label)` trong `hidden_objs` (mắt chọn hoặc dưới con trỏ, như `delete_label`); `H` và nút Hidden ở tab Labels giữ như nay (`look.eyes`, mọi người). Nút Lock ở tab Labels dùng `locked.set_all(label, on, len(s.layers))`; Lock trên thẻ và phím `l` giữ như nay (bộ đang chọn). Mắt bị ẩn theo đối tượng thì không kéo được (thêm vào điều kiện ~`gui.py:1442`).

- [ ] **Step 1: Test** `tests/test_object_hide_lock.py` (dữ liệu giả của `test_tracking`, như `tests/test_keys_focus.py`):
  - `test_hidden_object_draws_like_hidden_label_with_one_person`: ảnh từ `render_main`/`draw_overlay` với `hidden={(0,"mattrai")}` giống hệt (numpy `array_equal`) ảnh với `look.eyes["mattrai"]=False`, và khác ảnh không ẩn.
  - `test_hiding_person2_eye_keeps_person1_eye`: tạo người 2 bằng `s.add_layer()` + ghim người 2; ẩn `(1,"mattrai")` → ảnh khác ảnh không ẩn, và khác ảnh ẩn `(0,"mattrai")`.
  - `test_h_key_hides_only_selected_object`: chọn `eye:mattrai`, `app.handlers["hide"]()` → `(0,"mattrai") in app.hidden_objs`, `app.look.eyes["mattrai"] is True`.
  - `test_labels_tab_lock_locks_every_person`: 2 người; `app._toggle_label_lock("mattrai")` → `"mattrai" in locked` ở cả hai bộ (đổi `s.select_layer` để kiểm).
  - `test_hidden_object_cannot_be_dragged`: ẩn `(0,"mattrai")`, bấm-kéo vào điểm 14 → toạ độ ghim không đổi.
- [ ] **Step 2:** chạy → FAIL.
- [ ] **Step 3: Implement** theo Interfaces.
- [ ] **Step 4:** chạy file test mới, `test_gui.py`, `test_parity.py` → PASS. Test cũ nào kiểm "phím h đổi `look.eyes`" thì đó là đổi hành vi có chủ đích (spec 7b.3): sửa assert sang `hidden_objs` và ghi vào báo cáo task.

### Task 4: Widget `ObjectList` (thẻ CVAT, API giống Treeview)

**Files:**
- Create: `eyepin/gui_sidebar.py`
- Test: `tests/test_object_list.py`

**Interfaces:**
- Consumes: `IconButton`, `icon_image` (Task 2), `theme`.
- Produces: `class ObjectList(ttk.Frame)`:
  - `__init__(self, parent, on_action: Callable[[str, str], None], on_select: Callable[[], None])` — `on_action(action, iid)` với `action ∈ {"first","prev","next","last","outside","lock","occluded","hidden","keyframe","pinned","menu","label","focus"}`; với `"label"` widget gọi `on_action("label", iid)` sau khi ô chọn đổi (giá trị mới đọc bằng `label_of(iid)`); `on_select()` sau mỗi lần lựa chọn đổi do người bấm.
  - Giống Treeview: `insert(parent: str, index, iid: str, text: str = "", values: tuple = (), open: bool = False, card: dict | None = None) -> str`; `delete(*iids)`; `get_children(parent: str = "") -> tuple[str, ...]`; `exists(iid) -> bool`; `item(iid, option: str | None = None, **kw)` (`"text"`, `"open"`, `"values"`; `item(iid, open=True)` mở DETAILS); `set(iid, column: str) -> str` cho cột `"vai"`, `"sao"`, `"trang"` theo thứ tự `values`; `selection() -> tuple[str, ...]`; `selection_set(iid)`; `selection_remove(*iids)`; `identify_row(y) -> str` (cho menu chuột phải).
  - `card` (chỉ cho iid `eye:`): `{"id": int|None, "label": str, "color": "#rrggbb", "type": "SKELETON TRACK", "status": str, "outside": bool, "lock": bool, "occluded": bool, "hidden": bool, "keyframe": bool, "pinned": bool, "has_prev": bool, "has_next": bool, "has_first": bool, "has_last": bool}`; dòng `pt:` dùng `values=(nguồn "ghim"/"suy ra", sao, trạng thái "Occluded"/"Outside"/""/"—")`.
  - `activate(iid: str | None)` — tô sáng thẻ (hover trên ảnh) và cuộn tới nếu khuất; `activated() -> str | None`.
  - `begin_update()` / `end_update()` — giữa hai lệnh này, `delete(*all)` + `insert(...)` với **cùng dãy iid** chỉ cập nhật trạng thái thẻ tại chỗ (không tạo widget mới); dãy iid khác thì dựng lại.
  - Bố cục thẻ theo spec 4.2: vạch màu trái; hàng 1 `#id`, `type` (+ ` · status` chữ xám), ô chọn label (`mattrai`/`matphai`), nút `more`; hàng 2 `first prev next last` (mờ khi `has_*` False); hàng 3 `outside|inside`, `lock|unlock`, `occluded|not_occluded`, `eye_off|eye`, `star|star_off`, `pinned|unpinned`; `caret` mở/đóng DETAILS; DETAILS liệt kê dòng điểm (tên điểm, chữ nhỏ nguồn, trạng thái) — bấm dòng = chọn iid `pt:`. Thẻ chọn có viền đậm. Bấm thẻ = chọn `eye:`; nhấp đúp = `on_action("focus", iid)`; chuột phải = chọn + `on_action("menu", iid)`. Chữ khi trỏ chuột của 6 nút theo CVAT, tiếng Việt, ví dụ "Outside (o)", "Khoá (l)", "Occluded (q)", "Ẩn/hiện (h)", "Keyframe (k)", "Pinned (p)"; ObjectList nhận phím hiện hành qua `__init__(..., keys: dict[str, str] = {})`.
  - Cuộn: khung cuộn dọc (Canvas + Frame), con lăn chuột cuộn danh sách khi trỏ trong panel.

- [ ] **Step 1: Test** `tests/test_object_list.py` (widget đứng một mình, không cần App):
  - `test_treeview_like_api`: insert 2 thẻ (`eye:mattrai`, `eye:matphai`) mỗi thẻ 8 dòng `pt:`; `get_children()` đúng thứ tự; `get_children("eye:mattrai")` có 8 phần tử; `item("eye:mattrai","text")`; `set("eye:mattrai","sao")`, `set(...,"trang")`; `selection_set("pt:17")` → `selection()==("pt:17",)`; `selection_remove(*selection())` → `()`; `exists("eye:x") is False`.
  - `test_open_details`: `item("eye:mattrai", open=True)` → `item(...,"open") is True` và 8 dòng điểm hiện (`winfo_ismapped` sau `update_idletasks`); đóng thì ẩn.
  - `test_buttons_send_action_with_iid`: bấm (gọi `_click`) nút Outside, Lock, Occluded, Hidden, Keyframe, Pinned, first/prev/next/last của thẻ `eye:matphai@1` → `on_action` nhận đúng `(action, "eye:matphai@1")` theo thứ tự; nút `prev` khi `has_prev=False` không gửi.
  - `test_button_icons_follow_state`: `card["lock"]=True` → nút lock dùng icon `lock`; False → `unlock`; tương tự outside/inside, occluded/not_occluded, eye_off/eye, star/star_off, pinned/unpinned.
  - `test_same_iids_update_in_place`: đếm `len(winfo_children())` đệ quy sau lần dựng 1; `begin_update(); delete(*get_children()); insert(... cùng iid, card khác); end_update()` → số widget không đổi, và icon lock đã đổi theo card mới; thêm iid mới → dựng lại.
  - `test_order_of_buttons_matches_cvat`: thứ tự tên icon ở hàng 3 = `["outside|inside","lock|unlock","occluded|not_occluded","eye|eye_off","star|star_off","pinned|unpinned"]` (so theo nhóm).
  - `test_activate_highlights`: `activate("eye:matphai")` → `activated()=="eye:matphai"`; `activate(None)` → `None`.
  - `test_no_static_text_on_buttons`: không `IconButton` nào trong ObjectList có `cap`.
- [ ] **Step 2:** chạy → FAIL.
- [ ] **Step 3: Implement** `eyepin/gui_sidebar.py` theo Interfaces.
- [ ] **Step 4:** chạy → PASS.

### Task 5: Lắp ObjectList vào cửa sổ; thứ tự tab; Frame lân cận bật/tắt; thanh trên/trái dùng icon CVAT

**Files:**
- Modify: `eyepin/gui.py` (`_build` ~180–370, `refresh_objects` ~1608, `on_tree_click`, `_on_tree_select`, `select_eye`, `_pick_layer`, `on_hover`/`on_leave`, `show_settings` tab Workspace), `eyepin/gui_objects.py` (`_objects_extras`, `_build_obj_menu`, `_tree_right_click`, `collapse_all`, tab Labels/Issues icon), `eyepin/shortcuts.py` (`DEFAULT_SETTINGS["workspace"]["show_neighbors"] = True`)
- Modify tests chỉ ở cách truy cập nếu cần: `tests/test_gui.py`, `tests/test_parity.py`, `tests/test_gui_cvat.py`, `tests/test_keys_focus.py`
- Test: `tests/test_sidebar_app.py`

**Interfaces:**
- Consumes: `ObjectList` (Task 4), `hidden_objs`/`_obj_hidden`/`set_all` (Task 3), `IconButton` (Task 2).
- Produces: `App.tree` **là** một `ObjectList` (giữ tên thuộc tính để code và test cũ dùng tiếp). `App._on_object_action(action: str, iid: str) -> None` chọn iid rồi gọi đúng hàm có sẵn: `first→first_keyframe`, `prev→jump_pin(-1)`, `next→jump_pin(1)`, `last→last_keyframe`, `outside→toggle_flag("outside")`, `occluded→toggle_flag("occluded")`, `lock→toggle_lock`, `hidden→toggle_eye_hidden`, `keyframe→` hành vi ★ hiện có của `on_tree_click` (`s.toggle_eye_key(label, f)`), `pinned→toggle_pinned`, `label→swap_labels` khi label mới khác label cũ, `menu→popup_obj_menu` tại con trỏ, `focus→focus_object`. Mọi hành động sửa nhãn đi qua `_edit_blocked()` như hiện nay. Sau `label`, trả focus về `self.canvas`.
- Produces: tab theo thứ tự `Objects`, `Labels`, `Issues`, `Frame lân cận`; `App.set_neighbors_tab(on: bool)` thêm/gỡ tab (gỡ thì không tính ảnh thu nhỏ `t_prev`/`t_next`); Cài đặt F2 → Workspace có ô "Hiện tab Frame lân cận" ghi `settings["workspace"]["show_neighbors"]`.
- Đầu danh sách (spec 4.1): `Items: N`, Sort by, rồi nút `lock|unlock` (khoá tất cả), `eye|eye_off` (ẩn tất cả), `caret_down|caret_up` (mở/thu tất cả DETAILS), rồi `add` và `trash` (EyePin). Bỏ hàng nút keyframe/khoá/ẩn/Occluded/Outside cũ dưới bảng (đã lên thẻ). Menu ⋮ thêm mục "Remove" (= `delete_label`).
- Hover: `on_hover` → `self.tree.activate(iid của _eye_at(hover) ở bộ đang chọn hoặc None)`; trỏ chuột vào thẻ → mắt đó vẽ đậm (truyền `selected=` hiện có của `draw_overlay` theo `activated()` khi chuột ở panel).
- Thanh trên và thanh trái: đổi tên icon theo bảng spec 4.6, bỏ mọi `caption=`; nút phát/dừng dùng `play`/`pause`; nút trước/kế dùng `prev_filtered`/`next_filtered` khi đang lọc.

- [ ] **Step 1: Test** `tests/test_sidebar_app.py`:
  - `test_tabs_in_cvat_order`: tên tab = `["Objects", "Labels", "Issues", "Frame lân cận"]`.
  - `test_neighbors_tab_toggle`: `app.set_neighbors_tab(False)` → 3 tab, setting lưu `False`; bật lại → 4 tab, đứng cuối.
  - `test_card_buttons_act_on_their_object`: 2 người; `_on_object_action("occluded", "eye:matphai@1")` → cờ occluded đổi ở người 2 (dùng `s.layer_ctx(1)` để đọc), người 1 không đổi; `_on_object_action("hidden","eye:matphai@1")` → `(1,"matphai") in hidden_objs`.
  - `test_card_edit_blocked_in_qc`: đặt phiên QC như `tests/test_gui_cvat.py` làm; `_on_object_action("keyframe", "eye:mattrai")` và `("outside", ...)` không đổi nhãn (so `s.state()` trước/sau).
  - `test_label_change_returns_focus_to_canvas`: gọi `_on_object_action("label", "eye:mattrai")` sau khi đặt ô chọn sang `matphai` → hai mắt đổi chỗ như `swap_labels` hiện có, và `canvas.focus_set` được gọi (spy như `tests/test_keys_focus.py`).
  - `test_refresh_during_play_does_not_rebuild_cards`: đếm widget con của `app.tree` sau `refresh()`; `app.step(1)` 5 lần → số widget không đổi.
  - `test_hover_on_eye_activates_card`: `app.on_hover(Ev(*tâm mắt phải))` → `app.tree.activated()=="eye:matphai"`; `app.on_leave(None)` → `None`.
  - `test_menu_has_remove`: menu ⋮ có mục chứa `"Remove"`.
  - `test_no_captions_anywhere`: duyệt mọi widget của cửa sổ, không `IconButton` nào có `cap`.
- [ ] **Step 2:** chạy → FAIL.
- [ ] **Step 3: Implement** theo Interfaces. Trong `refresh_objects`: bọc bằng `begin_update()/end_update()`, giữ cách tính `src/star/gone/mark` hiện có, thêm `card={...}` (status = `"đã xoá"` nếu `gone` else `src`; `hidden=_obj_hidden(layer,label)`; `keyframe = f in keys`; `has_prev/has_next` từ `s.eye_keyframes(label)` so với `self.f`; màu từ `look.color_of`). `text` của dòng `eye:` giữ nguyên như hiện nay (test cũ đọc nó).
- [ ] **Step 4:** chạy `test_sidebar_app.py`, `test_gui.py`, `test_parity.py`, `test_gui_cvat.py`, `test_keys_focus.py`, `test_object_hide_lock.py` → PASS. Test cũ chỉ được sửa cách truy cập (ví dụ `item(..., "open")`), không đổi điều được kiểm; ngoại lệ duy nhất là thay đổi có chủ đích ở Task 3.
- [ ] **Step 5: Chạy app** `python -m eyepin gui "C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che"` (dữ liệu công khai), chụp cửa sổ bằng ảnh màn hình của script Tk (`ImageGrab` vùng cửa sổ) để người điều phối xem: thẻ, icon, chữ khi trỏ chuột.

### Task 6: Tài liệu và đối chiếu với CVAT

**Files:**
- Modify: `HUONG_DAN.md` (mục 2 "Gán nhãn", mục 6 "Phím hay dùng": tab Objects dạng thẻ, Hidden/Lock theo đối tượng, tab Frame lân cận bật/tắt), `TASKS.md`, `CLAUDE.md` (dòng module: `gui_sidebar.py`, `assets/icons`, `tools/build_icons.py`).

- [ ] **Step 1:** Cập nhật ba file; ghi rõ icon lấy từ CVAT/Ant Design (MIT), nằm ở `eyepin/assets/icons/`.
- [ ] **Step 2:** Đối chiếu bằng mắt với CVAT trên máy (job #4, dữ liệu công khai, chỉ xem): thứ tự nút, icon từng trạng thái. Ghi chỗ khác (nếu có) vào `TASKS.md`. Nếu Chrome không nối được thì ghi "chưa đối chiếu" và báo người dùng.
- [ ] **Step 3:** Chạy lần lượt mọi file test (`for f in tests/test_*.py`) và báo kết quả từng file.
