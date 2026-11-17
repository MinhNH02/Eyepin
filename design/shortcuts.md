# Phím tắt của EyePin

Phím mặc định theo CVAT 2.75 khi có hành động tương ứng. Đổi phím trong Cài đặt (F2) → tab Phím tắt; xem nhanh bằng F1.

## Chung

| Hành động | Phím EyePin | Phím CVAT | Ghi chú |
| --- | --- | --- | --- |
| Mở guide phím tắt | F1 | F1 |  |
| Mở cài đặt | F2 | F2 |  |
| Hoàn tác | Ctrl+Z | Ctrl+Z |  |
| Làm lại | Ctrl+Y / Ctrl+Shift+Z | Ctrl+Shift+Z / Ctrl+Y |  |
| Lưu phiên làm việc | Ctrl+S | Ctrl+S | CVAT lưu lên server; EyePin lưu file phiên trên máy (có tự lưu) |
| Xuất file import cho CVAT | Ctrl+Shift+S | — | ghi file XML để import vào job |
| Chạy hành động (Run actions) | Ctrl+E | Ctrl+E |  |
| Quét nhãn có sẵn | Ctrl+Shift+E | — | CVAT không có phím riêng; Ctrl+E mở hộp Run actions |
| Mở một job từ CVAT trên máy (đăng nhập, chọn task và job) |  | — | chỉ CVAT localhost; gán phím trong Cài đặt nếu cần |
| Gửi lên CVAT (thay toàn bộ nhãn của job đang mở, có hỏi trước và đối chiếu sau) |  | — | tắt khi job ở chế độ QC |
| Xoá nhãn mắt cũ và gán lại (rời chế độ QC) |  | — | CVAT chưa đổi gì cho tới khi gửi |
| Xoá toàn bộ nhãn (Remove annotations) |  | — | có hộp xác nhận, hoàn tác được |
| Hoàn tất job (lưu và xuất) |  | — | mục Finish the job trong Menu |
| Huỷ chế độ đang làm (ghim dở) | Esc | Esc |  |

## Frame

| Hành động | Phím EyePin | Phím CVAT | Ghi chú |
| --- | --- | --- | --- |
| Frame kế | f | F |  |
| Frame trước | d | D |  |
| Tiến theo bước (bước đặt trong Cài đặt) | v | V |  |
| Lùi theo bước | c | C |  |
| Frame kế thoả bộ lọc | → | → | không lọc thì đi từng frame |
| Frame trước thoả bộ lọc | ← | ← |  |
| Tiến 10 frame | Shift+→ | — | CVAT không có phím này |
| Lùi 10 frame | Shift+← | — | CVAT không có phím này |
| Về frame đầu | Home | — |  |
| Tới frame cuối | End | — |  |
| Phát / dừng | Space | Space |  |
| Nhảy vào ô nhập số frame | ` | ` |  |
| Frame ghim (keyframe) kế | r | R |  |
| Frame ghim (keyframe) trước | e | E |  |
| Xoá / khôi phục frame hiện tại | Alt+Del | Alt+Del |  |
| Tìm frame theo tên | Ctrl+F | — | CVAT có hộp Search frame by name |

## Đối tượng

| Hành động | Phím EyePin | Phím CVAT | Ghi chú |
| --- | --- | --- | --- |
| Chọn đối tượng kế | Tab | Tab |  |
| Chọn đối tượng trước | Shift+Tab / Shift+Tab | Shift+Tab |  |
| Chọn mắt trái (mattrai) | Ctrl+1 | Ctrl+1 |  |
| Chọn mắt phải (matphai) | Ctrl+2 | Ctrl+2 |  |
| Khoá/mở khoá mắt đang chọn | l | L |  |
| Khoá/mở khoá mọi mắt (mọi đối tượng) | Shift+L | T L | CVAT dùng chuỗi T rồi L |
| Ẩn/hiện mắt đang chọn | h | H |  |
| Ẩn/hiện toàn bộ nhãn | Shift+H | T H | CVAT dùng chuỗi T rồi H |
| Occluded cho điểm (đang chọn hoặc dưới chuột) | q / / | Q hoặc / |  |
| Outside cho điểm | o | O |  |
| Ghim / bỏ ghim frame này (keyframe) | k | K |  |
| Xoá mắt (label) đang chọn | Del | Del | xoá cả đường của mắt đó, hoàn tác được (Ctrl+Z) |
| Xoá mắt đang chọn kể cả khi bị khoá | Shift+Del | Shift+Del |  |
| Kết thúc nhãn từ frame này (Outside) |  | — | đánh Outside cả 8 điểm của mắt đang chọn |
| Pinned: khoá dời nguyên mắt và xoay | p | P |  |
| Nhân nhãn sang N frame sau (Propagate) | Ctrl+B | Ctrl+B |  |
| Đổi màu mắt đang chọn | Enter | Enter |  |
| Hoán đổi mattrai và matphai |  | — | ô chọn label trên thẻ đối tượng của CVAT |
| Phóng vào mắt đang chọn |  | — | nhấp đúp dòng trong panel Đối tượng |
| Sao chép nhãn hai mắt của frame | Ctrl+C | Ctrl+C |  |
| Dán nhãn vào frame hiện tại (thành frame ghim) | Ctrl+V | Ctrl+V |  |
| Xoay mắt đang chọn 1° theo chiều kim đồng hồ | . | — | CVAT xoay bằng tay cầm; Shift = 5° |
| Xoay mắt đang chọn 1° ngược chiều | , | — | Shift = 5° |
| Xoay mắt đang chọn 5° theo chiều kim đồng hồ | > | — |  |
| Xoay mắt đang chọn 5° ngược chiều | < | — |  |

## Ghim / vẽ

| Hành động | Phím EyePin | Phím CVAT | Ghi chú |
| --- | --- | --- | --- |
| Đối tượng mới (người mới): ghim 8 điểm với ID mới | Ctrl+N | — | CVAT: vẽ đối tượng mới bằng công cụ vẽ |
| Vẽ một mắt: chọn label, bấm 4 điểm hoặc kéo khung, chỉnh rồi Apply | n | N | CVAT: vẽ (lặp lại công cụ vẽ trước) |
| Ghim 8 điểm hai mắt cùng lúc (cách cũ) |  | — | gán phím trong Cài đặt nếu cần |
| Ghim khi che khoé (7 điểm) | Shift+N | Shift+N | CVAT: vẽ lại hình đang chọn |

## Hiển thị

| Hành động | Phím EyePin | Phím CVAT | Ghi chú |
| --- | --- | --- | --- |
| Toàn màn hình | F11 | — | CVAT có nút, không có phím mặc định |
| Thông tin job | Ctrl+I | — | CVAT có nút Info |
| Xoay ảnh 90° theo chiều kim đồng hồ | Ctrl+R | Ctrl+R |  |
| Xoay ảnh 90° ngược chiều kim đồng hồ | Ctrl+Shift+R | Ctrl+Shift+R |  |
| Công cụ Con trỏ (kéo nhãn) |  | — | chọn bằng nút trên thanh trái |
| Công cụ Dời ảnh (kéo chuột là dời ảnh) |  | — | chọn bằng nút trên thanh trái |
| Phóng to | + / = | cuộn chuột |  |
| Thu nhỏ | - | cuộn chuột |  |
| Vừa khung (tự động) | 0 | — |  |
| Ẩn/hiện số điểm | i | — |  |
| Điểm to hơn | ] | — | CVAT chỉnh trong Settings |
| Điểm nhỏ hơn | [ | — |  |
| Đổi mắt nằm trên | Shift+T | + / - | CVAT: đưa đối tượng lên/xuống lớp |
| Mở Image setups (lưới, độ sáng, tương phản, bão hoà, gamma) | Ctrl+G | — | CVAT: nút ^ giữa mép dưới khung ảnh |
| Bật/tắt lưới ảnh | g | — | CVAT: ô Image grid trong Image setups |

## Phím CVAT mà EyePin không có (không áp dụng cho skeleton mắt)

| Phím CVAT | Việc |
| --- | --- |
| P | pinned property của đối tượng |
| Enter | đổi màu |
| Ctrl+B | nhân đối tượng sang frame sau (EyePin tự bám theo ảnh) |
| G, Shift+G, M, Alt+M, J, Alt+J | nhóm, gộp, tách, nối, cắt (polygon/mask) |
| Shift+1..4 | công cụ mask |
| Ctrl+R, Ctrl+Shift+R | xoay |
| X, B | chương trước/sau |
| Alt+Del | xoá frame |
| Ctrl+Alt+Enter | lưới giao diện |

## Chuột

- Cuộn chuột: phóng to/thu nhỏ quanh con trỏ. Chuột phải hoặc giữa, hoặc kéo ở chỗ trống: dời ảnh.
- Kéo một điểm: dời điểm đó. Kéo vào thân mắt (không trúng điểm): dời cả mắt. Frame chưa ghim sẽ tự thành frame ghim.
