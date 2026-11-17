# Nghiên cứu nội suy giữa hai frame ghim, đo bằng IoU

Ngày 2026-11-17. Trạng thái: phần đo đã xây (lệnh `report`, hộp Thông tin); **nhãn của tool chưa đổi** (vẫn chỉ bám tiến).
Căn cứ: yêu cầu của người dùng ngày 2026-11-17, số đo trên case 01 (tái lập ở mục 8).

## 0. Tóm tắt
1. **IoU làm chỉ số chính là hợp với bài này** (người dùng chốt). Mắt dẹt nên IoU phạt lệch dọc (mí mắt) nặng hơn lệch ngang khoảng 2,5 lần, mà độ mở mắt lại nằm ở mí. Nhưng IoU không thay được sai số điểm: nó không thấy điểm trượt dọc viền hay hai điểm đổi chỗ, và cho 0 như nhau dù lệch 15 px hay 90 px. Báo cáo giữ cả hai, IoU đứng trước.
2. **Với ghim thô ±2 px, IoU bị chặn quanh 0,73**: một cách đoán hoàn hảo cũng chỉ đạt chừng đó, và lệch dọc 1 px đã còn 0,74. Muốn dùng ngưỡng IoU ≥ 0,75 hay Boundary IoU để quyết định thì cần nhãn đúng sai không quá 1 px (khi đó trần lên khoảng 0,85).
3. **Cách tốt nhất trên case 01 là bám hai chiều chọn theo độ khớp** (MVP 3). IoU trung bình 0,71 so với 0,64 của bám tiến (ghim mỗi 20 frame), 0,65 so với 0,51 (ghim mỗi 30 frame). Đường thẳng CVAT chỉ được 0,24 và 0,10. Cách này kéo 10% mẫu tệ nhất từ IoU ≤ 0,28 lên ≤ 0,54.
4. **Không giúp:** nội suy thêm cả dáng mắt, các biến thể của luật chọn phía, trộn hai phía theo thời gian.
5. **Chớp mắt:** mọi cách cho IoU gần 0. Phải ghim ở frame chớp.
6. **Cần người dùng quyết:** có cho cách hai chiều ghi vào nhãn thật không. Làm vậy là đổi quy tắc đã chốt "ghim frame N không đổi frame trước N" (mục 6).

## 1. Đã chốt, đã xây, đề xuất, chưa kiểm
- **Người dùng chốt (2026-11-17):** chất lượng nội suy đo bằng IoU, Dice, Boundary IoU, Precision/Recall; IoU quan trọng nhất.
- **Đã xây (có test):** `eyepin/overlap.py` (chỉ số vùng); `evaluate.py` lấy IoU làm dòng đầu, thêm cột thứ ba "hai chiều chọn theo độ khớp" (MVP 3, chỉ để so sánh); `tracking.track_backward`; spike `spike/interp_iou_spike.py`.
- **Đề xuất, chờ quyết:** mục 6.
- **Chưa kiểm:** dữ liệu khác case 01 (job #5–#9 chưa có ghim), hồng ngoại, ban đêm, kính, nhiều người; nhãn đúng sai không quá 1 px.

## 2. Áp các chỉ số vào nhãn mắt
Nhãn mắt là 8 điểm chứ không phải mask. **Vùng mắt** là đa giác khép kín qua 8 điểm theo thứ tự id: khoé đầu 14 → mí trên 15, 16, 17 → khoé cuối 18 → mí dưới 19, 20, 21 (matphai là 22–29). Gọi A là vùng đoán, B là vùng đúng.

| Chỉ số | Công thức | Với nhãn mắt |
|---|---|---|
| IoU | \|A∩B\| / \|A∪B\| | Chỉ số chính. Nhạy với lệch dọc (mục 3) |
| Dice | 2\|A∩B\| / (\|A\|+\|B\|) | Bằng 2·IoU/(1+IoU) ở từng mẫu, nên xếp hạng các cách đoán y như IoU. Chỉ in ra để đối chiếu với tài liệu khác |
| Boundary IoU | IoU của hai dải viền bên trong, mỗi dải rộng d (Cheng và cộng sự, CVPR 2021) | Bài báo lấy d = 2% đường chéo ảnh, khoảng 23 px với ảnh 1024×576. Mức này dày hơn cả mắt, nên chỉ số sẽ bằng IoU. EyePin lấy d = 2,5% bề rộng mắt đúng (1,8 px với mắt rộng 72 px), tối thiểu 1 px |
| Precision | \|A∩B\| / \|A\| | Thấp khi vùng đoán to quá hoặc lệch ra ngoài |
| Recall | \|A∩B\| / \|B\| | Thấp khi vùng đoán nhỏ quá hoặc hụt |

Cách tính (`overlap.compare`): lấy mẫu ở tâm các ô của lưới 8×8 ô mỗi pixel. Trong ba phép thử, IoU lệch không quá 0,0001 so với lưới 16×16. Dải viền tính bằng `cv2.distanceTransform`. Mỗi lần so mất vài mili giây (7–16 ms với mắt rộng 72 px); phần tính của báo cáo case 01 (40 mẫu, mỗi mẫu 4 lần so, kể cả bám lùi) mất khoảng 0,6 s.

Trường hợp đặc biệt:
- Một vùng rỗng (mắt nhắm hẳn, 8 điểm thẳng hàng): mọi chỉ số bằng 0 (đoán mở khi mắt nhắm là sai hẳn).
- Cả hai vùng rỗng: không tính.
- Nhãn đúng có khoé ước lượng hoặc điểm Outside: không tính IoU (đếm riêng). Sai số px vẫn tính trên các điểm thấy được.
- **Mốc** ở đầu mỗi nhóm của báo cáo: IoU của chính nhãn đúng khi dời 1 px vuông góc trục mắt. Con số này cho biết IoU đọc được tốt tới đâu với cỡ mắt của nhóm đó.

## 3. Đọc IoU trên mắt cho đúng (đo trên case 01)
Mắt mở của case 01 rộng 27–76 px, nhưng khoảng cách hai điểm giữa mí chỉ 3–17 px. Mỗi dòng dưới đây so nhãn đúng với chính nó khi bị làm lệch:

| Độ lệch | IoU trung bình (thấp nhất) | Dice | Boundary IoU |
|---|---|---|---|
| dời ngang 1 px | 0,897 (0,584) | 0,942 | 0,674 |
| dời dọc 1 px | 0,740 (0,404) | 0,846 | 0,236 |
| dời ngang 2 px | 0,814 (0,338) | 0,888 | 0,474 |
| dời dọc 2 px | 0,559 (0,136) | 0,705 | 0,036 |
| hai lần ghim độc lập, mỗi điểm ghim lệch ≤ 1 px | 0,854 (0,365) | 0,918 | 0,528 |
| hai lần ghim độc lập, mỗi điểm ghim lệch ≤ 2 px | **0,733** (0,002) | 0,836 | 0,296 |

Rút ra:
- **Lệch dọc 1 px làm IoU mất 0,26, gấp khoảng 2,5 lần lệch ngang 1 px (mất 0,10).** IoU vì vậy tự nhấn vào mí mắt. Đây là điểm cộng nếu nhãn được dùng để đo độ mở mắt; đó là cách hệ thống giám sát tài xế thường dùng điểm mắt, nhưng mình chưa kiểm với đội dùng dữ liệu.
- **Trần nhiễu:** điểm ghim thô ±2 px làm IoU giữa hai lần ghim cùng một mắt chỉ còn khoảng 0,73. Mọi cách đoán đo trên các ghim này đều bị chặn quanh mức đó, nên tỉ lệ IoU ≥ 0,75 phản ánh nhiễu của điểm ghim nhiều hơn chất lượng cách đoán.
- **Boundary IoU** với dải 1–2 px bị nhiễu điểm ghim lấn át (0,30 ở ±2 px; 0,04 khi lệch dọc 2 px). Nới dải tới nửa chiều cao mắt thì nó trùng IoU. Mắt mỏng tới mức gần như cả vùng đã là "viền", nên IoU vốn đã là một chỉ số về viền. Chưa nên dùng Boundary IoU để quyết định khi chưa có nhãn đúng ≤ 1 px.
- **Dice** không thêm thông tin (xem mục 2).
- **Precision/Recall** cho biết hướng lỗi. Lỗi chủ yếu của bộ bám là dời cả mắt, khi đó P ≈ R. Hai số chỉ tách nhau khi sai dáng mắt (chớp, mắt xa co lại lúc quay đầu): ví dụ ở mắt nhắm, bám tiến có P 0,04 nhưng R 0,59 (vùng đoán vẫn mở, to hơn vùng thật nhiều).
- **IoU không thay được sai số điểm:** điểm giữa mí trượt ngang dọc theo mí thì vùng gần như không đổi; hai điểm đổi chỗ cho nhau thì vùng y nguyên; mất bám 15 px hay 90 px đều cho IoU 0. Ngược lại, trung bình IoU không bị vài lần mất bám kéo lệch như trung bình px. Báo cáo giữ cả hai.

## 4. So các cách đoán trên case 01
Dữ liệu: case 01 (PhysDrive 7650–7859, 210 frame, một người, quay đầu hai lần), 24 frame ghim thô do AI đọc (±2 px, **không phải nhãn chuẩn**). Mọi cách chỉ dùng ghim trước `a` và ghim sau `b` của frame được kiểm.

**Cách 1, spike (ghim mỗi N frame, kiểm ở các frame ghim còn lại, mắt mở):**

| Cách đoán | Ghim mỗi 20 frame (22 mẫu): IoU tb / p10 / ≥0,5 / ≥0,75 / px | Ghim mỗi 30 frame (31 mẫu) |
|---|---|---|
| 1 đường thẳng CVAT | 0,24 / 0,00 / 5 / 1 / 25,3 | 0,10 / 0,00 / 2 / 0 / 28,1 |
| 2 bám tiến (tool hiện tại) | 0,64 / 0,28 / 17 / 9 / 5,2 | 0,51 / 0,07 / 19 / 9 / 11,3 |
| 3 bám lùi | 0,48 / 0,15 / 12 / 3 / 13,0 | 0,47 / 0,01 / 17 / 7 / 11,8 |
| 4 hai chiều, trộn theo thời gian | 0,61 / 0,30 / 15 / 7 / 6,6 | 0,57 / 0,13 / 21 / 9 / 6,8 |
| **5 hai chiều, chọn theo độ khớp (MVP 3)** | **0,71 / 0,54 / 20 / 12 / 3,3** | **0,65 / 0,29 / 25 / 15 / 4,4** |
| 6 bám tiến + nội suy dáng mắt | 0,61 / 0,22 / 18 / 7 / 5,3 | 0,51 / 0,06 / 19 / 10 / 10,8 |
| 7 hai chiều chọn + nội suy dáng mắt | 0,67 / 0,54 / 20 / 8 / 3,6 | 0,62 / 0,23 / 24 / 13 / 4,7 |

Trong đoạn quay đầu (ghim mỗi 20 frame, 12 mẫu), IoU của cách 2 / 5 là 0,61 / 0,69; ngoài đoạn (10 mẫu) là 0,68 / 0,73. Chớp mắt (2 mẫu): mọi cách từ 0,00 đến 0,06.

**Cách 2, lệnh `report` (bỏ từng ghim ra, nên mỗi phía cách ghim kề đúng N frame):**

| Ghim | Mẫu (mắt mở) | Đường thẳng CVAT | Bám tiến | Hai chiều chọn theo độ khớp |
|---|---|---|---|---|
| mỗi 10 frame | 37 | IoU 0,28; ≥0,5 22%; 18,1 px | IoU 0,57; ≥0,5 70%; ≥0,75 30%; 6,5 px | **IoU 0,69; ≥0,5 84%; ≥0,75 57%; 3,6 px** |
| mỗi 20 frame | 19 | IoU 0,09; ≥0,5 0%; 31,4 px | IoU 0,43; ≥0,5 53%; ≥0,75 11%; 12,5 px | **IoU 0,56; ≥0,5 63%; ≥0,75 26%; 6,8 px** |

Mốc của nhóm (dời 1 px vuông góc trục mắt) là 0,72–0,73, nên với ghim mỗi 10 frame, cách hai chiều (0,69) chỉ còn kém "lệch 1 px" một chút.

**Một lần chớp mắt thật** (mắt phải trên ảnh; ghim 80 mở, 90 nhắm hẳn với EAR 0,02, 100 mở). Nhìn ảnh: mắt bắt đầu khép ở 87, nhắm 88–91, mở lại 92–94; từ khoảng frame 92 đầu bắt đầu dời.
- **Không ghim 90:** mọi cách vẽ mắt mở ở frame 90 (IoU 0,00–0,06). Hai chiều không cứu được, vì cả hai phía mang hình mắt mở. Độ khớp bám tiến tụt từ 0,98 (frame 85) xuống 0,59–0,68 (87–90), nên tool đánh "cần ghim" frame 86–99.
- **Có ghim 90:**
  - Bám tiến giữ mắt mở tới 89 rồi giữ mắt nhắm tới 99, nên sai ở 87–89 và 92–99.
  - Hai chiều chuyển hình đúng chỗ: mở tới 86, khép một nửa ở 87, nhắm 88–91, trộn ở 92–94, mở ở 95–99 (độ khớp phía lùi 0,89–0,98).
  - Lần chớp này cần khoảng 3 ghim nếu chỉ bám tiến (đang khép, nhắm, vừa mở lại), còn với hai chiều thì một ghim ở frame nhắm là đủ.
- Các frame giữa hai ghim chưa có nhãn đúng, nên đây là đánh giá bằng mắt trên ảnh, chưa phải số đo IoU.

So với bảng sai số trong `design/2026-11-15-headturn-mvp-design.md` mục 2 (bám tiến 6,8 px, hai chiều chọn 5,0 px ở ghim mỗi 20 frame), số px hôm nay thấp hơn (5,2 và 3,3 px). Có thể vì bộ bám đã đổi sau ngày đó (mỗi mắt bám riêng), nhưng chưa truy nguyên.

## 5. Những hướng đã thử mà không giúp
- **Nội suy cả dáng mắt** (cách 6, 7: giữ vị trí do bộ bám tìm, lấy dáng mắt nội suy thẳng giữa ghim `a` và `b`): kém hơn không nội suy dáng (0,61 so với 0,64; 0,67 so với 0,71). Lý do mình đoán, chưa chứng minh: trên case 01, dáng mắt đổi theo kiểu thoáng qua (chớp) chứ không đều theo thời gian. Khi ghim `a` hoặc `b` rơi vào lúc nheo hay chớp, nội suy kéo mắt ở frame giữa khép theo.
- **Biến thể luật chọn phía** (`VARIANTS = True` trong spike): luôn lấy phía khớp hơn; trộn chỉ khi cả hai đủ khớp; dùng độ khớp thấp nhất trên cả đường đi thay vì độ khớp tại frame kiểm. Mọi biến thể đều không hơn luật MVP 3 (IoU 0,70 so với 0,71 ở ghim 20 frame; 0,61–0,64 so với 0,65 ở 30 frame). Khác biệt nhỏ hơn mức nhiễu của 22–31 mẫu.
- **Trộn hai phía theo thời gian** (cách 4): kém chọn theo độ khớp, vì phía mất bám kéo kết quả theo.
- Những mẫu cả hai phía cùng mất bám (ví dụ frame 110 mattrai, frame 80 mattrai) thì luật chọn nào cũng không cứu được. Chỉ ghim dày hơn ở đó mới giúp, và tool đã đánh "cần ghim" khi độ khớp tụt dưới 0,85.

## 6. Đề xuất (chờ người dùng quyết)
1. **Cho cách hai chiều chọn theo độ khớp ghi vào nhãn thật**, ví dụ thành một tuỳ chọn mặc định tắt. Lợi: IoU trung bình tăng 0,07–0,14; tỉ lệ IoU ≥ 0,5 tăng từ 70% lên 84% (ghim mỗi 10 frame). Giá: phá quy tắc đã chốt "ghim frame N không đổi frame trước N", vì frame giữa ghim trước và N sẽ đổi theo ghim N. Phần tính lại, bộ nhớ đệm đoạn bám và chọn keyframe phải làm lại theo hai phía, nên cần một bản thiết kế riêng.
2. **Tiêu chí đạt theo IoU** (đề xuất): "IoU ≥ 0,5 trên ít nhất 80% mẫu mắt mở tại frame ghim bị giấu", đặt cạnh tiêu chí cũ "≤ 10% bề rộng mắt". Trên case 01 với ghim mỗi 10 frame: bám tiến đạt 70%, hai chiều đạt 84%. Chỉ dùng ngưỡng 0,75 khi đã có nhãn đúng ≤ 1 px.
3. **Nhãn đúng tốt hơn**: ghim lại cẩn thận khoảng 20 frame của case 01 ở mức phóng to, sai không quá 1 px; hoặc cho hai người ghim độc lập để đo nhiễu thật, thay cho giả định ±2 px.
4. **Chớp mắt**: hướng dẫn ghim ở frame mắt nhắm. Về lâu dài cần bộ bám đổi được dáng mắt (`TASKS.md` mục 1).
5. Dice chỉ in ra để đối chiếu; chưa dùng Boundary IoU để quyết định (mục 3).

## 7. Giới hạn
Một clip, một người, ban ngày, không kính; điểm ghim do AI đọc (±2 px); chỉ đo tại frame ghim bị giấu (chỗ xấu nhất giữa hai ghim, nhưng chỉ ở những frame đó); 19–40 mẫu mỗi bảng, chớp mắt chỉ 1–3 mẫu. Ở frame quay đầu, điểm 14 của mắt xa là đầu nhìn thấy của mắt chứ không phải khoé thật, nên "vùng đúng" ở đó là phần mắt nhìn thấy. Điều này hợp với cách hiểu mask, nhưng khác cách hiểu điểm.

## 8. Tái lập
- `python spike\interp_iou_spike.py` (khoảng 2 phút): bảng mục 3 và bảng thứ nhất ở mục 4. Đặt `VARIANTS = True` để in thêm các biến thể ở mục 5.
- `python -m eyepin report <case01> --pins <file>`: bảng thứ hai ở mục 4. File ghim là `spike/out/pins_case01_ai.json`, chỉ giữ các frame chia hết cho 10 (hoặc 20) cùng frame 209.
- Test: `tests/test_overlap.py` (chỉ số, có giá trị tính tay); `tests/test_evaluate.py` (IoU trong báo cáo, luật chọn, báo cáo không đổi nhãn, tiêu chí MVP 3 trên case 01); `tests/test_tracking.py` (`track_backward`).
