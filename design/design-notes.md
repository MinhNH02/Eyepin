# Ghi chú thiết kế — tool gán nhãn mắt (mattrai / matphai)

**Trạng thái: đang trao đổi, chưa phải bản thiết kế đã duyệt.** Ghi lại tới ngày 2026-11-12.
Mỗi mục ghi rõ là *người dùng đã nói* hay *đề xuất chưa được xác nhận*.

## 1. Vấn đề cần giải quyết (người dùng đã nói)

- Vẽ shape tay cho 200 frame quá lâu.
- Dùng track thì nhanh hơn, nhưng CVAT nội suy đường thẳng giữa các keyframe. Sửa một keyframe là các
  frame ở giữa lệch theo, cử động mắt sai và không đạt yêu cầu.
- Hay bị sót hoặc bấm nhầm keyframe, làm các điểm không chuẩn.

## 2. Các tính năng (người dùng yêu cầu)

1. **Prelabel:** tool tự đặt sẵn nhãn mắt.
2. **Hint:** gợi ý các điểm, dùng được cho shape hoặc track, và cho phép người sửa trước khi apply.
3. **Vẽ bằng 4 điểm:** người đặt 14, 16, 18, 20 (mắt trái) hoặc 22, 24, 26, 28 (mắt phải), tool tự suy ra
   4 điểm còn lại. Dùng được cho cả shape và track.

4. **Đánh giá nhãn có sẵn** (thêm ngày 2026-11-12): nếu job đã có nhãn mắt (pre-label của BTC hoặc track
   người dùng đã làm), tool đánh giá các điểm đó.

## 3. Đã chốt (người dùng đã nói)

- **Không ghi ảnh ra đĩa là ưu tiên số một.** Ảnh chỉ nằm trong RAM.
- **Tool là một cửa sổ riêng trên máy**, không phải trang web và không gắn vào trang CVAT.
- **Kết nối:** gọi API của CVAT nội bộ bằng tài khoản của người dùng. Tài khoản là username/password tạo
  riêng trên CVAT. Server chỉ vào được từ máy đã đăng ký địa chỉ MAC và đang nối Wi-Fi công ty.
- **Màn hình chỉnh sửa:**
  - Gợi ý hiện ngay trên mắt như một nhãn, người dùng kéo điểm để chỉnh.
  - Khi đang ở frame N, bên phải có hai ảnh thu nhỏ của frame N−1 và N+1, cho thấy chúng sẽ thay đổi thế
    nào khi sửa frame N. Mục đích: so sánh, phát hiện điểm bị dịch quá nhiều, sót hoặc nhầm keyframe.
  - Chưa có gì ghi lên CVAT cho tới khi bấm Apply.
- **Cách làm việc với track:** track chạy tới frame 3; frame 4 đổi dáng mắt thì ghim keyframe và sửa; frame 5
  nội suy theo frame 4. Tool cho thấy hậu quả, người dùng tự quyết định ghim thêm hay sửa tiếp.
- **Sửa chỉ lan về phía sau:** sửa frame 4 thì frame 5 đi theo, frame 3 không bị kéo. Frame 3 chỉ để so sánh
  với frame 4.
- **Hỏi trước khi ghim:** CVAT nội suy frame 3 giữa keyframe trước đó và frame 4, nên muốn frame 3 đứng yên
  thì phải ghim nó thành keyframe ở vị trí hiện tại trước khi áp thay đổi ở frame 4. Tool phải hỏi người dùng
  trước khi ghim, không tự làm.
- **Đo bằng pixel:** độ dịch chuyển của điểm được tính và hiển thị theo pixel, không theo tỉ lệ phần trăm.
- **Vẽ bằng 4 điểm, cách suy ra 4 điểm còn lại: A + B** (xem `mockups/four-point-interp.html`).
  - A: tool dựng đường cong mượt qua 14-16-18 và 18-20-14 (tương tự 22-24-26, 26-28-22), đặt các điểm còn lại
    lên đường cong theo tỉ lệ trong guideline. Không nhìn vào ảnh.
  - B: sau A, tool dò theo điểm ảnh quanh mỗi điểm suy ra để bám mép mí thật.
  - **B không được dùng một bộ thông số cố định cho cả job:** 200 frame có thể là một người, cũng có thể gồm
    3 người, nên B phải tự điều chỉnh theo từng người.
- **Prelabel đi qua nút Hint:** mở job chưa có nhãn, người dùng bấm nút Hint để tool gợi ý, rồi chọn khoảng
  frame (từ frame bao nhiêu đến bao nhiêu) để áp gợi ý. Không có bước prelabel tự chạy khi mở job.
- **Luồng Hint đã được đồng ý:** Hint chạy trên frame đang xem trước, sau đó người dùng chọn khoảng frame;
  frame mà model không ổn định hoặc không thấy mặt thì để trống và đánh dấu trên dòng thời gian.
- **Kiểu track giữ ít keyframe nhất (đã đồng ý):** tool tính gợi ý cho mọi frame trong khoảng, rồi chỉ giữ ít
  keyframe nhất sao cho các frame giữa, sau khi nội suy đường thẳng như CVAT, không có điểm nào lệch quá 3 px
  so với gợi ý của chính frame đó. Luôn có keyframe ở đầu và cuối khoảng, ở mốc chia đoạn theo người và ở mọi
  frame người dùng đã sửa tay. Con số 3 px chỉnh được trong cài đặt.
- **Người dùng tự chia đoạn theo người:** người dùng tự xác định mỗi người từ frame bao nhiêu đến frame bao
  nhiêu. Tool không tự nhận diện người.

## 3b. Sự thật về CVAT đã tra cứu (xem `cvat-keyframe-behaviour.md`)

- Trong skeleton track, mỗi điểm có keyframe riêng. Kéo một điểm chỉ ghim riêng điểm đó, nhưng ngôi sao
  keyframe của cả skeleton vẫn sáng. Đây là nguyên nhân chính của hiện tượng lệch người dùng gặp.
- Hệ quả đã đưa vào thiết kế: tool luôn ghi keyframe đủ 8 điểm, và đánh dấu các frame "keyframe thiếu".

## 4. Đề xuất chưa được xác nhận

- Dựng cửa sổ bằng Tkinter (có sẵn trên máy, không cần cài thêm).
- Trên ảnh thu nhỏ: nhãn cũ nét đứt xám, nhãn mới nét màu, kèm số pixel của điểm dịch nhiều nhất; điểm vượt
  ngưỡng tô đỏ và frame đó được đánh dấu trên dòng thời gian.
- Ngưỡng cảnh báo mặc định, chỉnh được trong cài đặt: vàng khi một điểm dịch trên 8 px, đỏ khi trên 15 px
  (mục 6.9 của guideline v1.3: 90% trường hợp dịch dưới 7,7 px; trên 15 px thì phải kiểm tra lại).
- Ảnh nhỏ frame N−1: nhãn của nó đặt cạnh nhãn frame N, kèm khoảng cách pixel từng điểm giữa hai frame.
  Ảnh nhỏ frame N+1: nhãn mới sau khi sửa, kèm số pixel dịch so với trước.
- Hộp hỏi ghim có thêm lựa chọn "luôn ghim trong phiên này" để không phải trả lời lặp lại.
- Mặc định cả job là một đoạn; người dùng thêm mốc chia đoạn trên dòng thời gian.
- B giữ thông số riêng cho từng đoạn: khoảng dò tính theo kích thước mắt trong frame; nếu người dùng liên tục
  sửa điểm của B theo cùng một hướng thì tool áp độ lệch đó cho các frame còn lại của đoạn.
- Điểm suy ra mà người dùng đã kéo tay thì coi là điểm đặt tay, tool không tính lại nó nữa.
- Bộ nhớ đệm trong RAM có giới hạn (vài chục frame gần nhất), xoá khi đóng tool. Log và file xuất chỉ có toạ độ.
- Đăng nhập: thử access token trước nếu server hỗ trợ, không thì `POST /api/auth/login`. Không lấy cookie
  từ trình duyệt.
- Ghi ngược lên CVAT chỉ khi người dùng bấm Apply; trên server của BTC cần mentor đồng ý trước (guideline
  v1.3 mục 1.2 cấm nạp annotation lên task).

## 5. Câu hỏi còn mở

0. Tính năng đánh giá: một điểm thế nào thì bị coi là sai, kết quả hiện ra sao, và sau khi đánh giá tool có
   sửa nhãn có sẵn tại chỗ hay không?
1. Hai mốc cảnh báo 8 px và 15 px có hợp với người dùng không? (Người dùng mới chốt là đo theo pixel.)
2. Luật trạng thái mắt theo tài liệu nào? Guideline v1.3 và tài liệu trên CVAT (14/7/2026) khác nhau ở
   Occluded/Outside và vị trí điểm mí; xem Phụ lục B của `../guideline/guideline_cvat_2026-07-14.md`.
4. B điều chỉnh theo từng đoạn như đề xuất ở mục 4 có đúng ý người dùng không?
5. Mentor có cho phép tool tải frame hàng loạt qua API trên job thật không?
6. Server công ty chạy phiên bản CVAT nào, có mục access token không?
7. Phản hồi của người dùng về bản phác `mockups/edit-screen.html` (chưa nhận được).

## 6. Những gì đã có

Mã nguồn nằm ở `C:\Users\minhf\Documents\VinAI\Task\week2\tools\`:

| File | Việc | Đã kiểm tra tới đâu |
| --- | --- | --- |
| `validate_eye_skeletons.py` | Kiểm tra hình học mattrai/matphai trong file XML export, theo v1.3 | Dữ liệu giả lập và 198 gợi ý của tool; chưa thử với file export thật của CVAT |
| `eye_prelabel.py` | MediaPipe → 8 điểm mỗi mắt; đọc thư mục ảnh hoặc API CVAT; xuất XML/CSV; `--push` chỉ cho localhost | 200 frame công khai; phần API chỉ thử với server giả lập |
| `fetch_guide_text.ps1` | Tải ảnh guideline từ CVAT vào RAM, OCR tiếng Việt, xuất text | Đã chạy trên CVAT công ty với 20 ảnh |

Số đo của `eye_prelabel.py` trên 200 frame công khai (140 hồng ngoại DMD + 60 YawDD), đã xem hết:

- 193 frame có gợi ý nằm trên mắt.
- 1 frame sai hẳn (gọng kính dày, model đặt lệch cả khuôn mặt); phép tự kiểm tra lật ngang bắt được.
- 6 frame kính râm che kín mắt, model vẫn đoán ra mắt; chỉ bắt được 1 trong 6.
- Độ dao động của model giữa hai lần chạy khoảng 3% khoảng cách hai mắt, ngang ngưỡng điểm neo. Không có nhãn
  chuẩn nên chưa đo được độ chính xác từng điểm.

Dữ liệu thử: CVAT local (`http://localhost:8080`), project `eyes_label`, task #2 gồm 200 frame công khai.
