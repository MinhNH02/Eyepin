# Danh mục tính năng giao diện gán nhãn của CVAT (đối chiếu với EyePin)

Ghi ngày 2026-11-13 từ CVAT 2.75 chạy trên máy (localhost:8080, task #5, dữ liệu công khai PhysDrive), bằng Claude in Chrome.
Phím tắt và Settings đọc trực tiếp từ hộp thoại F1/F2 của CVAT; phần còn lại là quan sát màn hình. **Chưa ghi:** tab Labels,
tab Issues, hộp Info, hộp Filters, thanh Objects khi có đối tượng (nút lock/hide/occluded từng đối tượng), chế độ Review/Standard,
Run actions, Upload/Export.

Cột "EyePin": CÓ = đã làm, MỘT PHẦN, CHƯA.

## 1. Bố cục
| Vùng CVAT | Nội dung | EyePin |
| --- | --- | --- |
| Thanh trên | Menu, Save, Undo, Redo; điều hướng frame (đầu, lùi 10, lùi 1, phát, tiến 1, tiến 10, cuối), thanh trượt, ô nhập frame, tên file kèm copy/link/xoá frame; Fullscreen, Info, Filters, chọn chế độ (Standard…) | MỘT PHẦN (có điều hướng, undo/redo; chưa Save/Info/Filters/Fullscreen/xoá frame) |
| Thanh công cụ trái | Cursor, Move image, Rotate, Rectangle, Shape đa điểm, Magic (AI), Skeleton, Polygon, Polyline, Points, Mask, Cuboid, Ellipse, Tag… | MỘT PHẦN (chỉ Cursor/kéo; ghim thay cho Skeleton) |
| Khung ảnh | Zoom cuộn chuột, kéo ảnh, lưới, nút xếp lớp (layer stack) góc phải dưới, thanh frame ở dưới | CÓ (zoom, kéo) |
| Panel phải | Tab Objects (Sort by, khoá tất cả, ẩn tất cả, danh sách đối tượng + chi tiết), Labels, Issues; mục Appearance bên dưới | CHƯA (EyePin dùng hàng nút) |

## 2. Appearance (panel phải)
Color by Label/Instance/Group · Opacity · Selected opacity · Outlined borders · Show bitmap · Show projections.
EyePin: độ đặc nhãn, viền, điểm, số điểm, cỡ điểm; chưa Color by, Selected opacity, Outlined borders.

## 3. Settings (F2)
- **Player:** số frame nhảy khi bấm V/C; tốc độ phát; màu nền canvas; reset zoom / vừa ảnh khi đổi frame; xoay tất cả ảnh;
  làm mịn ảnh khi zoom; hiện frame đã xoá. Có thêm Brightness/Contrast/Saturation (EyePin CÓ).
- **Workspace:** tự động lưu (mỗi N phút); hiện mọi track nội suy; luôn hiện chi tiết đối tượng (nội dung chữ: ID, Source, Label,
  Attributes, Descriptions, Dimensions; vị trí và cỡ chữ); zoom thích ứng (trackpad); cắt polygon thông minh; hiện tag trên frame;
  đệm khi zoom vào đối tượng; **cỡ điểm điều khiển**; ngưỡng đơn giản hoá polygon.
- **Shortcuts:** bảng phím gán lại được.
EyePin: chưa có hộp Settings, chưa lưu cài đặt giữa các lần mở.

## 4. Menu (Menu trên cùng bên trái)
Upload annotations · Export job dataset · Remove annotations · Run actions · Open the task · Finish the job. EyePin: Mở thư mục/file, Xuất file import.

## 5. Phím tắt (đọc nguyên từ hộp F1)
- **Chung:** F1 phím tắt, F2 cài đặt, Esc huỷ chế độ, Ctrl+S lưu, Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y hoàn tác/làm lại, Tab (chặn thuật toán),
  Ctrl+Alt+Enter lưới giao diện, Ctrl+E chạy annotation actions.
- **Đối tượng:** Tab/Shift+Tab đối tượng kế/trước, T L khoá tất cả, L khoá một, T H ẩn tất cả, H ẩn một, Q hoặc / Occluded, P pinned,
  K keyframe, O outside, Del / Shift+Del xoá (Shift để xoá cả đối tượng bị khoá), Enter đổi màu, Ctrl+1…9 đổi label (ở dự án này: Ctrl+1 mattrai, Ctrl+2 matphai).
- **Lớp (z-order):** `-`/`_` xuống nền, `+`/`=` lên trước, hai phím một lớp lùi/tiến.
- **Sao chép/nhân:** Ctrl+C, Ctrl+V, Ctrl+B nhân đối tượng sang các frame sau (Propagate), N lặp lại lần vẽ trước, Shift+N vẽ lại.
- **Nhóm/gộp:** G nhóm, Shift+G bỏ nhóm, M gộp, Alt+M tách, J nối, Alt+J cắt (polygon/mask), Brush/Eraser/Polygon/Polygon-remove = Shift+1…4.
- **Xoay:** Ctrl+R / Ctrl+Shift+R xoay hình chữ nhật hoặc cả ảnh.
- **Frame:** F/D frame kế/trước, V/C nhảy theo bước, ←/→ tìm frame thoả bộ lọc, X/B chương trước/sau, Space phát, Alt+Del xoá frame,
  dấu huyền (`) vào ô frame, tìm frame theo tên, R/E keyframe kế/trước của track.
- Chưa có phím: snap to contour, snap to point, simplify polygon (không cần cho mắt).
EyePin: có F/D, ←/→, Shift±10, Home/End, Space, C/V (frame ghim), K, Q, O, H, Ctrl+Z/Y, Delete; khác nghĩa ở C/V, ←/→, H.

## 6. Hướng phát triển đề xuất (chờ người dùng chốt thứ tự)
1. **Khung giao diện kiểu CVAT:** thanh công cụ trái, ảnh giữa, panel phải (Objects, Labels, Appearance); dọn hàng nút.
2. **Panel Objects:** mỗi skeleton mắt là một dòng (ID, label, lock, hide, occluded, pinned, keyframe), mở ra thấy 8 điểm; chọn đối tượng; sắp xếp.
3. **Hộp Settings và Shortcuts:** lưu vào file; gán lại phím; đặt phím trùng CVAT.
4. **Phím trùng CVAT:** đổi C/V/←/→ về nghĩa CVAT, thêm Tab, L, P, R/E, Ctrl+C/V/B, Ctrl+S, Ctrl+1/2, Enter đổi màu, F1/F2.
5. **Công cụ khác (sau này):** Rectangle, Polygon, Polyline, Points, tag, nhóm/gộp/tách, xoay ảnh, Filters, Info, Review/Issues, import trực tiếp vào CVAT.
Nên thiết kế lõi theo kiểu "đối tượng có kiểu" (skeleton, rectangle, polygon...) để thêm công cụ sau mà không viết lại; hiện lõi chỉ biết hai skeleton mắt.

## 7. Khảo sát bổ sung (2026-11-13, CVAT local job #3 có hai track skeleton mắt)

**Dòng đối tượng trong panel Objects** (mỗi skeleton một thẻ, màu theo label): huy hiệu ID · loại ("SKELETON TRACK") · ô chọn label · nút ⋮.
Hàng nút thứ nhất: keyframe đầu / keyframe trước / keyframe kế / keyframe cuối. Hàng thứ hai: Outside · Lock · Occluded · Hidden · **Keyframe (ngôi sao)** · Pinned.
Mục "PARTS" mở ra từng điểm (14 [POINTS], 15 …), mỗi điểm có hàng nút riêng (không có Pinned).
Menu ⋮: Create object URL · Make a copy · Propagate · To background · To foreground · To one layer backward · To one layer forward · Move to layer… · Remove · Run annotation action.
Chọn một đối tượng: hiện khung nét đứt quanh skeleton, **tay cầm xoay (chấm trắng phía trên khung)**, nhãn chữ "MATTRAI 1 (FILE)" = label + ID + nguồn.

**Info (nút trên header):** Overview (Assignee, Start frame, Stop frame, Frames) và bảng Annotations statistics theo từng label và từng điểm: số theo loại hình
(Rectangle, Polygon, Polyline, Points, Ellipse, Cuboid, Skeleton, Mask, Tag) cùng ba cột **Manually / Interpolated / Total** (ví dụ 13 / 87 / 100).

**Filters:** hộp truy vấn gồm hai phần "Objects" và "Elements", mỗi phần có "Add rule" và "Add group"; nút Clear filters / Cancel / Submit.
Bộ lọc áp lên danh sách đối tượng và canvas (không chỉ để nhảy frame).

**Chưa đọc:** tab Labels, tab Issues, chế độ Review, các hộp Upload/Export/Run actions, Settings → Shortcuts (gán lại phím).

Đối chiếu EyePin sau đợt này: có ID (#1, #2) và loại "skeleton track", ngôi sao keyframe bấm được, xoay nhãn bằng tay cầm hoặc phím, khoá/ẩn từng mắt,
Occluded/Outside; chưa có Propagate, Make a copy, Move to layer, thống kê Manually/Interpolated trong Info, bộ lọc theo luật.

**Thử xoay label trên CVAT local (2026-11-13, job #3, đã Ctrl+Z, không Save):** chọn skeleton → khung chữ nhật thẳng (bốn góc nét đứt) và chấm tay cầm
phía trên giữa cạnh trên. Kéo tay cầm: cả skeleton xoay quanh tâm khung; thả ra khung tính lại thẳng theo hình mới, tay cầm vẫn ở giữa phía trên.
Nhãn chữ đổi từ "MATTRAI 1 (FILE)" sang "MATTRAI 1 (MANUAL)". Xoay ở frame nội suy (frame 5): keyframe từ 0/9 thành 9/9 (skeleton và 8 điểm).
Ctrl+Z trả lại đúng như cũ (0/9, FILE).
