# Bản thiết kế v3 — tool hỗ trợ gán nhãn mắt DMS cho CVAT

**Ngày:** 2026-11-13 · **Trạng thái:** bản nháp chờ người dùng duyệt. Thay cho bản v2 ngày 2026-11-12.

Cách đọc: **[Đã chốt]** là điều người dùng đã nói hoặc đã đồng ý. **[Đề xuất]** là lựa chọn của người viết, người
dùng chưa xác nhận. **[Còn mở]** là câu hỏi chưa có câu trả lời (mục 10). **[Đã kiểm]** là điều đã chạy thử và
thấy kết quả.

Tài liệu đi kèm:

- `cvat-keyframe-behaviour.md`: keyframe của CVAT vận hành thế nào (đọc từ mã nguồn CVAT 2.75).
- `../guideline/`: guideline học viên v1.3 và tài liệu lấy từ CVAT ngày 14/7/2026 (Phụ lục B của tài liệu sau
  liệt kê chỗ hai bản khác nhau).
- `../spike/`: bản demo dùng một lần ngày 2026-11-12 và kết quả (`out/qc_report.md`). Không phải mã sản phẩm.
- `mockups/main-screen.html`: bản phác màn hình (nút Hint trong đó không còn hiệu lực).

---

## 1. Mục đích

Người dùng gán nhãn hai skeleton mắt của bài DMS Landmark trong CVAT: `mattrai` (8 điểm, ID 14–21) và `matphai`
(8 điểm, ID 22–29). Tool là một cửa sổ riêng trên máy, giúp phần vẽ mắt nhanh và ít lỗi hơn; CVAT vẫn là nơi lưu
nhãn.

**Vì sao làm bây giờ [Đã chốt].** Người dùng sẽ trình bày một bản demo cho mentor và đội phát triển tool. Nếu demo
thành công, người dùng được truy cập dữ liệu lớn để làm việc. Demo ghi điểm khi có **một tính năng thật sự nổi
trội và tiện**, nhất là khi gán được **những trường hợp hiếm** mà cách làm hiện tại xử lý kém.

**Ba chỗ đau [Đã chốt]:**

1. Vẽ tay từng shape cho 200 frame quá lâu.
2. Dùng track thì nhãn bị lệch và keyframe rất rối: sửa một keyframe là frame giữa lệch theo, một số điểm tự di
   chuyển, khó biết mình đã sót keyframe.
3. Mắt bị khuất khi nghiêng hoặc quay đầu: nếu còn thấy khoảng trên 70% mắt thì vẫn phải vẽ và tự đoán vị trí khoé
   mắt bị che. Việc này khó với người gán, và model không phát hiện được.

## 2. Được phép, không được phép, chưa rõ

| Việc | Tình trạng | Ghi chú |
| --- | --- | --- |
| Dùng model nhận diện khuôn mặt hay điểm mốc để sinh nhãn | **Không được phép** [Đã chốt] | Bỏ hẳn phần gợi ý bằng MediaPipe |
| Lưu ảnh của công ty trên ổ đĩa của máy | **Được phép** [Đã chốt] | |
| Đưa ảnh lên mạng hoặc GitHub | **Không được phép** [Đã chốt] | |
| Thử nghiệm tự do trên CVAT local với dữ liệu công khai | **Được phép** [Đã chốt] | |
| Ghi nhãn vào job bằng tính năng import của CVAT | **Được phép** [Đã chốt] | Thay cho việc sửa từng nhãn qua API |
| Dùng trợ lý AI bên ngoài (Codex, Claude) cho việc import, prelabel và QC | **Được phép** [Đã chốt] | |
| Trợ lý AI trong mạng nội bộ công ty | **Chỉ Codex** [Đã chốt] | Claude chỉ dùng để phát triển và thử trên dữ liệu công khai |
| Đo trên điểm ảnh bằng xử lý ảnh thông thường (bám vùng mắt, dò mép sáng tối) | Coi là được phép [Đề xuất] | Chính người dùng đề xuất cách đo pixel sau khi có lệnh không dùng model; cần xác nhận lại với công ty |
| Cho Codex xem ảnh tài xế của công ty | **Chưa rõ** [Còn mở] | Ảnh gửi cho Codex là ảnh rời khỏi máy. Mặc định: Codex chỉ làm việc với toạ độ |
| Luật trạng thái mắt theo tài liệu nào | **Chưa rõ** [Còn mở] | Guideline v1.3 và tài liệu CVAT 14/7/2026 khác nhau |

## 3. Phạm vi

### 3.1. Bản demo (làm trước) [Đề xuất về cách chia]

1. Vẽ mắt bằng 4 điểm ghim, tool suy ra 4 điểm còn lại (mục 6.1).
2. Giữa các frame ghim, nhãn bám theo mắt, và keyframe ghi ra luôn đủ 8 điểm (mục 6.2).
3. **Tính năng chính của demo:** ước lượng khoé mắt bị che khi quay đầu (mục 6.3).
4. Màn hình chỉnh sửa có hai ảnh nhỏ frame trước và frame sau, đo bằng pixel (mục 6.5).
5. Quét nhãn để ra danh sách frame cần chú ý, chỉ dùng toạ độ (mục 6.6).
6. Xuất một file để import vào job (mục 6.7).

### 3.2. Làm sau demo

- Cách B: dò theo điểm ảnh để dời điểm suy ra tới mép mí thật [Đã chốt là muốn có].
- Thêm cách xử lý cho các trường hợp hiếm khác; người dùng sẽ bổ sung dần [Đã chốt].
- Bộ chỉ dẫn hoàn chỉnh cho Codex (mục 6.8 chỉ nêu khung).
- Năm skeleton còn lại của bài DMS.

### 3.3. Ngoài phạm vi

- Mọi model học máy để tìm mắt hay điểm mốc.
- Tự nhận diện ai là ai. Người dùng tự chia đoạn theo người [Đã chốt].
- Thay thế giao diện CVAT; chạy cho nhiều người dùng; chạy dưới dạng trang web [Đã chốt là cửa sổ riêng].
- Nhãn Face và bài HumanPose.

### 3.4. Điều phải tránh

- Đưa ảnh công ty ra khỏi máy.
- Ghi vào CVAT khi người dùng chưa chủ động xuất và import.
- Làm mất hoặc làm đổi nhãn không phải của hai mắt.
- Ghi keyframe lẻ từng điểm.
- Trình bày một điểm ước lượng như điểm nhìn thấy.

## 4. Ràng buộc kỹ thuật

### 4.1. Hành vi của CVAT (bản 2.75)

- Giữa hai keyframe, từng điểm được nội suy đường thẳng theo số frame. Sau keyframe cuối, điểm giữ nguyên vị trí
  tới hết job. Trước keyframe đầu, điểm coi như Outside.
- Occluded và Outside ở frame giữa lấy từ keyframe bên trái, không nội suy.
- Trong skeleton track, mỗi điểm có danh sách keyframe riêng. Kéo một điểm trong CVAT chỉ ghim riêng điểm đó,
  nhưng ngôi sao keyframe của cả skeleton vẫn sáng. Đây là nguyên nhân chỗ đau số 2.
- **Import vào job mặc định xoá toàn bộ nhãn đang có của job rồi mới nạp file.** File import vì thế phải chứa mọi
  nhãn của job.
- [Đã kiểm] Một file định dạng "CVAT 1.1" chứa được cả shape (thẻ `image`) lẫn track (thẻ `track`). Sau khi
  import, shape vẫn là shape, track vẫn là track với đúng các keyframe và cờ Occluded của từng điểm.
- [Đã kiểm] File track skeleton do tool tạo (keyframe đủ 8 điểm) import được vào job trên CVAT local. Việc import
  được gọi từ phía server; chưa thử qua đường API hay giao diện.

### 4.2. Kết nối

- Server công ty chỉ vào được từ máy đã đăng ký địa chỉ MAC, khi nối Wi-Fi công ty [Đã chốt].
- [Đã kiểm trên server công ty] Đăng nhập bằng username và password của CVAT qua `POST /api/auth/login`; khoá trả
  về dùng với header `Authorization: Token <khoá>`; lệnh gọi kèm `?org=2D`.
- Mật khẩu chỉ nằm trong RAM. Không ghi mật khẩu hay khoá vào file của dự án.
- Chưa biết server công ty chạy bản CVAT nào [Còn mở].

### 4.3. Guideline

- Thứ tự điểm, trái/phải theo khung hình, tỉ lệ vị trí điểm: theo guideline v1.3 mục 2 và 3.3.
- Guideline v1.3 mục 4.2: mắt còn thấy từ 4/8 điểm thì đặt đủ, điểm không thấy đánh Occluded; dưới 4/8 thì Outside
  cả skeleton. Tài liệu CVAT 14/7/2026: còn thấy từ 4 điểm thì đoán vị trí và không gán Occluded cho điểm nào; bị
  che từ 5 điểm thì Occluded cả nhãn. Người dùng nói ngưỡng "khoảng trên 70%". Ba nguồn chưa khớp nhau [Còn mở].

### 4.4. Môi trường

Windows 11, Python 3.12. Có sẵn: Tkinter, Pillow, OpenCV, NumPy, requests. Cửa sổ dựng bằng Tkinter để không phải
cài thêm [Đề xuất].

## 5. Cách dùng

1. Mở tool, chọn job. Tool tải danh sách frame, nhãn hiện có và ảnh (ảnh được lưu đệm trên đĩa).
2. Người dùng chia đoạn theo người nếu job có nhiều người.
3. Ở các frame cần ghim, người dùng đặt 4 điểm mỗi mắt. Tool suy ra 4 điểm còn lại.
4. Tool tính nhãn cho các frame ở giữa và đánh dấu những frame nó không chắc.
5. Người dùng lướt qua, sửa hoặc ghim thêm ở frame bị đánh dấu. Ở frame mắt bị che, tool gợi ý khoé bị che.
6. Người dùng bấm xuất. Tool tạo một file annotation chứa toàn bộ nhãn của job.
7. File được import vào job bằng tính năng import của CVAT, rồi người dùng tải lại trang job để kiểm tra.

## 6. Tính năng

### 6.1. Vẽ bằng 4 điểm [Đã chốt]

- Điểm ghim: 14, 16, 18, 20 (mắt trái) và 22, 24, 26, 28 (mắt phải). Tool suy ra 15, 17, 19, 21 và 23, 25, 27, 29.
- Cách A: với mỗi mí, dựng một parabol qua hai khoé và điểm giữa mí trong hệ trục khoé–khoé; các điểm còn lại
  đặt trên parabol tại vị trí dọc trục theo guideline v1.3 mục 3.3:

  | Mắt | Mí trên | Mí dưới |
  | --- | --- | --- |
  | mattrai (tính từ điểm 14) | 15 tại 0,21 · 17 tại 0,76 | 21 tại 0,24 · 19 tại 0,76 |
  | matphai (tính từ điểm 22) | 23 tại 0,23 · 25 tại 0,79 | 29 tại 0,25 · 27 tại 0,78 |

- Mắt nhắm: hai điểm giữa mí trùng nhau, parabol thành đường thẳng.
- Điểm suy ra mà người dùng đã kéo tay thì coi là điểm đặt tay, không bị tính lại [Đề xuất].
- Đã có mã cho cách A: `week2\tools\eye_interp.py`.

### 6.2. Giữa các frame ghim [Đề xuất, rút ra từ bản demo dùng một lần]

Bản demo trên 200 frame liên tiếp cho thấy:

- Nội suy đường thẳng giữa hai frame ghim cách nhau 50 frame lệch trên 5 px ở 125/200 frame, nặng nhất 17 px, vì
  đầu không cử động đều.
- Bám theo vùng ảnh quanh mắt (so khớp mẫu, không dùng model) giữ đúng vị trí khi mắt mở, nhưng không đổi được
  dáng mắt, nên sai khi chớp mắt. Trên một đoạn dài, phép bám trôi hẳn khỏi mắt.

Thiết kế:

- **Ba loại frame.** *Frame ghim*: người dùng đặt hoặc sửa điểm bằng tay; chỉ loại này làm mốc cho phép bám, làm
  mẫu dáng mắt ở mục 6.3, và được tính là công sức ở mục 8. *Frame tool tính*: tool lưu lại nhãn đã tính cho từng
  frame; nhãn này chỉ đổi khi frame ghim đứng ngay trước nó được đặt hoặc sửa. *Frame chưa có nhãn.*
- **Khi nào tính lại [Đã chốt].** Ghim hoặc sửa frame N thì chỉ các frame **sau** N, cho tới frame ghim kế tiếp,
  được tính lại theo frame N. Các frame trước N không bao giờ đổi.
- **Vị trí** của mắt ở frame tool tính lấy từ phép bám theo vùng ảnh, đi tới từ frame ghim đứng ngay trước nó
  [Đề xuất].
- **Dáng mắt** ở frame tool tính giữ như ở frame ghim đứng ngay trước nó. Khi mắt đổi dáng (bắt đầu nhắm, mở lại),
  người dùng ghim frame đó [Đề xuất; khớp với cách người dùng mô tả: frame đổi dáng mắt thì ghim rồi sửa].
- Hệ quả: muốn sửa một đoạn bị lệch thì ghim ở **frame đầu tiên** của đoạn lệch, không phải ở giữa hay cuối đoạn.
  Danh sách frame cần chú ý vì thế nhảy tới frame đầu của mỗi đoạn [Đề xuất].
- Tại mỗi frame ghim, tool hiện độ chênh pixel giữa nhãn tool tính ở frame liền trước và nhãn ghim, để người dùng
  thấy đoạn trước đó đã lệch bao nhiêu.
- Frame mà phép bám không chắc (độ khớp thấp, hoặc độ chênh lớn khi gặp frame ghim kế tiếp) được đánh dấu "cần ghim" trên
  dòng thời gian, thay vì đưa ra nhãn sai. Ngưỡng cụ thể để người xây chọn và đo trên dữ liệu thử; ngưỡng độ khớp
  0,6 dùng trong bản demo đã không bắt được frame nhắm mắt nào.
- **Keyframe ghi ra CVAT:** tool chọn số keyframe ít nhất sao cho phép nội suy đường thẳng của CVAT không lệch quá
  2 px so với vị trí tool đã tính ở mọi frame. Mọi keyframe đủ 8 điểm. Trong bản demo, điều này cần 36 keyframe cho
  200 frame.
- Bản xem trước của tool phải cho đúng vị trí mà CVAT sẽ hiển thị sau khi import.

### 6.3. Ước lượng khoé mắt bị che (tính năng chính của demo)

**Bốn bước đã chốt [Đã chốt]:**

1. Lấy mắt còn thấy rõ của chính người đó làm mẫu dáng mắt.
2. Ở frame bị che, người dùng đặt các điểm còn nhìn thấy.
3. Tool gợi ý vị trí khoé bị che, kèm vùng sai số, rồi tự đánh trạng thái cho điểm đó.
4. Tool ghi keyframe đủ 8 điểm, gồm cả trạng thái.

**Cách tính [Đề xuất]:**

- Mẫu dáng mắt lấy từ **chính con mắt đó ở các frame khác**: những frame ghim của người đó (trong đoạn do người
  dùng chia) mà cả 4 điểm ghim của mắt đó đều nhìn thấy. Không dùng dữ liệu của người khác và không huấn luyện gì.
- Khi trong đoạn không có frame nào như vậy, tool dùng mắt còn lại của người đó, lật ngang, lấy từ frame gần nhất
  mà mắt ấy thấy đủ (kể cả chính frame đang xét). Không có cả hai thì tool không gợi ý [Đề xuất].
- Điểm suy ra nằm giữa khoé ước lượng và điểm giữa mí (ví dụ 17 và 19 khi khoé 18 bị che) mặc định được coi là
  điểm ước lượng và nhận cùng trạng thái với khoé đó. Người dùng đổi lại từng điểm bằng phím tắt [Đề xuất].
- Ở frame bị che, tool khớp mẫu vào các điểm ghim còn thấy bằng phép dịch, xoay, co giãn và ép hẹp theo chiều
  ngang (mắt hẹp lại khi đầu quay), rồi đọc ra vị trí điểm bị che.
- Cần ít nhất 3 trong 4 điểm ghim của mắt đó nhìn thấy. Ít hơn thì tool không gợi ý.
- Vùng sai số lấy từ phép thử che giả ở mục 8.
- Gợi ý vẽ khác kiểu với điểm thường (ví dụ nét đứt) cho tới khi người dùng chấp nhận hoặc kéo lại.

**Trạng thái [Còn mở].** Điểm ước lượng được đánh Occluded hay để Visible tuỳ theo tài liệu nào được dùng để
chấm (mục 4.3). Tool có một cài đặt chọn giữa hai bộ luật; mặc định theo guideline v1.3 cho tới khi mentor trả lời
[Đề xuất].

**Mở rộng [Đã chốt là sẽ bổ sung].** Mỗi trường hợp hiếm là một phần riêng gồm: điều kiện nhận ra trường hợp, cách
gợi ý, và luật trạng thái. Thêm một trường hợp mới không phải sửa các phần còn lại của tool [Đề xuất về cách tổ
chức].

### 6.4. Chia đoạn theo người [Đã chốt]

- Người dùng tự xác định mỗi người từ frame bao nhiêu đến bao nhiêu. Mặc định cả job là một đoạn.
- Mẫu dáng mắt (mục 6.3) và mọi thông số học từ các lần người dùng sửa chỉ dùng trong đoạn đó.
- Phép bám và nội suy không đi qua mốc chia đoạn; frame đầu mỗi đoạn phải là frame ghim [Đề xuất].

### 6.5. Màn hình chỉnh sửa

- **Khung chính:** frame đang chọn, phóng to vào hai mắt; kéo điểm để chỉnh; điểm ghim vẽ to, điểm suy ra vẽ nhỏ,
  điểm ước lượng vẽ khác kiểu. Đặt trạng thái từng điểm bằng phím tắt; có hoàn tác [Đề xuất cho phóng to, phím tắt,
  hoàn tác].
- **Hai ảnh nhỏ bên phải [Đã chốt]:** frame N−1 chỉ để so sánh với frame N; frame N+1 cho thấy nó đổi thế nào khi
  sửa frame N. Mọi độ dịch chuyển tính và hiển thị bằng pixel.
- **Ngưỡng cảnh báo:** vàng khi một điểm dịch trên 8 px, đỏ trên 15 px, chỉnh được [Đề xuất].
- **Sửa chỉ lan về phía sau [Đã chốt]:** ghim hoặc sửa frame N thì các frame sau đổi theo frame N; frame N−1 và
  mọi frame trước nó không bị kéo. Vì tool lưu nhãn riêng cho từng frame, không cần ghim thêm frame N−1 để giữ nó
  đứng yên, nên hộp hỏi "ghim frame trước?" ở các bản thiết kế cũ được bỏ [Đề xuất bỏ hộp hỏi].
- **Dòng thời gian:** frame ghim, frame tool tính, frame cần ghim, frame chưa có nhãn, frame cần chú ý sau khi
  quét, mốc chia đoạn. Nếu nhãn đọc từ CVAT có keyframe chỉ ghim một phần số điểm, đánh dấu "keyframe thiếu" kèm
  nút ghim đủ [Đề xuất].

### 6.6. Quét [Đã chốt về luồng; tiêu chí là đề xuất]

Tool đi từ frame đầu tới frame cuối rồi đưa ra danh sách frame cần chú ý; bấm vào một dòng thì nhảy tới frame đó.

- **Đỏ, sai luật chắc chắn:** điểm 14 hoặc 22 không phải điểm trái nhất của mắt, điểm 18 hoặc 26 không phải điểm
  phải nhất; mí trên nằm dưới mí dưới; đường viền bắt chéo; điểm ngoài khung hình mà không Outside; thiếu điểm
  hoặc trùng skeleton.
- **Vàng, đáng nghi:** một điểm nhảy quá 15 px so với frame liền trước; keyframe thiếu; nhãn y hệt nhau qua nhiều
  frame liền; độ mở mắt đổi đột ngột; hai mắt có độ mở khác nhau nhiều.
- Số đo kèm mỗi frame: bề rộng mắt, độ mở ở ba cặp mí, tỉ lệ độ mở trên bề rộng, góc trục khoé–khoé, khoảng cách
  hai mắt, độ dịch so với frame trước. Ngưỡng tính theo tỉ lệ với bề rộng mắt [Đề xuất].
- Đã có mã kiểm tra hình học: `week2\tools\validate_eye_skeletons.py`.

### 6.7. Xuất file để import [Đã chốt về cách ghi; chi tiết là đề xuất]

- Tool không sửa nhãn trên server. Nó tạo **một file "CVAT 1.1"** chứa toàn bộ nhãn của job: hai mắt do tool tạo,
  mọi nhãn khác chép nguyên từ job (shape giữ là shape, track giữ là track).
- Trước khi tạo file, tool đọc lại nhãn hiện có của job và lưu một bản sao để khôi phục được.
- Sau khi import, tool đọc lại nhãn và báo hai điều: hai mắt có khớp bản xem trước không, và các nhãn khác có giữ
  nguyên không.
- CVAT local: tool tự gọi import. Server công ty: tool chỉ tạo file; người dùng hoặc Codex import bằng tính năng
  import của CVAT [Đề xuất].
- Người dùng chọn ghi hai mắt dưới dạng track hay shape [Đã chốt là có cả hai kiểu].
- **Nhãn mắt có sẵn trong job [Đề xuất].** Khi mở job, tool đọc nhãn mắt có sẵn và tính ra vị trí từng frame đúng
  như CVAT hiển thị; các frame này vào bảng như "frame có sẵn". Frame người dùng không đụng tới giữ nguyên vị trí
  đó khi xuất. Frame người dùng đã ghim hoặc cho tool tính thì lấy theo tool. Nếu nhãn trên CVAT đã đổi so với lúc
  mở job, tool báo và không xuất đè. Nhờ vậy xuất giữa chừng một phiên làm dở vẫn an toàn.

### 6.8. Vai trò của trợ lý AI [Đã chốt về vai trò; phạm vi là đề xuất]

- Người dùng muốn trợ lý AI làm hai việc: QC và prelabel. Trong mạng công ty, trợ lý là Codex.
- Mọi logic nằm trong các script chạy độc lập; trợ lý chỉ gọi script và đọc kết quả. Chỉ dẫn cho trợ lý viết thành
  file văn bản mà Codex đọc được.
- Mặc định trợ lý chỉ làm việc với toạ độ, bảng số đo và file annotation. Việc trợ lý xem ảnh để ghim điểm chỉ bật
  cho dữ liệu công khai, cho tới khi rõ Codex có được xem ảnh công ty không.
- Bản demo dùng một lần đã thử vai trò này với Claude đóng thế Codex; Codex chưa được chạy.

## 7. Dữ liệu thử (CVAT local, project `eyes_label`)

| Task | Nội dung | Frame |
| --- | --- | --- |
| #2 | Ảnh rời: 140 hồng ngoại (DMD) và 60 ảnh màu (YawDD) | 200 |
| #3, #4 | Video màu liên tiếp, mặt gần thẳng, ảnh cháy sáng, có chớp mắt (PhysDrive 2352–2551). Đang chứa track của bản demo dùng một lần | 100 + 100 |
| #5 | Quay đầu, mắt bên xa bị che một phần, có chớp mắt lúc quay (7650–7859) | 210 |
| #6 | Quay đầu qua lại, cúi nhắm mắt, tóc che mắt (680–879) | 200 |
| #7 | Mặt sát mép khung hình (2630–2729) | 100 |
| #8 | Quay hẳn đi, không thấy mắt (2780–2894) | 115 |
| #9 | Tay che trán và mắt (2895–2984) | 90 |

- Video PhysDrive chỉ có một người, ban ngày, không kính. README của bộ dữ liệu ghi có giới hạn về đạo đức nghiên
  cứu; chỉ dùng nội bộ để thử.
- Chưa có: video ban đêm hoặc hồng ngoại liên tiếp, kính loá trong video, job có nhiều người.
- Không có nhãn chuẩn do người gán cho bất kỳ dữ liệu nào ở trên.

## 8. Cách chứng minh trong demo [Đề xuất]

1. **Công sức:** số điểm người dùng phải đặt tay so với tổng số điểm được gán, trên task #5.
2. **Khoé bị che:** lấy các frame mà khoé mắt nhìn thấy rõ, che giả khoé đó, cho tool ước lượng, so với vị trí
   thật. Báo sai số bằng pixel và theo tỉ lệ bề rộng mắt. Con số này cũng là vùng sai số hiển thị ở mục 6.3.
3. **Khớp với CVAT:** sau khi import, vị trí từng frame đọc từ CVAT trùng với bản xem trước của tool.
4. **Không đụng nhãn khác:** thêm vài nhãn của skeleton khác vào job trước khi thử; sau khi import chúng giữ nguyên.
5. **Keyframe sạch:** mọi keyframe trong job sau khi import đều đủ 8 điểm.

**Điểm đối chiếu lấy từ đâu.** Không có nhãn chuẩn, nên mọi con số ở trên so với **điểm ghim tay được để riêng
ra**: ghim dày trên một đoạn, giấu bớt một phần điểm ghim, cho tool tính, rồi so với phần đã giấu. Phép thử che
giả ở điểm 2 cũng làm theo cách này trên chính các frame ghim.

- Trong lúc phát triển, người xây tự ghim trên dữ liệu công khai; các điểm đó chưa được ai kiểm, nên con số khi
  phát triển chỉ để so sánh giữa các cách làm.
- Con số đem ra demo cần điểm ghim của chính người dùng trên task #5 (xem mục 10, câu C).
- Giới hạn: phép thử che giả chỉ chạy được ở frame mà khoé mắt còn thấy, tức là lúc đầu quay ít. Vùng sai số hiển
  thị ở frame quay mạnh vì thế là con số suy rộng ra, và phải được ghi rõ như vậy khi trình bày.

## 9. Để người xây quyết định

- Cấu trúc mã, phím tắt, định dạng file bản nháp và thư mục đệm ảnh (thư mục đệm nằm ngoài thư mục mã nguồn).
- Cách so khớp vùng ảnh và ngưỡng "không chắc" ở mục 6.2, miễn là đo được trên task #3 đến #6.
- Cách khớp mẫu dáng mắt ở mục 6.3, miễn là phép thử che giả ở mục 8 cho ra con số.
- Cách gọi import trên CVAT local.
- Thứ tự làm. Gợi ý: đọc job và hiển thị → vẽ 4 điểm → xuất và import trên CVAT local (chứng minh mục 8.3–8.5
  sớm) → giữa các frame ghim → khoé bị che → quét.
- Mã trong `../spike/` chỉ để tham khảo; không dùng lại nguyên trạng.

## 10. Câu hỏi còn mở

### Hai câu cần trả lời trước khi lập plan (từ lần soát độc lập ngày 2026-11-13)

- **A (đã trả lời ngày 2026-11-13).** Ghim một frame thì chỉ các frame sau nó đổi theo; các frame trước không bao
  giờ được tính lại. Đã đưa vào mục 6.2 và 6.5.
- **B. Demo diễn ra ở đâu và khi nào?** Trên CVAT local với các task PhysDrive công khai, hay trên một job thật của
  công ty? Nếu là job thật thì phần import thủ công và các câu 3, 9 bên dưới nằm trên đường găng. Nếu là local: ảnh
  PhysDrive có được chiếu cho mentor và đội tool xem không (README của bộ dữ liệu có giới hạn sử dụng)?
- **C. Người dùng có tự ghim một tập frame đối chiếu trên task #5 trước buổi demo không?** Các con số ở mục 8 cần
  điểm ghim của chính người dùng. Ước lượng: khoảng 40 frame, mỗi frame 8 điểm.

### Các câu còn lại (đã có mặc định, không chặn việc lập plan)

1. **Luật trạng thái mắt** theo guideline v1.3 hay tài liệu CVAT 14/7/2026? Điều này quyết định điểm ước lượng
   được đánh Occluded hay không.
2. **Ngưỡng vẽ hay không vẽ:** "khoảng trên 70%" của người dùng tương ứng với mấy trong 8 điểm, và dưới ngưỡng thì
   Outside cả skeleton hay Occluded cả skeleton?
3. **Xử lý ảnh thông thường trên ảnh công ty** (bám vùng mắt, dò mép) có nằm trong lệnh "không dùng model" không?
4. **Codex có được xem ảnh tài xế của công ty không?**
5. **Track kết thúc ở đâu?** Đề xuất: mỗi mắt một track cho mỗi đoạn theo người, kết thúc bằng Outside ở cuối đoạn.
6. **"Sửa chỉ lan về phía sau" tới đâu?** Đề xuất: tới frame ghim kế tiếp, như cách CVAT nội suy.
7. **Thế nào là demo thành công?** Mentor và đội tool cần thấy con số nào hoặc cảnh nào.
8. **Nhãn mắt có sẵn trong job thật** (pre-label dạng shape của BTC): tool giữ dạng shape hay đổi sang track?
9. **Phiên bản CVAT của server công ty,** và tính năng import ở đó có nhận file chứa cả shape lẫn track không.
