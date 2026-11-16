# Ghi chú API CVAT 2.75.0 (thử trên CVAT local, 2026-11-16)

Kết quả của Task 0 trong `design/2026-11-16-cvat-direct-plan.md`. Thử trên job #5 (trống, 210 frame, `start_frame` 0, ảnh 1024×576, dữ liệu công khai) bằng phiên Chrome đã đăng nhập của người dùng; người dùng cho phép ghi thử; đã xoá sạch nhãn thử và kiểm job về 0 track, 0 shape, 0 tag. Mục nào ghi "đọc từ mã nguồn" là chưa thử trên server thật.

## Đã thử thật
1. **Import một lần (không TUS):** `POST /api/jobs/{id}/annotations?format=CVAT 1.1` với multipart trường `annotation_file` → `202 {rq_id}` → `GET /api/requests/{rq_id}` đến `status: finished` (các khoá: `status, message, id, operation, progress, created_date, started_date, finished_date, expiry_date, owner, result_url, result_id`). **Không được gửi tham số `filename` trên URL**: server hiểu là mã file TUS và trả `400 ["No such file were uploaded"]`. Client Task 2 đang gửi `filename=eyepin.xml` nên phải sửa.
2. File thử chỉ có `<track>` + `<image>` (không có `<meta>`) vẫn import được: 1 track mắt (keyframe 0, 20, 40; điểm 16 Outside ở frame 40; điểm 17 Occluded ở frame 20) + 1 shape mắt (frame 30). Sau import: `GET .../annotations` có 1 track (3 shape con ở frame 0, 20, 40) và 1 shape skeleton ở frame 30.
3. **Xuất "CVAT for images 1.1"** (`POST /api/jobs/{id}/dataset/export?format=...&save_images=false` → `rq_id` → `requests/{rq_id}` → `result_url` → zip, mục đầu là `annotations.xml`): **mọi track bị trải thành shape ở mọi frame** (210 `<image>` đều có `<skeleton>`, 0 `<track>`). Shape ở frame 30 giữ nguyên là shape. Cờ điểm giữ đúng (điểm 17 occluded ở frame 20; điểm 16 outside ở frame 40, vẫn có toạ độ).
4. **Xuất "CVAT for video 1.1":** track giữ keyframe: `<skeleton frame keyframe>` có `keyframe="1"` ở frame 0, 20, 40 và một `<skeleton>` cho mỗi frame còn lại (210 phần tử, `keyframe="0"` ở giữa; track kéo tới hết job vì keyframe cuối không Outside); `<points keyframe>` và `outside`/`occluded` từng điểm giữ đúng. **Shape bị đổi thành track một frame** (frame 30 `keyframe="1"` rồi frame 31 `outside`). Không có thẻ `<image>`.
5. Kết luận: **không định dạng xuất nào giữ nguyên cả track lẫn shape.** Đường nhận biết loại đối tượng không đổi là `GET /api/jobs/{id}/annotations` (JSON, có `shapes` và `tracks` đúng loại).

## Đọc từ mã nguồn CVAT (chưa thử trên job nhiều đoạn)
- **Sửa 2026-11-16 (đợt sửa sau review toàn nhánh; câu cũ "chỉ số EyePin `i` ↔ `meta.start_frame + i`" là SAI).** Có hai cách đánh số frame:
  - **Số tương đối của task** `r` (0 … size−1 của task): `start_frame`/`stop_frame` trong `GET /api/jobs/{id}` (và `GET /api/jobs?task_id=`), `data?type=frame&number=r`
    (`media_io/frame_provider.py` `SegmentFrameProvider.get_frame_index` đổi `r` sang số tuyệt đối), `deleted_frames` trong `data/meta`
    (`views.py` ~dòng 2714–2719: `get_rel_frame_number`), JSON `GET/PUT .../annotations` (`dataset_manager/bindings.py` `_import_shape`/`_import_track` gọi `rel_frame_id`).
  - **Số tuyệt đối của media** `a = data.start_frame + r * frame_step`: `data/meta.start_frame`/`stop_frame` (`views.py` ~2703–2705, 2721–2722) và **số frame trong
    XML "CVAT 1.1"** cả khi xuất lẫn khi nhập (`bindings.py` `_abs_frame_id`/`abs_frame_id` dùng cho `<image id>`, `frame=` của shape, track, tag; khi nhập
    `rel_frame_id` đổi ngược lại). Ghi chú: brief của đợt sửa nói XML dùng số tương đối; đọc `bindings.py` thì không phải — chưa thử trên server thật.
  - `data/meta.size` = số frame của job (`len(segment.frame_set)`); `data/meta.frames` với task ảnh rời có một phần tử mỗi frame, với **task tạo từ video chỉ
    có MỘT phần tử**; `included_frames` có giá trị với job thưa (ground truth).
  - Hai cách đánh số trùng nhau khi task không đặt `start_frame` (data.start_frame = 0) và `frame_step` = 1 — trường hợp của mọi task local hiện có.
- **EyePin làm gì (cvatsource.CvatSource):** chỉ số EyePin `i` ↔ `job.start_frame + i`, `i` chạy tới `job.stop_frame`; dùng cho `data?number=`, `deleted_frames` và
  (vì chỉ mở job có hai cách đánh số trùng nhau) cho XML. Từ chối mở (CvatError) khi `meta.size ≠ stop − start + 1`, khi `len(meta.frames) ≠ meta.size` (video),
  khi có `included_frames` (job thưa), và khi `(meta.start_frame, meta.stop_frame) ≠ (job.start_frame, job.stop_frame)` (task đặt start_frame/frame_step: XML sẽ
  mang số khác; nếu sau này xác nhận được thì đổi sang số XML `meta.start_frame + i * frame_step` thay vì từ chối).
- `deleted_frames` nằm trong `data/meta`; chưa thử hành vi frame đã xoá khi xuất.

## Hệ quả cho thiết kế (đã cập nhật vào kế hoạch)
- **Định dạng nền khi gửi** phải chọn theo loại đối tượng không phải mắt của job (đọc bằng JSON annotations): chỉ có shape → "CVAT for images"; chỉ có track → "CVAT for video"; không có gì → "CVAT for images"; có cả hai → "CVAT for video" kèm cảnh báo trong hộp xác nhận rằng các shape sẽ thành track một frame.
- **Định dạng để hiện nhãn mắt ở chế độ QC:** có track mắt → "CVAT for video" (giữ keyframe); chỉ có shape mắt → "CVAT for images".
- `CvatClient` cần thêm `annotations(job_id) -> dict` (JSON) và `import_xml` không gửi `filename`.
- Lệnh `DELETE /api/jobs/{id}/annotations` (204) xoá sạch nhãn của job, dùng để dọn sau khi thử.
