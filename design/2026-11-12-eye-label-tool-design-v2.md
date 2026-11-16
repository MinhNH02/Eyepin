# Bản thiết kế v2 — tool gán nhãn mắt cho CVAT (mattrai / matphai)

> **ĐÃ ĐƯỢC THAY bởi `2026-11-13-eye-label-tool-design-v3.md`.** Giữ lại để đối chiếu. Lưu ý: câu ở mục 12.3
> nói đoạn 200 frame "chỉ 1 frame mắt cử động quá 4 px" là SAI; phép bám khi đó đã trôi khỏi mắt.

**Ngày:** 2026-11-12 · **Trạng thái:** bản nháp, chưa được duyệt. Thay cho `2026-11-12-eye-label-tool-design.md`.

**[Đã chốt]** là điều người dùng đã nói hoặc đồng ý. **[Đề xuất]** là lựa chọn của người viết, chưa được xác nhận.
**[Còn mở]** là câu hỏi chưa có câu trả lời (mục 11).

## 0. Thay đổi so với bản trước

| Chủ đề | Bản trước | Bản này | Lý do |
| --- | --- | --- | --- |
| Gợi ý bằng model | Nút Hint dùng MediaPipe | **Bỏ.** Nhãn sinh ra từ 4 điểm ghim và phép nội suy | Người dùng được thông báo không được dùng model [Đã chốt] |
| Ảnh trên đĩa | Cấm tuyệt đối, chỉ RAM | **Được lưu trên ổ đĩa của máy**, không được đưa lên mạng hay GitHub | Công ty cho phép [Đã chốt] |
| Thử nghiệm | Thận trọng với mọi thao tác ghi | **Demo thoải mái trên CVAT local** với dữ liệu công khai | [Đã chốt] |
| Kiểu track ít keyframe | So với gợi ý của model, ngưỡng 3 px | Bỏ; keyframe là những frame người dùng ghim | Không còn gợi ý để so |
| Tiêu chí quét | Có hai tiêu chí dùng model | Chỉ còn tiêu chí tính từ toạ độ | Không dùng model |

Giữ nguyên: cửa sổ riêng trên máy, đo bằng pixel, sửa chỉ lan về phía sau, hỏi trước khi ghim, keyframe đủ 8
điểm, người dùng tự chia đoạn theo người, chỉ ghi lên CVAT khi bấm Apply.

## 1. Mục đích

Người dùng gán nhãn hai skeleton mắt trong CVAT: `mattrai` (ID 14–21) và `matphai` (ID 22–29). Hai chỗ đau
[Đã chốt]:

1. Vẽ shape tay cho 200 frame quá lâu.
2. Dùng track thì nhãn bị lệch: sửa một keyframe là frame giữa lệch theo, một số điểm tự di chuyển, khó biết
   mình đã sót keyframe. Nguyên nhân: trong skeleton track của CVAT, mỗi điểm có keyframe riêng; kéo một điểm
   chỉ ghim riêng điểm đó (xem `cvat-keyframe-behaviour.md`).

Tool giảm việc cho người dùng xuống còn **đặt 4 điểm mỗi mắt ở những frame cần ghim**. Phần còn lại (4 điểm kia,
các frame ở giữa) do phép tính toạ độ lo, và người dùng luôn xem trước được kết quả.

## 2. Mục tiêu, ngoài phạm vi, điều phải tránh

**Mục tiêu**

- Mỗi mắt chỉ cần đặt 4 điểm thay vì 8; các frame giữa hai frame ghim được nội suy.
- Track do tool ghi ra hiển thị trong CVAT đúng như bản xem trước của tool, và keyframe luôn đủ 8 điểm.
- Người dùng thấy trước hậu quả của một lần sửa lên frame bên cạnh, tính bằng pixel.
- Chỉ ra các frame cần chú ý trong nhãn có sẵn.

**Ngoài phạm vi**

- Mọi model nhận diện khuôn mặt hay điểm mốc. Tool không tự tìm mắt trong ảnh.
- Năm skeleton còn lại, nhãn Face, bài HumanPose.
- Tự quyết định trạng thái Visible / Occluded / Outside.
- Tự nhận diện ai là ai.

**Điều phải tránh**

- Đưa ảnh của công ty lên mạng, lên GitHub, hoặc gửi tới bất kỳ dịch vụ bên ngoài nào (kể cả trợ lý AI trực
  tuyến) [Đã chốt phần mạng và GitHub; phần dịch vụ bên ngoài là hệ quả do người viết suy ra].
- Ghi lên CVAT khi người dùng chưa bấm Apply.
- Xoá hoặc ghi đè nhãn có sẵn mà người dùng không biết.
- Ghi keyframe lẻ từng điểm.

## 3. Ràng buộc

### 3.1. Dữ liệu

- Ảnh lấy từ CVAT **được phép lưu trên ổ đĩa của máy** [Đã chốt]. Tool lưu vào một thư mục đệm riêng cho từng
  job để không phải tải lại [Đề xuất].
- Thư mục đệm nằm ngoài mọi thư mục mã nguồn và không bao giờ được đưa vào git. Nếu dự án dùng git, thư mục đệm
  phải có trong `.gitignore` [Đề xuất].
- Có nút xoá bộ đệm ảnh của một job [Đề xuất].
- Dữ liệu công khai (200 frame trong CVAT local) không bị ràng buộc gì.

### 3.2. Kết nối

- Server công ty chỉ vào được từ máy đã đăng ký địa chỉ MAC, khi nối Wi-Fi công ty [Đã chốt].
- Đăng nhập bằng username và password của CVAT; `POST /api/auth/login` trả về khoá, dùng với header
  `Authorization: Token <khoá>` (đã chạy được trên server công ty). Mọi lệnh gọi kèm `?org=2D`; không gửi header
  `Accept: application/json`.
- Nếu có biến môi trường `CVAT_TOKEN` thì dùng `Authorization: Bearer <token>` [Đề xuất].
- Mật khẩu chỉ nằm trong RAM, không ghi ra file.
- Chưa biết server công ty chạy bản CVAT nào [Còn mở]. Mô tả API lấy theo bản 2.75.

### 3.3. Phạm vi cho phép

- **CVAT local:** đọc, ghi, thử nghiệm tự do [Đã chốt].
- **Server công ty:** được tải ảnh về máy [Đã chốt]. Việc tool **ghi nhãn** qua API lên job thật chưa rõ đã được
  phép hay chưa; guideline v1.3 mục 1.2 cấm chức năng nạp annotation lên task [Còn mở]. Cho tới khi rõ, nút
  Apply chỉ bật với `localhost`.
- Luật trạng thái mắt và vị trí điểm mí khác nhau giữa guideline v1.3 và tài liệu trên CVAT ngày 14/7/2026
  [Còn mở].

### 3.4. Hành vi của CVAT mà tool phải tính đúng theo

- Giữa hai keyframe, toạ độ từng điểm nội suy đường thẳng theo số frame.
- Sau keyframe cuối, điểm giữ nguyên vị trí tới hết job. Trước keyframe đầu, điểm coi như Outside.
- Occluded và Outside ở frame giữa lấy từ keyframe bên trái.
- Mỗi điểm của skeleton có danh sách keyframe riêng.

### 3.5. Môi trường

Windows 11, Python 3.12, Tkinter, Pillow, OpenCV, NumPy, requests (đều có sẵn). Cửa sổ dựng bằng Tkinter
[Đề xuất].

## 4. Cách dùng

1. Mở tool, đăng nhập, chọn job. Tool tải nhãn mắt có sẵn và tải ảnh khi cần.
2. Ở frame cần ghim, người dùng đặt 4 điểm cho mỗi mắt. Tool suy ra 4 điểm còn lại.
3. Người dùng chuyển tới frame ghim tiếp theo và làm lại. Các frame ở giữa được nội suy.
4. Người dùng lướt qua, sửa những frame nội suy bị lệch (frame đó thành frame ghim mới).
5. Bấm **Apply** để ghi lên CVAT, rồi tải lại trang job trong CVAT để kiểm tra.

Có thể bấm **Quét** bất cứ lúc nào để lấy danh sách frame cần chú ý.

## 5. Vẽ bằng 4 điểm

### 5.1. Điểm ghim và điểm suy ra [Đã chốt]

- Điểm ghim: 14, 16, 18, 20 (mắt trái) và 22, 24, 26, 28 (mắt phải).
- Tool suy ra 15, 17, 19, 21 và 23, 25, 27, 29.
- Dùng được cho shape (một frame) và track (frame đó thành keyframe đủ 8 điểm).
- Điểm suy ra mà người dùng đã kéo tay thì coi là điểm đặt tay, không bị tính lại [Đề xuất].

### 5.2. Cách A: tính từ toạ độ [Đã chốt]

Với mỗi mí, dựng một parabol đi qua hai khoé và điểm giữa mí, trong hệ trục khoé–khoé. Các điểm còn lại đặt trên
parabol tại vị trí dọc trục lấy theo guideline v1.3 mục 3.3:

| Mắt | Mí trên | Mí dưới |
| --- | --- | --- |
| mattrai (tính từ điểm 14) | 15 tại 0,21 · 17 tại 0,76 | 21 tại 0,24 · 19 tại 0,76 |
| matphai (tính từ điểm 22) | 23 tại 0,23 · 25 tại 0,79 | 29 tại 0,25 · 27 tại 0,78 |

Đã có mã: `week2\tools\eye_interp.py`. Kết quả thử trên 198 frame công khai (396 mắt): điểm suy ra lệch trung vị
0,1–0,6 px, lớn nhất 2,4 px so với đường viền tham chiếu. Đường viền tham chiếu đó lấy từ một model chạy trước
khi có lệnh cấm, không phải nhãn người gán, nên con số này chỉ cho biết parabol khớp một dáng mắt mượt.

### 5.3. Cách B: dò theo điểm ảnh [Đã chốt là muốn có; Còn mở là có được phép không]

- Sau A, tool dò quanh mỗi điểm suy ra để dời nó tới mép mí thật, bằng phép xử lý ảnh thông thường (tìm biên
  sáng tối), không dùng model.
- Cần người dùng xác nhận lệnh "không dùng model" có cho phép cách này không.
- B có nút bật tắt riêng, mặc định tắt cho tới khi người dùng xem kết quả trên ảnh công khai [Đề xuất].
- Khi không thấy mép rõ ràng, B giữ kết quả của A [Đề xuất].

### 5.4. Chia đoạn theo người [Đã chốt]

- Người dùng tự xác định mỗi người từ frame bao nhiêu đến bao nhiêu. Mặc định cả job là một đoạn.
- Thông số của B và độ lệch học từ các lần người dùng sửa chỉ áp dụng trong đoạn đó [Đề xuất].
- Nội suy không đi qua mốc chia đoạn: frame đầu của mỗi đoạn phải là frame ghim [Đề xuất].

## 6. Nội suy giữa các frame ghim

- **Kiểu track:** tool ghi một track với keyframe tại đúng các frame người dùng đã ghim. CVAT tự nội suy đường
  thẳng ở giữa; bản xem trước của tool tính y như vậy.
- **Kiểu shape:** tool tự tính vị trí nội suy cho từng frame giữa và ghi mỗi frame một shape [Đề xuất].
- Người dùng chọn kiểu khi Apply [Đã chốt là có cả hai kiểu].

## 7. Màn hình chỉnh sửa

Bản phác: `mockups/main-screen.html` và `mockups/with-cvat-and-samples.html` (nút Hint trong hai bản phác này
không còn hiệu lực).

- **Khung chính:** frame đang chọn, phóng to vào hai mắt. Kéo điểm để chỉnh. Điểm ghim vẽ to, điểm suy ra vẽ nhỏ.
  Đặt trạng thái từng điểm bằng phím tắt. Có hoàn tác [Đề xuất cho phóng to, phím tắt, hoàn tác].
- **Hai ảnh nhỏ bên phải [Đã chốt]:** frame N−1 chỉ để so sánh với frame N; frame N+1 cho thấy nó đổi thế nào
  khi sửa frame N. Mọi độ dịch chuyển tính bằng pixel.
- **Ngưỡng cảnh báo:** vàng trên 8 px, đỏ trên 15 px, chỉnh được [Đề xuất].
- **Sửa chỉ lan về phía sau, hỏi trước khi ghim [Đã chốt]:** sửa frame N thì N+1 trở đi đổi theo, N−1 không bị
  kéo. Muốn vậy phải ghim N−1; tool hỏi trước khi ghim, với ba lựa chọn Ghim, Không ghim, Luôn ghim trong phiên
  này.
- **Keyframe đủ 8 điểm [Đề xuất]:** tool không bao giờ ghim lẻ. Frame trong CVAT chỉ ghim một phần số điểm được
  đánh dấu "keyframe thiếu", kèm nút ghim đủ.
- **Dòng thời gian:** frame ghim, keyframe thiếu, frame nội suy, frame chưa có nhãn, frame cần chú ý, mốc chia
  đoạn theo người.

## 8. Quét nhãn có sẵn

Tool đi từ frame đầu tới frame cuối rồi đưa ra danh sách frame cần chú ý [Đã chốt]. Tiêu chí, đều tính từ toạ độ
[Đề xuất]:

- **Đỏ:** thứ tự điểm sai; mí trên nằm dưới mí dưới; đường viền bắt chéo; điểm ngoài khung hình mà không Outside;
  thiếu điểm hoặc trùng skeleton.
- **Vàng:** một điểm nhảy quá 15 px so với frame liền trước; keyframe thiếu; nhãn có toạ độ y hệt nhau qua nhiều
  frame liền.

Mã kiểm tra hình học đã có: `week2\tools\validate_eye_skeletons.py`.

## 9. Apply

- Chỉ ghi khi bấm Apply; chỉ đụng tới `mattrai` và `matphai`.
- Trước khi ghi: hiện bảng tóm tắt để xác nhận, đọc lại nhãn trên server và dừng nếu nó đã đổi, lưu bản sao toạ
  độ nhãn cũ để khôi phục. Sau khi ghi: đọc lại để đối chiếu [Đề xuất].
- Nhãn có sẵn: sửa đúng shape hoặc track đang có, không tạo chồng, không xoá [Đề xuất; Còn mở].
- Bản nháp (toạ độ, trạng thái, mốc chia đoạn) tự lưu ra file theo từng job [Đề xuất].

## 10. Để người xây quyết định

- Cấu trúc mã, phím tắt, định dạng file bản nháp, cách tổ chức thư mục đệm ảnh.
- Thuật toán dò biên của B.
- Thứ tự làm. Gợi ý: xem nhãn và dòng thời gian → vẽ 4 điểm (A) → nội suy và xem trước → Apply trên CVAT local
  → Quét → B.
- Phép thử quan trọng nhất: tạo track bằng tool, export từ CVAT local ở định dạng "CVAT for images", so toạ độ
  từng frame với bản xem trước của tool; hai bên phải khớp.
- Dữ liệu thử: CVAT local, project `eyes_label`, task #2 gồm 200 frame công khai.

## 11. Câu hỏi còn mở

1. **Lệnh "không dùng model" cấm những gì?** Chỉ model nhận diện khuôn mặt, hay cả phép dò biên của cách B, hay
   cả việc dùng trợ lý AI (Claude, Codex) để chỉnh toạ độ và chạy script?
2. **Ghi nhãn lên job thật qua API** đã được phép chưa?
3. **Track kết thúc ở đâu?** CVAT giữ vị trí keyframe cuối tới hết job. Mỗi mắt là một track cho cả job, hay mỗi
   đoạn theo người một track?
4. **"Sửa chỉ lan về phía sau"** dừng ở keyframe kế tiếp (như CVAT), hay được mang tiếp qua các keyframe sau?
5. **Nhãn có sẵn khi Apply:** đề xuất ở mục 9 có đúng ý không?
6. **Luật trạng thái mắt:** theo guideline v1.3 hay tài liệu trên CVAT ngày 14/7/2026?
7. **Hướng "skill cho Claude hoặc Codex":** nếu được phép, skill chỉ làm việc với toạ độ (chạy nội suy, chạy
   kiểm tra, báo frame đáng nghi) và không xem ảnh của công ty. Có đúng ý người dùng không?
8. **Ngưỡng 8 px và 15 px** có hợp không? Thế nào là thành công với một job 200 frame?

## 12. Cập nhật sau trao đổi (cuối ngày 2026-11-12)

### 12.1. Ghi nhãn bằng tính năng import vào job [Đã chốt]

- Người dùng được dùng tính năng import annotation vào job. Đây là câu trả lời cho câu hỏi 2 ở mục 11: tool ghi
  nhãn lên CVAT bằng cách tạo file annotation rồi import, thay cho việc sửa từng nhãn qua API.
- **Hệ quả đã kiểm trong mã nguồn CVAT 2.75** (`cvat/apps/dataset_manager/task.py:986-1005`): import vào job mặc
  định chạy ở chế độ thay thế, tức là **xoá toàn bộ nhãn đang có của job rồi mới nạp file**. Giao diện CVAT dùng
  chế độ này. API bản 2.75 có thêm tham số `import_mode=append` (chỉ thêm, không xoá); chưa biết server công ty có
  tham số đó không.
- Vì vậy file import phải chứa **toàn bộ nhãn của job** (cả 7 skeleton và mọi nhãn khác), không chỉ hai mắt. Quy
  trình bắt buộc: export nhãn hiện có → chỉ sửa `mattrai` và `matphai` → import lại toàn bộ.
- **Rủi ro phải thử trước tiên trên CVAT local:** export rồi import lại có giữ nguyên nhãn không. Định dạng "CVAT
  for images" đổi track thành shape; định dạng "CVAT for video" giữ track. Phải chọn định dạng và chứng minh rằng
  một vòng export → import không làm đổi các nhãn không liên quan.
- Trước mỗi lần import, giữ lại file export gốc để khôi phục được.

### 12.2. Trợ lý AI [Đã chốt]

- Việc import có thể do một công cụ bên ngoài như Codex hoặc Claude thực hiện.
- **Trong mạng nội bộ của công ty chỉ được dùng Codex.** Mọi thứ chạy trên máy nối mạng công ty phải dùng được
  với Codex; Claude chỉ dùng để phát triển và thử trên dữ liệu công khai và CVAT local.
- Hệ quả [Đề xuất]: phần logic nằm trong các script Python chạy độc lập; phần hướng dẫn cho trợ lý AI viết thành
  một bộ chỉ dẫn mà Codex đọc được, không phụ thuộc tính năng riêng của Claude.
- [Còn mở] Codex có được xem ảnh tài xế của công ty không. Ảnh gửi cho Codex là ảnh rời khỏi máy. Cho tới khi rõ,
  bộ chỉ dẫn chỉ cho Codex làm việc với toạ độ và file annotation, không mở ảnh.

### 12.3. Dữ liệu thử đã có

- 140 ảnh hồng ngoại rời (DMD) và 60 ảnh màu rời (YawDD): task #2 trên CVAT local.
- 200 frame liên tiếp từ một video màu công khai (PhysDrive, frame 2352–2551, 30 fps, 1024×576): hai task 100
  frame trên CVAT local. Phép đo bằng so khớp vùng ảnh cho thấy trong cửa sổ này chỉ 1 frame mắt cử động quá 4 px.
- Chưa có video ban đêm hoặc video hồng ngoại liên tiếp.
