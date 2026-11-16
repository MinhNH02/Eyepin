# Bản thiết kế — tool gán nhãn mắt cho CVAT (mattrai / matphai)

> **ĐÃ ĐƯỢC THAY bởi `2026-11-12-eye-label-tool-design-v2.md`** (bỏ model, cho phép lưu ảnh trên đĩa). Giữ lại để đối chiếu.

**Ngày:** 2026-11-12 · **Trạng thái:** bản nháp để người dùng xem, chưa được duyệt.

Trong tài liệu này, **[Đã chốt]** là điều người dùng đã nói hoặc đã đồng ý. **[Đề xuất]** là lựa chọn của người
viết, người dùng chưa xác nhận. **[Còn mở]** là câu hỏi chưa có câu trả lời; danh sách đầy đủ ở mục 12.

Tài liệu đi kèm trong cùng thư mục dự án:

- `cvat-keyframe-behaviour.md`: keyframe của CVAT vận hành thế nào, đọc từ mã nguồn CVAT 2.75.
- `mockups/main-screen.html`: bản phác màn hình chính (mở bằng trình duyệt).
- `../guideline/`: guideline học viên v1.3 và tài liệu lấy từ CVAT ngày 14/7/2026.

---

## 1. Mục đích

Người dùng gán nhãn hai skeleton mắt trên ảnh tài xế trong CVAT nội bộ của công ty: `mattrai` (8 điểm, ID 14–21)
và `matphai` (8 điểm, ID 22–29). Hai chỗ đau hiện tại [Đã chốt]:

1. **Vẽ shape tay cho 200 frame quá lâu.**
2. **Dùng track thì nhãn bị lệch.** Sửa một keyframe là các frame ở giữa lệch theo, một số điểm tự di chuyển, và
   khó biết mình đã sót hay bấm nhầm keyframe. Nguyên nhân đã tra được: trong skeleton track của CVAT, mỗi điểm
   có keyframe riêng; kéo một điểm chỉ ghim riêng điểm đó nhưng ngôi sao keyframe của cả skeleton vẫn sáng
   (xem `cvat-keyframe-behaviour.md`).

Tool là một cửa sổ riêng chạy trên máy người dùng, làm việc với CVAT qua REST API, giúp đặt nhãn mắt nhanh hơn
và giữ cho track không bị lệch. CVAT vẫn là nơi lưu nhãn và là nơi kiểm tra cuối cùng.

## 2. Mục tiêu, ngoài phạm vi, điều phải tránh

### Mục tiêu

- Đặt nhãn mắt cho một khoảng frame nhanh hơn vẽ tay, bằng gợi ý của model và bằng cách vẽ 4 điểm.
- Mọi track do tool ghi ra không bị lệch ở frame giữa quá ngưỡng đã chọn.
- Người dùng luôn thấy trước hậu quả của một lần sửa lên frame bên cạnh, tính bằng pixel.
- Chỉ ra các frame cần chú ý trong nhãn có sẵn để người dùng không phải mở từng frame.

### Ngoài phạm vi

- Năm skeleton còn lại (lông mày, sống mũi, môi), nhãn Face, và bài HumanPose.
- Tự quyết định trạng thái Visible / Occluded / Outside thay người dùng.
- Tự nhận diện ai là ai trong ảnh. Người dùng tự chia đoạn theo người [Đã chốt].
- Huấn luyện model.
- Thay thế giao diện CVAT, chạy cho nhiều người dùng, hoặc chạy dưới dạng trang web.

### Điều phải tránh (làm được việc mà phạm các điều này vẫn là thất bại)

- **Ghi ảnh ra đĩa.** Đây là ưu tiên số một [Đã chốt]. Ảnh chứa mặt tài xế thật.
- Ghi bất cứ thứ gì lên CVAT khi người dùng chưa bấm Apply [Đã chốt].
- Xoá hoặc ghi đè nhãn có sẵn mà người dùng không biết.
- Ghi keyframe lẻ từng điểm (chính là lỗi đang muốn tránh).
- Trình bày gợi ý của model như đáp án đúng.
- Gửi ảnh hoặc nhãn tới bất kỳ dịch vụ nào ngoài server CVAT đang dùng.

## 3. Ràng buộc

### 3.1. Dữ liệu

- Frame lấy từ CVAT chỉ nằm trong RAM: không file ảnh, không ảnh thu nhỏ, không file tạm [Đã chốt].
- Bộ nhớ đệm frame trong RAM có giới hạn (mặc định 30 frame gần nhất) và bị xoá khi đóng tool [Đề xuất].
- Thứ được phép ghi ra đĩa: toạ độ, trạng thái điểm, số frame, cài đặt, log dạng text. Không ghi tên tài khoản
  hay mật khẩu [Đề xuất].
- Rủi ro còn lại, không chặn được từ trong tool và phải ghi rõ trong tài liệu sử dụng: Windows có thể đẩy RAM ra
  đĩa khi thiếu bộ nhớ, và có thể tạo bản ghi bộ nhớ khi chương trình bị treo.
- Bài học đã gặp: thư viện xử lý ảnh có thể tự ghi file tạm (Tesseract làm vậy với JPEG). Mỗi thư viện đọc ảnh
  dùng trong tool phải được kiểm bằng cách theo dõi thư mục tạm trong lúc chạy.

### 3.2. Kết nối

- Server công ty chỉ vào được từ máy đã đăng ký địa chỉ MAC, khi nối Wi-Fi công ty [Đã chốt]. Tool gọi thẳng
  tới server, không qua máy trung gian.
- Đăng nhập bằng username và password tạo riêng trên CVAT [Đã chốt]. Đã kiểm chứng trên server công ty:
  `POST /api/auth/login` trả về khoá, dùng với header `Authorization: Token <khoá>`.
- Đã kiểm chứng trên server công ty: lệnh gọi kèm `?org=2D` chạy được. Không gửi header
  `Accept: application/json` (ghi chú cũ: server trả 406).
- Nếu có biến môi trường `CVAT_TOKEN` thì dùng `Authorization: Bearer <token>` thay cho đăng nhập [Đề xuất].
- Mật khẩu và khoá chỉ nằm trong RAM. Không lấy cookie từ trình duyệt. Không gọi logout khi đóng tool, vì có thể
  làm phiên CVAT trên trình duyệt bị đăng xuất [Đề xuất].
- Chưa biết server công ty chạy bản CVAT nào [Còn mở]. Mọi mô tả API trong tài liệu này lấy theo bản 2.75.

### 3.3. Quy định của bài gán nhãn

- Guideline v1.3 mục 1.2 cấm dùng chức năng nạp annotation lên task của BTC. Việc tool ghi nhãn qua API trên job
  thật cần mentor đồng ý trước [Còn mở]. Cho tới lúc đó, tính năng ghi chỉ bật cho CVAT trên `localhost`.
- Việc tool tải frame hàng loạt qua API trên job thật cũng cần mentor đồng ý [Còn mở].
- Luật trạng thái mắt và vị trí điểm mí khác nhau giữa guideline v1.3 và tài liệu trên CVAT ngày 14/7/2026
  (Phụ lục B của `../guideline/guideline_cvat_2026-07-14.md`). Chưa biết tài liệu nào dùng để chấm [Còn mở].
- Trái/phải theo khung hình: mắt có toạ độ x nhỏ hơn là `mattrai`.

### 3.4. Hành vi của CVAT mà tool phải tính đúng theo

Tóm tắt từ `cvat-keyframe-behaviour.md` (CVAT 2.75):

- Giữa hai keyframe, toạ độ từng điểm được nội suy đường thẳng theo số frame.
- Sau keyframe cuối, điểm giữ nguyên vị trí tới hết job. Trước keyframe đầu, điểm coi như Outside.
- Occluded và Outside ở frame giữa lấy nguyên từ keyframe bên trái.
- Mỗi điểm của skeleton có danh sách keyframe riêng.
- Sửa một điểm ở frame chưa phải keyframe sẽ biến frame đó thành keyframe của riêng điểm ấy.

### 3.5. Môi trường

- Windows 11, Python 3.12. Có sẵn trên máy: Tkinter 8.6, Pillow (kèm ImageTk), OpenCV, NumPy, requests,
  MediaPipe 1.0.1 và model `face_landmarker.task`.
- Cửa sổ dựng bằng Tkinter để không phải cài thêm gì [Đề xuất].

## 4. Tổng quan cách dùng

1. Mở tool, nhập địa chỉ CVAT, đăng nhập, chọn job.
2. Tool tải thông tin job và nhãn mắt có sẵn (không tải ảnh hàng loạt ở bước này).
3. Người dùng làm một hoặc nhiều việc sau, theo thứ tự tuỳ ý:
   - **Quét** nhãn có sẵn để lấy danh sách frame cần chú ý (mục 8).
   - **Hint** để lấy gợi ý của model cho một khoảng frame (mục 6).
   - **Vẽ 4 điểm** để tự đặt nhãn (mục 7).
   - **Sửa** điểm ở từng frame, xem trước hậu quả lên frame bên cạnh (mục 5).
4. Mọi thay đổi nằm trong bản nháp của tool. Bấm **Apply** thì bản nháp mới được ghi lên CVAT (mục 9).
5. Người dùng tải lại trang job trong CVAT để kiểm tra kết quả.

## 5. Màn hình chỉnh sửa

Xem `mockups/main-screen.html`.

### 5.1. Khung chính

- Hiện frame đang chọn, phóng to vào vùng hai mắt; có điều khiển phóng to, thu nhỏ, kéo ảnh [Đề xuất].
  Guideline yêu cầu phóng tối thiểu 200% khi đặt điểm mắt.
- Nhãn đang sửa vẽ nét liền, gợi ý của model vẽ nét đứt [Đã chốt: gợi ý hiện như một nhãn trên mắt và chỉnh được].
- Người dùng kéo từng điểm để chỉnh. Mỗi điểm hiện số ID.
- Bốn điểm chính (14, 16, 18, 20 và 22, 24, 26, 28) vẽ to; bốn điểm còn lại vẽ nhỏ.
- Người dùng đặt trạng thái cho từng điểm (Visible, Occluded, Outside) bằng phím tắt khi trỏ vào điểm [Đề xuất].
- Có hoàn tác và làm lại trong phiên làm việc [Đề xuất].

### 5.2. Hai ảnh thu nhỏ bên phải [Đã chốt]

Khi đang ở frame N:

- **Frame N−1:** chỉ để so sánh. Nhãn của N−1 đặt cạnh nhãn của N, kèm khoảng cách pixel từng điểm giữa hai frame.
- **Frame N+1:** cho thấy nó thay đổi thế nào khi sửa frame N. Nhãn trước khi sửa vẽ nét đứt xám, nhãn sau khi
  sửa vẽ nét màu, kèm số pixel dịch chuyển của điểm dịch nhiều nhất.
- Mọi độ dịch chuyển tính và hiển thị bằng pixel [Đã chốt].
- Ngưỡng cảnh báo mặc định, chỉnh được trong cài đặt: vàng khi một điểm dịch trên 8 px, đỏ khi trên 15 px
  [Đề xuất; lấy từ guideline v1.3 mục 6.9].

### 5.3. Sửa chỉ lan về phía sau, hỏi trước khi ghim [Đã chốt]

- Sửa frame N thì frame N+1 trở đi thay đổi theo (theo công thức nội suy của CVAT), còn frame N−1 không bị kéo.
- Theo hành vi của CVAT, muốn N−1 đứng yên thì phải ghim N−1 thành keyframe ở vị trí đang hiển thị trước khi áp
  thay đổi ở N. **Tool phải hỏi người dùng trước khi ghim.**
- Hộp hỏi hiện khi người dùng bắt đầu sửa frame N mà frame N−1 chưa là keyframe đủ 8 điểm. Ba lựa chọn: Ghim,
  Không ghim, Luôn ghim trong phiên này [Đề xuất cho lựa chọn thứ ba].
- Nếu chọn Không ghim, ảnh thu nhỏ N−1 cho thấy nó bị kéo đi bao nhiêu pixel.

### 5.4. Keyframe đủ 8 điểm [Đề xuất, hệ quả trực tiếp của mục 1]

- Mọi keyframe do tool tạo ra đều gồm đủ 8 điểm của một mắt.
- Frame mà trong CVAT chỉ một phần số điểm có keyframe được gọi là **keyframe thiếu**. Dòng thời gian đánh dấu
  riêng loại này, kèm nút "ghim đủ 8 điểm" để ghim các điểm còn lại ở vị trí đang hiển thị.

### 5.5. Dòng thời gian

- Mỗi frame một ô, cho biết: keyframe đủ, keyframe thiếu, frame nội suy, frame chưa có nhãn.
- Đánh dấu frame cần chú ý (đỏ hoặc vàng) và frame model không đưa ra gợi ý.
- Thanh chia đoạn theo người (mục 7.3).
- Chọn khoảng frame bằng cách kéo trên dòng thời gian hoặc nhập số.

### 5.6. Kiểm tra luật ngay khi sửa [Đề xuất]

Frame đang sửa được kiểm theo các luật hình học ở mục 8.2 (mức đỏ) sau mỗi lần thả điểm.

## 6. Hint: gợi ý của model

### 6.1. Luồng [Đã chốt]

1. Người dùng bấm **Hint**. Tool gợi ý hai mắt trên frame đang xem, vẽ nét đứt.
2. Người dùng chọn khoảng frame (từ frame bao nhiêu đến bao nhiêu). Tool chạy gợi ý cho cả khoảng.
3. Người dùng lướt qua, sửa những frame cần sửa.
4. Bấm Apply để ghi.

Không có bước prelabel tự chạy khi mở job. Frame mà model không ổn định hoặc không thấy mặt thì để trống và
được đánh dấu trên dòng thời gian, thay vì đưa ra gợi ý sai.

### 6.2. Model

- Dùng lại phần đã có trong `eye_prelabel.py`: MediaPipe face landmarker, ánh xạ sang 8 điểm mỗi mắt theo tỉ lệ
  trong guideline v1.3 mục 3.3, và phép tự kiểm tra bằng ảnh lật ngang (bỏ gợi ý khi hai lần chạy lệch nhau quá
  10% khoảng cách hai mắt).
- Giới hạn đã đo trên 200 frame công khai (140 hồng ngoại, 60 ảnh màu):
  - 193 frame có gợi ý nằm trên mắt.
  - 1 frame sai hẳn vì gọng kính dày; phép tự kiểm tra bắt được.
  - 6 frame kính râm che kín mắt, model vẫn đoán ra mắt; phép tự kiểm tra chỉ bắt được 1.
  - Độ dao động của model giữa hai lần chạy khoảng 3% khoảng cách hai mắt.
  - Chưa có nhãn chuẩn nên chưa đo được độ chính xác từng điểm.
- Mọi điểm gợi ý để trạng thái Visible. Trạng thái do người dùng đặt.

### 6.3. Kiểu shape và kiểu track [Đã chốt]

Người dùng chọn kiểu khi áp gợi ý cho một khoảng:

- **Shape:** mỗi frame trong khoảng nhận một nhãn riêng.
- **Track, giữ ít keyframe nhất:** tool tính gợi ý cho mọi frame trong khoảng, rồi chỉ giữ số keyframe ít nhất
  sao cho ở mọi frame giữa, sau khi nội suy đường thẳng như CVAT, không có điểm nào lệch quá **3 px** so với
  gợi ý của chính frame đó. Con số 3 px chỉnh được trong cài đặt.
  - Luôn có keyframe ở đầu và cuối khoảng, ở mốc chia đoạn theo người, và ở mọi frame người dùng đã sửa tay.
  - Frame không có gợi ý (model không ổn định) nằm giữa một khoảng track: cách xử lý để người xây quyết định,
    miễn là frame đó được đánh dấu để người dùng xem lại.

## 7. Vẽ bằng 4 điểm

### 7.1. Luồng [Đã chốt]

Người dùng bấm lần lượt 4 điểm chính của một mắt: 14, 16, 18, 20 (mắt trái) hoặc 22, 24, 26, 28 (mắt phải).
Tool tự suy ra 4 điểm còn lại. Dùng được cho cả shape (áp cho một frame) và track (frame đó thành keyframe đủ
8 điểm).

Điểm suy ra mà người dùng đã kéo tay thì coi là điểm đặt tay; tool không tính lại nó khi 4 điểm chính thay đổi
[Đề xuất].

### 7.2. Cách suy ra: A rồi B [Đã chốt]

- **A, chỉ tính từ toạ độ.** Với mỗi mí, tool dựng một đường cong mượt đi qua hai khoé và điểm giữa mí
  (14–16–18 cho mí trên, 18–20–14 cho mí dưới; tương tự 22–24–26 và 26–28–22). Các điểm còn lại đặt trên đường
  cong tại các vị trí dọc trục khoé–khoé lấy theo guideline v1.3 mục 3.3:

  | Mắt | Mí trên | Mí dưới |
  | --- | --- | --- |
  | mattrai (tính từ điểm 14) | 15 tại 0,21 · 17 tại 0,76 | 21 tại 0,24 · 19 tại 0,76 |
  | matphai (tính từ điểm 22) | 23 tại 0,23 · 25 tại 0,79 | 29 tại 0,25 · 27 tại 0,78 |

  Mắt nhắm (điểm giữa mí nằm trên trục khoé–khoé) cho ra đường thẳng, đúng với quy định các cặp mí trên và mí
  dưới trùng nhau.

- **B, dò theo điểm ảnh.** Sau A, tool nhìn vào ảnh quanh mỗi điểm suy ra để dời điểm tới mép mí thật.
  - B là phần rủi ro nhất của thiết kế: nó có thể bị kéo nhầm vào gọng kính, lông mi hoặc vệt loá.
  - Khi không tìm thấy mép rõ ràng, B giữ nguyên kết quả của A [Đề xuất].
  - B có nút bật tắt riêng. Chỉ bật mặc định sau khi người dùng xem kết quả trên bộ 200 frame công khai và
    chấp nhận [Đề xuất].
  - Thuật toán dò cụ thể để người xây chọn.

### 7.3. Chia đoạn theo người [Đã chốt]

- Một job có thể là một người hoặc nhiều người. B không được dùng một bộ thông số cố định cho cả job.
- Người dùng tự xác định mỗi người từ frame bao nhiêu đến frame bao nhiêu. Mặc định cả job là một đoạn.
- Mỗi đoạn giữ thông số B riêng [Đề xuất]:
  - Khoảng dò tính theo kích thước mắt trong frame, không phải số pixel cố định.
  - Nếu người dùng liên tục sửa điểm của B theo cùng một hướng, tool áp độ lệch đó cho các frame còn lại của
    đoạn. Độ lệch học được không mang sang đoạn khác.

## 8. Quét: đánh giá nhãn có sẵn

### 8.1. Luồng [Đã chốt]

Nếu job đã có nhãn mắt (pre-label của BTC hoặc track người dùng đã làm), người dùng bấm **Quét**. Tool đi một
lượt từ frame đầu tới frame cuối rồi đưa ra danh sách các frame cần chú ý.

- Mỗi dòng ghi số frame, mắt nào, điểm nào và lý do. Xếp theo mức nặng nhẹ [Đề xuất].
- Bấm vào một dòng thì nhảy tới frame đó, điểm bị nghi được tô màu [Đề xuất].
- Tool chỉ chỉ ra chỗ đáng nghi. Nó không kết luận điểm nào đúng và không tự sửa [Đề xuất].

### 8.2. Tiêu chí [Đề xuất, người dùng chưa xác nhận hay bổ sung]

**Đỏ, sai luật chắc chắn** (guideline v1.3 mục 3.3 và 4.1; chỉ cần toạ độ):

- Điểm 14 hoặc 22 không phải điểm có x nhỏ nhất của mắt; điểm 18 hoặc 26 không phải điểm có x lớn nhất.
- Mí trên nằm dưới mí dưới đối diện (cặp 15–21, 16–20, 17–19; 23–29, 24–28, 25–27), đo theo trục khoé–khoé.
- Đường viền tự bắt chéo.
- Điểm nằm ngoài khung hình mà không đánh Outside.
- Thiếu điểm, hoặc một frame có hai skeleton cùng nhãn.

**Vàng, đáng nghi:**

- Một điểm nhảy quá 15 px so với frame liền trước (guideline v1.3 mục 6.9).
- Keyframe thiếu.
- Nhãn đứng yên nhiều frame liền trong khi khuôn mặt di chuyển (cần ảnh).
- Điểm lệch xa gợi ý của model (cần ảnh).

Luật về trạng thái (ví dụ mắt thấy dưới 4/8 điểm) tạm tắt cho tới khi biết tài liệu nào dùng để chấm.

Phần mã kiểm tra hình học đã có trong `validate_eye_skeletons.py`.

### 8.3. Ảnh khi quét

Hai tiêu chí cần ảnh buộc tool tải lần lượt từng frame vào RAM, mỗi frame một lần. Người dùng có thể chạy quét
chỉ với các tiêu chí không cần ảnh [Đề xuất].

## 9. Apply: ghi lên CVAT

- Chỉ ghi khi người dùng bấm Apply [Đã chốt].
- Chỉ đụng tới hai nhãn `mattrai` và `matphai` [Đề xuất].
- Trước khi ghi, hiện bảng tóm tắt: bao nhiêu shape được tạo, bao nhiêu được sửa, bao nhiêu track, ở những frame
  nào. Người dùng xác nhận rồi mới ghi [Đề xuất].
- Trước khi ghi, tool đọc lại nhãn trên server. Nếu nhãn mắt đã thay đổi so với lúc tải thì dừng và báo, không
  ghi đè [Đề xuất].
- Trước khi ghi, tool lưu một bản sao toạ độ của nhãn mắt hiện có ra file để có thể khôi phục [Đề xuất].
- Sau khi ghi, tool đọc lại để xác nhận kết quả khớp với bản nháp [Đề xuất].
- Ghi lên server không phải `localhost` bị khoá cho tới khi mentor đồng ý (mục 3.3).
- Sau Apply, người dùng phải tải lại trang job trong CVAT. Không nên vừa mở job trong CVAT với thay đổi chưa lưu
  vừa Apply từ tool.

**Cách xử lý nhãn có sẵn khi Apply [Còn mở].** Người dùng chưa trả lời. Đề xuất mặc định:

- Frame đã có shape mắt: sửa đúng shape đó, không tạo shape mới chồng lên.
- Track có sẵn: sửa keyframe của chính track đó.
- Không tự chuyển shape thành track hoặc ngược lại.
- Không xoá nhãn nào, trừ khi người dùng chọn xoá từng cái.

## 10. Bản nháp và khôi phục [Đề xuất]

- Bản nháp (toạ độ, trạng thái, mốc chia đoạn, cài đặt B) được tự lưu ra file theo từng job để không mất việc
  khi tool bị tắt. File này không chứa ảnh.
- Khi mở lại job, tool hỏi có tiếp tục bản nháp cũ hay bỏ.

## 11. Để người xây quyết định

- Cấu trúc mã và cách chia module.
- Thuật toán dò mép mí của B, trong các giới hạn ở mục 7.2 và 7.3.
- Thuật toán chọn keyframe ít nhất ở mục 6.3, miễn là kết quả thoả điều kiện 3 px.
- Phím tắt cụ thể và chi tiết giao diện ngoài những gì mục 5 quy định.
- Định dạng file bản nháp và file cài đặt.
- Thứ tự làm. Gợi ý: xem nhãn có sẵn và dòng thời gian → Quét → sửa và Apply trên CVAT local → Hint → vẽ 4
  điểm A → B.

### Cách kiểm tra gợi ý cho người xây

- Dữ liệu thử: CVAT local `http://localhost:8080`, project `eyes_label`, task #2 gồm 200 frame công khai.
- Phép thử quan trọng nhất: tạo một track bằng tool, export từ CVAT local ở định dạng "CVAT for images", rồi so
  toạ độ từng frame với bản xem trước của tool. Hai bên phải khớp nhau.
- Theo dõi thư mục tạm của Windows trong lúc chạy để chắc không có file ảnh nào sinh ra.

## 12. Câu hỏi còn mở

**Ba câu thêm sau khi một người đọc độc lập soát bản này; chúng ảnh hưởng nhiều nhất tới cách xây:**

- **A. Gợi ý trở thành nhãn lúc nào?** Apply ghi mọi frame có gợi ý trong khoảng, kể cả frame người dùng chưa
  mở xem, hay chỉ ghi những frame người dùng đã chấp nhận?
- **B. Một track do tool tạo kết thúc ở đâu?** CVAT giữ vị trí keyframe cuối tới hết job, nên track cho frame
  50–80 sẽ còn hiện ở 81–199 trừ khi tool đặt Outside ở frame 81. Và mỗi mắt là một track cho cả job, hay mỗi
  đoạn theo người một track? Nếu là một track liền thì mắt sẽ bị nội suy giữa hai người khác nhau.
- **C. "Sửa chỉ lan về phía sau" tới đâu?** Theo CVAT, sửa frame N chỉ đổi các frame tới keyframe kế tiếp. Người
  dùng có muốn phần chỉnh được mang tiếp qua các keyframe sau không? Ngoài ra, ghim N−1 ở mỗi lần sửa sẽ làm
  số keyframe tăng nhanh, ngược với ý "ít keyframe nhất"; điều đó có chấp nhận được không?

**Các câu còn lại, xếp theo mức ảnh hưởng tới việc xây:**

1. **Nhãn có sẵn khi Apply:** đề xuất ở mục 9 có đúng ý không? Có cần chuyển shape của BTC thành track không?
2. **Mentor:** có cho phép tool ghi nhãn qua API và tải frame hàng loạt trên job thật không?
3. **Luật trạng thái mắt và vị trí điểm mí:** theo guideline v1.3 hay tài liệu trên CVAT ngày 14/7/2026?
4. **Thế nào là thành công:** người dùng muốn một job 200 frame xong trong bao lâu, và kiểm bằng cách nào?
5. **Tiêu chí quét (mục 8.2):** còn thiếu loại lỗi nào người dùng hay gặp?
6. **Ngưỡng:** 8 px và 15 px cho cảnh báo, 3 px cho track, 30 frame cho bộ nhớ đệm có hợp không?
7. **B:** người dùng chấp nhận B tắt mặc định cho tới khi xem kết quả trên ảnh công khai không?
8. **Bản nháp tự lưu ra đĩa** (chỉ toạ độ): có được không?
9. **Phiên bản CVAT của server công ty.**

## 13. Làm rõ thêm sau khi soát [Đề xuất, trừ khi ghi khác]

- **Mục tiêu "track không lệch"** chỉ có nghĩa: bản xem trước của tool khớp với CVAT, và keyframe luôn đủ 8 điểm.
  Điều kiện 3 px chỉ áp dụng cho track sinh từ gợi ý của model. Track vẽ bằng 4 điểm hoặc track có sẵn không có
  mốc so sánh nào khác.
- **Mã có sẵn:** `eye_prelabel.py` và `validate_eye_skeletons.py` nằm trong thư mục `week2\tools` cạnh thư mục dự
  án. Người xây chép hai file này vào dự án và dùng lại, không viết lại từ mô tả, để kết quả khớp với số đo trên
  200 frame.
- **Bản phác có hiệu lực:** `mockups/main-screen.html`. Hai file `edit-screen.html` và `four-point-interp.html`
  là bản cũ hơn, chỉ để tham khảo. `design-notes.md` là nhật ký trao đổi; khi khác nhau thì bản thiết kế này thắng.
- **Định nghĩa nhãn:** hai skeleton tên `mattrai` và `matphai`, sublabel tên là chuỗi số "14"–"21" và "22"–"29"
  (guideline v1.3 mục 5.3; project `eyes_label` trên CVAT local dựng theo đúng thế). Theo ghi chú từ một job thật:
  pre-label của BTC là shape ở từng frame, một số nhãn là track do người làm. Chưa đối chiếu định nghĩa trên
  server công ty với bản local.
- **Trước khi mentor trả lời:** trên server công ty, tool chỉ đọc nhãn và chạy Quét với các tiêu chí không cần
  ảnh. Không tải frame, không ghi. Chạy Hint cho một khoảng được tính là tải frame hàng loạt.
