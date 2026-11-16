# EyePin: hướng dẫn sử dụng (1 trang)

EyePin giúp gán nhãn hai mắt `mattrai` (điểm 14–21) và `matphai` (22–29) trong CVAT: bạn ghim **4 điểm mỗi mắt** ở vài frame, tool suy ra 8 điểm, bám theo ảnh sang các frame sau, rồi xuất file để import vào CVAT. Không dùng model học máy.

## 1. Mở tool
- Bấm lối tắt **Eyepin** trên Desktop (mở sẵn case 01), hoặc chạy `python -m eyepin gui <thư_mục_ảnh>`.
- Mở với điểm ghim có sẵn (dùng khi demo): `python -m eyepin gui <thư_mục_ảnh> --pins file.json`. Chế độ này **không khôi phục và không ghi file phiên**; xuất file import vẫn dùng được.
- Dữ liệu demo là ảnh công khai. Không đặt ảnh tài xế thật vào thư mục dự án.

## 2. Gán nhãn: 5 bước
1. **Vẽ từng mắt.** Bấm `n` (hoặc nút ghim trên thanh trái), chọn **Label** `mattrai (mắt trái)` hoặc `matphai (mắt phải)`, kiểu **Track**, rồi chọn cách vẽ: **Bấm 4 điểm** (hai khoé, giữa mí trên, giữa mí dưới, thứ tự tuỳ ý) hoặc **Kéo khung** quanh mắt để hiện mắt mẫu. Mắt vẽ xong màu cam: kéo 4 điểm to cho khớp, rồi bấm **Apply** (hoặc `n`); `Esc` huỷ. Làm lại cho mắt kia. Vẽ mắt này không tạo keyframe cho mắt kia. Shape chưa hỗ trợ.
2. **Xem frame sau.** Đi bằng `f`/`d` (frame kế/trước), `r`/`e` (frame ghim kế/trước), `Space` (phát). Dải thời gian: **xanh lá** = frame ghim, **xanh xám** = tool tính, **vàng** = cần ghim (bộ bám khớp kém, dưới 0,85).
3. **Sửa chỗ sai.** Ở frame vàng hoặc lệch: ghim lại bằng `n`, kéo một điểm, kéo vào thân mắt để dời cả mắt, kéo chấm trắng ở cạnh hoặc góc khung chọn để to/nhỏ mắt, hoặc kéo chấm tròn phía trên để xoay; frame đó thành frame ghim. `k` ghim/bỏ ghim frame hiện tại từ nhãn tool đã tính. Chỉ các frame **sau** frame ghim tới frame ghim kế bị đổi; frame trước không bao giờ đổi.
4. **Đầu quay, khoé bị che.** Bấm `Shift+N`, rồi bấm 4 điểm của mắt thấy đủ và 3 điểm của mắt bị che khoé; tool ước lượng khoé (hiện vòng sai số). `q` đánh Occluded, `o` đánh Outside cho điểm đang trỏ chuột.
5. **Lưu và xuất.** `Ctrl+S` lưu phiên trên máy (tự lưu mỗi 2 phút). `Ctrl+Shift+S` xuất file XML (CVAT 1.1). Khi import vào job, CVAT **xoá hết nhãn cũ của job**, nên file phải chứa mọi nhãn cần giữ.

`Ctrl+Shift+E` quét nhãn có sẵn tìm lỗi hình học (kết quả ở tab Issues). `F1` xem hết phím tắt, `F2` đổi phím.

**Đóng tool:** nếu còn thay đổi chưa lưu (tiêu đề cửa sổ có dấu `*`), tool hiện hộp hỏi: **Có** = lưu rồi thoát, **Không** = thoát và bỏ thay đổi, **Huỷ** = ở lại làm tiếp.

**Lưới và màu ảnh (như hộp Image setups của CVAT):** bấm nút `^` giữa mép dưới khung ảnh hoặc `Ctrl+G`. Image grid: bật lưới (phím `g`), Size tính bằng pixel ảnh (1 là lưới từng pixel; khi thu nhỏ lưới tự thưa ra, dòng trạng thái ghi bước đang vẽ), màu, Opacity. Color settings: Brightness, Contrast, Saturation (%, 100 là gốc), Gamma (lớn hơn 1 làm sáng vùng tối); "Reset color settings" chỉ đặt lại màu, không tắt lưới. Chỉ để nhìn, không đổi ảnh hay nhãn.

**Chuột quá nhạy?** Mở `F2` > tab Workspace > "Độ nhạy chuột khi kéo". Đặt dưới 1 (ví dụ 0,5) để điểm, mắt và ảnh đi chậm lại khi kéo; 1 là như cũ. Cuộn chuột để zoom thì chỉnh ở "Hệ số zoom mỗi nấc" cùng tab.

## 3. Phát hiện quay đầu và báo độ chính xác (mới 16/11)
- **Quay đầu:** cần ít nhất 3 frame ghim đủ hai mắt. Đoạn quay hiện thành **dải cam** phía trên dải thời gian (cam đậm = đã xác nhận bằng bề rộng mắt tại frame ghim, cam nhạt = chưa xác nhận, có thể do người lái tiến/lùi) và ở **đầu tab Issues**: `Quay đầu #1 frame 20–79 co 30% (mạnh) mắt xa: mattrai ...`. Bấm dòng đó, hoặc nút kế/trước, để nhảy tới đoạn. "Co" là mức khoảng cách hai mắt giảm so với tư thế thẳng nhất trong clip, không phải góc.
- **Độ chính xác:** `Ctrl+I` mở hộp Thông tin, bấm **Tính độ chính xác tại frame ghim bị giấu**. Bảng so điểm bạn ghim với đường thẳng của CVAT và với bộ bám của tool, tách trong/ngoài đoạn quay đầu và frame chớp mắt.
- **Dòng lệnh, không cần cửa sổ:**
  `python -m eyepin turns <thư_mục_ảnh> --pins file.json` và `python -m eyepin report <thư_mục_ảnh> --pins file.json`.

## 4. Đọc kết quả cho đúng
- Ranh giới đoạn chỉ chính xác khi các frame ghim trong đoạn quay cách nhau **không quá khoảng 20 frame**; ghim thưa hơn thì ranh giới dính vào frame ghim, và đoạn có thể bị gộp.
- Bảng độ chính xác **chỉ đo tại frame ghim bị giấu**, không phải mọi frame. Điểm ghim thô sai khoảng ±2 px (cỡ 3% bề rộng mắt) nằm trong các số, nên ngưỡng 5% sát nhiễu đó.
- Các ngưỡng được chỉnh trên **một clip** (case 01: một người, ban ngày, không kính). Chưa kiểm trên hồng ngoại, kính, ban đêm, nhiều người.
- Tool không phát hiện cúi/ngửa đầu, không đổi nhãn khi báo cáo, và chưa có cột bám hai chiều.

## 5. Làm thẳng với CVAT trên máy (localhost)
- **Mở:** menu → "Mở từ CVAT…" (hoặc `python -m eyepin gui --cvat http://localhost:8080 --job <số job>`). Nhập tên và mật khẩu CVAT, chọn task rồi job. Ảnh chỉ nằm trong bộ nhớ, không ghi ra đĩa; mật khẩu và khoá đăng nhập không được lưu. Chỉ nhận địa chỉ `localhost` (server công ty chưa bật). Cần CVAT đang chạy (Docker Desktop; nếu cổng 8080 không trả lời thì chạy `docker restart traefik`).
- **Job chưa có nhãn mắt:** gán nhãn như mục 2, rồi menu → "Gửi lên CVAT". Hộp xác nhận nói rõ lần gửi **thay toàn bộ nhãn của job** (mặc định là Không), cảnh báo nếu job đã bị sửa trên CVAT kể từ lúc bạn mở và nếu sẽ xoá nhãn mắt đang có. Gửi xong tool tải nhãn về từ CVAT và đối chiếu từng keyframe, cờ Occluded/Outside và vị trí; lệch thì báo chỗ lệch và có nút "Khôi phục job về bản trước khi gửi".
- **Job đã có nhãn mắt: chế độ QC.** Nhãn hiện đúng như trên CVAT, tool tự Quét và mở tab Issues; mọi lệnh sửa và "Gửi" bị tắt. Muốn sửa: "Xoá nhãn mắt cũ và gán lại" (hộp xác nhận nêu sẽ xoá gì; CVAT chưa đổi gì cho tới khi bạn gửi).
- **Job nào EyePin từ chối mở hoặc từ chối gửi (thay vì làm sai):** task tạo từ file video; job thưa hoặc ground truth; task có `start_frame` hoặc `frame_step` riêng (số frame trong file nhãn của CVAT khác số frame ảnh, chưa thử nên không đoán); job có đối tượng không phải mắt hoặc tag nằm trên frame đã xoá trong CVAT; job có tag mà nền phải là video (job có track không phải mắt). Lý do: lần gửi thay toàn bộ nhãn của job, những trường hợp này sẽ làm mất nhãn khác mà không khôi phục được.
- **Giới hạn khác:** chưa thử trên server công ty; xoá frame bị tắt ở chế độ này; chưa thử GUI với đăng nhập thật, job nhiều đoạn, hai người trong một job; job rất dài có thể làm cửa sổ đứng khi bám ghim (ảnh tải đồng bộ).

## 6. Phím hay dùng
| Việc | Phím | Việc | Phím |
|---|---|---|---|
| Vẽ một mắt / Apply | `n` | Ghim khi che khoé | `Shift+N` |
| Frame kế / trước | `f` / `d` | Frame ghim kế / trước | `r` / `e` |
| Ghim / bỏ ghim frame này | `k` | Hoàn tác / làm lại | `Ctrl+Z` / `Ctrl+Y` |
| Occluded / Outside | `q` / `o` | Xoay mắt 1° | `.` / `,` |
| Phóng / thu, vừa khung | `+` `-` `0` | Thông tin job | `Ctrl+I` |
