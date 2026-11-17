"""Bám theo mắt qua các frame bằng so khớp vùng ảnh (OpenCV matchTemplate). Không dùng model.

Quy tắc đã chốt với người dùng: ghim hoặc sửa frame N thì chỉ các frame SAU N, cho tới frame ghim kế tiếp, đổi theo
frame N; các frame trước N không bao giờ đổi. Vì vậy mỗi đoạn được bám tiến từ frame ghim đứng ngay trước nó.

Phép bám chỉ dời cả mắt (dịch ngang, dịch dọc). Dáng mắt giữ như ở frame ghim; khi mắt đổi dáng (chớp, nhắm), điểm khớp
tụt xuống và người dùng ghim lại ở đó.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import cv2
import numpy as np

from .geometry import EYES, Point


@dataclass
class TrackResult:
    frame: int
    points: dict[int, Point]          # đủ 16 điểm hai mắt tại frame này
    score: float                      # độ khớp thấp nhất của hai mắt, 0..1
    scores: dict[str, float]


def _bbox(points: dict[int, Point], ids: Sequence[int]) -> tuple[float, float, float, float]:
    xs = [points[i][0] for i in ids]
    ys = [points[i][1] for i in ids]
    return min(xs), min(ys), max(xs), max(ys)


def _subpixel(r: np.ndarray, loc: tuple[int, int]) -> tuple[float, float]:
    """Tinh chỉnh vị trí đỉnh tương quan xuống dưới 1 pixel bằng parabol qua 3 điểm theo từng trục."""
    x, y = loc
    sx = sy = 0.0
    if 0 < x < r.shape[1] - 1:
        a, b, c = float(r[y, x - 1]), float(r[y, x]), float(r[y, x + 1])
        d = a - 2 * b + c
        if d < -1e-9:
            sx = max(-0.5, min(0.5, 0.5 * (a - c) / d))
    if 0 < y < r.shape[0] - 1:
        a, b, c = float(r[y - 1, x]), float(r[y, x]), float(r[y + 1, x])
        d = a - 2 * b + c
        if d < -1e-9:
            sy = max(-0.5, min(0.5, 0.5 * (a - c) / d))
    return sx, sy


def track_forward(get_gray: Callable[[int], np.ndarray], start: int, end: int, pins: dict[int, Point],
                  *, margin: tuple[float, float] = (0.3, 0.45), search: float = 0.45) -> list[TrackResult]:
    """Bám tiến từ frame `start` (đã có đủ 16 điểm `pins`) tới frame `end` (không tính end).

    get_gray(f): ảnh xám của frame f. margin: phần mở rộng vùng mẫu, tính theo (bề rộng, chiều cao) của mắt.
    search: bán kính tìm kiếm mỗi frame, tính theo bề rộng mắt.
    Kết quả gồm cả frame `start` (độ khớp 1.0) và mọi frame tới end-1.
    """
    base = get_gray(start)
    eyes = {}
    present = {l: sp for l, sp in EYES.items() if all(i in pins for i in sp.ids)}      # một frame ghim có thể chỉ có một mắt
    for label, spec in present.items():
        x0, y0, x1, y1 = _bbox(pins, spec.ids)
        w, h = x1 - x0, max(y1 - y0, 0.25 * (x1 - x0))
        bx0, by0 = int(round(x0 - margin[0] * w)), int(round(y0 - margin[1] * h))
        bx1, by1 = int(round(x1 + margin[0] * w)), int(round(y1 + margin[1] * h))
        bx0, by0 = max(bx0, 0), max(by0, 0)
        bx1, by1 = min(bx1, base.shape[1]), min(by1, base.shape[0])
        eyes[label] = {"tmpl": base[by0:by1, bx0:bx1].copy(), "x": bx0, "y": by0, "x0": bx0, "y0": by0,
                       "rad": max(3, int(round(search * w)))}
    out = [TrackResult(start, dict(pins), 1.0, {l: 1.0 for l in present})]
    for f in range(start + 1, end):
        g = get_gray(f)
        pts, scores = {}, {}
        for label, spec in present.items():
            e = eyes[label]
            th, tw = e["tmpl"].shape
            wx0, wy0 = max(0, e["x"] - e["rad"]), max(0, e["y"] - e["rad"])
            wx1, wy1 = min(g.shape[1] - tw, e["x"] + e["rad"]), min(g.shape[0] - th, e["y"] + e["rad"])
            if wx1 < wx0 or wy1 < wy0:
                scores[label] = 0.0
                dx = e["x"] - e["x0"]
                dy = e["y"] - e["y0"]
            else:
                r = cv2.matchTemplate(g[wy0:wy1 + th, wx0:wx1 + tw], e["tmpl"], cv2.TM_CCOEFF_NORMED)
                _, score, _, loc = cv2.minMaxLoc(r)
                sx, sy = _subpixel(r, loc)
                e["x"], e["y"] = wx0 + loc[0], wy0 + loc[1]
                scores[label] = float(score)
                dx, dy = e["x"] + sx - e["x0"], e["y"] + sy - e["y0"]
            for i in spec.ids:
                pts[i] = (pins[i][0] + dx, pins[i][1] + dy)
        out.append(TrackResult(f, pts, min(scores.values()), scores))
    return out


def track_backward(get_gray: Callable[[int], np.ndarray], start: int, end: int, pins: dict[int, Point], **kw) -> list[TrackResult]:
    """Bám lùi từ frame `start` (có đủ điểm `pins`) về frame `end` (tính cả end, end <= start): cùng phép so khớp với
    `track_forward` nhưng đi trên dãy frame đảo ngược. Kết quả theo thứ tự start, start-1, ..., end và mang số frame thật.

    Chỉ dùng để so sánh trong báo cáo độ chính xác (`evaluate.py`): nhãn của tool vẫn chỉ bám tiến (quy tắc đã chốt).
    """
    seq = track_forward(lambda k: get_gray(start - k), 0, start - end + 1, pins, **kw)
    return [TrackResult(start - r.frame, r.points, r.score, r.scores) for r in seq]


def propagate(get_gray: Callable[[int], np.ndarray], n_frames: int, pins: dict[int, dict[int, Point]],
              **kw) -> tuple[dict[int, TrackResult], dict[int, TrackResult]]:
    """Mỗi frame ghim bám tiến tới frame ghim kế tiếp (hoặc hết job).

    Trả về (nhãn, vị_trí_đến). `nhãn[f]` là nhãn do tool tính cho frame f (frame ghim lấy đúng điểm ghim); frame đứng trước
    frame ghim đầu tiên không có nhãn. `vị_trí_đến[g]` với g là frame ghim thứ hai trở đi: nơi phép bám đi tới từ frame
    ghim trước sẽ đặt mắt tại g. Khoảng cách tới điểm ghim thật tại g cho biết đoạn trước đã trôi bao nhiêu pixel.
    """
    frames = sorted(pins)
    labels: dict[int, TrackResult] = {}
    arrival: dict[int, TrackResult] = {}
    for k, f0 in enumerate(frames):
        f1 = frames[k + 1] if k + 1 < len(frames) else n_frames
        seg = track_forward(get_gray, f0, min(f1 + 1, n_frames), pins[f0], **kw)
        for r in seg:
            if r.frame < f1:
                labels[r.frame] = r
            elif r.frame == f1 and f1 in pins:
                arrival[f1] = r
    return labels, arrival


def pin_jump(arrival: TrackResult, pin: dict[int, Point]) -> float:
    """Độ trôi (pixel, lớn nhất trên các điểm) của đoạn trước một frame ghim."""
    return max((math.dist(arrival.points[i], pin[i]) for i in pin if i in arrival.points), default=0.0)


def reduce_keyframes(positions: Sequence[dict[int, Point]], tol: float, forced: Iterable[int] = ()) -> list[int]:
    """Chọn ít keyframe nhất sao cho nội suy đường thẳng giữa chúng (như CVAT) lệch không quá `tol` pixel so với
    `positions` ở mọi frame và mọi điểm. Frame đầu, frame cuối và các frame trong `forced` luôn được giữ."""
    n = len(positions)
    must = sorted({0, n - 1, *[f for f in forced if 0 <= f < n]})
    keys = [0]
    for target in must[1:]:
        a = keys[-1]
        while a < target:
            best = a + 1
            for b in range(a + 1, target + 1):
                if _fits(positions, a, b, tol):
                    best = b
                else:
                    break
            keys.append(best)
            a = best
    return keys


def _fits(positions: Sequence[dict[int, Point]], a: int, b: int, tol: float) -> bool:
    for t in range(a + 1, b):
        w = (t - a) / (b - a)
        for i, pa in positions[a].items():
            pb, pt = positions[b][i], positions[t][i]
            x = pa[0] + w * (pb[0] - pa[0])
            y = pa[1] + w * (pb[1] - pa[1])
            if math.hypot(x - pt[0], y - pt[1]) > tol:
                return False
    return True
