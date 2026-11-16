# EyePin nối thẳng với CVAT local

Ngày 2026-11-16. Trạng thái: người dùng chọn cách A; với nhãn mắt có sẵn, người dùng chốt chế độ QC + "xoá nhãn cũ rồi gán lại" (thay cho cách (d) nhận thành ghim) và giữ cảnh báo (b). Các chỗ ghi "đề xuất của mình" chưa được người dùng xem riêng.

## 1. Ý định và lý do
Người dùng (2026-11-16): "bạn đang khoá cố định theo data có sẵn ... cần một luồng nối trực tiếp đến CVAT để thao tác xong dữ liệu có thể truyền vào CVAT luôn". Hiện EyePin chỉ mở một thư mục ảnh trên ổ đĩa (kèm file nhãn export nếu có) và xuất file XML để người dùng tự import vào CVAT. Người dùng muốn: mở một job CVAT ngay trong EyePin, gán nhãn, rồi gửi thẳng kết quả vào job đó.

Người dùng đã chốt:
- Làm với **CVAT local** (`http://localhost:8080`, dữ liệu công khai) trước. Server công ty để sau, người dùng sẽ tự cải tiến.
- Chọn **cách A**: EyePin mở thẳng job, ảnh lấy qua API và chỉ giữ trong RAM, gửi lên bằng import.

## 2. Mục tiêu
1. Trong cửa sổ có lệnh **"Mở từ CVAT…"**: nhập địa chỉ server (mặc định `http://localhost:8080`), tên đăng nhập, mật khẩu; chọn task rồi job trong danh sách; EyePin mở job đó như đang mở một thư mục ảnh.
2. Ảnh của job lấy qua API, giải mã và giữ **chỉ trong RAM** (cùng giới hạn bộ nhớ đệm hiện có), không ghi ra đĩa.
3. Nhãn đang có trong job được tải về khi mở, làm "file nhãn nền" như hiện nay (giữ nguyên mọi nhãn không phải mắt khi gửi lại).
4. Lệnh **"Gửi lên CVAT"**: dựng file CVAT 1.1 như "Xuất file import" hiện nay, import vào đúng job qua API, chờ server xử lý xong, rồi **tải lại nhãn từ CVAT và đối chiếu** với nhãn tool tính (cùng tiêu chí với `tests/verify_vs_cvat.py`: vị trí trong 2 px + làm tròn, keyframe, cờ Occluded/Outside). Báo kết quả bằng chữ.
5. Trước khi gửi luôn có hộp xác nhận nói rõ: import **thay toàn bộ nhãn của job**; file gửi chứa lại mọi nhãn khác của job.
6. Phiên làm việc (ghim, cờ, undo đã lưu) gắn với **server + số job**, khôi phục được khi mở lại cùng job.

## 3. Không phải mục tiêu (lần này)
- Server CVAT công ty (cần mentor cho phép ghi; ảnh chỉ trong RAM đã được thiết kế sẵn để sau này không phải làm lại).
- Sửa từng nhãn qua API (PATCH). Luật đã chốt: ghi vào CVAT bằng tính năng import.
- Đồng bộ trực tiếp khi nhiều người cùng sửa một job.
- Shape mắt, tải ảnh theo chunk, upload file lớn bằng giao thức TUS.

## 4. Điều làm hỏng dù chạy đúng (anti-goal)
- Gửi lên làm mất nhãn không phải mắt của job, hoặc mất nhãn mắt người khác vừa sửa trên CVAT mà không cảnh báo.
- Ảnh bị ghi ra đĩa (kể cả file tạm).
- Gửi tới một server không phải localhost.
- Báo "đã gửi" khi chưa đối chiếu được với dữ liệu CVAT trả về.

## 5. Ràng buộc
- Quy tắc trong `CLAUDE.md` (người dùng đã chốt): không model học máy; ghi CVAT bằng import; CVAT local ghi tự do; server công ty không tự ghi, không điều khiển trình duyệt vào đó; ảnh công ty không bao giờ ra đĩa hay mạng.
- **Chỉ cho phép host `localhost`, `127.0.0.1`, `::1`** ở lần này (kiểm trong mã, báo lỗi tiếng Việt nếu khác).
- API CVAT (đã đọc trong mã nguồn `C:\Users\minhf\cvat`, bản `v2.74.0-62`; CVAT local chạy `v2.75.0`, cần kiểm lại khi chạy thật):
  - Đăng nhập: `POST /api/auth/login` với `{username, password}` → `{"key": ...}`; mọi lệnh sau gửi `Authorization: Token <key>` (CVAT local dùng tiền tố `Token`, ghi trong `CLAUDE.md`). Không gửi `Accept: application/json` (server công ty trả 406; giữ thói quen này).
  - Danh sách: `GET /api/tasks`, `GET /api/jobs?task_id=<id>` (có phân trang `page`, `page_size`).
  - Frame: `GET /api/jobs/{id}/data/meta` (tên frame, `start_frame`, `stop_frame`, `frame_filter`, `included_frames`, `deleted_frames`, kích thước); ảnh: `GET /api/jobs/{id}/data?type=frame&number=<n>&quality=original`.
  - Xuất nhãn: `POST /api/jobs/{id}/dataset/export?format=CVAT for images 1.1&save_images=False` → `202 {rq_id}` → hỏi `GET /api/requests/{rq_id}` tới khi `status` là `finished` (có `result_url`) hoặc `failed` → tải `result_url` (zip chứa `annotations.xml`). Các đường cũ `GET .../annotations?format=` trả 410.
  - Import: `POST /api/jobs/{id}/annotations?format=CVAT 1.1&filename=eyepin.xml` gửi multipart trường `annotation_file` (không dùng header TUS) → `202 {rq_id}` → hỏi `GET /api/requests/{rq_id}`. Mặc định `import_mode=replace` (xoá nhãn cũ của job rồi nạp).
  - Thông tin job: `GET /api/jobs/{id}` (có `updated_date`, `task_id`, `start_frame`, `stop_frame`).
- Thư viện: `requests` 2.34 đã cài; không thêm thư viện khác.
- Docker Desktop phải chạy; sau khi khởi động lại có thể phải `docker restart traefik` (ghi trong `CLAUDE.md`). Tool chỉ báo lỗi kết nối rõ ràng, không tự bật Docker.

## 6. Các cách đã cân nhắc
- **A. EyePin mở thẳng job, ảnh trong RAM, gửi bằng import (người dùng chọn).** Đúng ý "thao tác xong truyền vào CVAT luôn"; sang server công ty sau này chỉ thêm bước xin phép và xác nhận. Tốn nhất: phần đọc ảnh của `Session` phải tách khỏi thư mục trên đĩa.
- B. Tải job về thư mục rồi mở như cũ, cuối cùng gửi lên. Ít sửa lõi, nhưng ảnh nằm trên đĩa nên phải làm lại khi dùng dữ liệu công ty.
- C. Chỉ thêm nút gửi. Rẻ nhất nhưng không giải quyết việc tool bị gắn với dữ liệu có sẵn.

## 7. Thiết kế (phần đã quyết)
**Nguồn ảnh.** `Session` nhận một nguồn ảnh thay vì chỉ một thư mục: nguồn thư mục (hành vi hiện tại, giữ nguyên mọi test) và nguồn CVAT. Nguồn cho biết số frame, tên từng frame, kích thước ảnh, và trả ảnh BGR của frame thứ `i` (chỉ số 0..n-1 của EyePin; nguồn CVAT tự đổi sang số frame thật của job theo `data/meta`). Bộ nhớ đệm ảnh và ảnh xám của `Session` giữ nguyên giới hạn hiện có (40 ảnh màu, 250 MB ảnh xám).

**Đánh số frame.** File XML gửi lên dùng đúng số frame của job (CVAT 1.1 của job tính frame từ `start_frame` của job trong task). Builder phải đối chiếu cách `cvatxml` hiện đánh số với file export thật của một job không bắt đầu từ frame 0 (ví dụ job thứ hai của một task chia nhiều job) và test cả hai chiều.

**Nhãn nền.** Khi mở job: xuất "CVAT for images 1.1" (không kèm ảnh), đọc `annotations.xml` từ zip trong bộ nhớ (được phép ghi file tạm cho XML vì nó chỉ có toạ độ; ảnh thì không bao giờ). Dùng làm `Session.ann` như khi mở bằng `--xml`.

**Gửi lên.** Ngay trước khi gửi, xuất lại nhãn của job ("CVAT for images 1.1") và dùng bản mới này làm nền (đề xuất của mình: giữ được nhãn không phải mắt mà người khác vừa sửa trên CVAT), giữ bản này trong RAM làm **bản chụp trước khi gửi**. Dựng XML bằng đường `Session.export` hiện có, import, chờ, rồi xuất lại "CVAT for video 1.1" và đối chiếu như `verify_vs_cvat.py` (V1 vị trí, V2 cờ, V3 keyframe), chỉ trên các frame không bị xoá trong CVAT. Báo: số keyframe đã gửi, số frame lệch (nếu có), thời gian.

**Khi đối chiếu lệch** (đề xuất của mình): không tự khôi phục; báo rõ chỗ lệch và hiện nút "Khôi phục job về bản trước khi gửi" (import lại bản chụp). Nếu chính lần khôi phục lỗi thì báo lỗi của server và giữ bản chụp để thử lại; bản chụp chỉ là XML toạ độ nên được phép ghi ra file tạm khi người dùng bấm "Lưu bản chụp".

**Chống ghi đè** (đề xuất của mình). Mốc là `updated_date` của job lúc mở, và sau mỗi lần gửi thành công thì là `updated_date` mới. Mốc này **được lưu vào file phiên** (thêm một trường; file phiên cũ không có trường này vẫn mở được). Khi mở lại job mà khôi phục phiên, nếu `updated_date` hiện tại khác mốc đã lưu thì báo ngay "job đã bị sửa trên CVAT kể từ lần bạn gửi" (vẫn cho làm tiếp). Trước khi gửi, đọc lại `updated_date`; khác mốc thì hộp xác nhận nói rõ "job đã bị sửa trên CVAT; gửi sẽ thay các sửa đó", mặc định là Huỷ.

**Frame đã xoá** (đề xuất của mình). Frame mà CVAT đã xoá (`deleted_frames` trong `data/meta`) hiện là "đã xoá trong CVAT", chỉ đọc. Ở chế độ CVAT, lệnh xoá/khôi phục frame của EyePin bị tắt (không đưa được lên CVAT bằng import) kèm thông báo; khi khôi phục phiên thì `deleted_frames` của CVAT thắng. Đối chiếu sau khi gửi bỏ qua các frame này. Builder kiểm thật trên CVAT local xem `data?type=frame` có trả ảnh cho frame đã xoá không và file export có chứa frame đó không, rồi ghi lại.

**Nhãn mắt có sẵn trong job (người dùng chốt 2026-11-16, thay cho cách (d) nhận thành ghim):** "với nhãn có sẵn nên chuyển sang mode QC, nếu chưa có thì mới dùng EyePin, nếu đã có muốn chỉnh sửa thì xoá nhãn cũ và dùng các tính năng của EyePin".
- **Job chưa có nhãn mắt** (không track, không shape `mattrai`/`matphai`): mở ở chế độ gán nhãn bình thường của EyePin.
- **Job đã có nhãn mắt: chế độ QC.** Hiện nhãn đúng như CVAT hiển thị (đường `points_at` từ file nhãn hiện có), tự chạy Quét và mở tab Issues (đỏ/vàng theo `scan.py`), điều hướng theo vấn đề như hiện nay. Mọi lệnh sửa nhãn (vẽ, ghim, kéo, xoay, đổi kích thước, cờ, propagate, dán, xoá) bị chặn kèm thông báo "Job đã có nhãn mắt: đang ở chế độ QC. Muốn sửa thì bấm 'Xoá nhãn mắt cũ và gán lại'." "Gửi lên CVAT" bị tắt (không có gì để gửi). Phạm vi QC lần này là xem + Quét (đề xuất của mình; thêm thước đo khác là việc sau).
- **Lệnh "Xoá nhãn mắt cũ và gán lại"** (chỉ trong chế độ QC): hộp xác nhận nêu số track và shape mắt sẽ bị xoá khi gửi; đồng ý thì bỏ nhãn mắt khỏi nhãn nền trong phiên (nhãn không phải mắt giữ nguyên), rời chế độ QC, dùng EyePin như job trống. Trên CVAT chưa có gì thay đổi cho tới khi bấm "Gửi lên CVAT". Hoàn tác được trước khi gửi (quay lại chế độ QC).
- Phạm vi: lần này áp dụng khi mở **từ CVAT**. Mở thư mục với `--xml` giữ hành vi cũ (đề xuất của mình, để không đổi các test và luồng hiện có trước demo); áp dụng cho cả `--xml` là việc ghi trong `TASKS.md`.
- **(b) Cảnh báo trước khi gửi** (vẫn giữ). Trên bản nhãn nền vừa xuất lại, đếm nhãn mắt sẽ bị thay: shape mắt và track mắt đang có trên CVAT (gồm cả nhãn cũ người dùng đã chọn xoá, và nhãn ai đó vừa thêm sau khi mở). Nếu có, hộp xác nhận ghi số lượng và khoảng frame ("sẽ xoá 1 track mắt #37 (mattrai, frame 0–120) và 30 shape mắt"), mặc định là Huỷ.

**Đăng nhập.** Khoá (`key`) chỉ giữ trong RAM của phiên; không lưu mật khẩu, không lưu khoá ra đĩa. Địa chỉ server và tên đăng nhập gần nhất được nhớ trong `~/.eyepin/settings.json` cho tiện (đề xuất của mình).

**Lưu phiên.** Khoá của file phiên là `server + số job` thay cho đường dẫn thư mục; nội dung file phiên không đổi.

**Giao diện.** Menu và thanh trên: "Mở từ CVAT…" (hộp: địa chỉ, tên, mật khẩu, nút Đăng nhập, danh sách task, danh sách job kèm số frame và trạng thái), "Gửi lên CVAT" (chỉ bật khi đang mở từ CVAT). Thanh tiêu đề ghi `CVAT job #<id> (task <tên>)`. Việc mạng chạy trên luồng nền để cửa sổ không đứng; trong lúc chờ hiện tiến độ và chặn sửa nhãn.

**Mở bằng dòng lệnh** (cho demo và test): `python -m eyepin gui --cvat http://localhost:8080 --job <id>` (hỏi mật khẩu trong cửa sổ).

## 8. Edge case
| Trường hợp | Xử lý |
|---|---|
| CVAT tắt, sai địa chỉ, hết thời gian chờ | Báo lỗi tiếng Việt kèm gợi ý (bật Docker, `docker restart traefik`); không treo cửa sổ |
| Sai mật khẩu / khoá hết hạn (401) | Báo và mở lại hộp đăng nhập; không mất ghim đang làm |
| Job không có label `mattrai`/`matphai` dạng skeleton đủ 8 điểm | Từ chối mở, nói rõ thiếu gì |
| Job có frame đã xoá trong CVAT (`deleted_frames`) | Đánh dấu là frame đã xoá trong EyePin (như `Session.deleted`) |
| Job bắt đầu không phải frame 0 | Đánh số đúng như mục 7 |
| Import thất bại (`status: failed`) | Hiện thông báo lỗi của server; nhãn trong EyePin giữ nguyên |
| Đối chiếu sau khi gửi lệch | Báo rõ frame và điểm lệch; không báo thành công |
| Job đã có nhãn mắt (gán tay trên CVAT, hoặc gửi từ EyePin lần trước) | Chế độ QC; muốn sửa thì "Xoá nhãn mắt cũ và gán lại". Phiên đã lưu cho job này (ghim của lần làm trước) được hỏi khôi phục như hiện nay; khôi phục thì coi như đã chọn xoá nhãn cũ và gán lại |
| Đổi frame nhanh khi ảnh chưa tải xong | Hiện "đang tải", không chặn giao diện |

## 9. Cách kiểm
- Test đơn vị không cần Docker: một server CVAT giả (chạy `http.server` trong luồng) trả `data/meta`, ảnh tổng hợp, zip export và các bước `requests/{rq_id}`; kiểm đăng nhập, mở job, đánh số frame, gửi lên, chặn host lạ, chống ghi đè, lỗi 401/500.
- Test tích hợp với CVAT local thật (như `tests/verify_vs_cvat.py`, cần job trống, dọn sau khi xong).
- 206 test hiện có phải còn qua; mở bằng thư mục vẫn y như cũ.

## 10. Để người xây quyết định
Tên module (gợi ý `eyepin/cvatapi.py` cho client, nguồn ảnh cạnh `session.py`), cách tải trước ảnh (luồng nền, bao nhiêu frame), khoảng hỏi trạng thái `requests/{rq_id}`, bố cục hộp "Mở từ CVAT", chữ thông báo cụ thể.

## 11. Câu hỏi còn mở
Không còn câu chặn việc xây. Nhãn mắt có sẵn: người dùng chốt chế độ QC + "xoá nhãn cũ rồi gán lại", giữ cảnh báo (b); bỏ cách (d) (mục 7).

## 12. Kết quả lượt kiểm của người xây (2026-11-16)
Bốn câu: (1) nhãn mắt không do EyePin quản: chờ người dùng; (2) lưu mốc `updated_date` qua các lần mở; (3) khôi phục khi đối chiếu lệch; (4) xoá frame ở chế độ CVAT. Câu 2–4 đã được mình quyết trong mục 7 (đánh dấu "đề xuất của mình").
