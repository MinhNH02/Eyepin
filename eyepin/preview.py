"""Tính vị trí từng frame đúng như CVAT hiển thị, để bản xem trước của tool khớp với CVAT sau khi import.

Quy tắc của CVAT 2.75 (xem design/cvat-keyframe-behaviour.md):
  - Giữa hai keyframe: nội suy đường thẳng theo số frame.
  - Sau keyframe cuối: giữ nguyên vị trí keyframe cuối.
  - Trước keyframe đầu: không hiện (Outside).
  - Cờ occluded và outside ở frame giữa lấy từ keyframe bên trái, không nội suy.
"""
from __future__ import annotations

from .cvatxml import EyeKey, PointState


def position_at(keys: dict[int, EyeKey], frame: int, ids: list[int]) -> EyeKey | None:
    """Trạng thái của 8 điểm tại `frame`; None nếu frame đứng trước keyframe đầu tiên."""
    if not keys:
        return None
    frames = sorted(keys)
    if frame < frames[0]:
        return None
    left = max(f for f in frames if f <= frame)
    right = next((f for f in frames if f > frame), None)
    if frame == left or right is None:
        k = keys[left]
        return EyeKey(frame, {i: PointState(k.points[i].xy, k.points[i].outside, k.points[i].occluded, k.points[i].keyframe) for i in ids},
                      keyframe=frame == left, outside=k.outside)
    a, b = keys[left], keys[right]
    w = (frame - left) / (right - left)
    pts = {}
    for i in ids:
        pa, pb = a.points[i], b.points[i]
        pts[i] = PointState((pa.xy[0] + w * (pb.xy[0] - pa.xy[0]), pa.xy[1] + w * (pb.xy[1] - pa.xy[1])),
                            pa.outside, pa.occluded, False)
    return EyeKey(frame, pts, keyframe=False, outside=a.outside)
