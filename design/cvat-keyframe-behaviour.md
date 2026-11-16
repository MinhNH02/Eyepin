# Keyframe trong CVAT vận hành thế nào

Tra cứu ngày 2026-11-12. Tài liệu chính thức của CVAT chỉ mô tả cách dùng, không nói rõ công thức, nên các
kết luận dưới đây được đọc từ mã nguồn CVAT **bản 2.75** (`C:\Users\minhf\cvat`, cũng là bản đang chạy ở
CVAT local). Chưa bấm thử trên giao diện để tái hiện, và chưa biết server công ty chạy bản nào.

## Quy tắc chung của track

| # | Quy tắc | Nguồn |
| --- | --- | --- |
| 1 | Keyframe là frame mà track có lưu toạ độ. Các frame khác không lưu gì, CVAT tính ra mỗi lần hiển thị. | `cvat-core/src/annotations-objects/track.ts:20`, `:88` |
| 2 | Giữa hai keyframe: toạ độ nội suy **đường thẳng** theo số frame. | `points-track.ts:31-43`; tài liệu "Vocabulary → Interpolation" |
| 3 | Sau keyframe cuối: giữ nguyên vị trí của keyframe cuối cho tới hết job. | `track.ts:569-578` |
| 4 | Trước keyframe đầu: track coi như Outside, không hiện. | `track.ts:577` |
| 5 | Trạng thái Occluded và Outside ở frame giữa **lấy nguyên từ keyframe bên trái**, không nội suy. | `points-track.ts:38-41` |
| 6 | Sửa bất cứ thứ gì ở một frame chưa phải keyframe (kéo điểm, đổi Occluded, đổi Outside) sẽ **tự biến frame đó thành keyframe**. | `track.ts:368-428` |
| 7 | Phím `K` hoặc nút ngôi sao: bật thì ghim vị trí đang nội suy thành keyframe, tắt thì xoá keyframe. | `track.ts:451-478`; tài liệu "Track mode" |
| 8 | Khi export, server nội suy lại theo đúng công thức đường thẳng này. | `cvat/apps/dataset_manager/annotation.py:850-886`, `:1109-1124` |

## Riêng với skeleton

| # | Quy tắc | Nguồn |
| --- | --- | --- |
| 9 | Mỗi điểm của skeleton là **một track con, có danh sách keyframe riêng**. | `skeleton-track.ts:21`, `:44-73` |
| 10 | Kéo **một điểm** chỉ tạo keyframe cho **riêng điểm đó**. Các điểm còn lại của skeleton ở frame ấy vẫn là nội suy. | `cvat-canvas/src/typescript/canvasView.ts:1705`; `cvat-ui/.../canvas-wrapper.tsx:927-941` |
| 11 | Kéo hoặc co giãn **cả skeleton** (bằng khung bao) thì tạo keyframe cho mọi điểm. | `canvasView.ts:1609-1622`, `:1819-1834` |
| 12 | Ngôi sao keyframe của skeleton sáng lên khi **chỉ cần một điểm** có keyframe ở frame đó. | `skeleton-track.ts:208`; `cvat-core/src/object-state.ts:323-326` |
| 13 | Bấm `K` khi trỏ vào khung bao: bật hoặc tắt keyframe cho **tất cả** các điểm. | `object-state.ts:330-338`; tài liệu "Annotation with skeletons" |
| 14 | Nút nhảy tới keyframe trước/sau tính keyframe của bất kỳ điểm nào. | `skeleton-track.ts:232-261` |
| 15 | Trạng thái Outside/Occluded của cả skeleton là "tất cả các điểm đều Outside/Occluded". | `skeleton-track.ts:224-225` |

## Điều này giải thích hiện tượng người dùng gặp

Ví dụ: track mắt có keyframe đủ 8 điểm ở frame 1 và frame 10.

1. Ở frame 4, người dùng kéo 3 điểm. Theo quy tắc 10, chỉ 3 điểm đó có keyframe ở frame 4. Năm điểm còn lại
   vẫn nội suy giữa frame 1 và frame 10.
2. Theo quy tắc 12, frame 4 hiện ngôi sao, trông như đã được ghim đầy đủ.
3. Sau đó người dùng sửa frame 10. Năm điểm chưa ghim ở frame 4 bị kéo theo, dù frame 4 "đã là keyframe".
4. Ba điểm đã ghim ở frame 4 lại đứng yên, nên dáng mắt ở frame 4 bị méo: một phần theo vị trí cũ, một phần
   theo nội suy mới.

Đây khớp với ba điều người dùng mô tả: sửa một keyframe thì frame giữa lệch theo, một số điểm bị di chuyển,
và khó biết mình đã sót keyframe.

## Hệ quả cho thiết kế tool

- **Keyframe do tool ghi luôn đủ 8 điểm của một mắt.** Không bao giờ ghim lẻ từng điểm.
- **Tool hiện trạng thái keyframe theo từng điểm.** Frame mà chỉ một phần số điểm có keyframe được đánh dấu
  là "keyframe thiếu" trên dòng thời gian, kèm nút ghim đủ 8 điểm.
- **"Ghim frame 3" trong hộp hỏi nghĩa là ghim đủ 8 điểm** ở vị trí đang hiển thị.
- **Bản xem trước của tool phải tính đúng như CVAT:** nội suy đường thẳng theo từng điểm, giữ vị trí sau
  keyframe cuối, và lấy Occluded/Outside từ keyframe bên trái.
- **Đề xuất giảm số keyframe vẫn dùng được**, vì nó dựa đúng trên công thức nội suy đường thẳng này.

## Nguồn trên mạng

- Tài liệu "Track mode": https://docs.cvat.ai/docs/annotation/manual-annotation/modes/track-mode-basics/
- Tài liệu "Annotation with skeletons": https://docs.cvat.ai/docs/annotation/manual-annotation/shapes/skeletons/
- Tài liệu "Linear interpolation with one point": https://docs.cvat.ai/docs/annotation/manual-annotation/shapes/annotation-with-points/liner-interpolation-with-one-point/

Không tìm thấy issue nào trên GitHub mô tả đúng hiện tượng "kéo một điểm chỉ ghim một điểm".
