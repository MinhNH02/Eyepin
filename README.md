# eye_label_tool

Tài liệu để phát triển tool local gán nhãn hai skeleton mắt `mattrai` (14–21) và `matphai` (22–29) qua API CVAT.

## Trong thư mục này

| Đường dẫn | Nội dung |
| --- | --- |
| `guideline/VF50_guideline_hocvien_v1.3.md` | Bản sao guideline học viên v1.3 (chỉ text). Hai link ảnh trỏ về `week2\images`. |
| `guideline/guideline_cvat_2026-07-14.md` | Tài liệu "DMS Landmark" lấy từ guide của project trên CVAT, đã sửa lỗi OCR. Phụ lục A: chỗ OCR không chắc. Phụ lục B: khác biệt với v1.3. |
| `guideline/guideline_cvat_2026-07-14_ocr_raw.txt` | Text OCR gốc, chưa sửa, để đối chiếu. |
| `design/2026-11-13-eye-label-tool-design-v3.md` | **Bản thiết kế hiện hành (nháp, chờ duyệt):** không dùng model, vẽ bằng 4 điểm ghim, ước lượng khoé mắt bị che, ghi nhãn bằng file import. |
| `design/2026-11-12-eye-label-tool-design-v2.md`, `design/2026-11-12-eye-label-tool-design.md` | Hai bản thiết kế cũ, đã bị thay. Giữ để đối chiếu. |
| `spike/` | Bản demo dùng một lần ngày 2026-11-12 (hai hướng trên 200 frame liên tiếp) và kết quả trong `spike/out/`. Không phải mã sản phẩm. |
| `design/design-notes.md` | Ghi chú thiết kế: vấn đề, ba tính năng, điều đã chốt, đề xuất chưa xác nhận, câu hỏi còn mở. |
| `design/cvat-keyframe-behaviour.md` | Keyframe của CVAT vận hành thế nào, đọc từ mã nguồn bản 2.75, và hệ quả cho tool. |
| `design/mockups/` | Bản phác màn hình chỉnh gợi ý và hình minh hoạ cách suy 4 điểm còn lại. |

## Ở chỗ khác

- **Mã nguồn:** `C:\Users\minhf\Documents\VinAI\Task\week2\tools\` (`eye_prelabel.py`, `validate_eye_skeletons.py`, `fetch_guide_text.ps1`, thư mục `models`).
- **Bản gốc guideline v1.3:** `C:\Users\minhf\Documents\VinAI\Task\week2\` (file `.docx`, `.md` và thư mục `images`). Không chép `.docx` và ảnh sang đây vì chúng chứa ảnh tài xế thật.
- **Dữ liệu thử:** CVAT local `http://localhost:8080`, project `eyes_label`: task #2 (200 ảnh rời), task #3–#4 (200 frame liên tiếp), task #5–#9 (năm trường hợp hiếm, 715 frame). File nguồn ở `C:\Users\minhf\Downloads\dms_build\` (thư mục `cases` chứa năm trường hợp hiếm).

## Quy tắc dữ liệu

- Từ 2026-11-12: ảnh từ CVAT công ty được lưu trên ổ đĩa của máy, nhưng không được đưa lên mạng hay GitHub.
- Không đặt file ảnh nào có mặt tài xế thật vào thư mục này.
