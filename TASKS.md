# EyePin: danh sách việc

Quy tắc: mỗi việc xong là tick `[x]` ngay trong file này, kèm ngày nếu cần. Việc mới phát sinh thêm vào đúng nhóm. Cập nhật lần cuối: 2026-11-16.
`[x]` xong và đã có test hoặc đã kiểm · `[~]` làm một phần · `[ ]` chưa làm.

## 1. Lõi tính toán
- [x] Suy 8 điểm mỗi mắt từ 4 điểm ghim theo tỉ lệ guideline v1.3 (`geometry.derive`)
- [x] Bấm 4 điểm theo thứ tự tuỳ ý, tự gán vai trò và tự chia hai mắt theo vị trí x (`assign_roles`, `split_eyes`)
- [x] Ước lượng khoé mắt bị che khi quay đầu từ 3 điểm còn lại (`estimate_hidden_corner`)
- [x] Đọc, ghi file CVAT 1.1 (shape và track), giữ nguyên nhãn khác (`cvatxml`)
- [x] Xem trước đúng như CVAT nội suy (`preview.position_at`)
- [x] Bám mắt giữa các frame bằng so khớp vùng ảnh, tinh chỉnh dưới pixel, chỉ đi về phía sau (`tracking`)
- [x] Chọn ít keyframe nhất để nội suy CVAT lệch không quá 2 px (`reduce_keyframes`)
- [x] Quét nhãn có sẵn: luật đỏ (thứ tự khoé, mí đảo, bắt chéo, ngoài khung), luật vàng (nhảy, keyframe thiếu, đứng yên)
- [x] Luật EAR trong quét: mắt gần nhắm, mắt mở rộng bất thường, độ mở nhảy đột ngột
- [x] Đo Lucas-Kanade với matchTemplate trên 200 frame PhysDrive (`spike/lk_vs_template.py`): LK không tốt hơn, giữ matchTemplate
- [ ] Đo lại LK với matchTemplate trên đoạn quay đầu (case 01) khi có điểm ghim của người dùng
- [ ] Chỉnh ngưỡng EAR (`EAR_CLOSED/WIDE/JUMP`) theo nhãn thật; hiện chỉ là điểm xuất phát
- [ ] EAR đối chiếu với ảnh (bắt "mắt đã chớp mà nhãn còn mở"): cần thêm bằng chứng từ ảnh
- [ ] Đo sai số ước lượng khoé bị che trên frame quay đầu thật (cần ~40 frame người dùng ghim ở task #5); chỉnh công thức và bán kính vòng sai số (4,5 px)
- [x] Ghim từng mắt riêng ở hai frame khác nhau (2026-11-15): frame ghim có thể chỉ có một mắt; track mỗi mắt bắt đầu từ frame ghim đầu của nó, giảm keyframe riêng từng mắt (ví dụ 56 và 80 thay vì 97 dùng chung)
- [ ] Chia đoạn theo người (nhiều người trong một job), người dùng tự xác định khoảng frame
- [ ] Bám có thể đổi dáng mắt (hiện chỉ dời mắt, chớp và nhắm làm điểm khớp tụt)

## 2. Phiên làm việc và dữ liệu
- [x] Ghim, bỏ ghim, kéo điểm, Undo/Redo 100 bước
- [x] Cờ Occluded/Outside theo frame ghim, chép sang frame sau như CVAT
- [x] Kéo thả điểm hoặc cả mắt ở frame bất kỳ có nhãn (frame đó tự thành frame ghim, một bước hoàn tác)
- [x] Sao chép, dán nhãn giữa các frame (Ctrl+C, Ctrl+V)
- [x] Lưu phiên (Ctrl+S), tự lưu mỗi 2 phút khi có thay đổi, hỏi khôi phục khi mở lại, ghi nguyên tử
- [x] Xuất file import cho CVAT (Ctrl+Shift+S)
- [x] Ảnh chỉ giữ trong RAM (tối đa 40 frame), không ghi ảnh ra đĩa
- [ ] Lưu lịch sử hoàn tác vào file phiên (hiện mở lại thì mất Ctrl+Z)
- [ ] "Lưu thành…" ra đường dẫn tuỳ chọn
- [ ] Import thẳng vào CVAT từ cửa sổ (hiện xuất file rồi import tay)
- [ ] Test giữ nguyên nhãn không phải mắt khi import (cần project local có thêm label)

- [x] Đối chiếu tool với CVAT trong Docker (`tests/verify_vs_cvat.py`, job #5 trống): nội suy, cờ, keyframe, xoay và kéo điểm, quét, số keyframe — 6/6 đạt (2026-11-13)
- [x] Sửa lỗi tìm được nhờ đối chiếu: CVAT xuất bỏ điểm Outside khỏi skeleton nên `scan` lỗi KeyError; `cvatxml.parse` giờ điền lại điểm Outside
- [ ] Đối chiếu với CVAT trên dữ liệu có ghim thật đặt đúng trên mắt (verify_vs_cvat dùng điểm ghim giả; bộ bám nhiễu nên ra 97/210 keyframe, số thật sẽ ít hơn)
- [ ] Đối chiếu đường shape (không chỉ track) và nhãn khác mắt còn nguyên sau import

## 3. Giao diện (kiểu CVAT)
- [x] Thanh ngang trên: Menu, Lưu, Hoàn tác, Làm lại, điều hướng frame, Phát, nhảy keyframe
- [x] Nhóm bên phải có chữ nhỏ dưới biểu tượng: Thông tin, Toàn màn hình (F11), Lọc, Hiển thị
- [x] Thanh công cụ dọc bên trái chỉ biểu tượng, có chú thích khi rê chuột
- [x] Điều khiển canvas: Con trỏ, Dời ảnh, Phóng to, Thu nhỏ, Vừa khung, Xoay ảnh 90° hai chiều
- [x] Zoom bằng cuộn chuột, dời ảnh bằng chuột phải, giữa hoặc công cụ Dời ảnh
- [x] Hộp hỏi khi đóng tool còn thay đổi chưa lưu (2026-11-16): Có = lưu rồi thoát, Không = thoát bỏ thay đổi, Huỷ = ở lại; lưu lỗi thì không thoát; mở bằng `--pins` chỉ hỏi "vẫn thoát?" vì không có file phiên. `App.confirm_close`, `tests/test_close_confirm.py`
- [x] Lưới ảnh và chỉnh màu như hộp Image setups của CVAT (2026-11-16, khảo sát annotator; thiết kế `design/2026-11-16-grid-color-design.md`, kế hoạch `design/2026-11-16-grid-color-plan.md`): nút `^` giữa mép dưới khung ảnh / `Ctrl+G`; lưới (phím `g`, Size 1–1000, tự thưa khi hai đường gần hơn 8 px màn hình, màu, Opacity); Brightness/Contrast/Saturation theo % và Gamma như CVAT (giá trị lưu theo thang cũ về mặc định kèm thông báo); thước theo trục mắt đang chọn; toạ độ ảnh và khoảng cách tới điểm gần nhất ở góc phải dòng trạng thái. Module `eyepin/imagefx.py`; `tests/test_imagefx.py`, `tests/test_image_setups.py`. Đo `spike/perf_view.py` trên case 01 (khung vẽ 1498×817): trước khi sửa sang frame 67–85 ms, kéo điểm 15–21 ms; sau, lưới tắt 50–66 ms và 10–19 ms, lưới Size 100 49–86 ms và 9–17 ms, lưới Size 1 phóng ×8 78 ms và 10 ms (dao động giữa các lần chạy lớn hơn chênh lệch; `render_base` thêm 0,2 ms khi bật lưới)
- [x] Sửa EyePin vẽ ảnh lệch nửa pixel so với CVAT (2026-11-16): đo trên CVAT 2.75 local, pixel i phủ [i, i+1) (`design/cvat-api-notes.md`, mục "Quy ước pixel"); `render.warp_image` bù nửa pixel. Ảnh nhỏ frame trước/sau (`render_thumb`) chưa bù, sai tối đa nửa pixel của ảnh nhỏ
- [ ] Người dùng quyết: nhãn làm bằng EyePin trước ngày sửa lệch nửa pixel (2026-11-16) nằm lệch (−0,5; −0,5) px so với ảnh khi mở trên CVAT; có cần dời lại các nhãn đó không
- [x] Độ nhạy chuột (2026-11-16, nhiều người dùng than chuột quá nhạy): Cài đặt (F2) > Workspace > "Độ nhạy chuột khi kéo", 0,1–3 lần, mặc định 1 = như cũ; nhân quãng chuột kéo kể từ chỗ bấm (kéo điểm, kéo cả mắt, xoay, vẽ khung, dời ảnh); cuộn chuột zoom vẫn chỉnh bằng "Hệ số zoom mỗi nấc". `tests/test_mouse_speed.py`
- [ ] Phím tắt tăng giảm độ nhạy chuột ngay khi đang gán nhãn (hiện chỉ chỉnh trong F2)
- [x] Khung ảnh co giãn theo cửa sổ; panel phải cố định rộng 350 px
- [x] Ba màu cam #FF6600, nền giấy, chữ đen (`theme.py`)
- [x] Panel Đối tượng: #ID, loại "skeleton track", cột ★ keyframe bấm được, khoá, ẩn, Occluded, Outside
- [x] Xoay label: tay cầm phía mí trên (kéo), phím `,` `.` (1°) và `<` `>` (5°)
- [x] Xoay label giống CVAT (đã thử trên CVAT local 2026-11-13): tâm xoay là tâm khung bao thẳng, tay cầm trên cạnh trên khung, khung góc nét đứt và tên "MATTRAI #1"; xoay ở frame nội suy thì cả 8 điểm thành keyframe
- [x] Bộ lọc frame (ghim, cần ghim, có Occluded/Outside, đỏ, vàng, chưa có nhãn); ←/→ nhảy frame thoả
- [x] Hộp Thông tin job
- [x] Lớp hiển thị: ảnh, từng mắt, viền, điểm, số điểm; cỡ điểm, độ đặc, độ sáng, tương phản, bão hoà; đổi mắt nằm trên
- [x] Ẩn/hiện toàn bộ nhãn
- [x] Mắt đầu hiện ngay (8 điểm, màu cam) sau khi bấm đủ 4 điểm, không chờ đủ 8 điểm hai mắt
- [x] Cài đặt (F2): Player, Workspace, Phím tắt gán lại được; guide phím tắt (F1) tách riêng, sinh ra `design/shortcuts.md`
- [x] Phím tắt đổi theo CVAT (F/D, V/C bước, R/E keyframe, ←/→ lọc, L, H, Tab, Ctrl+1/2, Q, O, K, Ctrl+Z…)
- [x] Thẻ đối tượng: nút nhảy keyframe đầu/trước/kế/cuối và ngôi sao ghim/bỏ ghim (2026-11-13)
- [x] Thẻ đối tượng: thuộc tính Pinned và hàng nút riêng cho từng điểm
- [x] Menu ⋮ của đối tượng: Make a copy, Propagate, đưa lên hoặc xuống lớp, Remove, Run annotation action
- [x] Thống kê Manually / Interpolated / Total và số keyframe khi xuất trong hộp Thông tin
- [x] Xoá label (2026-11-15): Delete xoá mắt đang chọn khỏi mọi frame (Shift+Del xoá cả mắt khoá), nút thùng rác, menu ⋮; "Kết thúc nhãn từ frame này" đánh Outside cả 8 điểm; ghim lại mắt đã xoá chỉ cần 4 điểm; hoàn tác được; CVAT thật nhận đúng (V9)
- [x] ID và track như CVAT (2026-11-15): mỗi mắt là một đối tượng có ID thật (đánh khi ghim, 1 rồi 10 rồi 19… vì CVAT tính cả 8 điểm con; đã kiểm giao diện CVAT hiện đúng 1 và 10), lưu trong phiên và file xuất, đọc lại từ file nhãn, ID đã xoá không dùng lại; keyframe, ngôi sao, điều hướng keyframe và phím K theo từng đối tượng; mỗi mắt bám độc lập
- [x] Nhiều đối tượng cùng label, nhiều người trong một job (2026-11-15): `Layer` (một bộ mattrai + matphai) trong `Session`; nút "+" hoặc Ctrl+N tạo người mới với ID mới (1, 10, 19, 28…); bấm mắt hoặc dòng của người nào thì thao tác lên người đó; khoá, Pinned theo từng người; xuất nhiều track mỗi label; CVAT thật nhận đúng (V11)
- [ ] Đối tượng từ file nhãn có sẵn (nhiều track mỗi label) chưa nạp thành đối tượng sửa được: mới chỉ hiển thị
- [ ] Bộ lọc theo luật (Add rule, Add group) cho Objects và Elements
- [x] Tab Labels và tab Issues (chưa khảo sát CVAT)
- [x] Kiểu "Color by" Label / Instance / Group, Outlined borders, Selected opacity
- [x] Tuỳ chọn "xoay tất cả ảnh" (Settings → Player)
- [ ] Lưu hướng xoay ảnh giữa các lần mở
- [ ] Phím tắt cho công cụ Con trỏ và Dời ảnh
- [ ] Thử tay toàn bộ giao diện trên máy người dùng (mới kiểm bằng test và ảnh chụp)

- [x] Tái hiện từ CVAT (2026-11-14, xem `design/cvat-parity.md`): Sort by, khoá/ẩn/thu gọn tất cả, đổi label (hoán đổi trái/phải), Pinned, Make a copy, Propagate (hướng, số bản sao, khoảng frame), đổi lớp, Remove, URL đối tượng, đổi màu (Enter)
- [x] Selected opacity, Color by (Label/Instance/Group), Outlined borders + màu, chữ cạnh mắt (nội dung, cỡ chữ)
- [x] Menu: Remove annotations, Run actions, Finish the job; hàng tên frame (sao chép tên, đường dẫn, xoá/khôi phục frame, tìm theo tên); Show deleted frames; Rotate all images; focused object padding; hệ số zoom
- [x] Đối chiếu CVAT thêm V7 (Propagate) và V8 (hoán đổi label): 8/8 đạt
- [ ] Bộ lọc theo luật (Add rule, Add group) cho Objects và Elements (mới có bộ lọc chọn một)

- [x] Tốc độ (2026-11-14): sửa một frame ghim chỉ tính lại đúng đoạn bám của nó và ảnh xám đệm trong RAM: xoay nhãn bằng phím từ 1,4 s xuống khoảng 40 ms; kéo chuột gộp sự kiện để không bị trễ
- [x] Vẽ mượt (2026-11-15): ảnh nền dựng một lần, kéo điểm và xoay nhãn chỉ gửi cho Tk mảnh ảnh thay đổi quanh mắt (vẽ nhẹ từ khoảng 30 ms xuống khoảng 10 ms); zoom và dời ảnh dùng vẽ nhẹ; ảnh thu nhỏ và dải thời gian cập nhật sau khi ngừng thao tác
- [ ] Chạy bám trong luồng nền khi đổi nhiều frame ghim cùng lúc (hiện vẫn chạy ngay trên luồng giao diện)

## 4. Cấu trúc, mở rộng
- [x] Sơ đồ kiến trúc bằng `/archify` (`.archify/architecture-eyepin-modules-20261113-155705/`)
- [x] Vẽ lại sơ đồ kiến trúc có `icons.py`, `gui_objects.py`, `gui_frames.py` (2026-11-14)
- [~] Tách `gui.py`: panel Đối tượng và thao tác frame đã tách (`gui_objects.py`, `gui_frames.py`); còn hộp F1/F2 và điều khiển canvas
- [ ] "Đối tượng có kiểu" ở lõi (skeleton, rectangle, polygon, polyline, points) để thêm công cụ vẽ sau này
- [ ] Tách chế độ Shape và Track; 4 điểm ghim là tính năng riêng trong Track; QC (EAR) chạy riêng trên nhãn 8 điểm
- [ ] `git init` cục bộ (không đẩy lên mạng) để có mốc quay lại
- [ ] Viết thiết kế v4 và kế hoạch theo từng pha (chưa có file kế hoạch)

## 5. Khảo sát CVAT thật (ghi vào `design/cvat-feature-inventory.md`)
- [x] Bố cục, Settings (Player, Workspace), toàn bộ bảng phím tắt, Menu
- [x] Thẻ đối tượng, menu ⋮, tay cầm xoay, hộp Info, hộp Filters
- [ ] Tab Labels
- [ ] Tab Issues và chế độ Review
- [ ] Hộp Upload, Export, Run actions
- [ ] Settings → Shortcuts (cách gán lại phím trong CVAT)

## 6. Câu hỏi cần người dùng hoặc mentor trả lời
- [ ] Luật trạng thái Occluded/Outside: theo guideline v1.3 hay tài liệu CVAT 14/7/2026 (hai tài liệu mâu thuẫn)
- [ ] Guideline gọi mắt trái, mắt phải theo vị trí trên ảnh hay theo phía thật của người lái (tool đang dùng vị trí trên ảnh: x nhỏ là mattrai)
- [ ] Codex có được xem ảnh công ty không
- [ ] Mentor có cho ghi nhãn bằng API vào job thật không (hiện chỉ dùng import)
- [ ] Phiên bản CVAT của server công ty
- [ ] Địa điểm và ngày demo
- [ ] Dữ liệu thử chưa có: video ban đêm, hồng ngoại liên tiếp, kính loá, job nhiều người

## 7. MVP cho demo chiều 2026-11-16 (thiết kế: `design/2026-11-15-headturn-mvp-design.md`, bản 2, chờ duyệt)
- [x] Ghim thô case 01: 24 frame, AI đọc trên ảnh phóng to, sai số khoảng ±2 px, không phải nhãn chuẩn (`spike/out/pins_case01_ai.json`, 2026-11-16)
- [x] Spike đo tín hiệu quay đầu và so sánh các cách dự đoán tại frame ghim bị giấu (`spike/headturn_spike.py`, 2026-11-16); kết quả ở mục 2 của bản thiết kế
- [x] Spike đo model landmark (MediaPipe) trên case 01, chỉ đo, không ghi nhãn (`spike/model_spike.py`, 2026-11-16); kết quả ở mục 15 của bản thiết kế
- [ ] Người dùng quyết: quy tắc cấm model là của ai, và model có được xuất hiện trong demo (cột so sánh của báo cáo) không
- [x] Kế hoạch xây MVP 1 (`design/2026-11-16-headturn-mvp1-plan.md`, 4 task, chờ người dùng xem và chọn cách thực hiện)
- [x] MVP 1: `eyepin/headturn.py` phát hiện đoạn quay đầu theo từng người; hiện ở dải thời gian, tab Issues, lệnh `turns`; mở cửa sổ với `--pins` (xây 2026-11-16, 168 test qua; còn chờ rà soát độc lập và `verify_vs_cvat.py 5` chưa chạy vì CVAT local tắt)
- [x] MVP 2: `eyepin/evaluate.py` báo cáo sai số tại frame ghim bị giấu (đường thẳng CVAT, bám tiến); lệnh `report` và nút trong hộp Thông tin (xây 2026-11-16, 181 test qua). Cột hai chiều thuộc MVP 3, chưa có
- [x] Trang hướng dẫn sử dụng `HUONG_DAN.md` (2026-11-16); phím tắt lấy từ `design/shortcuts.md`. Docstring đầu `eyepin/gui.py` còn ghi phím cũ (P, G, C/V, S, E), cần sửa cho khớp `shortcuts.py`
- [x] Sửa: xoay/sửa nhãn bằng phím làm khung nhìn canh lại nên ảnh dời và phóng theo nhãn; giờ khung tự động chỉ canh lại khi đổi frame, đổi cỡ khung, xoay ảnh, frame vừa có nhãn lần đầu hoặc bấm Vừa khung (2026-11-16, test `test_editing_a_label_never_moves_the_view`)
- [x] Sửa: ghim khi che khoé (7 điểm) giờ vẽ mắt đầu ngay khi đủ 4 điểm của mắt thấy đủ hoặc 3 điểm của mắt bị che khoé (2026-11-16)
- [x] Giật khi khung ảnh lớn (2026-11-16): nhãn giờ vẽ bằng đối tượng vector của Canvas (`gui.CanvasPainter`, như CVAT vẽ SVG), ảnh nền chỉ dựng lại khi đổi frame hoặc khung nhìn. Đo xen kẽ trên case 01, khung 1900×980: kéo điểm 70–87 → 20–31 ms mỗi lần di chuột, vẽ nhẹ 34 → 9–10 ms, sang frame 174–200 → 134–149 ms. Nhãn mờ (< 100%) vẫn vẽ lên ảnh như cũ vì Canvas không có độ trong suốt
- [x] Vẽ từng mắt kiểu CVAT (2026-11-16, người dùng yêu cầu): phím N / nút ghim mở bảng "Vẽ mắt" (Label mắt trái/mắt phải, kiểu Track, Bấm 4 điểm hoặc Kéo khung ra mắt mẫu), mắt vẽ dở màu cam kéo chỉnh được, Apply (nút hoặc N) / Huỷ (Esc). Apply giữ nguyên vai trò điểm (`Session.pin_eye` + `geometry.validate_four`), không tạo keyframe cho mắt kia. Ghim 8 điểm cũ không còn phím mặc định
- [x] Đổi kích thước mắt như CVAT (2026-11-16): mắt đang chọn có 8 tay cầm (4 góc, 4 giữa cạnh) trên khung chọn; kéo cạnh giãn/co một chiều, kéo góc hai chiều, cạnh đối diện đứng yên, mắt kia và khung nhìn không đổi; bấm sát khoé mắt vẫn kéo điểm (`resize_handles`, `App._resize_override`)
- [x] Điểm có màu riêng theo vị trí (8 màu, `render.POINT_PALETTE`, hai mắt dùng chung bảng); tay cầm xoay và đổi kích thước to hơn, viền trắng, đẩy ra xa khoé mắt, vùng bấm rộng hơn (`render.ROTATE_HIT`, `RESIZE_HIT`) để không bấm nhầm vào điểm bên trong (2026-11-16)
- [ ] Đổi kích thước: chưa có giữ tỉ lệ (Shift) và chưa đổi hình con trỏ khi rê lên tay cầm
- [x] Sửa Occluded/Outside (2026-11-16): cờ kế thừa theo keyframe của chính mắt; Q/O ở frame tool tính thành keyframe của riêng mắt đó; nút ở panel dùng phần đang chọn (cả mắt khi chọn dòng mắt), không dùng vị trí chuột cũ
- [x] Báo quay đầu cho người dùng chỉnh tay (2026-11-16): thanh báo ở đáy ảnh khi có đoạn mới (nút Tới đoạn quay đầu, Đóng), dòng trạng thái "QUAY ĐẦU #n (frame a–b)" khi đang ở trong đoạn
- [x] Nối thẳng CVAT local + chế độ QC cho job đã có nhãn mắt (thiết kế `design/2026-11-16-cvat-direct-design.md`, kế hoạch `design/2026-11-16-cvat-direct-plan.md`, ghi chú API thật `design/cvat-api-notes.md`; 347 test qua; mỗi task có review độc lập; Task 7 đã kiểm trên CVAT 2.75.0 thật qua cầu nối: file XML của EyePin được nhận, bản xuất video khớp từng keyframe/cờ/vị trí). Module mới: `frames.py`, `cvatapi.py`, `cvatsource.py`, `qc.py`, `cvatsync.py`, `gui_cvat.py`
- [ ] Thử GUI với đăng nhập thật vào CVAT local (cần mật khẩu của người dùng): `python -m eyepin gui --cvat http://localhost:8080 --job 5`. Người dùng thử 2026-11-16: lần đăng nhập đầu và mở job 9 chạy được; đăng nhập lại thì lỗi CSRF (đã sửa, dòng dưới); cần thử lại sau khi sửa
- [x] Sửa lỗi "CSRF Failed: CSRF token missing" khi đăng nhập lại (2026-11-16, log CVAT 2.75): CVAT trả khoá và đặt cookie phiên; client bỏ khoá khi đăng nhập lại nhưng còn gửi cookie, nên CVAT xác thực bằng phiên và đòi CSRF cho POST (403). Sau lần đăng nhập hỏng, client còn đọc được (nhờ cookie) mà ghi bị 403. Giờ client không nhận cookie nào (`CvatClient.__init__`); CVAT giả trong test có cookie phiên và CSRF như thật; 3 test mới trong `tests/test_cvatapi.py`
- [x] Review toàn nhánh (2026-11-16): sửa lỗi Critical về số frame (task video mở thành 1 frame, gửi sẽ xoá đối tượng khác), nút Khôi phục chỉ khi đã gửi, lỗi mạng khi bám để nhãn cũ (`Session.stale`), từ chối khi đối tượng không phải mắt nằm trên frame đã xoá hoặc job có tag với nền video; 380 test qua
- [ ] Hỗ trợ task có `start_frame`/`frame_step` (hiện từ chối): số frame trong XML CVAT là số tuyệt đối `data.start_frame + rel*step`, còn JSON/ảnh/`deleted_frames` là số tương đối; cần tách hai danh sách số frame và thử trên một task thật có start_frame > 0
- [ ] Job dài: bám ghim tải ảnh đồng bộ trên luồng chính (cửa sổ đứng, bộ nhớ đệm xám ~424 frame ở 1024×576); cần tải trước/luồng nền và mục "đang tải"
- [ ] Chưa thử trên CVAT thật: task nhiều job, frame đã xoá, job có đối tượng không phải mắt hoặc tag, nút khôi phục, hai người trong một job, sửa trên giao diện web có đổi `updated_date` không (mới biết import có đổi)
- [ ] Áp dụng chế độ QC khi mở thư mục với `--xml`
- [ ] Vẽ lại `/archify` (luồng dữ liệu đổi: nguồn ảnh, CVAT API, chế độ QC) và cập nhật đường dẫn ở `CLAUDE.md`
- [x] Đợt sửa sau review toàn nhánh (2026-11-16, báo cáo `.superpowers/sdd/cvat-direct/final-fix-report.md`): số frame job lấy từ `job.start_frame/stop_frame`, từ chối job video/thưa/lệch số; nền có nhãn ngoài phạm vi thì không gửi; đếm đối tượng không phải mắt trước/sau khi gửi; không có nút Khôi phục khi chưa gửi gì; lỗi mạng khi bám đặt `Session.stale` và chặn gửi; Khôi phục nhớ phiên của lần gửi; hỏi trước khi đóng lúc đang bận; frame xoá theo CVAT
- [ ] Quyết cách đánh số frame XML khi task đặt start_frame/frame_step (mã CVAT: XML dùng số tuyệt đối `data.start_frame + r*step`); EyePin đang từ chối loại job này — xem final-fix-report.md
- [ ] Các mục "minor (deferred)" trong `.superpowers/sdd/cvat-direct/progress.md` (đọc trước khi dùng cho dữ liệu công ty)
- [ ] Shape (nhãn một frame, không bám): lõi, vẽ, lưu phiên và xuất file đều chưa có; CVAT chỉ nhận shape khi file nền là export "CVAT for images"
- [ ] `Ctrl+N` (người mới) vẫn ghim 8 điểm cùng lúc; đổi sang bảng Vẽ mắt cho thống nhất
- [ ] Sang frame ở toàn màn hình vẫn khoảng 140 ms (đổ ảnh nền 1,9 triệu điểm ảnh vào Tk, `warpAffine` lập phương, hai ảnh thu nhỏ); phát (Space) ở toàn màn hình sẽ chậm hơn nhịp 120 ms
- [ ] Vẽ lại `/archify`: luồng vẽ đổi (`render.draw_overlay` dùng chung cho ảnh và Canvas)
- [ ] Vẽ lại `/archify` sau khi ghép nhánh `feature/grid-color` và nhánh của kế hoạch cvat-sidebar-icons vào `develop`: thêm module `imagefx.py` (màu, lưới, thước, chữ đo) giữa `gui`/`render`; vẽ trên mã đã ghép để không phải vẽ hai lần
- [ ] Ghi nguồn gốc từng điểm ghim vào phiên (thay cách nhận ghim K/kéo một điểm bằng "trùng khít bám tiến" của `evaluate.py`)
- [ ] MVP 3: bám lùi và bám hai chiều chọn theo độ khớp, chỉ dùng trong báo cáo (không đổi nhãn)
- [ ] Sau khi đóng băng mã: vẽ lại `/archify`, cập nhật `CLAUDE.md`
- [ ] Sau demo: ghi nguồn gốc từng điểm ghim vào phiên (người bấm, phím K, dán, Propagate) để thống kê sai số không phải đoán
- [ ] Sau demo: người dùng quyết có cho bám hai chiều ghi vào nhãn thật không (đổi quy tắc "không đổi frame trước N")
- [ ] Sau demo: đo bề rộng mắt từng frame bằng so khớp mẫu có co giãn ngang (cho cả phát hiện quay đầu lẫn dáng mắt)
- [ ] Người dùng quyết (2026-11-16): lấy phần nào của skill `cvat-facial-tracking-expert` của đồng nghiệp (`Downloads\CVATTraining`) vào EyePin. Đã đọc mã, chưa chạy được. Hợp quy tắc ngay: cột hai chiều cho MVP 3, dấu hiệu mí từ ảnh (`eye_lid_cue`) cho tab Issues, ngưỡng thống kê theo từng mắt cho quét. Cần quyết trước: chế độ hiệu chỉnh từ prelabel (cần job có prelabel, đổi quy tắc "không đổi frame trước N"). Không lấy: ghi PATCH, host server công ty, MediaPipe. Cần hỏi đồng nghiệp trước khi chép mã

## 8. Lỗi từ rà soát 2026-11-16 (chưa sửa; báo cáo của 3 agent: test lõi, test GUI, QA)

Ưu tiên cao:
- [ ] Bảng màu điểm ghi đè Color by Instance/Group và đổi màu bằng Enter (`render._draw_eye`, lỗi do đợt màu điểm hôm nay): chỉ áp dụng khi tô theo nhãn, hoặc thêm công tắc
- [ ] Điểm vắng trong file CVAT bị điền thành (0,0) Outside (`cvatxml._read_skeleton_points`); `preview.position_at` và `scan` dùng điểm này nên báo nhảy giả (đã thấy: 10 cảnh báo vàng sai trên XML có điểm Outside)
- [ ] `session.end_eye_here` chép cả hai mắt vào `pins[frame]`, mắt kia thành keyframe ngoài ý muốn (session.py:474)

Ưu tiên trung bình:
- [ ] Bấm một lần không kéo vẫn ghim frame và thêm bước hoàn tác rỗng (gui.py `on_release`, nhánh drag_eye và drag; `session.drag_points`)
- [ ] Đang kéo tay cầm đổi kích thước hoặc xoay mà đổi frame bằng phím mũi tên gây `AttributeError` ('NoneType'.items) và kẹt trạng thái kéo; `go()` cần huỷ kéo đang dở
- [ ] `session.load_pins` không "tất cả hoặc không gì": NaN, hai khoé trùng, frame chỉ có một mắt bị bỏ âm thầm, toạ độ ngoài ảnh vẫn nhận; docstring đang sai
- [ ] Focus ở ô số frame (↑/↓ không trả focus về ảnh, gui.py ~1124) làm Del và Ctrl+Z bị nuốt (known issue a)
- [ ] Caps Lock có thể làm hỏng phím tắt chữ, vì binding là chữ thường (`<Control-z>`, `<Control-s>`); cần kiểm trên máy thật
- [ ] NumLock khi gán lại phím trong F2 có thể lưu thành Alt+… (known issue c; kiểm lại `shortcuts.py:189`)
- [ ] `session.clear_all` (session.py:528) đếm và ghi undo sai khi bộ đang chọn trống mà bộ khác có ghim

Ưu tiên thấp:
- [ ] Số keyframe khi xuất (session.py quanh 902) chỉ đếm track đầu; thông báo "Đã ghi N keyframe" sai
- [ ] `scan.py` không báo "đứng yên" khi mắt vắng giữa chừng (scan.py:149-151)
- [ ] `cvatxml`: track không có thẻ con nào có frame bị xoá khỏi cây nhưng không tính vào dropped (SUSPECTED)
- [ ] `frames.py` sắp xếp theo chuỗi (`10.jpg` đứng trước `2.jpg`); ảnh đầu hỏng gây AttributeError
- [ ] `cvatapi`: login trả 200 không phải JSON ném ValueError, hiện "Lỗi: Expecting value" (chưa tiếng Việt)
- [ ] `cvatsync._compare` ghép track theo thứ tự chứ không theo ID (SUSPECTED, chưa kiểm với server thật)
- [ ] `finish_job` luôn báo "Đã lưu phiên", kể cả khi lưu lỗi hoặc đang chạy `--pins`
- [ ] `preview` ghi vào thư mục không tồn tại vẫn thoát mã 0 (`__main__.py:113` không kiểm `cv2.imwrite`)
- [ ] Tooltip: `<ButtonPress>` chỉ gắn trên khung, bấm vào nhãn biểu tượng không ẩn chú thích (SUSPECTED)
- [ ] Tay cầm xoay: thân nối bắt đầu từ mép hộp chặt nên nằm trong khung; docstring ghi "cách cạnh trên khung" nhưng đo từ đỉnh hộp mắt; vùng bấm tay cầm đổi cỡ đè lên vùng kéo thân mắt (SUSPECTED); tay cầm xoay không được kẹp vào canvas
- [ ] Bấm chỗ trống không bỏ chọn mắt: chờ quyết hành vi giống CVAT
- [ ] Remove annotations đếm pins của bộ đang chọn nên báo "Chưa có nhãn nào để xoá" dù bộ khác có ghim (gui_frames.py:92)
- [ ] Docstring `gui.py` đầu file còn phím cũ (S quét, E xuất, C/V ghim)
- [ ] Chuỗi tiếng Anh trong UI: "Confirm propagation", "Items:", "Sort by", "Manually/Interpolated/Total", tab "Issues"/"Labels", "Make a copy", "Run annotation action"; nhãn "Keyframe khi xuất" chỉ đếm track đầu
- [ ] `shortcuts._NAMES` thiếu period, comma, greater, less, Return nên guide hiện tên Tk thô
- [ ] `__main__` sinh guide từ `~/.eyepin/settings.json`: chạy lại sau khi gán phím sẽ ghi phím cá nhân vào `design/shortcuts.md`

Tài liệu lệch code:
- [ ] `HUONG_DAN.md`: "Bấm dòng đó để nhảy" (thực ra cần double-click); "Ctrl+Shift+E ... kết quả ở tab Issues" (không tự chọn tab Issues); "chấm trắng" (tay cầm nay là lõi tối viền trắng); "q/o cho điểm đang trỏ" (có fallback); "chỉ localhost" (cũng nhận 127.0.0.1 và ::1); "vàng = cần ghim" trùng màu cảnh báo vàng
- [ ] `design/shortcuts.md` và F1 liệt kê P, Enter, Ctrl+B, Ctrl+R, Alt+Del là "không áp dụng", nhưng `shortcuts.py` (dòng 71-92) vẫn gán chúng: sửa guide hoặc bỏ gán
- [ ] Mục 3 trong TASKS: dòng "docstring gui.py vẫn ghi phím cũ" nên là [~]; "tối đa 40 frame" cần ghi thêm ảnh xám giữ tới GRAY_BUDGET 250 MB; "Import thẳng vào CVAT từ cửa sổ" đã có gửi qua API nên đổi [~]
- [ ] `CLAUDE.md` mục "Chưa có": bỏ hai mắt ghim riêng, kéo điểm ở frame không ghim, import thẳng vào CVAT (các mục này đã có)
- [ ] Mục 7 trong TASKS nhắc tới `.superpowers/...`, thư mục này không đưa lên git (xem ghi chú ở `.gitignore`)

Test và môi trường:
- [ ] `MemoryError` lặp lại khi chạy đầy đủ `test_gui`/`test_parity` (5 lỗi trong lần rà soát) và khi chạy song song có `test_cvatsync`; chạy riêng thì qua. Nghi bộ nhớ tăng dần qua nhiều test trong một tiến trình (chưa chứng minh)
- [ ] `App._autosave_job` không được huỷ khi đóng (gui.py:597-609, 639-651): log có 54 dòng "invalid command name ..._autosave_tick"
