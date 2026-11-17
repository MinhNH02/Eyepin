# Danh sách lỗi cần sửa (buglist)

Cập nhật: 2026-11-17. Xếp từ ƯU TIÊN CAO xuống THẤP. Sửa xong mục nào thì đổi `[ ]` thành `[x]` và thêm ✅ ngay đầu mục (người điều phối tick sau khi test qua).

Cách làm (người dùng yêu cầu 2026-11-17): mỗi lỗi giao cho một agent riêng, làm lần lượt (các lỗi cùng đụng `gui.py`/`session.py` nên không chạy song song). Lỗi cao dùng agent mạnh (Opus), lỗi trung bình dùng Sonnet, lỗi thấp gộp theo nhóm. Mỗi agent: tìm nguyên nhân gốc, viết test thất bại trước, sửa, chạy test từng file (máy thiếu bộ nhớ ảo, chạy cả bộ có thể `MemoryError`), ghi báo cáo vào `.superpowers/sdd/bugfix/B<số>-report.md`. Lỗi không tái hiện được thì ghi "không tái hiện" thay vì sửa mò.

Nguồn: review cuối kế hoạch 1 (`.superpowers/sdd/cvat-sidebar/progress.md`), `TASKS.md` mục 3 và mục 8 (rà soát 2026-11-16). Một số mục của TASKS mục 8 có từ trước các đợt sửa gần đây: agent phải tái hiện lại trước khi sửa.

Ngoài phạm vi (cần người dùng quyết, không sửa ở đây): nút frame trước/sau theo bộ lọc; nút "Gửi CVAT" mờ nuốt cú bấm; menu ⋮ chưa có icon; đối chiếu bằng mắt với CVAT thật.

## Ưu tiên CAO (Opus)

- [x] ✅ **B01 — Phím `h` báo sai.** (đã sửa 2026-11-17: `h` ẩn mắt dưới con trỏ thì chọn luôn thẻ mắt đó; 7 test mới `tests/test_bugfix_b01.py`; hệ quả cần biết: bấm `Del` ngay sau `h` giờ xoá mắt vừa ẩn; báo cáo `.superpowers/sdd/bugfix/B01-report.md`) `gui.py` `toggle_eye_hidden` (~1709): `h` ẩn mắt dưới con trỏ rồi báo "bấm h lần nữa để hiện", nhưng bấm lần nữa lại tác động mắt đang chọn trong panel chứ không hiện lại mắt kia. Cách sửa gợi ý: khi `h` ẩn mắt dưới con trỏ thì chọn luôn mắt đó (`select_eye(label, quiet=True)`) để bấm lần nữa hiện lại đúng mắt; thông báo phải đúng sự thật.
- [x] ✅ **B02 — Điểm vắng trong file CVAT bị điền thành (0,0) Outside.** `cvatxml._read_skeleton_points`; `preview.position_at` và `scan` dùng điểm giả này nên báo nhảy giả (đã thấy 10 cảnh báo vàng sai trên XML có điểm Outside). Ảnh hưởng dữ liệu thật khi mở job có nhãn sẵn.
- [x] ✅ **B03 — `Session.end_eye_here` chép cả hai mắt vào `pins[frame]`** (`session.py` ~474): mắt kia thành keyframe ngoài ý muốn.
- [x] ✅ **B04 — Bảng màu điểm ghi đè Color by Instance/Group và đổi màu bằng Enter** (`render._draw_eye`): chỉ áp dụng khi tô theo nhãn, hoặc thêm công tắc.
- [x] ✅ **B05 — Kéo tay cầm (đổi kích thước/xoay) rồi đổi frame bằng phím mũi tên gây `AttributeError` ('NoneType'.items) và kẹt trạng thái kéo.** `go()` cần huỷ kéo đang dở.
- [x] ✅ **B06 — Focus ở ô số frame nuốt Del và Ctrl+Z** (↑/↓ không trả focus về ảnh, `gui.py` ~1124). Đã có `_click_focus` cho chuột; kiểm lại đường phím ↑/↓ và Enter trong ô số frame.
- [x] ✅ **B07 — `Session.load_pins` không "tất cả hoặc không gì"**: NaN, hai khoé trùng, frame chỉ có một mắt bị bỏ âm thầm, toạ độ ngoài ảnh vẫn nhận; docstring sai.

## Ưu tiên TRUNG BÌNH (Sonnet)

- [x] ✅ **B08 — Hoàn tác (Ctrl+Z) sau Del hoặc đổi label không khôi phục ẩn riêng / Pinned** (`hidden_objs`, `pinned_eyes` nằm ngoài lịch sử hoàn tác của `Session`).
- [x] ✅ **B09 — Xoá một người GIỮA phiên làm `hidden_objs` / `locked` / `pinned_eyes` trỏ nhầm người** (chỉ số người dịch lại; xoá người cuối thì đúng).
- [x] ✅ **B10 — Header "khoá tất cả" sai sau khi xoá mắt đang khoá của người thứ 2 trở đi.**
- [x] ✅ **B11 — Bấm một lần không kéo vẫn ghim frame và thêm bước hoàn tác rỗng** (`gui.py` `on_release`, `session.drag_points`).
- [x] ✅ **B12 — `Session.clear_all` (session.py ~528) và Remove annotations (`gui_frames.py` ~92) đếm/ghi undo sai khi bộ đang chọn trống mà bộ khác có ghim.**
- [x] ✅ **B13 — `App._autosave_job` không được huỷ khi đóng** (`gui.py` ~597–651): log có dòng "invalid command name ..._autosave_tick". Cùng nhóm: test phát để lại ~11 callback `after` (`_tick`) chưa huỷ.
- [x] ✅ **B14 — Caps Lock làm hỏng phím tắt chữ** (binding chữ thường `<Control-z>`, `<Control-s>`...). Tái hiện bằng sự kiện giả có bit Lock rồi sửa.
- [x] ✅ **B15 — Tooltip nút Hidden mờ chỉ nhắc tab Labels; nút từng điểm vẫn bật khi điểm không có ở frame hiện tại** (vô hại nhưng gây khó hiểu).

## Ưu tiên THẤP (Sonnet, gộp nhóm)

- [x] ✅ **B16 — Nhóm CVAT/IO** (đã sửa 3/4 mục 2026-11-17, mục `cvatxml` không tái hiện; 16 test `tests/test_bugfix_b16.py`; báo cáo LOW1-report.md): `cvatapi` login trả 200 không phải JSON ném `ValueError` hiện "Lỗi: Expecting value" (cần tiếng Việt); `frames.py` sắp theo chuỗi (`10.jpg` trước `2.jpg`) và ảnh đầu hỏng gây `AttributeError`; `preview` ghi vào thư mục không tồn tại vẫn thoát mã 0 (`__main__.py` ~113 không kiểm `cv2.imwrite`); `cvatxml`: track không có thẻ con nào bị xoá khỏi cây nhưng không tính vào dropped (nghi ngờ, cần tái hiện).
- [x] ✅ **B17 — Nhóm báo cáo sai:** số keyframe khi xuất chỉ đếm track đầu (`session.py` ~902, thông báo "Đã ghi N keyframe"); `finish_job` luôn báo "Đã lưu phiên" kể cả khi lưu lỗi hoặc đang chạy `--pins`; `scan.py` không báo "đứng yên" khi mắt vắng giữa chừng (~149–151).
- [x] ✅ **B18 — Nhóm phím và tài liệu lệch:** `shortcuts._NAMES` thiếu period, comma, greater, less, Return (guide hiện tên Tk thô); `shortcuts.py` đã bị đổi CRLF→LF (đưa về kiểu xuống dòng ban đầu của file gốc nếu các file khác dùng CRLF, giữ nhất quán); `__main__` sinh guide từ `~/.eyepin/settings.json` nên ghi phím cá nhân vào `design/shortcuts.md` (sinh từ mặc định); docstring đầu `gui.py` còn phím cũ.
- [x] ✅ **B19 — Nhóm chuỗi tiếng Anh trong UI:** "Confirm propagation", "Items:", "Sort by", "Manually/Interpolated/Total", tab "Issues"/"Labels", "Make a copy", "Run annotation action". Ghi rõ: người dùng chưa quyết có Việt hoá hay giữ tên CVAT (annotator đã quen CVAT) — agent KHÔNG đổi, chỉ lập danh sách chuỗi và báo lại.

## Phát sinh trong lúc sửa (thêm 2026-11-17)

- [x] ✅ **B20 — Chấm màu ở tab Labels** (`gui_objects.py` ~423 và ~459) dùng chỉ số 0/1 thay vì `obj_id - 1`: ở Color by Instance chấm của matphai khác màu matphai trên ảnh (có từ trước; phát hiện khi sửa B04). Ưu tiên thấp.

- [x] ✅ **B21 — Còn sót sau khi sửa B05 (kéo dở):** Esc giữa lúc kéo không huỷ kéo; bấm `l`, `h`, `H`, `p` giữa lúc kéo không huỷ nên thả chuột vẫn sửa được mắt vừa bị khoá/ẩn; khi phát (Space) `_tick` không bỏ bản nháp vẽ mắt như `go()` làm nên bản nháp đi theo sang frame khác. Ưu tiên trung bình.

- [x] ⛔ **B22 — BỎ, không làm (người dùng 2026-11-17: "không cần thiết lắm").** Sau B06 (cần người dùng quyết):** ↑/↓ trong ô số frame giờ đi MỘT frame rồi trả focus về ảnh, nên giữ ↑ không còn đi liên tục (↑/↓ không phải phím tắt toàn cục); muốn đi tiếp phải dùng ←/→ hoặc F/D. Ngoài ra bấm vào tab của panel phải có thể làm panel giữ focus, khi đó ←/→ đổi tab thay vì đổi frame (chưa sửa).

- [x] ✅ **B23 — Còn sót sau B07 (thấp):** (docstring `session.py` và chuỗi `--pins` đã sửa; còn lại: `preview` vẫn in Traceback khi file ghim hỏng, và câu trong `CLAUDE.md`). Gốc: docstring đầu `session.py` (dòng 6) còn ghi "frame ghim cần đủ cả hai mắt"; chuỗi trợ giúp `--pins` trong `__main__.py` ghi "8 điểm ghim của mỗi mắt" (thật ra 4); lệnh `preview` không bắt lỗi file ghim nên vẫn in Traceback. Thêm vào `CLAUDE.md` câu "frame một mắt nạp như `pin_eye`; cả file `--pins` là một bước hoàn tác".

- [x] ✅ **B24 — Còn sót sau B17/B18 (thấp):** hộp Thông tin, hàng "Keyframe khi xuất" (`gui.py` ~734) vẫn chỉ đếm track đầu của người đang chọn; docstring `gui.py` dòng "Thanh điều hướng" còn nói nút chữ (nay là icon); `shortcuts.py` đang LF (gốc CRLF) — chuyển lại CRLF sau khi phiên khác xong.

## Từ review cuối đợt (2026-11-17, `.superpowers/sdd/bugfix/REVIEW-report.md`)

- [x] ✅ **B25 (Important, hồi quy do B16) — Sắp tên ảnh "tự nhiên" lệch với CVAT** (`frames.py:17-29`): CVAT và script tạo task sắp theo chuỗi (lexicographical), nên với tên không đệm số 0 thì `--xml` ghép nhãn sai ảnh và file xuất sai frame; `load_state` không đối chiếu tên ảnh nên phiên cũ khôi phục lên ảnh khác mà không báo. Sửa: quay về `sorted()`, `load_state` đối chiếu tên ảnh đầu/cuối.
- [x] ✅ **B26 (Important, có từ trước) — `Session.drag_points` còn lỗi kiểu B03:** kéo một mắt ở frame chưa ghim làm mắt kia thành keyframe; ở frame chỉ có keyframe của mắt kia thì lần kéo bị mất, để lại điểm lẻ trong `pins` và một bước hoàn tác rỗng. Cùng loại: `paste_points` dán một mắt (Ctrl+V) còn xoá cờ Occluded/Outside của mắt kia. Sửa: chỉ ghim mắt được kéo/dán (như `_flag_key`).
- [x] ✅ **B27 (Important, hồi quy do B11) — Ngưỡng "chỉ bấm" 3 px tính sau khi nhân độ nhạy chuột** (`gui.py:2290-2293`): độ nhạy thấp hoặc phóng to thì lần chỉnh tinh bị bỏ (không dời, không hoàn tác). Sửa: đo quãng dời trên toạ độ con trỏ thật.
- [ ] **B28 (Minor) — Remove annotations giữ khoá/ẩn/Pinned của người 1** (mắt vẽ lại thừa hưởng; Del thì không giữ — không nhất quán); thông báo "Đã xoá N frame ghim" đếm hai lần khi hai người cùng ghim một frame. Nút khoá label ở tab Labels vẫn khoá theo số thứ tự người (lệch với nút "khoá tất cả" B10).
- [ ] **B29 (Minor) — Tài liệu chưa theo hành vi đã đổi:** `CLAUDE.md` (LayerSet/toggle_lock_all), `HUONG_DAN.md` (Del sau h, `--pins` một bước hoàn tác và luật chặt hơn, Caps Lock, bấm không kéo, Esc/l/h/H/p huỷ kéo); áp các mục "Tài liệu cần sửa" của báo cáo MED-A..D, LOW1, LOW2; tick các dòng tương ứng trong `TASKS.md`; thêm: thư mục ảnh sắp theo chuỗi như CVAT (B25), ngưỡng bấm/kéo 3 px đo trên con trỏ thật (B27), kéo/dán chỉ ghim mắt được kéo (B26).
- [ ] **B30 (Minor) — Còn sót nhỏ:** đóng cửa sổ ở màn đăng nhập không huỷ hẹn giờ của màn đó; Enter bàn phím số (`KP_Enter`) trong ô số frame chưa xử lý.

## Không tái hiện / đã được sửa (ghi lại khi agent xác nhận)

(trống)
