"""Báo cáo độ chính xác tại frame ghim bị giấu (MVP 2, spec mục 8): bỏ một frame ghim `g` của một mắt ra rồi xem hai cách đoán đặt bốn điểm ghim
của mắt đó lệch bao nhiêu so với điểm người đã ghim.

- đường thẳng CVAT: nội suy thẳng giữa ghim trước `a` và ghim sau `b` của chính mắt đó (cái CVAT làm nếu không có tool);
- bám tiến (tool): `Session.arrival[g]`, vị trí bộ bám tới được frame `g` từ ghim `a` (không dùng ghim `g`, nên là phép bỏ-một-ghim miễn phí).

Chỉ đo tại frame ghim bị giấu, không phải mọi frame. Điểm ghim của người đặt (nhất là ghim thô, khoảng ±2 px) có sai số riêng và nằm trong các số này.
Không đổi nhãn nào của phiên.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from .geometry import EYES, Point
from .scan import EAR_CLOSED, eye_ear

METHODS = ("đường thẳng CVAT", "bám tiến (tool)")
TIGHT, LOOSE = 5.0, 10.0            # ngưỡng "đạt": phần trăm bề rộng mắt
MIN_SAMPLES = 5                     # nhóm ít hơn thế thì không in tỉ lệ
EXACT_PX = 1e-6                     # điểm ghim trùng khít bám tiến: sai số đúng bằng 0
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


@dataclass
class Evaluation:
    samples: list
    untestable: int                 # frame ghim của một mắt không có ghim kề cả hai phía
    excluded_manual: int            # ghim không phải bốn điểm người đặt (trùng khít bám tiến)
    skipped: int                    # không đủ điểm để tính
    spacing: float | None           # khoảng cách trung vị giữa hai ghim liên tiếp của cùng một mắt
    pins: int                       # số frame ghim (mọi người)


@dataclass(frozen=True)
class Stats:
    n: int
    mean: float
    median: float
    p90: float
    mean_pct: float
    ok5: int
    ok10: int


def mean_error(pred: dict[int, Point], truth: dict[int, Point], ids) -> float | None:
    ids = list(ids)
    return statistics.fmean(math.dist(pred[i], truth[i]) for i in ids) if ids else None


def evaluate(session) -> Evaluation:
    samples: list[Sample] = []
    untestable = excluded = skipped = 0
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
                    if arr is None or not all(i in arr.points for i in spec.pins):
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
                    pa, pb = session.pins[a], session.pins[b]
                    line = {i: (pa[i][0] + w * (pb[i][0] - pa[i][0]), pa[i][1] + w * (pb[i][1] - pa[i][1])) for i in spec.pins}
                    ear = eye_ear(spec, truth)
                    samples.append(Sample(li, label, g, a, b, width,
                                          {METHODS[0]: mean_error(line, truth, ids), METHODS[1]: mean_error(arr.points, truth, ids)},
                                          any(t.first <= g <= t.last for t in turns), ear is not None and ear < EAR_CLOSED))
    return Evaluation(samples, untestable, excluded, skipped, statistics.median(gaps) if gaps else None, len(every_pin))


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


def format_table(ev: Evaluation, source: str) -> str:
    spacing = f"khoảng cách ghim trung vị {ev.spacing:g} frame" if ev.spacing is not None else "chưa tính được khoảng cách ghim"
    lines = [f"Độ chính xác tại frame ghim bị giấu (nguồn điểm ghim: {source})",
             f"{ev.pins} frame ghim, {spacing}; {len(ev.samples)} mẫu (một mẫu = một mắt tại một frame ghim, đo khi bỏ ghim đó ra)"]
    if not ev.samples:
        lines.append("Chưa có mẫu nào: cần ít nhất 3 frame ghim của cùng một mắt (ghim đầu, ghim giữa để kiểm, ghim cuối).")
    for name, group in groups(ev) if ev.samples else []:
        lines.append(f"Nhóm {name}: {len(group)} mẫu")
        if not group:
            lines.append("  không có mẫu")
            continue
        for m in METHODS:
            st = stats([s.errors[m] for s in group], [s.width for s in group])
            rate = (f"≤5% {st.ok5}/{st.n} ({100 * st.ok5 / st.n:.0f}%)  ≤10% {st.ok10}/{st.n} ({100 * st.ok10 / st.n:.0f}%)"
                    if st.n >= MIN_SAMPLES else f"chưa đủ mẫu ({st.n} mẫu)")
            lines.append(f"  {m:<18s} tb {st.mean:5.1f} px ({st.mean_pct:4.1f}%)  trung vị {st.median:5.1f}  p90 {st.p90:5.1f}  {rate}")
    lines.append(f"{ev.untestable} ghim không kiểm được (ghim đầu hoặc cuối của một mắt, thiếu ghim kề một phía); "
                 f"{ev.excluded_manual} ghim không phải bốn điểm người đặt (phím K, kéo một điểm) bị loại; {ev.skipped} ghim thiếu điểm để tính.")
    lines.append("Chú ý: đo tại frame ghim bị giấu, không phải mọi frame; các frame ở giữa hai ghim có thể kém hơn. Sai số của chính điểm ghim "
                 "(ghim thô khoảng ±2 px, cỡ 3% bề rộng mắt) nằm trong các số trên, nên ngưỡng 5% sát nhiễu đó.")
    return "\n".join(lines)
