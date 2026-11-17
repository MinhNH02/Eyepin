# EyePin: phát hiện quay đầu, báo cáo độ chính xác, thử bám hai chiều (bản 2)

Ngày 2026-11-16, thay bản 1 ngày 2026-11-15. Hạn demo: chiều 2026-11-16. Trạng thái: **MVP 1 đã xây ngày 2026-11-16** (kế hoạch `design/2026-11-16-headturn-mvp1-plan.md`, `eyepin/headturn.py`); MVP 2 đã xây cùng ngày (`eyepin/evaluate.py`, hai cách đoán: đường thẳng CVAT và bám tiến); MVP 3 đã xây ngày 2026-11-17 (cột thứ ba của báo cáo, chỉ để so sánh), cùng lúc báo cáo lấy IoU vùng mắt làm chỉ số chính (xem `design/2026-11-17-interp-iou-research.md`). Người dùng chưa duyệt chính thức mục 15 (đo model).
Căn cứ: hội thoại 2026-11-15/16, báo cáo `C:\Users\minhf\reports\Thuật toán keypoint cho nhãn mắt.md`, và số đo ở mục 2 (tái lập bằng `python spike\headturn_spike.py`).

## 1. Ý định và lý do
Người dùng muốn tool tự báo "đối tượng quay đầu từ frame nào tới frame nào", cho biết nhãn trên đoạn đó tin được đến đâu, và giảm sai số trung bình. Mục tiêu dài hạn là ≥ 80% frame đúng. Demo cho mentor chiều 16/11. Quay đầu là chỗ khó nhất, nên báo trung thực quan trọng hơn con số đẹp.

Người dùng đã chốt (2026-11-16): bám hai chiều **chỉ dùng để so sánh trong báo cáo**, không đổi nhãn mặc định; quy tắc "ghim frame N không làm đổi frame trước N" giữ nguyên. Điểm ghim thô của case 01 do AI đọc.

## 2. Số đo làm căn cứ
Dữ liệu: case 01 (PhysDrive 7650–7859, 210 frame, một người, công khai), 24 frame ghim thô trong `spike/out/pins_case01_ai.json` (AI đọc trên ảnh phóng to 6 lần, sai số khoảng ±2 px, **không phải nhãn chuẩn**). Đối chứng: đoạn mặt thẳng `physdrive_seg` (200 frame, 5 ghim của spike). Bằng mắt thường, case 01 có hai đoạn quay đầu, khoảng frame 20–70 và 100–150 (mắt xa chỉ còn một lát mỏng sát mép mặt).

**Tín hiệu tại frame ghim** (tách hẳn hai nhóm):

| Chỉ số | Frame quay đầu | Frame không quay |
|---|---|---|
| Khoảng cách hai mắt / mốc | 0,67–0,84 | 0,87–1,01 |
| Bề rộng mắt xa / mắt gần | 0,40–0,71 | 0,81–1,08 |

**Giữa hai frame ghim** chỉ dùng được khoảng cách hai mắt: bộ bám chỉ dời cả mắt nên bề rộng mắt đứng yên từ ghim này tới ghim kế. Khi bộ bám mất mắt, khoảng cách hai mắt thành vô nghĩa (đo được "co 99%"), nên phải bỏ các frame có độ khớp dưới 0,85.

**Phát hiện đoạn quay đầu** (ngưỡng vào 0,86, ra 0,90, dài tối thiểu 5 frame, bỏ frame khớp kém):

| Ghim | Đoạn phát hiện | Frame không tin được |
|---|---|---|
| mỗi 10 frame | 21–79 (co 28%), 100–160 (co 32%) | 59/210 |
| mỗi 20 frame | 21–79, 100–160 | 85/210 |
| mỗi 30 frame | 30–89, 120–179 (ranh giới dính vào frame ghim) | 118/210 |
| mỗi 50 frame | một đoạn 50–199 (sai: gộp hai đoạn) | 128/210 |
| đối chứng mặt thẳng | không có đoạn nào (đúng) | 87/200 |

**Sai số tại frame ghim bị giấu** (trung bình 4 điểm ghim của một mắt; "đạt" tính theo phần trăm bề rộng mắt):

| Cách dự đoán | Ghim mỗi 30 frame (32 mắt) | Ghim mỗi 20 frame (24 mắt) |
|---|---|---|
| Đường thẳng CVAT (không có tool) | 28,7 px; đạt ≤10%: 3/32 | 27,5 px; 4/24 |
| Bám tiến (tool hiện tại) | 13,6 px; 17/32; ≤5%: 9/32 | 6,8 px; 16/24; ≤5%: 8/24 |
| Hai chiều, trộn theo thời gian | 8,3 px; 20/32 | 8,0 px; 14/24 (kém hơn bám tiến) |
| Hai chiều, chọn theo độ khớp | 4,3 px; 27/32 (84%); ≤5%: 17/32 | 5,0 px; 20/24 (83%); ≤5%: 15/24 |

Đọc các số này thế nào:
- Sai số lớn đến từ **mất bám** (lệch 15–90 px), không phải từ sai lệch dưới pixel. Mọi lần lệch trên 10 px đều có độ khớp dưới 0,85 ở phía bị lệch.
- Trộn hai chiều theo thời gian không an toàn: phía bám hỏng kéo kết quả theo. Chọn theo độ khớp thì tốt hơn cả hai phía ở cả hai mật độ ghim.
- Bộ bám không lệch toạ độ: thử dịch ảnh một khoảng đã biết, sai ≤ 0,007 px (dịch nguyên) và ≤ 0,16 px (dịch lẻ), không lệch về một phía.

Giới hạn của số đo: một người, một clip, ban ngày, không kính. Ghim thô ±2 px tương đương khoảng 3% bề rộng mắt, nên ngưỡng 5% nằm sát nhiễu của chính điểm ghim. Frame bị giấu nằm giữa hai ghim, là chỗ xấu nhất. Ở frame quay đầu, điểm 14 của mắt xa là đầu nhìn thấy của mắt, không phải khoé thật. Các ngưỡng 0,86 / 0,90 / 0,85 chỉnh trên đúng clip này.

## 3. Mục tiêu và tiêu chí đạt
1. **MVP 1, phát hiện quay đầu.** Trên case 01 với ghim thô mỗi 10 frame: đúng hai đoạn, đoạn một chứa frame 30–65, đoạn hai chứa 105–145, ranh giới lệch không quá 10 frame so với 21–79 và 100–160. Trên đoạn mặt thẳng: không có đoạn nào. Kết quả hiện ở dải thời gian, tab Issues và dòng lệnh.
2. **MVP 2, báo cáo độ chính xác.** In được bảng như mục 2 cho phiên đang mở: ba cách dự đoán, sai số px và phần trăm bề rộng mắt, tỉ lệ đạt ở ngưỡng 5% và 10%, tách trong/ngoài đoạn quay đầu, kèm số mẫu và khoảng cách ghim. Kiểm tính hợp lý trên case 01: đường thẳng CVAT phải sai nhiều hơn bám tiến.
3. **MVP 3, bám hai chiều chọn theo độ khớp (thử nghiệm).** Là cột thứ ba của bảng MVP 2. Trên case 01 sai số trung bình của nó không lớn hơn bám tiến. Nhãn, file xuất và mọi test hiện có không đổi.

Câu nói được ở demo về mục tiêu 80%: trên case 01, ở ngưỡng 10% bề rộng mắt, bám hai chiều chọn theo độ khớp đạt 83–84% số mắt tại frame bị giấu, bám tiến đạt 53–67%; ở ngưỡng 5% là 53–63% so với 28–33%. Đây là số trên một clip với ghim thô, không phải cam kết cho dữ liệu khác.

## 4. Không phải mục tiêu
- Không dùng model học máy. Không dùng ảnh công ty; demo chạy trên dữ liệu công khai.
- Không đổi nhãn mặc định, không đổi quy tắc "không đổi frame trước N".
- Không quy ra độ. Không phát hiện cúi/ngửa đầu.
- Không chứng minh thống kê 80% (cần cỡ 100–300 clip độc lập).
- Không viết lại giao diện, không import thẳng vào CVAT.

## 5. Điều làm hỏng dự án dù chạy đúng
Báo "không quay đầu" trên đoạn quay thật; hoặc một con số sai số không kèm số mẫu, khoảng cách ghim và nguồn điểm ghim. Mọi con số in ra phải mang ba thứ đó.

## 6. Ràng buộc
- Chỉ xử lý ảnh cổ điển và hình học. Ảnh chỉ trong RAM.
- 139 test hiện có và `tests\verify_vs_cvat.py 5` (11/11) phải còn qua.
- Việc xong thì tick `TASKS.md`. Thêm module mới thì vẽ lại `/archify` và cập nhật `CLAUDE.md` (làm sau khi đóng băng mã).
- Giao diện theo `theme.py`.

## 7. Các cách đã cân nhắc
**Tín hiệu phát hiện quay đầu**
- *Bề rộng mắt từ nhãn do tool bám.* Loại: bề rộng không đổi giữa hai ghim.
- *Khoảng cách hai mắt, bỏ frame khớp kém, xác nhận bằng bề rộng mắt tại frame ghim.* **Chọn.** Đã đo tách được ở mục 2. Đánh đổi: ranh giới chỉ chính xác khi ghim trong đoạn quay cách nhau không quá khoảng 20 frame; lẫn với việc người lái tiến/lùi nếu không có ghim xác nhận.
- *Đo bề rộng mắt từng frame bằng so khớp mẫu có co giãn ngang.* Tốt hơn về nguyên tắc (cũng sửa được dáng mắt), nhưng là thay đổi lớn trong bộ bám, không kịp hôm nay. Để sau.

**Giảm sai số**
- *Sửa quy ước toạ độ, giải mã dưới pixel.* Loại: đã đo, không có lệch để sửa.
- *Hai chiều, trộn theo thời gian.* Loại: kém hơn bám tiến ở mật độ ghim 20 frame.
- *Hai chiều, chọn theo độ khớp.* **Chọn, ở dạng thử nghiệm chỉ để báo cáo.**
- *Nội suy bề rộng theo cos(góc quay).* Loại: công thức chưa có nguồn, và sai số chính là mất bám.

## 8. Thiết kế
### MVP 1: `eyepin/headturn.py`
Hàm thuần toạ độ, kiểm được không cần ảnh. Tính riêng cho từng người (`Layer`).
- **Khoảng cách hai mắt** `d(f)`: khoảng cách giữa tâm 8 điểm của mattrai và matphai. Điểm Outside không tính.
- **Mốc**: phân vị 90 của `d` tại các frame ghim có đủ hai mắt (ít ghim thì gần bằng giá trị lớn nhất). Nghĩa là "so với tư thế thẳng nhất trong clip".
- **Frame tin được**: mỗi mắt hoặc là frame ghim của mắt đó, hoặc có độ khớp ≥ 0,85.
- **Đoạn quay đầu**: trên frame tin được, vào đoạn khi `d/mốc ≤ 0,86`, ra khi `≥ 0,90`. Frame không tin được giữ nguyên trạng thái và được đếm là "không chắc". Đoạn ngắn hơn 5 frame bị bỏ.
- **Một mắt**: frame chỉ còn một mắt có nhãn (mắt kia chưa ghim, đã xoá hoặc Outside) được coi là đang quay đầu và đếm riêng. Frame không còn mắt nào giữ nguyên trạng thái.
- **Xác nhận và mắt xa**: tại các frame ghim trong đoạn, nếu bề rộng mắt hẹp / mắt rộng ≤ 0,75 thì đoạn được "xác nhận" và mắt hẹp là mắt xa. Không có ghim nào như vậy thì ghi "chưa xác nhận (có thể do tiến/lùi)".
- **Mức**: co dưới 20% là nhẹ, 20–30% là vừa, từ 30% là mạnh (đề xuất của mình, chưa có nguồn).
- Dưới 3 frame ghim có đủ hai mắt: trả về "chưa đủ ghim để phát hiện", không đoán.

Đầu ra mỗi đoạn: frame đầu, frame cuối, frame co mạnh nhất, mức co, mức, mắt xa, số ghim xác nhận, số frame không chắc, số frame một mắt, số frame "cần ghim" bên trong. Ví dụ:
`Quay đầu  #1  frame 21–79  co 28% (vừa)  mắt xa: mattrai  xác nhận tại 6 ghim  13 frame không chắc`

Chỗ hiện:
- Dải thời gian: một dải màu trên các frame của đoạn.
- Tab Issues: các đoạn quay đầu đứng đầu danh sách; chọn thì nhảy tới frame đầu đoạn; nút kế/trước đi qua cả chúng. `Session` giữ danh sách này riêng (không trộn vào `findings` vì `findings` là kết quả quét file XML) và tính lại sau mỗi lần `recompute`.
- Dòng lệnh: `python -m eyepin turns <thư_mục_ảnh> --pins <file.json>`.
- Mở cửa sổ với ghim có sẵn: `python -m eyepin gui <thư_mục_ảnh> --pins <file.json>`, để demo không đụng tới file phiên đang lưu.

### MVP 2: `eyepin/evaluate.py`
Với từng người, từng mắt, từng frame ghim `g` có ghim trước `a` và ghim sau `b` của chính mắt đó:
- *Đường thẳng CVAT*: nội suy thẳng 8 điểm giữa `a` và `b`.
- *Bám tiến*: `Session.arrival[g]`, đã có sẵn, không tốn thêm phép bám.
- *Hai chiều (thử nghiệm)*: xem MVP 3.

Sai số của một mẫu: trung bình khoảng cách trên 4 điểm ghim của mắt (hai khoé, hai điểm giữa mí), bỏ điểm ước lượng (`Layer.estimates`) và điểm Outside. Chuẩn hoá theo bề rộng mắt tại `g`.

Loại khỏi thống kê, đếm riêng:
- Ghim có từ hai điểm ghim trở lên trùng khít với bám tiến (sai số đúng bằng 0): đó là ghim tạo bằng phím K hoặc ghim chỉ kéo một điểm, không phải bốn điểm người đặt.
- Ghim tại frame mắt nhắm (EAR dưới `EAR_CLOSED`): báo thành nhóm "chớp mắt".

Đây là cách nhận biết tạm. Ghim tạo bằng dán hoặc Propagate vẫn bị tính là người đặt; ghi nguồn gốc từng điểm ghim vào phiên là việc sau demo.

Bảng in ra: mỗi cách dự đoán một dòng gồm trung bình, trung vị, phân vị 90 (px), tỉ lệ đạt ≤ 5% và ≤ 10%; chia hai nhóm trong/ngoài đoạn quay đầu; số mẫu mỗi nhóm; khoảng cách ghim trung vị. Nhóm dưới 5 mẫu in "chưa đủ mẫu" thay cho tỉ lệ. Dòng cuối: số đoạn không kiểm được (sau ghim cuối), số ghim bị loại theo từng lý do, và câu "đo tại frame ghim bị giấu, không phải mọi frame".

Chỗ hiện: `python -m eyepin report <thư_mục_ảnh> --pins <file.json>`, và một mục trong hộp Thông tin có nút tính (không tính tự động, vì cột hai chiều phải chạy thêm phép bám).

### MVP 3: bám hai chiều chọn theo độ khớp
- `tracking.py` thêm bám lùi: chạy `track_forward` trên dãy frame đảo ngược từ ghim `b`.
- Tại frame `t` giữa `a` và `b`, với kết quả tiến (độ khớp `cf`) và lùi (`cb`): nếu chỉ một phía có độ khớp ≥ 0,85 thì lấy phía đó; ngược lại trộn theo thời gian `(1−w)·tiến + w·lùi`, `w = (t−a)/(b−a)`.
- Chỉ `evaluate.py` gọi. `Session.labels`, file xuất và hai test "không đổi frame trước N" không đổi.

## 9. Edge case và cách xử lý
| Trường hợp | Xử lý |
|---|---|
| Chỉ còn một mắt | Coi là đang quay đầu, đếm "frame một mắt" |
| Không còn mắt nào (case 04) | Giữ trạng thái đoạn, đếm vào "không chắc" |
| Bộ bám mất mắt, chớp mắt | Frame có độ khớp < 0,85 không được tin; đoạn dưới 5 frame bị bỏ |
| Clip đã quay sẵn từ đầu | Mốc lấy theo cả clip; nếu cả clip đều quay thì không phát hiện được (giới hạn, ghi trong báo cáo) |
| Người lái tiến/lùi | Đoạn không có ghim xác nhận bằng bề rộng mắt ghi "chưa xác nhận" |
| Ghim thưa hơn khoảng 20 frame trong đoạn quay | Ranh giới dính vào frame ghim; báo số frame không chắc và gợi ý ghim ở frame "cần ghim" |
| Khoé ước lượng | Không tính vào sai số; vẫn dùng cho khoảng cách hai mắt |
| Nhiều người | Tính và báo riêng từng người, kèm ID đối tượng |
| Trước ghim đầu, sau ghim cuối | Không có mẫu kiểm; báo số đoạn không kiểm được |
| Frame đã xoá | Bỏ qua; đoạn được phép vắt qua |
| Ghim tạo bằng K, kéo một điểm | Loại khỏi thống kê sai số, đếm riêng |
| Dưới 3 ghim đủ hai mắt | "Chưa đủ ghim để phát hiện" |
| Cúi/ngửa đầu, hướng nhìn đổi | Không phát hiện; ghi rõ là ngoài phạm vi |

## 10. Cách kiểm
- Test đơn vị cho `headturn` bằng dãy số dựng sẵn: không đổi; co 30% trong 30 frame; co dưới 5 frame; có frame không tin được ở giữa; mất một mắt; tỉ lệ lớn hơn 1; dưới 3 ghim.
- Test đơn vị cho `evaluate` bằng ảnh tổng hợp: dịch chuyển thuần thì bám tiến sai gần 0 và đường thẳng sai đúng bằng độ cong đã dựng; ghim trùng khít bị loại.
- Kiểm trên dữ liệu thật (cần thư mục ảnh, bỏ qua nếu thiếu): case 01 và đoạn đối chứng theo tiêu chí mục 3.
- Trước khi đóng băng: chạy lại 139 test và `verify_vs_cvat.py 5`.

## 11. Lịch, kịch bản demo, phương án lùi
Ước lượng của mình, chưa kiểm: MVP 1 khoảng 2,5 giờ; MVP 2 khoảng 1,5 giờ; MVP 3 khoảng 1 giờ; nối giao diện khoảng 1 giờ; tài liệu và `/archify` khoảng 0,5 giờ.
- Trước khi sửa mã: sao lưu `eyepin\` và `tests\` sang một thư mục bên cạnh (dự án chưa có git).
- Đóng băng mã ít nhất 2 giờ trước demo. Sau đó chỉ chạy thử kịch bản.
- Thứ tự cắt khi thiếu giờ: bỏ MVP 3, rồi bỏ phần hộp Thông tin của MVP 2 (giữ dòng lệnh). Dòng lệnh `turns` của MVP 1 không cắt.
- Nếu phần giao diện hỏng: khôi phục các file giao diện từ bản sao lưu, demo bằng cửa sổ cũ và kết quả dòng lệnh.

Kịch bản: mở case 01 với ghim thô, chỉ hai dải quay đầu trên dải thời gian, nhảy tới từng đoạn từ tab Issues, mở hộp Thông tin xem bảng ba cách dự đoán, nói rõ các giới hạn ở mục 2.

## 12. Để người xây quyết định
Màu và vị trí dải trên dải thời gian; cách trình bày trong tab Issues và hộp Thông tin; định dạng in của `turns` và `report`; tên hàm và kiểu dữ liệu; cách đệm kết quả bám lùi.

## 13. Câu hỏi còn mở (không chặn việc xây)
1. Giờ demo, để đặt mốc đóng băng mã.
2. Phiên case 01 đang lưu có 3 frame ghim (7, 19, 46). Demo nạp ghim thô bằng `--pins` nên không đụng tới nó.
3. Sau demo: có cho bám hai chiều ghi vào nhãn thật (một tuỳ chọn, mặc định tắt) không. Việc này đổi quy tắc đã chốt nên cần người dùng quyết riêng.

## 14. Khác gì so với bản 1
| Bản 1 | Bản 2 | Lý do |
|---|---|---|
| Góc quay từ bề rộng mắt và `arccos` | Mức co của khoảng cách hai mắt, xác nhận bằng bề rộng tại frame ghim | Bề rộng không đổi giữa hai ghim; trên đoạn mặt thẳng công thức cũ báo sai 25 frame và không tính được ở 159/200 frame |
| Mốc là frame ghim đầu | Phân vị 90 tại các frame ghim | Frame đầu của case 01 đã hơi quay |
| Ngưỡng 15° / 10° | Vào 0,86, ra 0,90, bỏ frame khớp dưới 0,85 | Đo trên case 01 và đoạn đối chứng |
| Đo bằng đường thẳng giữa hai ghim | Ba cách, trong đó bám tiến lấy từ `arrival` | Tool xuất nhãn do bộ bám tính, không phải đường thẳng |
| Ba khoảng góc quay | Trong/ngoài đoạn quay đầu | Không đủ mẫu cho ba nhóm |
| Sửa quy ước toạ độ | Bỏ | Đã đo, không lệch |
| Bám hai chiều trộn theo thời gian, ghi vào nhãn | Chọn theo độ khớp, chỉ để báo cáo | Trộn theo thời gian kém hơn bám tiến ở ghim 20 frame; người dùng chốt giữ quy tắc cũ |
| Nội suy bề rộng theo cos | Bỏ | Chưa có nguồn; sai số chính là mất bám |
| Không có tiêu chí đạt, lịch, phương án lùi | Mục 3 và 11 | Thiếu trong bản 1 |

## 15. Bổ sung sáng 2026-11-16: đo model landmark (chờ người dùng quyết, chưa đổi thiết kế)
Người dùng đọc bản 2 và nêu ý: logic nội suy chưa đủ, cần model (YOLO kết hợp landmark khuôn mặt). Ý này ngược với quy tắc "không dùng model học máy" ở mục 6 và trong `CLAUDE.md`, nên mới chỉ **đo**, chưa đưa vào sản phẩm. Chạy lại: `python spike\model_spike.py` (MediaPipe FaceLandmarker có sẵn trên máy, ảnh công khai, chạy cục bộ, không ghi nhãn).

Sai số tại frame ghim bị giấu, cùng thước đo với mục 2 (trung bình 4 điểm ghim mỗi mắt; đạt = sai số so với bề rộng mắt):

| Cách dự đoán | Ghim mỗi 30 frame (32 mắt) | | | Ghim mỗi 20 frame (24 mắt) | | |
|---|---|---|---|---|---|---|
| | tb px | ≤5% | ≤10% | tb px | ≤5% | ≤10% |
| Bám tiến (tool hiện tại) | 13,6 | 9 | 17 | 6,8 | 8 | 16 |
| Hai chiều, chọn theo độ khớp | 4,3 | 17 | 27 | 5,0 | 15 | 20 |
| Model trực tiếp, không ghim | 4,4 | 9 | 23 | 4,3 | 8 | 17 |
| Ghim trước + độ dịch của model | 3,7 | 17 | 26 | 3,3 | 14 | 18 |
| Hai ghim kề + độ dịch của model, trộn theo thời gian | 2,8 | 18 | 29 | 2,8 | 14 | 22 |

- Model tìm được mặt ở 210/210 frame, sai số lớn nhất tại frame ghim là 8,6 px (bộ bám có lúc lệch 15–90 px).
- Model dùng một mình không chính xác hơn về tỉ lệ đạt 5% (15/48 mắt trên cả 24 frame ghim; 12/24 đạt 10% ở frame quay đầu): nó đặt điểm theo quy ước của nó, không theo guideline, và đoán khoé thật của mắt xa trong khi ghim thô lấy đầu nhìn thấy.
- "Độ dịch của model" = điểm ghim + (model ở frame đang xét − model ở frame ghim). Cách này giữ quy ước của người ghim và lấy chuyển động, đổi dáng mắt từ model. Bản "ghim trước" không đổi frame trước frame ghim nên giữ được quy tắc đã chốt; bản "hai ghim kề" thì không.
- Góc quay model báo tại frame ghim: 18–29° ở 12 frame quay đầu, 0–13° ở 12 frame còn lại. Nếu được dùng model, MVP 1 có thể tính theo từng frame và không phụ thuộc mật độ ghim.
- Chưa đo YOLO: trên clip này bộ tìm mặt đi kèm MediaPipe không mất frame nào, nên YOLO (chỉ cho khung mặt và 5 điểm) chưa có chỗ để cải thiện.
- Giới hạn như mục 2: một người, một clip, ban ngày, không kính; ghim thô ±2 px nên mức 2,8 px đã sát nhiễu của điểm ghim; chưa thử hồng ngoại, kính, ban đêm (bản prelabel cũ từng ghi 1 lần lệch hẳn do kính dày và 6 frame kính râm model tự vẽ mắt).

Việc cần người dùng quyết: quy tắc cấm model là của ai (người dùng tự đặt hay mentor/công ty yêu cầu), và có cho model xuất hiện trong demo dưới dạng cột so sánh của báo cáo MVP 2 hay không.
