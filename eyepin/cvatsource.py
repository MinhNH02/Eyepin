"""Nguồn ảnh CVAT và mở một job: frame lấy qua API và chỉ nằm trong RAM; nhãn hiện có của job là nhãn nền của phiên.

Số frame: chỉ số EyePin `i` ứng với `frame_numbers[i]` = `job.start_frame + i` (số TƯƠNG ĐỐI của task, từ `GET /api/jobs/{id}`; cũng là số của
`data?type=frame&number=`, `deleted_frames` và JSON annotations). `meta.start_frame` là số TUYỆT ĐỐI của media, không dùng. Số trong XML "CVAT 1.1" là
số tuyệt đối (bindings.py `abs_frame_id`); EyePin chỉ mở job mà hai cách đánh số trùng nhau (task không đặt start_frame/frame_step) và gồm các ảnh rời
liên tiếp (không phải video, không thưa). XML đọc từ CVAT được đổi sang chỉ số EyePin (`cvatxml.parse_bytes`) và `cvatxml.write_eyes` đổi ngược lại.
Xem design/cvat-api-notes.md.
"""
from __future__ import annotations

import cv2
import numpy as np

from . import cvatxml, qc
from .cvatapi import EYES, CvatClient, CvatError, LoginNeeded
from .session import Session

IMAGES = "CVAT for images 1.1"     # shape giữ nguyên là shape; track bị trải thành shape ở mọi frame
VIDEO = "CVAT for video 1.1"       # track giữ keyframe; shape thành track một frame


class CvatSource:
    """Một job của CVAT như một nguồn ảnh (cùng giao diện với `frames.DirSource`). Không tải frame nào cho tới khi `read`."""

    def __init__(self, client: CvatClient, job_id: int):
        self.client, self.job_id = client, job_id
        self.job = client.job(job_id)
        meta = client.meta(job_id)
        frames = meta.get("frames") or []
        try:
            start, stop = int(self.job["start_frame"]), int(self.job["stop_frame"])
        except (KeyError, TypeError, ValueError) as e:
            raise CvatError("CVAT không trả khoảng frame (start_frame, stop_frame) của job #%d." % job_id) from e
        n = stop - start + 1
        if n <= 0 or not frames:
            raise CvatError("Job này không có frame nào.")
        if meta.get("included_frames"):
            raise CvatError("Job #%d là job thưa (chỉ gồm một số frame chọn lẻ của task, ví dụ job ground truth): EyePin chưa hỗ trợ loại job này."
                            % job_id)
        size = int(meta.get("size", -1))
        if size != n:
            raise CvatError("CVAT trả số frame của job #%d không khớp: job gồm frame %d–%d (%d frame) nhưng data/meta báo size %d. "
                            "EyePin không mở để khỏi gửi nhãn lệch frame." % (job_id, start, stop, n, size))
        if len(frames) != size:
            raise CvatError("Job #%d có %d frame nhưng CVAT chỉ liệt kê %d tên ảnh: task tạo từ video (hoặc media không phải ảnh rời). "
                            "EyePin hiện chỉ hỗ trợ job gồm các ảnh rời liên tiếp." % (job_id, size, len(frames)))
        m_start, m_stop = meta.get("start_frame"), meta.get("stop_frame")
        if (m_start, m_stop) != (start, stop):
            # Số trong XML "CVAT 1.1" là số tuyệt đối của media (bindings.py abs_frame_id = data.start_frame + số tương đối * frame_step,
            # cũng là cách tính meta.start_frame/stop_frame), còn data?number=, deleted_frames và JSON dùng số tương đối của task. Hai cách
            # đánh số chỉ trùng khi task không đặt start_frame/frame_step; chưa xác nhận trên server thật nên từ chối thay vì gửi lệch frame.
            raise CvatError("Task của job #%d đặt frame bắt đầu hoặc bước nhảy frame (media: frame %s–%s; task: frame %d–%d): số frame trong file "
                            "XML của CVAT khác số frame của job nên EyePin chưa mở loại job này (để khỏi gửi nhãn lệch frame)."
                            % (job_id, m_start, m_stop, start, stop))
        self.frame_numbers: list[int] = [start + i for i in range(n)]      # số tương đối của task (data?number=, deleted_frames, JSON; XML khi trùng)
        self.names = [str(f.get("name", "")) for f in frames]
        self.width, self.height = int(frames[0]["width"]), int(frames[0]["height"])
        gone = {int(k) for k in meta.get("deleted_frames") or []}
        self.deleted: set[int] = {i for i, k in enumerate(self.frame_numbers) if k in gone}
        self.key = f"cvat:{client.url}|job{job_id}"
        self.title = f"CVAT job #{job_id} ({self._task_name()})"

    def _task_name(self) -> str:
        task_id = self.job.get("task_id")
        try:
            for t in self.client.tasks():
                if t["id"] == task_id:
                    return t.get("name") or f"task #{task_id}"
        except LoginNeeded:
            raise
        except CvatError:
            pass                                            # tên chỉ để hiện; không vì nó mà không mở được job
        return f"task #{task_id}"

    def read(self, i: int) -> np.ndarray:
        data = self.client.frame(self.job_id, self.frame_numbers[i])
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)     # giải mã trong RAM, không qua file
        if img is None:
            raise CvatError("Không giải mã được ảnh frame %d của CVAT." % self.frame_numbers[i])
        return img


def _eye_label_ids(labels: list[dict]) -> set[int]:
    return {lb["id"] for lb in labels if lb.get("name") in EYES}


_is_eye = qc.is_eye_obj             # quy tắc "là mắt" nằm ở qc.py; tên cũ giữ cho cvatsync


def base_format(annotations_json: dict, eye_label_ids: set[int] | None = None) -> tuple[str, str]:
    """(định dạng làm nền khi gửi, định dạng để hiện nhãn mắt của job), theo JSON của `GET /api/jobs/{id}/annotations`.

    Nền: "CVAT for video" khi có track không phải mắt (shape đi cùng sẽ thành track một frame), ngược lại "CVAT for images".
    Hiện nhãn mắt: "CVAT for video" khi có track mắt (giữ keyframe), ngược lại "CVAT for images". `eye_label_ids` là id nhãn của hai skeleton
    mắt (từ `CvatClient.labels`); không đưa vào thì skeleton đủ 8 điểm được coi là mắt.
    """
    tracks = annotations_json.get("tracks") or []
    base = VIDEO if any(not _is_eye(t, eye_label_ids) for t in tracks) else IMAGES
    display = VIDEO if any(_is_eye(t, eye_label_ids) for t in tracks) else IMAGES
    return base, display


def open_job(client: CvatClient, job_id: int) -> Session:
    """Mở một job của CVAT thành phiên làm việc: nhãn hiện có là nhãn nền (job có nhãn mắt thì phiên ở chế độ QC)."""
    problem = client.eye_labels_ok(job_id)
    if problem:
        raise CvatError(problem + " EyePin chỉ mở job có hai skeleton mắt 'mattrai' và 'matphai' (8 điểm mỗi mắt).")
    eye_ids = _eye_label_ids(client.labels(job_id))
    source = CvatSource(client, job_id)
    aj = client.annotations(job_id)
    base, display = base_format(aj, eye_ids)
    nums = source.frame_numbers
    try:
        ann = cvatxml.parse_bytes(client.export_xml(job_id, base), nums)
        if display != base and qc.json_has_eyes(aj, eye_ids):       # hai định dạng giữ khác nhau: nền từ `base`, nhãn mắt (keyframe) từ `display`
            shown = cvatxml.parse_bytes(client.export_xml(job_id, display), nums)
            ann.tracks, ann.shapes = shown.tracks, shown.shapes
    except ValueError as e:
        raise CvatError(str(e)) from e
    session = Session(source=source, ann=ann)
    session.cvat = {"job": job_id, "updated": source.job.get("updated_date")}
    session.base_format, session.display_format = base, display
    session.qc = qc.has_eye_labels(ann) or qc.json_has_eyes(aj, eye_ids)     # JSON thấy mắt mà XML không (track rỗng/toàn Outside): vẫn là QC, không cho gán đè
    return session
