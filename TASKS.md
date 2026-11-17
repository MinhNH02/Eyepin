# EyePin: danh sách việc

Quy tắc: mỗi việc xong là tick `[x]` ngay trong file này, kèm ngày nếu cần. Việc mới phát sinh thêm vào đúng nhóm. Cập nhật lần cuối: 2026-11-17.
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
- [x] Thử nội suy thẳng dáng mắt giữa hai ghim, giữ vị trí do bộ bám tìm (2026-11-17, spike `spike/interp_iou_spike.py`): **không giúp** trên case 01 (IoU 0,61 so với 0,64 của bám tiến); thử thêm 4 biến thể luật chọn phía của bám hai chiều: không hơn luật MVP 3. Chi tiết: mục 5 của `design/2026-11-17-interp-iou-research.md`

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

### Panel phải kiểu CVAT và icon gốc (2026-11-16, thiết kế `design/2026-11-16-cvat-sidebar-icons-design.md`, kế hoạch `-plan.md`; báo cáo `.superpowers/sdd/cvat-sidebar/task-{1,2,3,4,5,5b,6}-report.md`)
- [x] Icon gốc của CVAT / Ant Design (MIT) dựng sẵn thành PNG mặt nạ alpha trắng 16/20/24 px ở `eyepin/assets/icons/` (giấy phép và nguồn: `NOTICE.md`), dựng bằng `python tools/build_icons.py` từ SVG ở `tools/icon_src/`; `eyepin/icons.py` vẽ; không còn phông biểu tượng
- [x] Nút không có chữ cố định, chữ (tiếng Việt + phím tắt) chỉ hiện thành tooltip khi trỏ chuột; thiếu file PNG thì nút lùi về chữ ngắn
- [x] Panel phải có tab `Objects | Labels | Issues | Frame lân cận`; tab Objects là danh sách thẻ đối tượng (`eyepin/gui_sidebar.py`, `ObjectList`, nối bởi `App.tree`): ID, `SKELETON TRACK · trạng thái`, chọn label, menu ⋮, điều hướng keyframe, nút Outside / Lock / Occluded / Hidden / Keyframe / Pinned theo thứ tự CVAT, mục DETAILS 8 điểm mỗi điểm có Outside và Occluded riêng; đầu danh sách: Items, Sort by, khoá/ẩn/thu mở tất cả, "+", thùng rác
- [x] Bấm thẻ = chọn mắt, bấm đúp = phóng vào mắt, bấm phải = menu đối tượng; rê chuột trên mắt sáng thẻ và ngược lại
- [x] Đổi hành vi có chủ ý: Hidden và Lock trên thẻ (và phím `h`, `l`) chỉ tác động MỘT mắt của MỘT người (mắt đang hiện dưới con trỏ, không có thì thẻ đang chọn); `H`, `L` (và nút khoá tất cả: khoá/mở khoá mọi mắt của mọi người) và nút ở tab Labels tác động nhãn mọi người; Del/q/o theo con trỏ trên ảnh (chỉ mắt/điểm đang hiện); bấm ra ngoài ô số frame trả focus về ảnh
- [x] Tab "Frame lân cận" tắt được (F2 > Workspace > "Hiện tab Frame lân cận", mặc định bật; tắt thì không tính ảnh nhỏ)
- [x] Thanh trên: nút frame trước/sau đi theo bộ lọc đang đặt (như ←/→); ◀KF/KF▶ có icon ghép riêng; phóng to và thu nhỏ có icon khác nhau
- [x] Sửa: NumLock không còn biến phím gán lại thành Alt+phím trong F2; thông báo sau khi xoá ghi "Bấm n để vẽ lại mắt này"
- [x] Tài liệu: `HUONG_DAN.md`, `CLAUDE.md` cập nhật theo đợt này (Task 6, 2026-11-17)
- [x] Sửa sau final review (2026-11-17, báo cáo `.superpowers/sdd/cvat-sidebar/final-fix-report.md`, test `tests/test_final_fixes.py`): phím theo con trỏ (Del, h, l, q/o) và phím xoay `, . < >` bỏ qua mắt/điểm đang ẩn; đổi label từ chối khi một mắt khoá, ẩn riêng/Pinned đi theo mắt; xoá mắt quên ẩn riêng/Pinned/khoá đúng người; "+"/Ctrl+N khi đang chọn thẻ người 1 ghim vào người mới; `L`/nút khoá tất cả khoá mọi người; nút Hidden của thẻ mờ khi label ẩn ở tab Labels; bật tab Frame lân cận không ném lỗi CVAT; rê chuột trên thẻ không vẽ lại ảnh nhỏ/dải thời gian; mở DETAILS một thẻ cập nhật nút thu/mở tất cả; một chuỗi phát `_tick` (huỷ khi dừng, đóng); bấm chỗ trống không chọn người khác qua mắt ẩn; `tools/build_icons.py` nạp PyMuPDF lúc dựng (test không cần PyMuPDF)
- [ ] Đối chiếu bằng mắt với CVAT thật: chưa làm (tiện ích Chrome mất kết nối); bố cục lấy từ mã nguồn CVAT v2.75.0. Khi có kết nối, so thứ tự nút và icon từng trạng thái trên job #4 (dữ liệu công khai, chỉ xem)
- [ ] Việc nhỏ hoãn lại (chưa sửa, đáng để ý):
  - rê chuột nối ảnh với thẻ chỉ chạy cho người đang chọn
  - nút từng điểm (Outside, Occluded) vẫn bật khi điểm đó không có ở frame hiện tại (vô hại)
  - nút "Gửi CVAT" khi bị tắt vẫn nuốt cú bấm (tooltip giải thích lý do)
  - `hidden_objs` / `locked` / Pinned có thể trỏ nhầm người sau khi xoá một người GIỮA phiên (chỉ số người dịch lại; xoá người cuối thì đúng)
  - hoàn tác (Ctrl+Z) việc đổi label không đổi lại trạng thái ẩn riêng / Pinned (chúng nằm ngoài lịch sử hoàn tác của Session)
- [~] Việc kế (đã thiết kế), xem `design/2026-11-16-cvat-home-design.md` và `-plan.md`: **màn đăng nhập + nhớ đăng nhập + Đăng xuất rút gọn đã xây 2026-11-17** (mục 7, dòng "Màn đăng nhập là cửa trước"); trang chủ (lưới task có ảnh, nhãn prelabeled, Task 1/2/5/6 còn lại) còn dọn dẹp đầy đủ khi đăng xuất đã xây 2026-11-17 (nút Đăng xuất, Task 4/7, xem dòng "Nút Đăng xuất đầy đủ")
- [x] Sau khi đóng băng mã: vẽ lại `/archify` (người dùng quyết) vì sơ đồ hiện tại chưa có `gui_sidebar.py`, `assets/icons`, `tools/build_icons.py`, rồi cập nhật đường dẫn ở `CLAUDE.md` (2026-11-17: `.archify/architecture-eyepin-flow-20261117-105831/`)

## 4. Cấu trúc, mở rộng
- [x] Sơ đồ kiến trúc bằng `/archify` (`.archify/architecture-eyepin-modules-20261113-155705/`)
- [x] Vẽ lại sơ đồ kiến trúc có `icons.py`, `gui_objects.py`, `gui_frames.py` (2026-11-14)
- [~] Tách `gui.py`: panel Đối tượng và thao tác frame đã tách (`gui_objects.py`, `gui_frames.py`); còn hộp F1/F2 và điều khiển canvas
- [ ] "Đối tượng có kiểu" ở lõi (skeleton, rectangle, polygon, polyline, points) để thêm công cụ vẽ sau này
- [ ] Tách chế độ Shape và Track; 4 điểm ghim là tính năng riêng trong Track; QC (EAR) chạy riêng trên nhãn 8 điểm
- [ ] `git init` cục bộ (không đẩy lên mạng) để có mốc quay lại
- [ ] Viết thiết kế v4 và kế hoạch theo từng pha (chưa có file kế hoạch)
- [ ] Sơ đồ kiến trúc (2026-11-17) chưa ghim bằng chứng mã nguồn (`meta.repository`): cây làm việc còn nhiều thay đổi chưa commit; commit xong thì vẽ lại với `--repo-root`
- [ ] Sơ đồ kiến trúc: giao diện Viewer đang tiếng Anh (`meta.locale: en`, nội dung tiếng Việt); nếu trình bày bằng tiếng Việt thì thêm `meta.translations`

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
- [x] Điểm có màu riêng theo vị trí (8 màu, `render.POINT_PALETTE`, hai mắt dùng chung bảng; chỉ khi Color by Label và mắt chưa đổi màu bằng Enter, B04); tay cầm xoay và đổi kích thước to hơn, viền trắng, đẩy ra xa khoé mắt, vùng bấm rộng hơn (`render.ROTATE_HIT`, `RESIZE_HIT`) để không bấm nhầm vào điểm bên trong (2026-11-16)
- [ ] Đổi kích thước: chưa có giữ tỉ lệ (Shift) và chưa đổi hình con trỏ khi rê lên tay cầm
- [x] Sửa Occluded/Outside (2026-11-16): cờ kế thừa theo keyframe của chính mắt; Q/O ở frame tool tính thành keyframe của riêng mắt đó; nút ở panel dùng phần đang chọn (cả mắt khi chọn dòng mắt), không dùng vị trí chuột cũ
- [x] Báo quay đầu cho người dùng chỉnh tay (2026-11-16): thanh báo ở đáy ảnh khi có đoạn mới (nút Tới đoạn quay đầu, Đóng), dòng trạng thái "QUAY ĐẦU #n (frame a–b)" khi đang ở trong đoạn
- [x] Nối thẳng CVAT local + chế độ QC cho job đã có nhãn mắt (thiết kế `design/2026-11-16-cvat-direct-design.md`, kế hoạch `design/2026-11-16-cvat-direct-plan.md`, ghi chú API thật `design/cvat-api-notes.md`; 347 test qua; mỗi task có review độc lập; Task 7 đã kiểm trên CVAT 2.75.0 thật qua cầu nối: file XML của EyePin được nhận, bản xuất video khớp từng keyframe/cờ/vị trí). Module mới: `frames.py`, `cvatapi.py`, `cvatsource.py`, `qc.py`, `cvatsync.py`, `gui_cvat.py`
- [x] Màn đăng nhập là cửa trước (2026-11-17, người dùng chọn cách A trong ba cách; thiết kế `design/2026-11-16-cvat-home-design.md` mục 9): `python -m eyepin gui` không kèm thư mục ảnh hiện màn đăng nhập (`eyepin/gui_login.py`: `LoginScreen`, `FrontDoor`, `LoginMixin`) trước khi dựng `App`; liên kết "Làm việc không cần CVAT → mở thư mục ảnh"; nhớ **khoá** có hạn bằng DPAPI (`eyepin/cvatlogin.py`, `cvat_login.bin`, mặc định 8 giờ, F2 > Workspace chỉnh 0–72, không bao giờ lưu mật khẩu); còn khoá hợp lệ thì bỏ qua màn (401 xoá khoá, CVAT tắt giữ khoá); menu "Đăng xuất…" (xoá khoá và tên đăng nhập rồi đóng); `CvatClient.token/use_token/whoami`; `App.shutdown` tách khỏi `on_close`; `EyePin.bat`. Test mới: `tests/test_cvatlogin.py` (20), `tests/test_gui_login.py` (40), `tests/test_cvatapi.py` (+8). `--selftest`, thư mục ảnh, `--pins`, `--xml` vào thẳng như cũ. Đã chụp màn hình kiểm giao diện; chạy `python -m eyepin gui` thật mở đúng cửa sổ
- [ ] Thử màn đăng nhập với đăng nhập thật vào CVAT local (cần mật khẩu của người dùng; mới thử với CVAT giả): đăng nhập, ghi nhớ rồi mở lại tool (có bỏ qua màn không), khoá bị huỷ, Đăng xuất. Mới biết `GET /api/users/self` có trên CVAT 2.75 local (trả 401 khi chưa đăng nhập), chưa xem phản hồi có `username` với khoá thật
- [ ] Người dùng quyết: đổi lối tắt Desktop `Eyepin.lnk` (đang trỏ `EyePin_case01.bat`, mở thẳng case 01, bỏ qua màn đăng nhập) sang `EyePin.bat`? Mình chưa đổi vì là lối tắt của người dùng
- [x] Nút Đăng xuất đầy đủ (2026-11-17, người dùng: "làm nút đăng xuất đi"; thiết kế `design/2026-11-16-cvat-home-design.md` mục 9b, kế hoạch gốc Task 4 + 7): nút icon `logout` ngoài cùng bên phải thanh cam (menu vẫn có "Đăng xuất…"); `Session.unsent` (bật ở mọi thay đổi nhãn, undo, redo; tắt sau gửi thành công VÀ đối chiếu khớp; lưu vào file phiên; file cũ chưa có cờ mà có ghim thì coi là chưa rõ); `cvatlogin.cvat_session_files/unsent_sessions/wipe_local` (nhận file phiên CVAT bằng nội dung, KHÔNG tạo `sessions/cvat/`); `LoginMixin.logout`: một hộp xác nhận khi không có gì chưa gửi, job đang mở chưa gửi thì Gửi rồi đăng xuất / Bỏ công này / Huỷ, job khác chưa gửi thì liệt kê và hỏi Xoá luôn / Huỷ; xoá khoá, tên đăng nhập, mọi phiên CVAT, giữ phiên thư mục ảnh và file người dùng tự lưu; xoá lỗi thì báo tên file và không đóng; huỷ tự lưu trước khi xoá; không gọi `POST /api/auth/logout`. Hook `_after_send`/`_send_finished` trong `gui_cvat.py` cho "Gửi rồi đăng xuất". Test mới: `tests/test_logout.py` (38), `tests/test_cvatlogin.py` (+10 → 30); chạy lại các file GUI nặng (`test_gui`, `test_parity`, `test_sidebar_app`, `test_gui_cvat`, `test_final_fixes`...) đều qua. Đã chụp màn hình kiểm nút. Chưa thử với CVAT thật
- [ ] Hộp "Mở từ CVAT…" cũ (đăng nhập lại khi CVAT trả 401 giữa job) chưa có ô Ghi nhớ và chưa dọn khoá đã nhớ; khoá hỏng được xoá ở lần mở tool kế tiếp. Làm gọn khi có trang chủ và hộp đăng nhập nhỏ (kế hoạch Task 5, 6)
- [x] Job chỉ có nhãn mắt trong JSON (track rỗng, toàn Outside) vào chế độ QC thay vì chế độ gán (2026-11-17, kế hoạch trang chủ Task 1): quy tắc dùng chung `qc.is_eye_obj` / `qc.json_has_eyes`, `open_job` đặt `session.qc` theo cả XML lẫn JSON. Test `tests/test_qc.py`, `tests/test_cvatsource.py`; hộp "Xoá nhãn mắt cũ và gán lại" và câu mở job có câu riêng cho ca QC chỉ do JSON (phiên chưa có gì để bỏ, nhãn cũ trên CVAT bị thay khi Gửi). Test `tests/test_gui_cvat.py`
- [ ] Thử GUI với đăng nhập thật vào CVAT local (cần mật khẩu của người dùng): `python -m eyepin gui --cvat http://localhost:8080 --job 5`. Người dùng thử 2026-11-16: lần đăng nhập đầu và mở job 9 chạy được; đăng nhập lại thì lỗi CSRF (đã sửa, dòng dưới); cần thử lại sau khi sửa
- [x] Sửa lỗi "CSRF Failed: CSRF token missing" khi đăng nhập lại (2026-11-16, log CVAT 2.75): CVAT trả khoá và đặt cookie phiên; client bỏ khoá khi đăng nhập lại nhưng còn gửi cookie, nên CVAT xác thực bằng phiên và đòi CSRF cho POST (403). Sau lần đăng nhập hỏng, client còn đọc được (nhờ cookie) mà ghi bị 403. Giờ client không nhận cookie nào (`CvatClient.__init__`); CVAT giả trong test có cookie phiên và CSRF như thật; 3 test mới trong `tests/test_cvatapi.py`
- [x] Review toàn nhánh (2026-11-16): sửa lỗi Critical về số frame (task video mở thành 1 frame, gửi sẽ xoá đối tượng khác), nút Khôi phục chỉ khi đã gửi, lỗi mạng khi bám để nhãn cũ (`Session.stale`), từ chối khi đối tượng không phải mắt nằm trên frame đã xoá hoặc job có tag với nền video; 380 test qua
- [ ] Hỗ trợ task có `start_frame`/`frame_step` (hiện từ chối): số frame trong XML CVAT là số tuyệt đối `data.start_frame + rel*step`, còn JSON/ảnh/`deleted_frames` là số tương đối; cần tách hai danh sách số frame và thử trên một task thật có start_frame > 0
- [ ] Job dài: bám ghim tải ảnh đồng bộ trên luồng chính (cửa sổ đứng, bộ nhớ đệm xám ~424 frame ở 1024×576); cần tải trước/luồng nền và mục "đang tải"
- [ ] Chưa thử trên CVAT thật: task nhiều job, frame đã xoá, job có đối tượng không phải mắt hoặc tag, nút khôi phục, hai người trong một job, sửa trên giao diện web có đổi `updated_date` không (mới biết import có đổi)
- [ ] Áp dụng chế độ QC khi mở thư mục với `--xml`
- [x] Vẽ lại `/archify` (luồng dữ liệu đổi: nguồn ảnh, CVAT API, chế độ QC) và cập nhật đường dẫn ở `CLAUDE.md` (2026-11-17; chế độ QC nằm trong thẻ "CVAT và dữ liệu")
- [x] Đợt sửa sau review toàn nhánh (2026-11-16, báo cáo `.superpowers/sdd/cvat-direct/final-fix-report.md`): số frame job lấy từ `job.start_frame/stop_frame`, từ chối job video/thưa/lệch số; nền có nhãn ngoài phạm vi thì không gửi; đếm đối tượng không phải mắt trước/sau khi gửi; không có nút Khôi phục khi chưa gửi gì; lỗi mạng khi bám đặt `Session.stale` và chặn gửi; Khôi phục nhớ phiên của lần gửi; hỏi trước khi đóng lúc đang bận; frame xoá theo CVAT
- [ ] Quyết cách đánh số frame XML khi task đặt start_frame/frame_step (mã CVAT: XML dùng số tuyệt đối `data.start_frame + r*step`); EyePin đang từ chối loại job này — xem final-fix-report.md
- [ ] Các mục "minor (deferred)" trong `.superpowers/sdd/cvat-direct/progress.md` (đọc trước khi dùng cho dữ liệu công ty)
- [ ] Shape (nhãn một frame, không bám): lõi, vẽ, lưu phiên và xuất file đều chưa có; CVAT chỉ nhận shape khi file nền là export "CVAT for images"
- [ ] `Ctrl+N` (người mới) vẫn ghim 8 điểm cùng lúc; đổi sang bảng Vẽ mắt cho thống nhất
- [ ] Sang frame ở toàn màn hình vẫn khoảng 140 ms (đổ ảnh nền 1,9 triệu điểm ảnh vào Tk, `warpAffine` lập phương, hai ảnh thu nhỏ); phát (Space) ở toàn màn hình sẽ chậm hơn nhịp 120 ms
- [x] Vẽ lại `/archify`: luồng vẽ đổi (`render.draw_overlay` dùng chung cho ảnh và Canvas) (2026-11-17: nêu trong sublabel của `render.py`, nhãn `CanvasPainter` ở `gui.py`)
- [ ] Vẽ lại `/archify` có `cvatlogin.py`, `gui_login.py` và luồng khởi động mới (màn đăng nhập → `App`); sơ đồ `.archify/architecture-eyepin-flow-20261117-105831/` vẽ trước khi có hai module này. Quy tắc của `CLAUDE.md`: thêm module thì vẽ lại, nên làm khi các session khác ngừng sửa mã (gộp một lần)
- [ ] Ghi nguồn gốc từng điểm ghim vào phiên (thay cách nhận ghim K/kéo một điểm bằng "trùng khít bám tiến" của `evaluate.py`)
- [x] MVP 3 (2026-11-17): cột "hai chiều chọn theo độ khớp" trong báo cáo (`tracking.track_backward` + `evaluate.choose`, luật theo spec mục 8 và spike của dự án, không chép mã của đồng nghiệp); chỉ để so sánh, nhãn vẫn bám tiến (test `test_report_never_changes_the_tool_labels`). Case 01, ghim mỗi 10 frame: IoU tb bám tiến 0,57 → hai chiều 0,69; tiêu chí spec (không kém bám tiến) có test trên case 01
- [x] Chỉ số vùng cho chất lượng nội suy (2026-11-17, người dùng chốt: IoU, Dice, Boundary IoU, Precision/Recall; IoU ưu tiên cao nhất): `eyepin/overlap.py`; báo cáo `report` và hộp Thông tin in IoU trước, rồi Dice, Boundary IoU, Precision/Recall, sai số px, kèm "mốc" (IoU khi nhãn đúng lệch 1 px). Nghiên cứu và số đo: `design/2026-11-17-interp-iou-research.md`; spike `spike/interp_iou_spike.py`. Test `tests/test_overlap.py`, `tests/test_evaluate.py`
- [ ] Người dùng quyết: tiêu chí đạt theo IoU (đề xuất: IoU ≥ 0,5 trên ít nhất 80% mẫu mắt mở tại frame ghim bị giấu; bám tiến đang 70%, hai chiều 84% trên case 01 ghim mỗi 10 frame), xem mục 6 của bản nghiên cứu
- [ ] Nhãn đúng sai không quá 1 px cho một phần case 01 (khoảng 20 frame ghim cẩn thận, hoặc hai người ghim độc lập): với ghim thô ±2 px, IoU bị chặn quanh 0,73, nên ngưỡng 0,75 và Boundary IoU chưa dùng được
- [ ] Hộp Thông tin: bảng độ chính xác giờ khoảng 40 dòng mà ô kết quả chỉ cao 26 dòng (cuộn chuột được, chưa có thanh cuộn); `gui.py` đang có session khác sửa nên chưa đụng
- [x] Vẽ lại `/archify` có `overlap.py` và đường bám lùi của `evaluate.py` (gộp vào lần vẽ lại sau khi đóng băng mã) (2026-11-17)
- [x] Sau khi đóng băng mã: vẽ lại `/archify`, cập nhật `CLAUDE.md` (2026-11-17)
- [ ] Sau demo: ghi nguồn gốc từng điểm ghim vào phiên (người bấm, phím K, dán, Propagate) để thống kê sai số không phải đoán
- [ ] Sau demo: người dùng quyết có cho bám hai chiều ghi vào nhãn thật không (đổi quy tắc "không đổi frame trước N"). Căn cứ số đo IoU: mục 4 và 6 của `design/2026-11-17-interp-iou-research.md`
- [ ] Sau demo: đo bề rộng mắt từng frame bằng so khớp mẫu có co giãn ngang (cho cả phát hiện quay đầu lẫn dáng mắt)
- [ ] Người dùng quyết (2026-11-16): lấy phần nào của skill `cvat-facial-tracking-expert` của đồng nghiệp (`Downloads\CVATTraining`) vào EyePin. Đã đọc mã, chưa chạy được. Hợp quy tắc ngay: cột hai chiều cho MVP 3, dấu hiệu mí từ ảnh (`eye_lid_cue`) cho tab Issues, ngưỡng thống kê theo từng mắt cho quét. Cần quyết trước: chế độ hiệu chỉnh từ prelabel (cần job có prelabel, đổi quy tắc "không đổi frame trước N"). Không lấy: ghi PATCH, host server công ty, MediaPipe. Cần hỏi đồng nghiệp trước khi chép mã

## 8. Lỗi từ rà soát 2026-11-16 (chưa sửa; báo cáo của 3 agent: test lõi, test GUI, QA)

Ưu tiên cao:
- [x] Bảng màu điểm ghi đè Color by Instance/Group và đổi màu bằng Enter (`render._draw_eye`, lỗi do đợt màu điểm hôm nay): chỉ áp dụng khi tô theo nhãn, hoặc thêm công tắc. Đã sửa 2026-11-17 (B04): bảng màu điểm chỉ dùng khi Color by Label và mắt chưa có màu riêng (Enter); Instance/Group/màu riêng thì 8 điểm cùng màu mắt (khớp vạch màu của thẻ). Mặc định không đổi. Test `tests/test_bugfix_b04.py`
- [x] Điểm vắng trong file CVAT bị điền thành (0,0) Outside (`cvatxml._read_skeleton_points`); `preview.position_at` và `scan` dùng điểm này nên báo nhảy giả (đã thấy: 10 cảnh báo vàng sai trên XML có điểm Outside). Đã sửa 2026-11-17 (B02): `cvatxml._fill_absent` điền toạ độ CVAT đang giữ (nội suy giữa hai frame gần nhất có điểm đó), vẫn Outside; cây XML không đổi. Test `tests/test_bugfix_b02.py`
- [x] `session.end_eye_here` chép cả hai mắt vào `pins[frame]`, mắt kia thành keyframe ngoài ý muốn (session.py:474). Đã sửa 2026-11-17 (B03): dùng `_flag_key` nên chỉ mắt được kết thúc thành keyframe ở frame đó (mắt kia không đổi); kết thúc được cả khi frame chỉ là keyframe của mắt kia (trước đó báo "chưa có nhãn"). Test `tests/test_bugfix_b03.py`

Ưu tiên trung bình:
- [ ] Bấm một lần không kéo vẫn ghim frame và thêm bước hoàn tác rỗng (gui.py `on_release`, nhánh drag_eye và drag; `session.drag_points`)
- [x] Đang kéo tay cầm đổi kích thước hoặc xoay mà đổi frame bằng phím mũi tên gây `AttributeError` ('NoneType'.items) và kẹt trạng thái kéo; `go()` cần huỷ kéo đang dở. Đã sửa 2026-11-17 (B05): `App._cancel_drag` huỷ mọi loại kéo (tay cầm, điểm, cả mắt, điểm bản nháp, khung vẽ mắt) như CVAT, không ghim, không thêm bước hoàn tác, khung nhìn về như trước khi bấm; gọi khi đổi frame (`go`, nhịp phát), trước mọi lệnh sửa nhãn (`edit_command`: Ctrl+Z, Del, Ctrl+N...) và khi mở thư mục/job khác. Trước đó kéo tới frame có nhãn thì thả chuột ghim ngầm frame mới. Test `tests/test_bugfix_b05.py`
- [x] `session.load_pins` không "tất cả hoặc không gì": NaN, hai khoé trùng, frame chỉ có một mắt bị bỏ âm thầm, toạ độ ngoài ảnh vẫn nhận; docstring đang sai. Đã sửa 2026-11-17 (B07): kiểm hết mọi frame trước khi đổi gì (frame nguyên trong khoảng, không lặp; id 14–29; toạ độ hai số hữu hạn trong ảnh; khoé không trùng, `validate_four`), sai thì ValueError tiếng Việt nêu frame/mắt/điểm và phiên y nguyên (trước đó inf còn ném OverflowError, `turns` in Traceback); frame một mắt nạp như `pin_eye`; cả file một bước hoàn tác, tính lại một lần. Test `tests/test_bugfix_b07.py`
- [x] Focus ở ô số frame (↑/↓ không trả focus về ảnh, gui.py ~1124) làm Del và Ctrl+Z bị nuốt (known issue a). Đã sửa 2026-11-17 (B06): `App._leave_entry` (ô về số frame hiện tại, focus về ảnh, trả "break") cho Enter, ↑/↓, Esc (bỏ số gõ dở), Tab/Shift+Tab (trước đó sang panel phải, ←/→ đổi tab); Enter không còn chạy tiếp phím tắt Enter (đổi màu mắt). ↑/↓ giờ chỉ đi một frame mỗi lần vào ô. Gõ chữ trong ô và ô của hộp phụ vẫn không chạy phím tắt. Test `tests/test_bugfix_b06.py`
- [ ] Caps Lock có thể làm hỏng phím tắt chữ, vì binding là chữ thường (`<Control-z>`, `<Control-s>`); cần kiểm trên máy thật
- [x] NumLock khi gán lại phím trong F2 có thể lưu thành Alt+… (known issue c): đã sửa trong đợt panel phải kiểu CVAT (2026-11-16, xem mục đó), test `tests/test_keys_focus.py::test_numlock_is_not_alt_when_rebinding`
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
- [ ] `test_gui_cvat.py` báo 30 lỗi một lần (2026-11-17 khoảng 12:00) khi chạy từng file toàn bộ nền trong lúc máy nặng (`test_gui` 786 s thay vì khoảng 65 s) và các session khác đang sửa `session.py`, `gui.py`, `gui_objects.py`; chạy lại riêng qua 3/3 lần (47 test). Không lưu được nội dung lỗi nên nguyên nhân CHƯA xác nhận (nghi: mã bị sửa dở giữa lúc chạy, hoặc thiếu bộ nhớ như dòng trên). Lần sau chạy toàn bộ nên ghi ra file đủ nội dung lỗi, không chỉ 3 dòng cuối
- [ ] `App._autosave_job` không được huỷ khi đóng (gui.py:597-609, 639-651): log có 54 dòng "invalid command name ..._autosave_tick"
