# EyePin đối chiếu CVAT: bảng tính năng và trạng thái

Lập 2026-11-14 từ khảo sát CVAT 2.75 local (`cvat-feature-inventory.md`). Cột "Loại": **Demo** = cần cho demo phần mắt, **Đầy đủ** = làm để tool giống CVAT như người dùng yêu cầu ("tái hiện từng tính năng"),
**N/A** = không áp dụng cho skeleton mắt (CVAT có nhưng tool không cần). Trạng thái cập nhật cùng `TASKS.md`: `[x]` xong, `[ ]` chưa.

## Header và Menu
| Tính năng CVAT | Loại | Cách làm trong EyePin | Trạng thái |
| --- | --- | --- | --- |
| Menu: Upload annotations / Export job dataset | Demo | Mở file nhãn / Xuất file import | [x] |
| Menu: Remove annotations | Đầy đủ | Xoá toàn bộ frame ghim (có xác nhận, hoàn tác được) | [x] |
| Menu: Run actions | Đầy đủ | Hộp chọn hành động: quét, giảm keyframe, nhân nhãn sang N frame | [x] |
| Menu: Finish the job | Đầy đủ | Lưu phiên rồi mời xuất file import | [x] |
| Menu: Open the task | N/A | Không có máy chủ | — |
| Save, Undo, Redo, điều hướng frame | Demo | | [x] |
| Thanh trượt frame | Đầy đủ | Dải thời gian ở đáy (bấm để nhảy) | [x] |
| Tên file + sao chép tên, sao chép đường dẫn | Đầy đủ | Nút bên cạnh tên frame | [x] |
| Xoá frame / Show deleted frames | Đầy đủ | Đánh dấu frame xoá: bỏ qua khi điều hướng, khôi phục được | [x] |
| Tìm frame theo tên | Đầy đủ | Hộp tìm kiếm cạnh ô số frame | [x] |
| Fullscreen, Info (+ thống kê), Filters | Demo | | [x] |
| Filters theo luật (Add rule, Add group) | Đầy đủ | Bộ lọc có điều kiện trên ID, nhãn, keyframe, trạng thái | [ ] (chưa làm) |
| Chế độ Standard / Review, Issues vẽ vùng | N/A | Không có quy trình review trong tool | — |

## Panel Objects, Labels, Issues
| Tính năng CVAT | Loại | Cách làm | Trạng thái |
| --- | --- | --- | --- |
| Thẻ: ID, loại, keyframe, ★, khoá, ẩn, Occluded, Outside | Demo | | [x] |
| Sort by (ID tăng, giảm, tên label, thời gian cập nhật) | Đầy đủ | Danh sách chọn ở đầu panel | [x] |
| Khoá tất cả, ẩn tất cả (đầu panel) | Đầy đủ | Hai nút và menu thu gọn | [x] |
| Ô chọn label trên thẻ | Đầy đủ | Menu "Đổi nhãn trái/phải" (hoán đổi vai trò hai mắt) | [x] |
| Pinned | Đầy đủ | Mắt pinned không dời nguyên mắt hay xoay được, vẫn sửa từng điểm | [x] |
| Menu ⋮: Make a copy | Đầy đủ | Sao chép nhãn của mắt | [x] |
| Menu ⋮: Propagate | Đầy đủ | Hộp nhập số frame, nhân nhãn sang N frame sau (thành frame ghim) | [x] |
| Menu ⋮: To background / foreground / one layer backward / forward / Move to layer | Đầy đủ | Thứ tự vẽ của hai mắt | [x] |
| Menu ⋮: Remove / phím Del (xoá đối tượng) | Đầy đủ | Xoá mắt khỏi mọi frame; Shift+Del xoá cả mắt khoá; hoàn tác được | [x] |
| Kết thúc đối tượng (Outside từ frame này) | Đầy đủ | Đánh Outside cả 8 điểm | [x] |
| Menu ⋮: Create object URL | Đầy đủ | Sao chép "thư mục#frame#nhãn" | [x] |
| Menu ⋮: Run annotation action | Đầy đủ | Mở hộp Run actions | [x] |
| Phần PARTS: từng điểm và nút riêng | Demo | Dòng điểm, Occluded/Outside theo điểm | [x] |
| Tab Labels: danh sách label, khoá và ẩn theo label | Đầy đủ | Tab "Labels" | [x] |
| Tab Issues: đếm, trước/sau, ẩn, đã xử lý | Đầy đủ | Tab "Issues" dùng kết quả quét (đỏ/vàng) | [x] |

## Appearance, Settings, canvas
| Tính năng CVAT | Loại | Cách làm | Trạng thái |
| --- | --- | --- | --- |
| Opacity, cỡ điểm, viền, số điểm | Demo | | [x] |
| Selected opacity | Đầy đủ | Độ đặc riêng cho mắt đang chọn | [x] |
| Color by Label / Instance / Group | Đầy đủ | Ba kiểu tô màu | [x] |
| Outlined borders (+ màu) | Đầy đủ | Viền đen quanh đường mắt, đổi màu được | [x] |
| Show bitmap, Show projections | N/A | Chỉ cho mask, cuboid | — |
| Enter: đổi màu đối tượng | Đầy đủ | Đổi màu riêng cho mắt đang chọn | [x] |
| Settings Player: bước, tốc độ, nền, vừa khung, làm mịn | Demo | | [x] |
| Settings: Rotate all images | Đầy đủ | Tuỳ chọn giữ hay bỏ hướng xoay khi đổi frame | [x] |
| Workspace: auto save, cỡ điểm | Demo | | [x] |
| Workspace: luôn hiện chữ trên nhãn, nội dung chữ, cỡ chữ | Đầy đủ | Chữ "ID · label · nguồn" cạnh mắt, cỡ chữ chỉnh được | [x] |
| Workspace: focused object padding (zoom vào đối tượng) | Đầy đủ | Nhấp đúp dòng trong panel để zoom vào mắt, đệm chỉnh được | [x] |
| Workspace: adaptive zoom | Đầy đủ | Hệ số zoom mỗi nấc chỉnh được | [x] |
| Workspace: show all interpolation tracks, show tags, đơn giản hoá polygon | N/A | | — |
| Shortcuts: gán lại phím | Demo | | [x] |
| Công cụ vẽ Rectangle, Polygon, Polyline, Points, Cuboid, Ellipse, Tag, Magic, nhóm, gộp | N/A | Ngoài phạm vi mắt (ghi lại trong TASKS "đối tượng có kiểu") | — |


## Đã đối chiếu với CVAT thật (2026-11-14)
- Propagate: hộp CVAT có hướng (←/→), số bản sao (mặc định = số frame còn lại), khoảng FROM–TO; EyePin làm đúng ba thứ đó.
- Pinned: CVAT không cho kéo nguyên skeleton khi Pinned nhưng vẫn kéo được từng điểm; EyePin làm tương tự (cộng thêm chặn xoay).
- Sort by của CVAT: ID tăng/giảm, thời gian cập nhật, tên label. Tab Labels: chấm màu, tên, khoá, ẩn. Tab Issues: đếm, trước/sau, ẩn, đã xử lý.
- Số liệu: `tests/verify_vs_cvat.py` V7 (Propagate) và V8 (hoán đổi label) đạt qua vòng import vào CVAT.

- Nhiều đối tượng cùng label (2026-11-15): CVAT cho tạo đối tượng thứ hai cùng label; EyePin có nút "+" (Ctrl+N), mỗi người một bộ mattrai và matphai với ID 19, 28…; V11 đạt (CVAT có hai track mỗi label).
