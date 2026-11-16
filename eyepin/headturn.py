"""Phát hiện đoạn quay đầu từ nhãn hai mắt: hàm thuần toạ độ và độ khớp của bộ bám, không đọc ảnh, không dùng model.

Tín hiệu: khoảng cách hai mắt d(f) so với mốc (phân vị 90 của d tại các frame ghim đủ hai mắt). Khoảng cách co lại khi đầu quay.
Chỉ tin frame là ghim hoặc có độ khớp >= TRUST (bộ bám mất mắt thì d vô nghĩa). Số đo và các ngưỡng: design/2026-11-15-headturn-mvp-design.md
mục 2 và 8; ngưỡng chỉnh trên một clip (case 01), chưa kiểm trên dữ liệu khác.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from .geometry import EYES, Point

ENTER, LEAVE, MIN_LEN, TRUST, CONFIRM_WIDTH, MIN_PINS = 0.86, 0.90, 5, 0.85, 0.75, 3
LEVEL_MILD, LEVEL_MEDIUM = 0.20, 0.30        # mức co: dưới 0,20 nhẹ; dưới 0,30 vừa; còn lại mạnh (đề xuất, chưa có nguồn)


@dataclass(frozen=True)
class Turn:
    first: int
    last: int
    peak: int | None        # frame co mạnh nhất; None nếu đoạn chỉ gồm frame một mắt
    shrink: float | None    # 1 - min(d / mốc) trên frame tin được có đủ hai mắt; None như trên
    level: str              # "nhẹ" | "vừa" | "mạnh" | "một mắt"
    far_eye: str | None     # mắt xa: "mattrai" | "matphai" | None
    confirmed: int          # số frame ghim trong đoạn có bề rộng mắt hẹp / mắt rộng <= CONFIRM_WIDTH
    unsure: int             # frame trong đoạn không tin được hoặc không còn mắt nào
    one_eye: int            # frame trong đoạn chỉ còn một mắt
    need_pin: int           # frame "cần ghim" trong [first, last]

    def message(self, index: int) -> str:
        parts = ["Quay đầu", f"#{index}", f"frame {self.first}–{self.last}",
                 f"co {self.shrink * 100:.0f}% ({self.level})" if self.shrink is not None else "mất một mắt"]
        if self.far_eye:
            parts.append(f"mắt xa: {self.far_eye}")
        parts.append(f"xác nhận tại {self.confirmed} ghim" if self.confirmed else "chưa xác nhận (có thể do tiến/lùi)")
        if self.unsure:
            parts.append(f"{self.unsure} frame không chắc")
        if self.one_eye:
            parts.append(f"{self.one_eye} frame một mắt")
        if self.need_pin:
            parts.append(f"{self.need_pin} frame cần ghim")
        return "  ".join(parts)


@dataclass(frozen=True)
class TurnReport:
    status: str             # "ok" | "few_pins"
    baseline: float | None  # mốc (px); None khi few_pins
    turns: tuple[Turn, ...]
    untrusted: int          # số frame có đủ hai mắt nhưng không tin được, cả clip
    both_pins: int          # số frame ghim đủ hai mắt


def level_of(shrink: float | None) -> str:
    if shrink is None:
        return "một mắt"
    return "nhẹ" if shrink < LEVEL_MILD else "vừa" if shrink < LEVEL_MEDIUM else "mạnh"


class _Open:
    """Đoạn đang mở trong lúc duyệt các frame."""

    def __init__(self, first: int):
        self.first = first
        self.low = math.inf
        self.peak: int | None = None
        self.unsure = 0
        self.one_eye = 0
        self.missing = {label: 0 for label in EYES}


def detect(n_frames: int, points: dict[int, dict[int, Point]], scores: dict[int, dict[str, float]],
           keys: dict[str, set[int]], need_pin=(), skip=()) -> TurnReport:
    """`points[f]`: điểm không Outside của frame f (mắt vắng thì không có id nào của nó); `scores[f][nhãn mắt]`: độ khớp của bộ bám;
    `keys[nhãn mắt]`: tập frame ghim của mắt đó; `skip`: frame đã xoá."""
    skip = set(skip)
    frames = [f for f in range(n_frames) if f not in skip]
    centres: dict[int, dict[str, Point]] = {}
    for f in frames:
        pts = points.get(f) or {}
        c = {}
        for label, spec in EYES.items():
            got = [pts[i] for i in spec.ids if i in pts]
            if got:
                c[label] = (sum(p[0] for p in got) / len(got), sum(p[1] for p in got) / len(got))
        centres[f] = c

    def dist(f: int) -> float:
        a, b = centres[f]["mattrai"], centres[f]["matphai"]
        return math.dist(a, b)

    both = [f for f in frames if len(centres[f]) == 2 and f in keys["mattrai"] and f in keys["matphai"]]
    ds = sorted(dist(f) for f in both)
    baseline = ds[min(len(ds) - 1, int(0.9 * len(ds)))] if ds else 0.0
    if len(both) < MIN_PINS or baseline <= 0:
        return TurnReport("few_pins", None, (), 0, len(both))

    def trusted(f: int) -> bool:
        return all(f in keys[label] or scores.get(f, {}).get(label, 0.0) >= TRUST for label in EYES)

    need = set(need_pin)
    turns: list[Turn] = []
    untrusted = 0
    cur: _Open | None = None
    prev = frames[0] if frames else 0

    def close(last: int) -> None:
        if last - cur.first + 1 >= MIN_LEN:
            turns.append(_finish(cur, last, points, keys, need))

    for f in frames:
        c = centres[f]
        if len(c) == 1:                                    # một mắt: coi là đang quay đầu
            if cur is None:
                cur = _Open(f)
            cur.one_eye += 1
            cur.missing[next(l for l in EYES if l not in c)] += 1
        elif len(c) == 2 and trusted(f):
            r = dist(f) / baseline
            if cur is None:
                if r <= ENTER:
                    cur = _Open(f)
                    cur.low, cur.peak = r, f
            elif r >= LEAVE:
                close(prev)
                cur = None
            elif r < cur.low:
                cur.low, cur.peak = r, f
        else:                                              # không tin được, hoặc không còn mắt nào
            if len(c) == 2:
                untrusted += 1
            if cur is not None:
                cur.unsure += 1
        prev = f
    if cur is not None:
        close(prev)
    return TurnReport("ok", baseline, tuple(turns), untrusted, len(both))


def for_session(session) -> list[TurnReport]:
    """Báo cáo quay đầu của từng Layer (từng người) trong `session`, cùng thứ tự `session.layers`. Điểm Outside không tính vào nhãn."""
    out = []
    for i in range(len(session.layers)):
        with session.layer_ctx(i):
            keys = {label: set(session.eye_keyframes(label)) for label in EYES}
            points, scores = {}, {}
            for f, r in session.labels.items():
                outside = {pid for pid, kind in session.flags_at(f).items() if kind == "outside"}
                points[f] = {pid: p for pid, p in r.points.items() if pid not in outside}
                scores[f] = r.scores
            out.append(detect(session.n_frames, points, scores, keys, session.need_pin, session.deleted))
    return out


LIMITS = ("Giới hạn: ranh giới chỉ chính xác khi các frame ghim trong đoạn quay cách nhau không quá khoảng 20 frame; "
          "không phát hiện cúi/ngửa đầu; ngưỡng chỉnh trên một clip (case 01), chưa kiểm trên dữ liệu khác.")


def format_report(session, source: str) -> str:
    """Văn bản in ra của lệnh `turns`. Mọi số đi kèm số frame ghim, khoảng cách ghim trung vị và nguồn điểm ghim (spec mục 5)."""
    pins = sorted({f for L in session.layers for f in L.pins})
    gaps = [b - a for a, b in zip(pins, pins[1:])]
    spacing = f"khoảng cách ghim trung vị {statistics.median(gaps):g} frame" if gaps else "chưa tính được khoảng cách ghim"
    lines = [f"{session.title}: {session.n_frames} frame, {len(pins)} frame ghim, {spacing} "
             f"(nguồn điểm ghim: {source})"]
    for i, rep in enumerate(session.turns):
        ids = ", ".join(f"#{v}" for v in sorted(session.layers[i].obj_ids.values()))
        who = f"Người {i + 1} (đối tượng {ids})" if ids else f"Người {i + 1} (chưa có đối tượng)"
        if rep.status == "few_pins":
            lines.append(f"{who}:")
            lines.append(f"  Chưa đủ ghim để phát hiện (cần ít nhất {MIN_PINS} frame ghim đủ hai mắt, đang có {rep.both_pins}).")
            continue
        lines.append(f"{who}: mốc khoảng cách hai mắt {rep.baseline:.1f} px, {rep.untrusted}/{session.n_frames} frame không tin được")
        lines.extend(f"  {t.message(k)}" for k, t in enumerate(rep.turns, 1))
        if not rep.turns:
            lines.append("  Không có đoạn quay đầu.")
    lines.append(LIMITS)
    return "\n".join(lines)


def _finish(cur: _Open, last: int, points, keys, need: set[int]) -> Turn:
    """Xác nhận bằng bề rộng mắt tại các frame ghim đủ hai mắt trong đoạn, rồi đóng gói."""
    votes = {label: 0 for label in EYES}
    confirmed = 0
    for f in range(cur.first, last + 1):
        pts = points.get(f)
        if not pts or f not in keys["mattrai"] or f not in keys["matphai"]:
            continue
        if not all(i in pts for spec in EYES.values() for i in (spec.first, spec.last)):
            continue
        width = {label: math.dist(pts[spec.first], pts[spec.last]) for label, spec in EYES.items()}
        wide, narrow = max(width.values()), min(width, key=width.get)
        if wide > 0 and width[narrow] / wide <= CONFIRM_WIDTH:
            confirmed += 1
            votes[narrow] += 1
    if confirmed:
        far = max(votes, key=votes.get)
    elif any(cur.missing.values()):
        far = max(cur.missing, key=cur.missing.get)
    else:
        far = None
    shrink = None if math.isinf(cur.low) else 1.0 - cur.low
    return Turn(cur.first, last, cur.peak, shrink, level_of(shrink), far, confirmed, cur.unsure, cur.one_eye,
                sum(cur.first <= f <= last for f in need))
