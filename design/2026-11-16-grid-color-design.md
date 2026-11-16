# Lưới ảnh và chỉnh màu (Image setups như CVAT, thêm phần đo)

Ngày 2026-11-16. Bản thiết kế ngắn, chờ người dùng duyệt. Chỗ ghi "đề xuất của mình" là người viết tự quyết.

## Ý định và lý do

Khảo sát annotator do người dùng hỏi (2026-11-16): Tâm "có thể thêm mode lưới để đo frame", "vẽ khoé mắt nghiêng khó"; Tiến "độ
phân giải thấp ảnh vỡ khó vẽ"; Hoàng "kính che mắt, loá". Người dùng muốn lưới "để xẻ nhỏ và tính khoảng cách giữa các điểm cũng như
giữa các pixel", kèm chỉnh độ sáng, độ bão hoà, opacity, gamma; đưa ảnh chụp hộp **Image setups** của CVAT làm mẫu và **chọn cách 2:
giống CVAT, thêm phần đo của EyePin**. Mục đích: đặt điểm chính xác tới mức pixel trên ảnh nhỏ (guideline: mắt rộng khoảng 25 px ở
100%), và người gán quen tay khi qua lại giữa EyePin và CVAT.

## Mục tiêu, không phải mục tiêu, phản mục tiêu

- Mục tiêu: hộp Image setups như CVAT (lưới + Color settings + gamma); lưới xuống tới 1 px; toạ độ và khoảng cách dưới con trỏ; thước
  theo trục mắt; cùng thang số và cách tính màu với CVAT; điểm đặt trong EyePin nằm đúng chỗ đó khi mở trong CVAT.
- Không phải mục tiêu: hút điểm vào pixel; đổi ảnh gốc hay nhãn; các bộ lọc ảnh khác của CVAT.
- Phản mục tiêu: kéo điểm chậm đi (hiện 20–31 ms mỗi lần di chuột ở khung 1900×980); sang frame chậm thêm rõ (hiện khoảng 140 ms);
  lưới phủ xám ảnh khi thu nhỏ; cùng con số mà ảnh trông khác CVAT.

## Ràng buộc (đã đọc trong mã)

- CVAT (mã nguồn v2.74 trên máy, server 2.75; `cvat-ui/.../canvas2d/image-setups-content.tsx`, `gamma-filter.tsx`,
  `canvas-wrapper.tsx`, `cvat-canvas/.../canvasView.ts`): hộp mở bằng nút `^` giữa mép dưới khung ảnh. Image grid: ô bật, Size 5–1000
  pixel ảnh (mặc định 100), màu White/Black/Red/Green/Blue, Opacity 0–100 (mặc định 100); lưới vuông từ góc ảnh, nét 2 px màn hình
  không đổi khi phóng. Color settings: Brightness 50–200, Contrast 50–200, Saturation 0–300 (mặc định 100, áp bằng CSS
  `brightness() contrast() saturate()` với giá trị /100, đúng thứ tự đó); Gamma 0,2–2,6 bước 0,01 (mặc định 1, bộ lọc Gamma của
  fabric 5.2.1, áp vào ảnh trước CSS); nút "Reset color settings". Opacity và Selected opacity nằm ở bảng Appearance, EyePin đã có.
- EyePin (`render.Look.adjust`): độ sáng **cộng** −100..100 (chú thích ghi "như CVAT" là sai: CVAT nhân), tương phản 0,3–3, bão hoà 0–2
  theo trung bình ba kênh; hộp "Chỉnh hiển thị" chỉ mở từ menu Xem; giá trị lưu ở `settings.json` mục `display` khi bật
  `remember_display` (`DISPLAY_KEYS`).
- **Lệch nửa pixel** (đã thử phép vẽ của EyePin, chưa thử trên CVAT): `render_base` dùng `warpAffine` không bù 0,5, nên tâm pixel ảnh i
  ứng với toạ độ i. CVAT vẽ ảnh từ góc (0,0) (`drawImage(..., 0, 0, ...)`), nên pixel i phủ [i, i+1], tâm ở i+0,5. Nếu đúng, điểm đặt
  trong EyePin hiện trên CVAT lệch nửa pixel lên trên, sang trái (khoảng 2% bề rộng mắt 25 px). Lưới pixel sẽ làm lộ ra ngay.

## Các cách đã xét

1. Giống hệt CVAT: quen tay, nhưng lưới nhỏ nhất 5 px và không đo được khoảng cách.
2. **Giống CVAT, thêm phần đo của EyePin (người dùng chọn 2026-11-16).** Khác CVAT duy nhất ở Size cho xuống 1.
3. Thêm gamma và lưới vào hộp cũ, giữ thang cũ: nhanh nhất nhưng vẫn lệch CVAT, khó tìm.

## Thiết kế

1. **Hộp Image setups.** Mở bằng nút `^` giữa mép dưới khung ảnh (như CVAT), mục trong menu Xem, và một phím (đề xuất của mình; người
   xây chọn phím chưa dùng trong `shortcuts.py`). Nội dung và thang số như CVAT, trừ Size 1–1000. Hộp "Chỉnh hiển thị" cũ giữ cỡ điểm,
   opacity, màu; bỏ ba thanh độ sáng, tương phản, bão hoà khỏi đó (chuyển sang hộp mới).
2. **Màu như CVAT.** Thứ tự: gamma, rồi brightness (nhân), contrast ((v − 0,5)·c + 0,5 trên thang 0–1), saturate (ma trận của Filter
   Effects, hệ số 0,213 / 0,715 / 0,072). Công thức gamma của fabric 5.2.1 theo mình hiểu là v' = 255·(v/255)^(1/γ); người xây kiểm
   lại trong mã fabric 5.2.1 hoặc so ảnh với CVAT local. Phần theo từng kênh dùng bảng tra (LUT) để nhanh. Chỉ để nhìn.
3. **Đổi thang cũ.** Giá trị độ sáng, tương phản, bão hoà đã lưu theo thang cũ không đổi được chính xác (cộng sang nhân), nên đặt về
   mặc định 100 và báo một lần (đề xuất của mình).
4. **Lưới.** Đường kẻ tại toạ độ ảnh nguyên chia hết cho Size, từ góc ảnh, đúng như CVAT (pixel i phủ [i, i+1]); chỉ trong phạm vi ảnh;
   nét mảnh không đổi khi phóng; xoay ảnh 90° thì lưới xoay theo. Khi hai đường cách nhau dưới 8 px màn hình (bản duyệt ghi 4 px; sửa lúc lập kế hoạch vì nét 1 px cách 4 px vẫn phủ
   khoảng 40% ảnh) thì tự nhân Size lên
   (×5, ×10…) cho tới khi đủ thưa, và ghi Size đang hiện thật trên dòng trạng thái. Size ≤ 2 thì ảnh tạm hiện không làm mịn để mỗi ô
   trùng một pixel (đề xuất của mình). Không được làm chậm việc kéo điểm: lưới chỉ đổi khi khung nhìn đổi.
5. **Sửa lệch nửa pixel.** Trước tiên kiểm trên CVAT local: đặt một điểm vào giữa một pixel nổi bật trong EyePin, gửi lên CVAT, phóng to
   xem điểm có nằm giữa pixel không. Đúng là lệch thì bù 0,5 khi vẽ ảnh (cả làm mịn lẫn không làm mịn) để pixel i phủ [i, i+1] như
   CVAT. Toạ độ điểm đã lưu không đổi. Nhãn làm bằng EyePin trước khi sửa thì lệch nửa pixel so với ảnh; ghi vào TASKS để người dùng
   quyết có cần làm gì không.
6. **Đo.** Dòng trạng thái hiện toạ độ ảnh dưới con trỏ (2 chữ số lẻ) và khoảng cách tới điểm nhãn gần nhất (px và % bề rộng mắt
   đó), cập nhật khi di chuột mà không vẽ lại khung (chỉ đổi chữ).
7. **Thước theo trục mắt** (ô bật trong hộp, mặc định tắt): mắt đang chọn có đường khoé–khoé và vạch vuông góc tại tỉ lệ guideline v1.3
   mục 3.3 của mắt đó (mattrai mí trên 0,21 · 0,48 · 0,76, mí dưới 0,24 · 0,50 · 0,76; matphai 0,23 · 0,51 · 0,79 và 0,25 · 0,52 ·
   0,78), xoay theo mắt.
8. **Lưu.** Mọi giá trị của hộp mới lưu như các cài đặt hiển thị khác (theo `remember_display`).

## Kiểm

Test như hiện có (render vẽ ra ảnh numpy nên kiểm được không cần cửa sổ): công thức màu khớp CSS/fabric trên vài giá trị; lưới đúng toạ độ
ở nhiều mức phóng và khi xoay; tự thưa khi thu nhỏ; đổi thang cũ; phép bù nửa pixel (pixel i hiện trong [i, i+1]); đo toạ độ và khoảng
cách. Đo lại thời gian kéo điểm và sang frame trên case 01 ở khung 1900×980, trước và sau. Kiểm trên CVAT local ở mục 5.

## Để người xây quyết

Phím mở hộp, nét và màu thước theo trục mắt, cách vẽ lưới (vào ảnh nền hay đối tượng Canvas), bố cục hộp. Sau khi xong: tick và thêm
việc trong `TASKS.md`, cập nhật `HUONG_DAN.md` và `design/shortcuts.md`.
