# EyePin: hướng dẫn sử dụng (1 trang)

EyePin giúp gán nhãn hai mắt `mattrai` (điểm 14–21) và `matphai` (22–29) trong CVAT: bạn ghim **4 điểm mỗi mắt** ở vài frame, tool suy ra 8 điểm, bám theo ảnh sang các frame sau, rồi xuất file để import vào CVAT. Không dùng model học máy.

## 1. Mở tool
- **Có tài khoản CVAT:** chạy `EyePin.bat` (hoặc `python -m eyepin gui`). Màn đăng nhập hiện trước: nhập địa chỉ CVAT, tên đăng nhập, mật khẩu rồi bấm Đăng nhập (xem mục 5). Muốn làm việc không cần CVAT thì bấm **Làm việc không cần CVAT → mở thư mục ảnh**.
- Bấm lối tắt **Eyepin** trên Desktop (đang trỏ tới `EyePin_case01.bat`: mở thẳng case 01, **không qua màn đăng nhập**), hoặc chạy `python -m eyepin gui <thư_mục_ảnh>` (cũng vào thẳng).
- Mở với điểm ghim có sẵn (dùng khi demo): `python -m eyepin gui <thư_mục_ảnh> --pins file.json`. Chế độ này **không khôi phục và không ghi file phiên**; xuất file import vẫn dùng được.
- Dữ liệu demo là ảnh công khai. Không đặt ảnh tài xế thật vào thư mục dự án.

## 2. Gán nhãn: 5 bước
1. **Vẽ từng mắt.** Bấm `n` (hoặc nút ghim trên thanh trái), chọn **Label** `mattrai (mắt trái)` hoặc `matphai (mắt phải)`, kiểu **Track**, rồi chọn cách vẽ: **Bấm 4 điểm** (hai khoé, giữa mí trên, giữa mí dưới, thứ tự tuỳ ý) hoặc **Kéo khung** quanh mắt để hiện mắt mẫu. Mắt vẽ xong màu cam: kéo 4 điểm to cho khớp, rồi bấm **Apply** (hoặc `n`); `Esc` huỷ. Làm lại cho mắt kia. Vẽ mắt này không tạo keyframe cho mắt kia. Shape chưa hỗ trợ.
2. **Xem frame sau.** Đi bằng `f`/`d` (frame kế/trước), `r`/`e` (frame ghim kế/trước), `Space` (phát). Dải thời gian: **xanh lá** = frame ghim, **xanh xám** = tool tính, **vàng** = cần ghim (bộ bám khớp kém, dưới 0,85).
3. **Sửa chỗ sai.** Ở frame vàng hoặc lệch: ghim lại bằng `n`, kéo một điểm, kéo vào thân mắt để dời cả mắt, kéo chấm trắng ở cạnh hoặc góc khung chọn để to/nhỏ mắt, hoặc kéo chấm tròn phía trên để xoay; frame đó thành frame ghim. `k` ghim/bỏ ghim frame hiện tại từ nhãn tool đã tính (hoặc bấm nút Keyframe trên thẻ của mắt đó). Chỉ các frame **sau** frame ghim tới frame ghim kế bị đổi; frame trước không bao giờ đổi.
4. **Đầu quay, khoé bị che.** Bấm `Shift+N`, rồi bấm 4 điểm của mắt thấy đủ và 3 điểm của mắt bị che khoé; tool ước lượng khoé (hiện vòng sai số). `q` đánh Occluded, `o` đánh Outside cho điểm dưới con trỏ (không có thì cho mục đang chọn ở panel; từng điểm cũng có nút riêng trong mục DETAILS của thẻ). `Del` xoá mắt dưới con trỏ, hoặc mắt đang chọn; xoá nhầm thì bấm `n` để vẽ lại mắt đó. Các phím theo con trỏ (`Del`, `h`, `l`, `q`, `o`) chỉ nhắm mắt/điểm **đang hiện**: con trỏ nằm trên mắt đã ẩn thì phím tác động mục đang chọn ở panel.
5. **Lưu và xuất.** `Ctrl+S` lưu phiên trên máy (tự lưu mỗi 2 phút). `Ctrl+Shift+S` xuất file XML (CVAT 1.1). Khi import vào job, CVAT **xoá hết nhãn cũ của job**, nên file phải chứa mọi nhãn cần giữ.

`Ctrl+Shift+E` quét nhãn có sẵn tìm lỗi hình học (kết quả ở tab Issues). `F1` xem hết phím tắt, `F2` đổi phím.

**Panel bên phải (kiểu CVAT)** có tab `Objects | Labels | Issues | Frame lân cận`.
- **Objects là danh sách thẻ:** mỗi mắt một thẻ (ID, `SKELETON TRACK`, chọn label, menu ⋮, nhảy keyframe, rồi các nút Outside, Lock, Occluded, Hidden, Keyframe, Pinned; mục DETAILS liệt kê 8 điểm, mỗi điểm có Outside và Occluded riêng). Bấm thẻ = chọn mắt, bấm đúp = phóng vào mắt, bấm phải = menu. Rê chuột lên mắt trên ảnh thì thẻ sáng lên và ngược lại (chỉ người đang chọn).
- **Hidden và Lock trên thẻ (và phím `h`, `l`) chỉ tác động MỘT mắt** của một người (mắt đang hiện dưới con trỏ, không có thì thẻ đang chọn; mắt đã ẩn thì hiện lại bằng thẻ của nó). `H` (ẩn mọi nhãn), `L` và nút khoá tất cả ở đầu danh sách (khoá/mở khoá mọi mắt của mọi người), các nút ở tab Labels tác động nhãn của mọi người. Khi một label đang ẩn ở tab Labels, nút Hidden trên thẻ của nó mờ đi (hiện label ở tab Labels trước).
- **Đổi label trên thẻ** (ô mattrai/matphai hoặc menu ⋮) hoán đổi hai mắt của người đó; trạng thái ẩn và Pinned đi theo mắt. Một trong hai mắt đang khoá thì không đổi được (mở khoá trước).
- **Tab "Frame lân cận"** (ảnh nhỏ các frame kề) tắt được: `F2` > Workspace > "Hiện tab Frame lân cận". Tắt thì tab biến mất và tool không tính ảnh nhỏ nữa.
- **Icon không có chữ cố định;** muốn biết nút làm gì (và phím tắt) thì trỏ chuột vào nút, chữ tiếng Việt hiện ra. Icon là bộ gốc của CVAT.
- Bấm ra ngoài ô số frame, hoặc rời ô bằng `Enter` (nhảy tới frame đã gõ), `↑`/`↓` (frame kế/trước), `Esc` (bỏ số đang gõ) hay `Tab`, thì bàn phím trả về ảnh, phím tắt dùng được ngay. Nút frame trước/sau ở thanh trên đi theo bộ lọc đang đặt, giống `←`/`→`.

**Đóng tool:** nếu còn thay đổi chưa lưu (tiêu đề cửa sổ có dấu `*`), tool hiện hộp hỏi: **Có** = lưu rồi thoát, **Không** = thoát và bỏ thay đổi, **Huỷ** = ở lại làm tiếp.

**Lưới và màu ảnh (như hộp Image setups của CVAT):** bấm nút `^` giữa mép dưới khung ảnh hoặc `Ctrl+G`. Image grid: bật lưới (phím `g`), Size tính bằng pixel ảnh (1 là lưới từng pixel; khi thu nhỏ lưới tự thưa ra, dòng trạng thái ghi bước đang vẽ), màu, Opacity. Color settings: Brightness, Contrast, Saturation (%, 100 là gốc), Gamma (lớn hơn 1 làm sáng vùng tối); "Reset color settings" chỉ đặt lại màu, không tắt lưới. Chỉ để nhìn, không đổi ảnh hay nhãn.

**Chuột quá nhạy?** Mở `F2` > tab Workspace > "Độ nhạy chuột khi kéo". Đặt dưới 1 (ví dụ 0,5) để điểm, mắt và ảnh đi chậm lại khi kéo; 1 là như cũ. Cuộn chuột để zoom thì chỉnh ở "Hệ số zoom mỗi nấc" cùng tab.

## 3. Phát hiện quay đầu và báo độ chính xác (mới 16/11)
- **Quay đầu:** cần ít nhất 3 frame ghim đủ hai mắt. Đoạn quay hiện thành **dải cam** phía trên dải thời gian (cam đậm = đã xác nhận bằng bề rộng mắt tại frame ghim, cam nhạt = chưa xác nhận, có thể do người lái tiến/lùi) và ở **đầu tab Issues**: `Quay đầu #1 frame 20–79 co 30% (mạnh) mắt xa: mattrai ...`. Bấm dòng đó, hoặc nút kế/trước, để nhảy tới đoạn. "Co" là mức khoảng cách hai mắt giảm so với tư thế thẳng nhất trong clip, không phải góc.
- **Độ chính xác:** `Ctrl+I` mở hộp Thông tin, bấm **Tính độ chính xác tại frame ghim bị giấu** (cuộn chuột trong ô kết quả để xem hết). Bảng so nhãn bạn ghim với đường thẳng của CVAT, với bộ bám của tool và với cách "hai chiều chọn theo độ khớp", tách trong/ngoài đoạn quay đầu và frame chớp mắt. Dòng đầu mỗi cách đoán là **IoU** của vùng mắt (1 = trùng khít, 0 = không chung chút nào; chỉ số chính), dòng sau là Dice, Boundary IoU, Precision/Recall và sai số điểm ghim (px). Đầu mỗi nhóm có **mốc**: IoU còn bao nhiêu khi chính nhãn đúng lệch 1 px theo chiều dọc mắt (thường khoảng 0,7), để biết IoU đọc được tốt tới đâu.
- **Dòng lệnh, không cần cửa sổ:**
  `python -m eyepin turns <thư_mục_ảnh> --pins file.json` và `python -m eyepin report <thư_mục_ảnh> --pins file.json`.

## 4. Đọc kết quả cho đúng
- Ranh giới đoạn chỉ chính xác khi các frame ghim trong đoạn quay cách nhau **không quá khoảng 20 frame**; ghim thưa hơn thì ranh giới dính vào frame ghim, và đoạn có thể bị gộp.
- Bảng độ chính xác **chỉ đo tại frame ghim bị giấu**, không phải mọi frame. Điểm ghim thô sai khoảng ±2 px (cỡ 3% bề rộng mắt) nằm trong các số, nên ngưỡng 5% sát nhiễu đó.
- Các ngưỡng được chỉnh trên **một clip** (case 01: một người, ban ngày, không kính). Chưa kiểm trên hồng ngoại, kính, ban đêm, nhiều người.
- Mắt rất dẹt, nên IoU tụt nhanh khi lệch dọc: lệch dọc 1 px đã còn khoảng 0,74, còn hai lần ghim thô (±2 px) cùng một mắt chỉ đạt khoảng 0,73. Vì vậy với ghim thô, IoU trên 0,75 khó đạt dù cách đoán đúng; mắt nhắm thì IoU gần 0 với mọi cách.
- Tool không phát hiện cúi/ngửa đầu và không đổi nhãn khi báo cáo. Cột "hai chiều" chỉ để so sánh: nhãn của tool vẫn chỉ bám tiến.

## 5. Làm thẳng với CVAT trên máy (localhost)
- **Đăng nhập (màn đầu tiên, mới 17/11):** `EyePin.bat` hoặc `python -m eyepin gui`. Đăng nhập xong, tool mở hộp chọn task rồi job (hoặc mở thẳng job nếu chạy `python -m eyepin gui --cvat http://localhost:8080 --job <số job>`; `--cvat` chỉ điền sẵn địa chỉ). Sau đó vẫn mở job khác bằng menu → "Mở từ CVAT…".
- **Ghi nhớ đăng nhập:** ô "Ghi nhớ đăng nhập trên máy này (8 giờ)" mặc định bật. Còn trong hạn thì lần mở sau **bỏ qua màn đăng nhập** và vào thẳng danh sách task. Tool chỉ nhớ **khoá** CVAT cấp, mã hoá bằng Windows (chỉ tài khoản Windows này đọc được, file `cvat_login.bin` trong thư mục `.eyepin`); **mật khẩu không bao giờ được lưu**. Đổi hạn ở `F2` > Workspace > "Nhớ đăng nhập CVAT (giờ)" (0 = không nhớ, tối đa 72). Khoá bị CVAT huỷ hoặc hết hạn thì tool xoá file và hiện màn đăng nhập; CVAT tắt thì giữ khoá và báo lỗi.
- **Đăng xuất (nút ngoài cùng bên phải thanh cam, hoặc menu → "Đăng xuất…"):** dọn dữ liệu làm việc trên máy này rồi **về màn đăng nhập** (không đóng tool; đăng nhập lại được bằng tài khoản khác, tool không tự mở lại job cũ). Nên bấm trước khi về nếu công ty quy định xoá file. Tool xoá: **khoá đăng nhập đã nhớ, tên đăng nhập, và mọi phiên làm việc đã lưu** (mọi file trong thư mục `sessions` của `.eyepin`: phiên job CVAT **và phiên thư mục ảnh**, ví dụ case 01). Tool **không xoá**: cài đặt (phím tắt, giao diện), ảnh gốc, và file bạn tự xuất ngoài `.eyepin` (bản chụp, file XML): nếu cần xoá thì bạn tự xoá. Phiên thư mục ảnh đang mở còn thay đổi chưa lưu: tool báo phiên đó sẽ bị xoá và hỏi **Tiếp tục?** (không hỏi lưu, vì bản lưu bị xoá ngay sau đó; cần giữ ghim thì Huỷ rồi xuất file import).
- **Thoát EyePin (nút ✕ cạnh nút Đăng xuất, menu → "Thoát EyePin", hoặc nút trên màn đăng nhập):** đóng tool như nút X của cửa sổ, **không xoá gì** (đăng nhập đã nhớ và phiên đã lưu vẫn còn).
  - **Hỏi trước khi xoá công chưa gửi.** Không có gì chưa gửi: một hộp xác nhận. Job đang mở còn ghim **chưa gửi lên CVAT**: hộp **Có** (gửi lên CVAT rồi đăng xuất) / **Không** (đăng xuất và bỏ công này) / **Huỷ** (mặc định). Gửi lỗi, đối chiếu lệch hoặc bạn huỷ ở hộp gửi thì tool dừng, không xoá gì. Các job khác còn phiên chưa gửi: tool liệt kê (số job, số frame ghim) và hỏi **Xoá luôn** / **Huỷ**; tool không tự gửi các job đó (cần mở job và đối chiếu).
  - **Phiên lưu từ trước 17/11** (chưa có cờ "chưa gửi") mà có ghim bị coi là "chưa rõ đã gửi hay chưa" và hiện trong danh sách trên: lần đăng xuất đầu có thể hỏi về các phiên thử cũ.
  - Xoá lỗi file nào (đang bị chương trình khác giữ...) thì tool báo **tên file**, không nói "đã sạch" và **ở lại job**: đóng chương trình giữ file đó rồi bấm Đăng xuất lại. Máy tắt đột ngột thì file tự lưu vẫn còn tới lần Đăng xuất sau.
  - Đây **chỉ là đăng xuất ở máy này**, không đăng xuất khỏi CVAT (khoá vẫn còn hiệu lực trên CVAT tới khi CVAT tự huỷ; muốn huỷ hẳn thì đăng xuất trên web CVAT).
- **Màn đăng nhập không phải cổng bảo vệ:** nó chỉ kiểm tài khoản CVAT. Tool chạy trên máy, nên ảnh và file trên máy vẫn mở được qua liên kết "Làm việc không cần CVAT" hoặc qua dòng lệnh.
- **Mở:** nhập tên và mật khẩu CVAT, chọn task rồi job. Ảnh chỉ nằm trong bộ nhớ, không ghi ra đĩa. Chỉ nhận địa chỉ `localhost` (server công ty chưa bật). Cần CVAT đang chạy (Docker Desktop; nếu cổng 8080 không trả lời thì chạy `docker restart traefik`).
- **Job chưa có nhãn mắt:** gán nhãn như mục 2, rồi menu → "Gửi lên CVAT". Hộp xác nhận nói rõ lần gửi **thay toàn bộ nhãn của job** (mặc định là Không), cảnh báo nếu job đã bị sửa trên CVAT kể từ lúc bạn mở và nếu sẽ xoá nhãn mắt đang có. Gửi xong tool tải nhãn về từ CVAT và đối chiếu từng keyframe, cờ Occluded/Outside và vị trí; lệch thì báo chỗ lệch và có nút "Khôi phục job về bản trước khi gửi".
- **Job đã có nhãn mắt: chế độ QC.** Nhãn hiện đúng như trên CVAT, tool tự Quét và mở tab Issues; mọi lệnh sửa và "Gửi" bị tắt. Muốn sửa: "Xoá nhãn mắt cũ và gán lại" (hộp xác nhận nêu sẽ xoá gì; CVAT chưa đổi gì cho tới khi bạn gửi).
- **Job nào EyePin từ chối mở hoặc từ chối gửi (thay vì làm sai):** task tạo từ file video; job thưa hoặc ground truth; task có `start_frame` hoặc `frame_step` riêng (số frame trong file nhãn của CVAT khác số frame ảnh, chưa thử nên không đoán); job có đối tượng không phải mắt hoặc tag nằm trên frame đã xoá trong CVAT; job có tag mà nền phải là video (job có track không phải mắt). Lý do: lần gửi thay toàn bộ nhãn của job, những trường hợp này sẽ làm mất nhãn khác mà không khôi phục được.
- **Giới hạn khác:** chưa thử trên server công ty; xoá frame bị tắt ở chế độ này; chưa thử GUI với đăng nhập thật (màn đăng nhập mới chỉ thử với CVAT giả), job nhiều đoạn, hai người trong một job; job rất dài có thể làm cửa sổ đứng khi bám ghim (ảnh tải đồng bộ).

## 6. Phím hay dùng
| Việc | Phím | Việc | Phím |
|---|---|---|---|
| Vẽ một mắt / Apply | `n` | Ghim khi che khoé | `Shift+N` |
| Frame kế / trước | `f` / `d` | Frame ghim kế / trước | `r` / `e` |
| Ghim / bỏ ghim frame này | `k` | Hoàn tác / làm lại | `Ctrl+Z` / `Ctrl+Y` |
| Occluded / Outside | `q` / `o` | Xoay mắt 1° | `.` / `,` |
| Ẩn / khoá một mắt | `h` / `l` | Ẩn / khoá mọi nhãn | `H` / `L` |
| Xoá mắt (dưới con trỏ) | `Del` | Xoá cả mắt đang khoá | `Shift+Del` |
| Phóng / thu, vừa khung | `+` `-` `0` | Thông tin job | `Ctrl+I` |
