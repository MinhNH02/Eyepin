"""So vùng mắt của nhãn đoán với nhãn đúng bằng các chỉ số kiểu mask: IoU (chỉ số chính), Dice, Boundary IoU, Precision, Recall.

Vùng mắt là đa giác khép kín qua 8 điểm của một mắt theo thứ tự id: khoé đầu → mí trên → khoé cuối → mí dưới (`geometry.EYES`).
Hai đa giác được lấy mẫu ở tâm các ô của một lưới mịn (mặc định 8×8 ô mỗi pixel), nên kết quả không lệch theo cách tô đa giác
và đủ mịn cho mắt rộng vài chục pixel.

- IoU = |đoán ∩ đúng| / |đoán ∪ đúng|; Dice = 2|đoán ∩ đúng| / (|đoán| + |đúng|) = 2·IoU / (1 + IoU) (cùng thông tin với IoU).
- Precision = |đoán ∩ đúng| / |đoán| (phần đoán nằm trên mắt thật); Recall = |đoán ∩ đúng| / |đúng| (phần mắt thật được phủ).
  Precision thấp: vùng đoán to quá hoặc lệch ra ngoài; Recall thấp: vùng đoán nhỏ quá hoặc hụt.
- Boundary IoU (Cheng và cộng sự, CVPR 2021): IoU của hai dải viền bên trong mỗi vùng, mỗi dải gồm các điểm cách viền vùng đó
  không quá `band` pixel. Dải rộng hơn nửa chiều cao mắt thì Boundary IoU bằng IoU, nên `band` phải nhỏ (mặc định 2,5% bề rộng
  mắt đúng, tối thiểu 1 px).

Mắt dẹt (rộng vài chục pixel, cao chỉ hơn chục pixel) nên IoU phạt lệch dọc nặng hơn lệch ngang nhiều lần. Mắt nhắm hẳn có diện
tích 0: so với mắt mở thì mọi chỉ số bằng 0, hai mắt cùng nhắm thì không so được (trả None). Chỉ dùng toạ độ, không đọc ảnh,
không dùng model.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .geometry import EyeSpec, Point

SUBSAMPLE = 8            # số điểm lấy mẫu mỗi chiều trong một pixel
BAND_FRAC = 0.025        # bề rộng dải viền của Boundary IoU theo bề rộng mắt đúng (mắt rộng 72 px: 1,8 px)
MIN_BAND_PX = 1.0


@dataclass(frozen=True)
class Overlap:
    iou: float
    dice: float
    boundary_iou: float
    precision: float
    recall: float
    band: float              # bề rộng dải viền đã dùng cho Boundary IoU (px)


def polygon(spec: EyeSpec, pts: dict[int, Point]) -> np.ndarray:
    """Đa giác vùng mắt: 8 điểm theo thứ tự id quanh viền."""
    return np.array([pts[i] for i in spec.ids], dtype=float)


def _box(poly: np.ndarray) -> tuple[float, float, float, float]:
    return float(poly[:, 0].min()), float(poly[:, 1].min()), float(poly[:, 0].max()), float(poly[:, 1].max())


def _grid(box, sub: int) -> tuple[np.ndarray, np.ndarray]:
    """Toạ độ tâm các cột và các hàng ô mẫu phủ khung `box` (nới 1 px mỗi phía, để viền mẫu luôn là ô ngoài vùng)."""
    x0, y0 = math.floor(box[0]) - 1, math.floor(box[1]) - 1
    x1, y1 = math.ceil(box[2]) + 1, math.ceil(box[3]) + 1
    return x0 + (np.arange((x1 - x0) * sub) + 0.5) / sub, y0 + (np.arange((y1 - y0) * sub) + 0.5) / sub


def _inside(xs: np.ndarray, ys: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Ô mẫu (hàng ys × cột xs) nằm trong đa giác, theo luật chẵn lẻ với tia nằm ngang; mỗi cạnh chỉ xét các hàng nó cắt."""
    inside = np.zeros((len(ys), len(xs)), dtype=bool)
    xj, yj = poly[-1]
    for xi, yi in poly:
        if yi != yj:
            rows = (yi > ys) != (yj > ys)
            if rows.any():
                x_cut = xi + (ys[rows] - yi) * (xj - xi) / (yj - yi)
                inside[rows] ^= xs[None, :] < x_cut[:, None]
        xj, yj = xi, yi
    return inside


def _band(mask: np.ndarray, band: float, sub: int) -> np.ndarray:
    """Dải viền bên trong vùng: ô của vùng cách ô ngoài vùng gần nhất không quá `band` pixel (khoảng cách Euclid giữa tâm ô,
    lệch so với khoảng cách tới viền thật không quá 1/sub pixel)."""
    dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return mask & (dist <= band * sub + 1e-6)


def area(spec: EyeSpec, pts: dict[int, Point], sub: int = SUBSAMPLE) -> float:
    """Diện tích vùng mắt (px²) theo cùng cách lấy mẫu như `compare`."""
    poly = polygon(spec, pts)
    return float(_inside(*_grid(_box(poly), sub), poly).sum()) / sub ** 2


def compare(spec: EyeSpec, pred: dict[int, Point], truth: dict[int, Point], *, band: float | None = None,
            sub: int = SUBSAMPLE) -> Overlap | None:
    """So vùng mắt đoán với vùng mắt đúng. Trả None khi cả hai vùng đều rỗng (hai mắt cùng nhắm hẳn)."""
    g, p = polygon(spec, truth), polygon(spec, pred)
    if band is None:
        band = max(MIN_BAND_PX, BAND_FRAC * math.dist(truth[spec.first], truth[spec.last]))
    gb, pb = _box(g), _box(p)
    if gb[2] < pb[0] or pb[2] < gb[0] or gb[3] < pb[1] or pb[3] < gb[1]:      # hai khung không chạm nhau: chung bằng 0
        if area(spec, truth, sub) == 0 and area(spec, pred, sub) == 0:
            return None
        return Overlap(0.0, 0.0, 0.0, 0.0, 0.0, band)
    xs, ys = _grid((min(gb[0], pb[0]), min(gb[1], pb[1]), max(gb[2], pb[2]), max(gb[3], pb[3])), sub)
    G, P = _inside(xs, ys, g), _inside(xs, ys, p)
    n_g, n_p = int(G.sum()), int(P.sum())
    if n_g == 0 and n_p == 0:
        return None
    inter, union = int((G & P).sum()), int((G | P).sum())
    Gb, Pb = _band(G, band, sub), _band(P, band, sub)
    b_union = int((Gb | Pb).sum())
    return Overlap(iou=inter / union,
                   dice=2 * inter / (n_g + n_p),
                   boundary_iou=int((Gb & Pb).sum()) / b_union if b_union else 0.0,
                   precision=inter / n_p if n_p else 0.0,
                   recall=inter / n_g if n_g else 0.0,
                   band=band)
