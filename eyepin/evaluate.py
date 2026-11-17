"""Báo cáo độ chính xác tại frame ghim bị giấu (MVP 2 và 3, spec mục 8; chỉ số vùng: design/2026-11-17-interp-iou-research.md): bỏ một
frame ghim `g` của một mắt ra rồi xem ba cách đoán đặt mắt đó lệch bao nhiêu so với nhãn người đã ghim.

- đường thẳng CVAT: nội suy thẳng giữa ghim trước `a` và ghim sau `b` của chính mắt đó (cái CVAT làm nếu không có tool);
- bám tiến (tool): `Session.arrival[g]`, vị trí bộ bám tới được frame `g` từ ghim `a` (không dùng ghim `g`, nên là phép bỏ-một-ghim miễn phí);
- hai chiều chọn theo độ khớp (MVP 3, chỉ để so sánh): thêm phép bám lùi từ ghim `b`; phía nào khớp ≥ MATCH_FLAG tại `g` mà phía kia không
  thì lấy phía đó, còn lại trộn theo thời gian. Nhãn của tool không đổi: vẫn chỉ bám tiến (quy tắc đã chốt).

Chỉ số chính là IoU của vùng mắt (đa giác qua 8 điểm, `overlap.py`); phụ là Dice, Boundary IoU, Precision/Recall và sai số trung bình trên
4 điểm ghim (px). Chỉ đo tại frame ghim bị giấu, không phải mọi frame. Điểm ghim của người đặt (nhất là ghim thô, khoảng ±2 px) có sai số
riêng và nằm trong các số này. Không đổi nhãn nào của phiên.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from . import overlap
from .geometry import EYES, EyeSpec, Point
from .scan import EAR_CLOSED, eye_ear
from .session import MATCH_FLAG
from .tracking import track_backward

METHODS = ("đường thẳng CVAT", "bám tiến (tool)", "hai chiều chọn theo độ khớp")
TIGHT, LOOSE = 5.0, 10.0            # ngưỡng "đạt" của sai số điểm: phần trăm bề rộng mắt
IOU_OK, IOU_GOOD = 0.5, 0.75        # ngưỡng "đạt" của IoU (như AP50 / AP75 của COCO); 0,75 sát trần nhiễu của ghim thô ±2 px
MIN_SAMPLES = 5                     # nhóm ít hơn thế thì không in tỉ lệ
EXACT_PX = 1e-6                     # điểm ghim trùng khít bám tiến: sai số đúng bằng 0
NUDGE_PX = 1.0                      # mốc đọc IoU: chính nhãn đúng dời chừng này pixel vuông góc trục mắt
GROUP_ALL = "tất cả (không tính chớp mắt)"
GROUP_IN = "trong đoạn quay đầu"
GROUP_OUT = "ngoài đoạn quay đầu"
GROUP_BLINK = "chớp mắt (mắt nhắm)"


@dataclass(frozen=True)
class Sample:
    layer: int
    label: str
    frame: int
    prev: int
    next: int
    width: float                    # bề rộng mắt tại frame ghim (px)
    errors: dict                    # tên cách đoán -> sai số trung bình trên các điểm ghim (px)
    in_turn: bool
    closed: bool
    overlaps: dict = field(default_factory=dict)   # tên cách đoán -> overlap.Overlap (None: hai vùng cùng rỗng); rỗng khi nhãn đúng có điểm ước lượng/Outside
    ref_iou: float | None = None    # IoU của chính nhãn đúng khi dời NUDGE_PX vuông góc trục mắt: mốc để đọc IoU (mắt nhắm: None)


@dataclass
class Evaluation:
    samples: list
    untestable: int                 # frame ghim của một mắt không có ghim kề cả hai phía
    excluded_manual: int            # ghim không phải bốn điểm người đặt (trùng khít bám tiến)
    skipped: int                    # không đủ điểm để tính
    spacing: float | None           # khoảng cách trung vị giữa hai ghim liên tiếp của cùng một mắt
    pins: int                       # số frame ghim (mọi người)
    no_region: int = 0              # mẫu không tính IoU vì nhãn đúng có điểm ước lượng hoặc Outside


@dataclass(frozen=True)
class Stats:
    n: int
    mean: float
    median: float
    p90: float
    mean_pct: float
    ok5: int
    ok10: int


@dataclass(frozen=True)
class RegionStats:
    n: int
    iou_mean: float
    iou_median: float
    iou_p10: float                  # 10% mẫu tệ nhất có IoU không quá mức này
    ok: int                         # IoU >= IOU_OK
    good: int                       # IoU >= IOU_GOOD
    dice: float
    boundary_iou: float
    precision: float
    recall: float


def mean_error(pred: dict[int, Point], truth: dict[int, Point], ids) -> float | None:
    ids = list(ids)
    return statistics.fmean(math.dist(pred[i], truth[i]) for i in ids) if ids else None


def _lerp(pa: dict[int, Point], pb: dict[int, Point], w: float, ids) -> dict[int, Point]:
    return {i: (pa[i][0] + w * (pb[i][0] - pa[i][0]), pa[i][1] + w * (pb[i][1] - pa[i][1])) for i in ids}


def choose(fwd: dict[int, Point], cf: float, back: dict[int, Point], cb: float, w: float, tau: float = MATCH_FLAG) -> dict[int, Point]:
    """MVP 3: chỉ một phía khớp >= tau thì lấy phía đó; cả hai cùng khớp hoặc cùng kém thì trộn theo thời gian (1-w)·tiến + w·lùi."""
    if cf >= tau > cb:
        return dict(fwd)
    if cb >= tau > cf:
        return dict(back)
    return _lerp(fwd, back, w, fwd)


def _two_way(session, spec: EyeSpec, g: int, b: int, fwd: dict[int, Point], cf: float, w: float) -> dict[int, Point]:
    back = track_backward(session.gray, b, g, {i: session.pins[b][i] for i in spec.ids})[-1]
    return choose(fwd, cf, {i: back.points[i] for i in spec.ids}, back.scores[spec.label], w)


def _nudged(spec: EyeSpec, pts: dict[int, Point], d: float) -> dict[int, Point]:
    (x0, y0), (x1, y1) = pts[spec.first], pts[spec.last]
    length = math.hypot(x1 - x0, y1 - y0)
    nx, ny = -(y1 - y0) / length, (x1 - x0) / length
    return {i: (x + d * nx, y + d * ny) for i, (x, y) in pts.items()}


def evaluate(session) -> Evaluation:
    samples: list[Sample] = []
    untestable = excluded = skipped = no_region = 0
    gaps: list[int] = []
    every_pin: set[int] = set()
    for li in range(len(session.layers)):
        with session.layer_ctx(li):
            turns = session.turns[li].turns if li < len(session.turns) else ()
            every_pin |= set(session.pins)
            for label, spec in EYES.items():
                keys = session.eye_keyframes(label)
                gaps += [b - a for a, b in zip(keys, keys[1:])]
                for k, g in enumerate(keys):
                    if k == 0 or k == len(keys) - 1:
                        untestable += 1
                        continue
                    a, b = keys[k - 1], keys[k + 1]
                    arr, truth = session.arrival.get(g), session.pins[g]
                    if arr is None or not all(i in arr.points for i in spec.ids):
                        skipped += 1
                        continue
                    if sum(math.dist(arr.points[i], truth[i]) < EXACT_PX for i in spec.pins) >= 2:
                        excluded += 1                    # ghim tạo bằng phím K hoặc chỉ kéo một điểm, không phải bốn điểm người đặt
                        continue
                    left_out = set(session.estimates.get(g, ())) | {i for i, kind in session.flags.get(g, {}).items() if kind == "outside"}
                    ids = [i for i in spec.pins if i not in left_out]
                    width = math.dist(truth[spec.first], truth[spec.last])
                    if not ids or width <= 0:
                        skipped += 1
                        continue
                    w = (g - a) / (b - a)
                    fwd = {i: arr.points[i] for i in spec.ids}
                    preds = {METHODS[0]: _lerp(session.pins[a], session.pins[b], w, spec.ids),
                             METHODS[1]: fwd,
                             METHODS[2]: _two_way(session, spec, g, b, fwd, arr.scores.get(label, 0.0), w)}
                    eight = {i: truth[i] for i in spec.ids}
                    overlaps, ref = {}, None
                    if left_out & set(spec.ids):
                        no_region += 1                   # vùng đúng có điểm đoán (khoé ước lượng) hoặc điểm Outside: không đo vùng
                    else:
                        overlaps = {m: overlap.compare(spec, p, eight) for m, p in preds.items()}
                        r = overlap.compare(spec, _nudged(spec, eight, NUDGE_PX), eight)
                        ref = r.iou if r is not None and overlap.area(spec, eight) > 0 else None
                    ear = eye_ear(spec, truth)
                    samples.append(Sample(li, label, g, a, b, width, {m: mean_error(p, truth, ids) for m, p in preds.items()},
                                          any(t.first <= g <= t.last for t in turns), ear is not None and ear < EAR_CLOSED,
                                          overlaps, ref))
    return Evaluation(samples, untestable, excluded, skipped, statistics.median(gaps) if gaps else None, len(every_pin), no_region)


def groups(ev: Evaluation) -> list[tuple[str, list[Sample]]]:
    open_eyes = [s for s in ev.samples if not s.closed]
    return [(GROUP_ALL, open_eyes), (GROUP_IN, [s for s in open_eyes if s.in_turn]), (GROUP_OUT, [s for s in open_eyes if not s.in_turn]),
            (GROUP_BLINK, [s for s in ev.samples if s.closed])]


def stats(errors_px: list[float], widths: list[float]) -> Stats | None:
    if not errors_px:
        return None
    ordered = sorted(errors_px)
    pct = [100.0 * e / w for e, w in zip(errors_px, widths)]
    n = len(ordered)
    return Stats(n, statistics.fmean(ordered), statistics.median(ordered), ordered[min(n - 1, math.ceil(0.9 * n) - 1)],
                 statistics.fmean(pct), sum(p <= TIGHT + 1e-9 for p in pct), sum(p <= LOOSE + 1e-9 for p in pct))


def region_stats(overlaps: list) -> RegionStats | None:
    ov = [o for o in overlaps if o is not None]
    if not ov:
        return None
    ious = sorted(o.iou for o in ov)
    n = len(ious)
    return RegionStats(n, statistics.fmean(ious), statistics.median(ious), ious[max(0, math.ceil(0.1 * n) - 1)],
                       sum(i >= IOU_OK - 1e-9 for i in ious), sum(i >= IOU_GOOD - 1e-9 for i in ious),
                       statistics.fmean(o.dice for o in ov), statistics.fmean(o.boundary_iou for o in ov),
                       statistics.fmean(o.precision for o in ov), statistics.fmean(o.recall for o in ov))


def _rate(k: int, n: int) -> str:
    return f"{k}/{n} ({100 * k / n:.0f}%)"


def format_table(ev: Evaluation, source: str) -> str:
    spacing = f"khoảng cách ghim trung vị {ev.spacing:g} frame" if ev.spacing is not None else "chưa tính được khoảng cách ghim"
    pad = " " * 30
    lines = [f"Độ chính xác tại frame ghim bị giấu (nguồn điểm ghim: {source})",
             f"{ev.pins} frame ghim, {spacing}; {len(ev.samples)} mẫu (một mẫu = một mắt tại một frame ghim, đo khi bỏ ghim đó ra)",
             f"Chỉ số chính: IoU vùng mắt (đa giác qua 8 điểm). Phụ: Dice (= 2·IoU/(1+IoU)), Boundary IoU (dải viền "
             f"{100 * overlap.BAND_FRAC:g}% bề rộng mắt), Precision/Recall (thấp: vùng đoán to quá / hụt), lệch điểm ghim (px)."]
    if not ev.samples:
        lines.append("Chưa có mẫu nào: cần ít nhất 3 frame ghim của cùng một mắt (ghim đầu, ghim giữa để kiểm, ghim cuối).")
    for name, group in groups(ev) if ev.samples else []:
        refs = [s.ref_iou for s in group if s.ref_iou is not None]
        mark = f"; mốc: chính nhãn đúng dời {NUDGE_PX:g} px vuông góc trục mắt còn IoU {statistics.fmean(refs):.2f}" if refs else ""
        lines.append(f"Nhóm {name}: {len(group)} mẫu{mark}")
        if not group:
            lines.append("  không có mẫu")
            continue
        for m in [m for m in METHODS if all(m in s.errors for s in group)]:
            rs = region_stats([s.overlaps.get(m) for s in group if s.overlaps])
            if rs is None:
                lines.append(f"  {m:<28s}IoU không tính được (nhãn đúng có điểm ước lượng/Outside, hoặc mắt nhắm hẳn)")
            else:
                rate = (f"≥{IOU_OK:g} {_rate(rs.ok, rs.n)}  ≥{IOU_GOOD:g} {_rate(rs.good, rs.n)}" if rs.n >= MIN_SAMPLES
                        else f"chưa đủ mẫu ({rs.n} mẫu)")
                lines.append(f"  {m:<28s}IoU tb {rs.iou_mean:.2f}  trung vị {rs.iou_median:.2f}  p10 {rs.iou_p10:.2f}  {rate}")
                lines.append(f"{pad}Dice {rs.dice:.2f}  Boundary IoU {rs.boundary_iou:.2f}  Precision {rs.precision:.2f}  Recall {rs.recall:.2f}")
            st = stats([s.errors[m] for s in group], [s.width for s in group])
            rate = (f"≤5% {_rate(st.ok5, st.n)}  ≤10% {_rate(st.ok10, st.n)}" if st.n >= MIN_SAMPLES else f"chưa đủ mẫu ({st.n} mẫu)")
            lines.append(f"{pad}lệch điểm ghim tb {st.mean:5.1f} px ({st.mean_pct:4.1f}%)  trung vị {st.median:5.1f}  p90 {st.p90:5.1f}  {rate}")
    lines.append(f"{ev.untestable} ghim không kiểm được (ghim đầu hoặc cuối của một mắt, thiếu ghim kề một phía); "
                 f"{ev.excluded_manual} ghim không phải bốn điểm người đặt (phím K, kéo một điểm) bị loại; {ev.skipped} ghim thiếu điểm để tính; "
                 f"{ev.no_region} mẫu không tính IoU (nhãn đúng có khoé ước lượng hoặc điểm Outside).")
    lines.append("Chú ý: đo tại frame ghim bị giấu, không phải mọi frame; các frame ở giữa hai ghim có thể kém hơn. Sai số của chính điểm ghim "
                 "(ghim thô khoảng ±2 px, cỡ 3% bề rộng mắt) nằm trong các số trên, nên ngưỡng 5% sát nhiễu đó. Mắt dẹt nên IoU rất nhạy "
                 f"với lệch dọc (xem mốc ở đầu mỗi nhóm); trên case 01, hai lần ghim thô cùng một mắt chỉ đạt IoU khoảng 0.73, nên tỉ lệ "
                 f"≥{IOU_GOOD:g} bị nhiễu của điểm ghim chặn. Cột hai chiều chỉ để so sánh: nhãn của tool vẫn chỉ bám tiến.")
    return "\n".join(lines)
