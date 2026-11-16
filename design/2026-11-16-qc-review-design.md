# QC: tìm lỗi, sửa trong EyePin, gửi lại CVAT

Ngày 2026-11-16. Trạng thái: bản thiết kế chờ người dùng duyệt. Người dùng đã chọn cách B (mục 5). Mọi chỗ ghi
"đề xuất của mình" là quyết định của người viết, người dùng chưa xem riêng.

## 1. Ý định và lý do

Người dùng nói (nguyên văn, theo thứ tự):
- "khi QA QC hãy hiển thị bug những frame rõ nhất cho người review để tiết kiệm thời gian và nâng cao hiệu suất"
- người duyệt thấy lỗi thì "sửa luôn trong EyePin rồi gửi lại CVAT"
- job cần QC có "cả hai, track và shape"
- demo được lùi tới khi sản phẩm xong, nên "làm tốt nhất có thể"
- được làm mọi thứ với dữ liệu và CVAT local; demo ổn thì công ty cho dùng dữ liệu của công ty

Vậy chỗ nghẽn là **thời gian của người duyệt**. Thành công nghĩa là người duyệt không phải tua từng frame: mở job, thấy ngay
các lỗi chắc chắn nhất, mỗi lỗi ở đúng frame nhìn rõ nhất, sửa một chỗ là xong cả đoạn, gửi lại mà không làm hỏng gì khác.

Ý tưởng lấy từ skill `cvat-facial-tracking-expert` của đồng nghiệp (`C:\Users\minhf\Downloads\CVATTraining`): xếp lỗi theo đoạn,
mỗi đoạn xin một frame; dấu hiệu mí từ ảnh; ngưỡng theo thống kê của từng mắt; chớp mắt phải cả hai mắt cùng khép; kiểm hình học
trước khi ghi. **Chỉ lấy ý tưởng, tự viết mã trong EyePin**; muốn chép mã của đồng nghiệp thì hỏi họ trước. Không lấy: đường
ghi PATCH, host server công ty, phần MediaPipe, phần hiệu chỉnh cả track từ prelabel.

## 2. Quyết định cũ bị thay

- `design/2026-11-16-cvat-direct-design.md` mục 7 chốt "job có nhãn mắt: QC chỉ xem; muốn sửa thì xoá nhãn cũ rồi gán lại".
  Nay người dùng muốn **sửa ngay trong QC**. Lệnh "Xoá nhãn mắt cũ và gán lại" vẫn giữ cho ai muốn gán lại từ đầu (đề xuất của mình).
- Quy tắc "ghim frame N không đổi frame trước N" vẫn giữ nguyên ở chế độ gán nhãn. Trong QC, nút "Áp cho cả đoạn" đổi cả frame
  trước chỗ sửa, nhưng **chỉ trong đoạn bị báo lỗi**. Người dùng chọn cách B sau khi được nói rõ điều này.

## 3. Mục tiêu, không phải mục tiêu, phản mục tiêu

Mục tiêu:
- G1. Mở job đã có nhãn mắt (track lẫn shape, một hoặc nhiều người), giữ đúng loại, keyframe, cờ của từng đối tượng.
- G2. Danh sách lỗi xếp từ chắc chắn nhất; mỗi đoạn lỗi là một mục, mở ra ở frame nhìn rõ lỗi nhất, phóng sẵn vào mắt.
- G3. Sửa ngay trong QC (kéo điểm, kéo mắt, xoay, co giãn, cờ, hoàn tác như chế độ gán nhãn), và "Áp cho cả đoạn".
- G4. Gửi lại CVAT; mọi đối tượng, keyframe, cờ không bị sửa giữ nguyên.
- G5. Đo được bằng số: bắt được bao nhiêu lỗi, báo nhầm bao nhiêu, lỗi thật đứng hạng mấy, sửa một đoạn còn sai bao nhiêu.

Không phải mục tiêu (lần này):
- Hiệu chỉnh cả track từ prelabel (cách C), ghi lên server công ty, sửa nhãn không phải mắt, chấm điểm người gán.
- Phát hiện "thiếu nhãn" (mắt thấy rõ mà không có nhãn): để sau, ghi vào TASKS.

Phản mục tiêu (có chạy cũng coi là hỏng):
- QC làm đổi frame hoặc đối tượng không ai sửa.
- Danh sách dài toàn báo nhầm khiến người duyệt bỏ không xem.
- "Áp cho cả đoạn" làm đoạn tệ hơn mà không báo.
- Đổi loại đối tượng (shape thành track hay ngược lại) của **bất kỳ** nhãn nào trong job, kể cả nhãn không phải mắt; mất thuộc tính.
  (ID và `source` thì import của CVAT luôn đổi, xem mục 4.)

## 4. Ràng buộc

Quy tắc dự án (`CLAUDE.md`): không model học máy; ảnh không rời máy; ghi CVAT chỉ bằng import; EyePin chỉ nối CVAT local. Server
công ty: khi được phép mới bỏ chốt localhost (`cvatapi._check_local`). Lúc đó QC dùng lại y nguyên, không làm lại.

Sự thật về CVAT, đã kiểm trên 2.75 (`design/cvat-api-notes.md`, `design/cvat-keyframe-behaviour.md`):
- Không định dạng xuất nào giữ cả track lẫn shape: "CVAT for video" đổi shape thành track một frame, "CVAT for images" trải track
  thành shape ở mọi frame. Chỉ `GET /api/jobs/{id}/annotations` (JSON) cho đúng loại.
- Một file import "CVAT 1.1" chứa được cả `<track>` lẫn `<image>`, và cả hai giữ loại sau import.
- Import thay toàn bộ nhãn của job.
- Skeleton track: mỗi điểm có keyframe riêng; nội suy đường thẳng; Outside/Occluded ở frame giữa chép từ keyframe bên trái.
- Import "CVAT 1.1" đặt `source="file"` cho mọi track, shape và điểm con (đọc trong mã nguồn CVAT v2.74 trên máy,
  `cvat/apps/dataset_manager/formats/cvat.py` khoảng dòng 1331–1459); theo người đọc kiểm, import cũng bỏ qua `<track id>` nên mọi đối
  tượng nhận ID mới. Chưa thử trên server 2.75. Hệ quả: sau mỗi lần gửi, đối tượng được nhận lại theo **nội dung**, không theo ID; dữ
  liệu phiên gắn theo ID (phần đã sửa, "báo nhầm") phải gắn lại sau khi gửi. Hành vi này đã có từ khi EyePin gửi nhãn lần đầu.

Mã hiện có không đủ cho G1, G4 (đã đọc):
- `cvatsource.open_job` lấy nhãn mắt từ file xuất "CVAT for video" khi có track mắt, nên shape mắt thành track một frame.
- `cvatxml._skeleton_el` ghi mọi điểm là keyframe, skeleton luôn `occluded="0"`, `source="manual"`, bỏ thuộc tính khác.
  Gửi lại nguyên trạng sẽ đổi nội suy của những track không ai sửa.
- `Annotations.shapes` là `{nhãn: {frame: EyeKey}}`: một shape mỗi nhãn mỗi frame, hai người cùng frame thì đè nhau.
- `scan.eye_at` gộp mọi track và shape cùng nhãn thành một, nên Quét không tách được từng người.
- Mô hình phiên hiện nay là "ghim rồi tool bám": nhãn tính từ frame ghim. Nhãn có sẵn của job không phải ghim; QC cần một mô hình
  "đối tượng CVAT sửa được" riêng, nhưng dùng lại thao tác chuột, hoàn tác, vẽ của chế độ gán nhãn.

Khác:
- Không có nhãn chuẩn do người gán (`CLAUDE.md`), nên đo bằng **lỗi cấy giả** (mục 6.7).
- Python 3.12, numpy, OpenCV, Pillow. Không thêm scipy (đề xuất của mình; chỉ thêm nếu số đo cho thấy cần).
- Ảnh đọc qua API của CVAT local, từng frame; dấu hiệu từ ảnh phải chạy nền, không chặn giao diện.

## 5. Các cách đã xét

- **A. Sửa như CVAT.** Nhãn có sẵn sửa được; sửa ở frame nào thì frame đó thành keyframe, nội suy hai bên đổi như CVAT; shape sửa
  đúng frame đó. Dễ đoán, nhưng một lỗi trôi dài nhiều frame phải sửa nhiều lần.
- **B. Sửa một frame, tool sửa cả đoạn lỗi** (người dùng chọn 2026-11-16). Như A, thêm "Áp cho cả đoạn": bám ảnh từ chỗ vừa sửa ra
  hai phía, chỉ trong đoạn bị báo, hai mép đoạn ghim cứng vào nhãn cũ. Tiết kiệm thời gian nhất cho lỗi kéo dài; xây nhiều hơn;
  đổi frame trước chỗ sửa trong đoạn; phải đo để chắc nó không làm hỏng thêm.
- **C. Hiệu chỉnh cả track như skill của đồng nghiệp.** Loại: đổi cả những frame chưa ai xem, QC không có điểm dừng; hợp với
  prelabel sai có hệ thống hơn là nhãn người gán sai cục bộ.

Xây B theo ba lớp, mỗi lớp dùng được ngay: lớp 1 = A (mở, sửa, gửi lại đúng); lớp 2 = tìm lỗi, xếp hạng, hiển thị; lớp 3 = Áp cho cả đoạn.

## 6. Thiết kế

### 6.1 Mở job ở chế độ QC (lớp 1)

- Nhãn mắt đọc từ JSON annotations, cùng `labels` để biết id nhãn mắt và id từng điểm con (tên điểm "14"…"29").
- **Nhãn không phải mắt cũng giữ đúng loại** (đề xuất của mình, theo phản mục tiêu ở mục 3). Một job DMS Landmark có 7 skeleton
  (guideline v1.3), nên nếu mắt có cả track lẫn shape thì nhãn khác nhiều khả năng cũng vậy; đường hiện nay (nền "CVAT for video"
  kèm cảnh báo) sẽ đổi shape của người khác thành track ở mỗi lần gửi QC. Vì vậy file gửi đi và bản chụp để khôi phục đều dựng từ
  JSON annotations của **toàn job**, không từ file xuất.
- Mỗi đối tượng mắt giữ đủ để ghi lại y hệt: loại (track/shape), id CVAT, nhãn, mọi keyframe của từng điểm (toạ độ, outside,
  occluded), cờ của cả skeleton, thuộc tính, group, z_order, source. Người xây kiểm trên CVAT local trường nào CVAT giữ sau import
  và ghi lại.
- Số người: guideline v1.3 và skill của đồng nghiệp đều chỉ gán mắt cho người phía trước (tài xế), nên trường hợp chính là một
  người (đề xuất của mình: không dựng dữ liệu hai người để đo). Mã vẫn quét theo từng đối tượng nên nhiều người không làm sai.
  Ghép mattrai với matphai của cùng người (cho luật "chớp cả hai mắt"): dùng `group` nếu CVAT có, không thì ghép theo khoảng cách
  ở các frame chung; mập mờ thì không ghép và bỏ luật đó cho cặp ấy.
- Mở thư mục với `--xml` vẫn theo hành vi cũ (ngoài phạm vi lần này).

### 6.2 Sửa trong QC (lớp 1)

- Track: sửa ở frame f (kéo điểm, kéo mắt, xoay, co giãn, đổi cờ) tạo keyframe **đủ 8 điểm** tại f (quy tắc dự án: luôn ghi đủ 8
  điểm). Điểm không bị kéo giữ đúng vị trí đang hiện ở f, nên đường nội suy của chúng không đổi. Frame giữa keyframe trước và
  keyframe sau đổi theo nội suy, đúng như CVAT.
- Shape: sửa đúng shape đó.
- Hoàn tác, làm lại như chế độ gán nhãn. Phiên lưu trên máy ghi **phần đã sửa so với nhãn gốc** (theo id đối tượng), để mở lại
  khôi phục được. Job bị sửa trên CVAT kể từ lúc mở thì cảnh báo như hiện nay.

### 6.3 Gửi lại CVAT (lớp 1)

- Dùng lại `cvatsync.prepare`/`send`/`restore` (bản chụp để khôi phục, hộp xác nhận, đọc lại sau import).
- File gửi: đối tượng không sửa ghi đúng như đọc vào (keyframe từng điểm, cờ, thuộc tính, id nếu giữ được); đối tượng đã sửa ghi
  bản mới. Cần đổi `cvatxml` để ghi được keyframe từng điểm, cờ skeleton, thuộc tính, và nhiều shape cùng nhãn một frame.
- Đối chiếu sau khi gửi (nhận đối tượng theo nội dung vì ID đổi), thêm: số track và số shape của **mọi** nhãn không đổi; mọi đối
  tượng không sửa trùng khít (trong sai số làm tròn 0,01 px); đối tượng đã sửa khớp như kiểm hiện nay.

### 6.4 Tìm lỗi và xếp hạng (lớp 2)

Quét theo **từng đối tượng**, không gộp theo nhãn. Các dấu hiệu:
- Hình học (đã có, giữ): thứ tự khoé, mí đảo, bắt chéo, ngoài khung.
- Theo thống kê của chính mắt đó (ý từ skill): bước nhảy và độ mở đổi đột ngột tính bằng độ lệch so với trung vị của chuỗi, chia
  theo bề rộng mắt, thay cho ngưỡng cố định 15 px và EAR cố định. Một mắt nhắm trong khi mắt cùng người mở.
- Từ ảnh:
  - **Trôi khỏi mắt.** Từ mỗi keyframe của track (và mỗi shape), bộ bám của EyePin theo mắt trong ảnh; so với vị trí nhãn ở từng
    frame; khoảng cách chia bề rộng mắt là mức trôi. Bắt lỗi hay gặp nhất của track người gán: nội suy đường thẳng giữa hai
    keyframe thưa không theo kịp chuyển động. Đây là nhận định của mình; MVP 2 (`evaluate.py`) đã cho thấy đường thẳng sai nhiều
    trong đoạn quay đầu; tần suất trên nhãn người gán thật chưa biết.
  - **Mí lệch ảnh** (ý từ skill): tìm mép mí trên trong ảnh, trong khung mắt chuẩn hoá theo hai khoé, so với một frame tham chiếu
    gần đó; báo "nhãn mở mà ảnh nhắm" và ngược lại; chớp chỉ tính khi cả hai mắt cùng khép. Chỉ dùng để xếp hạng, không dùng để sửa
    điểm (chính skill ghi nó không sửa điểm tốt hơn cách khác).
- Gộp: các frame liền nhau cùng đối tượng, cùng loại lỗi là một mục. **Frame rõ nhất** của mục là frame có mức lệch lớn nhất (đã
  chia bề rộng mắt); bằng nhau thì lấy frame giữa.
- Xếp hạng (đề xuất của mình, người xây chỉnh theo số đo ở 6.7): đỏ trước; rồi số dấu hiệu độc lập cùng báo (hình học, thống kê,
  ảnh); rồi mức lệch.
- "Báo nhầm": người duyệt đánh dấu một mục là báo nhầm thì mục đó ẩn, lưu trong phiên; chỉ hiện lại nếu nhãn ở đoạn đó đổi.
- Sửa xong một đối tượng thì quét lại đối tượng đó; mục đã hết lỗi biến mất; hiện "còn N lỗi".

### 6.5 Hiển thị (lớp 2)

- Tab Issues: danh sách đã xếp hạng. Mỗi dòng: mức, `#ID` và nhãn, đoạn a–b, frame rõ nhất, lý do kèm số đo. Bấm dòng thì sang
  frame rõ nhất, phóng vào mắt (đã có "phóng vào mắt"), tô các điểm liên quan; dải thời gian đánh dấu các đoạn lỗi.
- **Lưới xem nhanh** (đề xuất của mình, người dùng xem lại khi duyệt): một cửa sổ gồm nhiều ô, mỗi ô là vùng mắt phóng to tại frame
  rõ nhất của một mục, có nhãn vẽ đè và lý do. Người duyệt lướt một lượt để biết lỗi nào thật; bấm ô thì sang frame đó; có phím
  đánh "báo nhầm" ngay trên ô. Đây là ý "ảnh review" của skill.

```
┌ Xem nhanh: 12 / 37 lỗi ─────────────────────────────────┐
│ [mắt phóng to]  [mắt phóng to]  [mắt phóng to]  [ ... ] │
│ #10 mattrai     #19 matphai     #10 mattrai              │
│ f 120–134       f 88            f 301–340                │
│ trôi 0,42 bề rộng  mí đảo       nhãn mở, ảnh nhắm        │
└──────────────────────────────────────────────────────────┘
```

### 6.6 Áp cho cả đoạn (lớp 3)

- Có ở một mục lỗi kiểu vị trí (trôi, nhảy, cả mắt lệch) của track, sau khi người duyệt đã sửa frame rõ nhất f của đoạn [a, b].
- Tính: bám từ f về sau tới b+1 và từ f về trước tới a−1 bằng bộ bám của EyePin (bám lùi là cùng hàm chạy trên thứ tự frame đảo).
  Tại a−1 và b+1 (ngoài đoạn) so với nhãn hiện có; chỉnh dần trong đoạn để kết quả khớp nhãn cũ ở hai mép. Ghi: keyframe đủ 8 điểm
  tại a−1 và b+1 bằng đúng vị trí đang hiện (để ngoài đoạn không đổi), cộng ít keyframe nhất trong đoạn (`reduce_keyframes`, giữ f).
- Shape: các shape bị báo trong đoạn được thay bằng kết quả bám từ shape vừa sửa; shape không bị báo giữ nguyên.
- Lỗi kiểu mí (chớp, mở nhắm): lần đầu **không** có nút này (bộ bám chỉ dời cả mắt, không đổi dáng); chỉ thêm khi đo được cách làm
  tốt (đề xuất của mình).
- Một bước hoàn tác. Áp xong thì quét lại đoạn; nếu dấu hiệu trôi trong đoạn **tăng** so với trước khi áp thì báo và gợi ý hoàn tác.

### 6.7 Đo (xuyên suốt, mỗi lớp)

- Dữ liệu: ảnh công khai trên CVAT local (case 01 và các job #5–#9). Nhãn "sạch" làm bằng EyePin từ điểm ghim có sẵn (ví dụ
  `spike/out/pins_case01_ai.json`). **Lệch đo:** bộ dò trôi và "Áp cho cả đoạn" dùng cùng bộ bám đã làm ra nhãn sạch này, nên trên
  nhãn đó số báo nhầm dễ thấp hơn thật và sai số sau khi sửa dễ đẹp hơn thật. Số đo trên nhãn do EyePin làm chỉ chứng minh luồng
  chạy đúng; muốn nói về nhãn người gán thì cần nhãn người gán thật (mục 8).
- Bộ cấy lỗi (script trong repo): bỏ keyframe giữa đoạn chuyển động (trôi), giữ mí mở khi chớp, đảo mí, dời một khoé 3–6 px, dời cả
  mắt, lệch một shape, nhãn đứng yên. Cấy vào cả track lẫn shape, job một người và hai người.
- Số đo: tỉ lệ bắt được mỗi loại; số mục báo nhầm trên 100 frame nhãn sạch; bao nhiêu lỗi cấy nằm trong 10 mục đầu; frame rõ nhất
  có nằm trong vùng cấy không; với lỗi trôi: sau một lần sửa + Áp cho cả đoạn, sai số còn lại so với nhãn sạch (px và % bề rộng
  mắt), và ngoài đoạn có trùng khít không.
- Chạy trọn vòng trên CVAT local: import job có lỗi cấy, mở trong EyePin, sửa, gửi, đọc lại JSON, kiểm G4.
- Mức đạt (đề xuất của mình, người dùng quyết khi xem số): mọi lỗi đỏ cấy vào đều bắt được; ít nhất 9/10 lỗi trôi cấy vào nằm
  trong danh sách; sau Áp cho cả đoạn sai số còn lại không quá 2 px; ngoài đoạn trùng khít.

## 7. Để người xây quyết

Tên module và cách chia (gợi ý: mô hình đối tượng QC, quét QC, dấu hiệu mí, bộ cấy lỗi); ngưỡng và trọng số xếp hạng (theo số đo);
số ô và phím của lưới xem nhanh; cách chạy nền dấu hiệu ảnh; chi tiết ghép mắt cùng người. Sau khi xong mỗi lớp: tick và thêm việc
trong `TASKS.md`; đổi module lớn thì vẽ lại `/archify` và cập nhật `CLAUDE.md` (quy tắc dự án).

## 8. Còn mở

- Xin phép đồng nghiệp nếu muốn chép mã (hiện tự viết, không cần).
- "Thiếu nhãn" và tạo shape mới trong QC: để sau.
- Chờ người dùng (sau lượt người đọc kiểm, 2026-11-16): job QC thật trông thế nào (video liền hay ảnh rời; shape mắt dày hay thưa;
  một mắt có đổi qua lại giữa track và shape không; ảnh hồng ngoại/ban đêm hay ảnh màu ban ngày); có ai gán tay được một đoạn video
  công khai trên CVAT local để đo trên nhãn người thật không; chấp nhận việc mỗi lần gửi mọi đối tượng nhận ID mới và
  `source="file"` không.
