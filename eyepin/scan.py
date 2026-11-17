"""Quét nhãn mắt có sẵn từ frame đầu tới frame cuối và liệt kê các frame cần chú ý.

Chỉ dùng toạ độ trong file nhãn (không đọc ảnh). Kết quả là danh sách `Finding`, mỗi cái ứng với một đoạn frame liên tiếp có
cùng một vấn đề; `frame` là frame đầu đoạn vì đó là chỗ nên ghim hoặc sửa (ghim frame N chỉ làm đổi các frame sau N).

Luật theo guideline VF-50 v1.3 mục 3.3, 4.1 và 6.9:
  đỏ (sai luật chắc chắn): thứ tự khoé, mí trên nằm dưới mí dưới, đường viền bắt chéo, điểm ngoài khung hình mà không Outside
  vàng (đáng nghi): điểm nhảy quá ngưỡng so với frame trước, keyframe thiếu, nhãn đứng yên nhiều frame,
        và ba luật độ mở mắt (EAR, Soukupová và Čech 2016): mắt gần nhắm, mắt mở quá rộng, độ mở nhảy đột ngột.
        Luật EAR cần đủ 8 điểm của mắt. Ngưỡng EAR chưa chỉnh theo dữ liệu thật (xem EAR_*), chỉ là điểm xuất phát.
Luật về trạng thái Occluded/Outside chưa được dùng vì chưa rõ tài liệu nào dùng để chấm.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .cvatxml import Annotations, EyeKey
from .geometry import EYES, EyeSpec
from .preview import position_at

EPS = 0.5          # dung sai làm tròn toạ độ (px)
EAR_CLOSED = 0.08  # dưới mức này coi như mắt khép: nên kiểm hai mí có bám đúng mí đã khép không
EAR_WIDE = 0.50    # trên mức này mắt mở rộng bất thường: hai mí có thể đặt sai
EAR_JUMP = 0.15    # độ mở đổi quá mức này giữa hai frame liền kề (chớp mắt thật cũng có thể gây ra)


@dataclass
class Finding:
    level: str                 # "red" | "yellow"
    code: str
    label: str                 # mattrai | matphai
    frame: int                 # frame đầu đoạn
    last: int                  # frame cuối đoạn
    points: tuple[int, ...]
    message: str
    value: float | None = None
    frames: list[int] = field(default_factory=list, repr=False)


def eye_at(ann: Annotations, label: str, frame: int) -> EyeKey | None:
    """Nhãn mắt tại frame: shape nếu có, không thì vị trí CVAT sẽ hiển thị từ track."""
    spec = EYES[label]
    shape = ann.shapes.get(label, {}).get(frame)
    if shape is not None:
        return shape
    best = None
    for tr in ann.tracks.get(label, []):
        k = position_at(tr.keys, frame, spec.ids)
        if k is not None:
            best = k
    return best


def _drawn(key: EyeKey, spec: EyeSpec) -> dict[int, tuple[float, float]]:
    if key.outside:
        return {}
    return {i: key.points[i].xy for i in spec.ids if i in key.points and not key.points[i].outside}


def _signed(first, last, p) -> float:
    ax, ay = last[0] - first[0], last[1] - first[1]
    n = math.hypot(ax, ay) or 1e-9
    return (ax * (p[1] - first[1]) - ay * (p[0] - first[0])) / n


def _dist_to_line(a, b, p) -> float:
    """Khoảng cách có dấu (px) từ p tới đường thẳng qua a, b; 0 nếu a trùng b."""
    n = math.hypot(b[0] - a[0], b[1] - a[1])
    if n < 1e-9:
        return 0.0
    return ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / n


def _cross(p1, p2, p3, p4, tol: float = 0.3) -> bool:
    """Hai đoạn cắt nhau thật: mỗi đầu mút phải nằm cách đường kia hơn `tol` px và hai phía trái dấu.
    Nhờ dung sai, mắt nhắm (hai mí trùng nhau, các điểm gần thẳng hàng) không bị báo là bắt chéo."""
    d1, d2 = _dist_to_line(p3, p4, p1), _dist_to_line(p3, p4, p2)
    d3, d4 = _dist_to_line(p1, p2, p3), _dist_to_line(p1, p2, p4)
    return min(abs(d1), abs(d2), abs(d3), abs(d4)) > tol and d1 * d2 < 0 and d3 * d4 < 0


_PAIRS = {"mattrai": [(15, 21), (16, 20), (17, 19)], "matphai": [(23, 29), (24, 28), (25, 27)]}


def eye_ear(spec: EyeSpec, pts: dict[int, tuple[float, float]]) -> float | None:
    """Tỉ lệ độ mở mắt (EAR): trung bình khoảng cách ba cặp mí trên-dưới chia bề rộng hai khoé. None nếu thiếu điểm hoặc hai khoé trùng nhau."""
    pairs = _PAIRS[spec.label]
    need = {spec.first, spec.last, *[i for p in pairs for i in p]}
    if not need <= set(pts):
        return None
    width = math.dist(pts[spec.first], pts[spec.last])
    if width < 1e-6:
        return None
    return sum(math.dist(pts[u], pts[l]) for u, l in pairs) / len(pairs) / width


def _rule_findings(key: EyeKey, spec: EyeSpec, width: float | None, height: float | None):
    """Các vấn đề đỏ của một frame: danh sách (mã, các điểm, thông điệp, giá trị)."""
    d = _drawn(key, spec)
    out = []
    if len(d) == 8:
        xs = {i: p[0] for i, p in d.items()}
        bad = []
        if xs[spec.first] > min(xs.values()) + EPS:
            bad.append(spec.first)
        if xs[spec.last] < max(xs.values()) - EPS:
            bad.append(spec.last)
        if bad:
            what = " và ".join(f"{i} không phải điểm {'trái' if i == spec.first else 'phải'} nhất" for i in bad)
            out.append(("corner_order", tuple(bad), f"khoé mắt sai vị trí: {what}", None))
        dist = {i: _signed(d[spec.first], d[spec.last], p) for i, p in d.items()}
        pairs = _PAIRS[spec.label]
        votes = sum((dist[u] > dist[l]) - (dist[u] < dist[l]) for u, l in pairs)
        if votes:
            s = 1 if votes > 0 else -1
            for u, l in pairs:
                if s * (dist[u] - dist[l]) < -EPS:
                    out.append(("lid_order", (u, l), f"mí trên {u} nằm dưới mí dưới {l}", abs(dist[u] - dist[l])))
        ids = spec.ids
        edges = [(ids[k], ids[(k + 1) % 8]) for k in range(8)]
        hit = set()
        for a in range(8):
            for b in range(a + 2, 8):
                if a == 0 and b == 7:
                    continue
                e1, e2 = edges[a], edges[b]
                if _cross(d[e1[0]], d[e1[1]], d[e2[0]], d[e2[1]]):
                    hit.update((*e1, *e2))
        if hit:
            out.append(("crossing", tuple(sorted(hit)), "đường viền bắt chéo", None))
    if width is not None and height is not None:
        bad = tuple(i for i, (x, y) in d.items() if not (0 <= x <= width and 0 <= y <= height))
        if bad:
            out.append(("out_of_frame", bad, f"điểm {', '.join(map(str, bad))} nằm ngoài khung hình nhưng không đánh Outside", None))
    return out


def scan(ann: Annotations, n_frames: int, *, width: float | None = None, height: float | None = None,
         jump_px: float = 15.0, still_frames: int = 30) -> list[Finding]:
    raw: list[tuple] = []        # (level, code, label, frame, points, message, value)
    for label, spec in EYES.items():
        prev_pts = None
        prev_ear = None
        still_run = 0
        still_start = 0
        for f in range(n_frames):
            key = eye_at(ann, label, f)
            if key is None:
                if still_run and still_run + 1 >= still_frames:      # mắt vắng giữa chừng: báo chuỗi đứng yên trước khi đặt lại
                    raw.append(("yellow", "still", label, still_start, tuple(spec.ids),
                                f"nhãn đứng yên {still_run + 1} frame liền", float(still_run + 1)))
                prev_pts, prev_ear, still_run = None, None, 0
                continue
            for code, pts, msg, val in _rule_findings(key, spec, width, height):
                raw.append(("red", code, label, f, pts, msg, val))
            counted = [i for i in spec.ids if i in key.points and key.points[i].keyframe]
            is_pinned_frame = f in ann.shapes.get(label, {}) or any(f in tr.keys and tr.keys[f].keyframe for tr in ann.tracks.get(label, []))
            if is_pinned_frame and 0 < len(counted) < 8 and f not in ann.shapes.get(label, {}):
                missing = tuple(i for i in spec.ids if i not in counted)
                raw.append(("yellow", "partial_keyframe", label, f, missing,
                            f"keyframe thiếu: mới ghim {len(counted)}/8 điểm", float(len(counted))))
            pts_now = {i: key.points[i].xy for i in spec.ids if i in key.points}
            ear = eye_ear(spec, _drawn(key, spec)) if len(_drawn(key, spec)) == 8 else None
            if ear is not None:
                if ear < EAR_CLOSED:
                    raw.append(("yellow", "ear_closed", label, f, tuple(spec.ids), f"mắt gần nhắm (EAR {ear:.2f}): kiểm tra hai mí có bám đúng mí đã khép không", ear))
                elif ear > EAR_WIDE:
                    raw.append(("yellow", "ear_wide", label, f, tuple(spec.ids), f"mắt mở rộng bất thường (EAR {ear:.2f}): hai mí có thể đặt sai", ear))
                if prev_ear is not None and abs(ear - prev_ear) > EAR_JUMP:
                    raw.append(("yellow", "ear_jump", label, f, tuple(spec.ids),
                                f"độ mở mắt đổi đột ngột (EAR {prev_ear:.2f} → {ear:.2f}): chớp mắt thật hay nhãn sai?", abs(ear - prev_ear)))
            prev_ear = ear
            if prev_pts is not None and len(pts_now) == 8:
                jumped = [(i, math.dist(pts_now[i], prev_pts[i])) for i in spec.ids if i in prev_pts]
                big = [(i, v) for i, v in jumped if v > jump_px]
                if big:
                    worst = max(v for _, v in big)
                    raw.append(("yellow", "jump", label, f, tuple(i for i, _ in big),
                                f"điểm {', '.join(str(i) for i, _ in big)} nhảy {worst:.1f} px so với frame trước", worst))
            if prev_pts is not None and pts_now and all(
                    i in prev_pts and math.dist(pts_now[i], prev_pts[i]) < 1e-6 for i in pts_now):
                still_run += 1
                if still_run == 1:
                    still_start = f - 1
            else:
                if still_run + 1 >= still_frames:
                    raw.append(("yellow", "still", label, still_start, tuple(spec.ids),
                                f"nhãn đứng yên {still_run + 1} frame liền", float(still_run + 1)))
                still_run = 0
            prev_pts = pts_now if pts_now else None
        if still_run + 1 >= still_frames:
            raw.append(("yellow", "still", label, still_start, tuple(spec.ids), f"nhãn đứng yên {still_run + 1} frame liền",
                        float(still_run + 1)))
    return _merge(raw)


def _merge(raw) -> list[Finding]:
    """Gộp các frame liên tiếp có cùng (mã, mắt, điểm) thành một đoạn; sắp xếp đỏ trước, theo frame."""
    raw = sorted(raw, key=lambda r: (r[1], r[2], r[4], r[3]))
    out: list[Finding] = []
    for level, code, label, f, pts, msg, val in raw:
        if code == "still":                   # đã là một đoạn
            out.append(Finding(level, code, label, f, f + int(val) - 1, pts, msg, val))
            continue
        last = out[-1] if out else None
        if last and (last.code, last.label, last.points) == (code, label, pts) and f - last.last == 1 and code not in ("jump", "ear_jump"):
            last.last = f
            last.frames.append(f)
            last.value = max(last.value or 0, val or 0) or None
            continue
        out.append(Finding(level, code, label, f, f, pts, msg, val, [f]))
    out.sort(key=lambda x: (x.level != "red", x.frame, x.label))
    return out
