"""Hình học của hai mắt: suy 4 điểm còn lại từ 4 điểm ghim, và đoán khoé bị che.

Mọi hàm chỉ dùng toạ độ, không đọc ảnh, không dùng model. Tỉ lệ vị trí dọc trục khoé–khoé lấy từ guideline VF-50
v1.3 mục 3.3. Toạ độ là pixel của ảnh gốc, trục y hướng xuống.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]


@dataclass(frozen=True)
class EyeSpec:
    label: str
    first: int           # khoé đầu (x nhỏ nhất)
    last: int            # khoé cuối (x lớn nhất)
    up: int              # giữa mí trên
    lo: int              # giữa mí dưới
    up_mid: float        # vị trí dọc trục của điểm `up`
    lo_mid: float        # vị trí dọc trục của điểm `lo`
    derived: dict        # {id điểm suy ra: ("up" | "lo", vị trí dọc trục)}

    @property
    def ids(self) -> list[int]:
        return list(range(self.first, self.first + 8))

    @property
    def pins(self) -> tuple[int, int, int, int]:
        return (self.first, self.up, self.last, self.lo)

    @property
    def mid_ratio(self) -> float:
        """Vị trí dọc trục của trung điểm hai điểm giữa mí."""
        return (self.up_mid + self.lo_mid) / 2


MATTRAI = EyeSpec("mattrai", 14, 18, 16, 20, 0.48, 0.50,
                  {15: ("up", 0.21), 17: ("up", 0.76), 19: ("lo", 0.76), 21: ("lo", 0.24)})
MATPHAI = EyeSpec("matphai", 22, 26, 24, 28, 0.51, 0.52,
                  {23: ("up", 0.23), 25: ("up", 0.79), 27: ("lo", 0.78), 29: ("lo", 0.25)})
EYES = {"mattrai": MATTRAI, "matphai": MATPHAI}


def derive(spec: EyeSpec, pins: dict[int, Point]) -> dict[int, Point]:
    """Từ 4 điểm ghim suy ra đủ 8 điểm. Mỗi mí là một parabol qua hai khoé và điểm giữa mí."""
    p0, p1 = pins[spec.first], pins[spec.last]
    ax, ay = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(ax, ay)
    if length < 1e-6:
        raise ValueError(f"{spec.label}: hai khoé mắt trùng nhau")
    nx, ny = -ay / length, ax / length          # pháp tuyến đơn vị của trục khoé–khoé

    def lid(mid: Point) -> tuple[float, float]:
        mx, my = mid[0] - p0[0], mid[1] - p0[1]
        u = min(max((mx * ax + my * ay) / length ** 2, 0.05), 0.95)   # vị trí điểm giữa dọc trục
        return mx * nx + my * ny, u                                    # (độ cao so với trục, vị trí)

    lids = {"up": lid(pins[spec.up]), "lo": lid(pins[spec.lo])}
    out = {i: tuple(pins[i]) for i in spec.pins}
    for pid, (which, t) in spec.derived.items():
        h_mid, u_mid = lids[which]
        h = h_mid * t * (1 - t) / (u_mid * (1 - u_mid))
        out[pid] = (p0[0] + t * ax + h * nx, p0[1] + t * ay + h * ny)
    return out


def estimate_hidden_corner(spec: EyeSpec, visible: dict[int, Point], hidden: int) -> Point:
    """Đoán một khoé bị che từ 3 điểm ghim còn lại (khoé kia và hai điểm giữa mí).

    Dựa vào việc trung điểm của hai điểm giữa mí nằm ở khoảng `mid_ratio` dọc trục khoé–khoé. Quy tắc này giữ nguyên khi
    mắt bị co theo một hướng (trung điểm được bảo toàn qua phép biến đổi affine). Sai số đo trên 198 frame công khai:
    trung vị khoảng 3 px (13% bề rộng mắt), 90% dưới 4,4 px; chưa đo trên frame quay đầu.
    """
    if hidden not in (spec.first, spec.last):
        raise ValueError("chỉ đoán được hai khoé mắt")
    u = spec.mid_ratio
    up, lo = visible[spec.up], visible[spec.lo]
    m = ((up[0] + lo[0]) / 2, (up[1] + lo[1]) / 2)
    if hidden == spec.last:
        f = visible[spec.first]
        return (f[0] + (m[0] - f[0]) / u, f[1] + (m[1] - f[1]) / u)
    l = visible[spec.last]
    return ((m[0] - u * l[0]) / (1 - u), (m[1] - u * l[1]) / (1 - u))


def assign_roles(spec: EyeSpec, pts: list[Point]) -> dict[int, Point]:
    """Gán vai trò cho 4 điểm người dùng bấm (thứ tự tuỳ ý): hai khoé, giữa mí trên, giữa mí dưới.

    Hai khoé là cặp xa nhau nhất; khoé trái nhất (x nhỏ) là điểm đầu. Hai điểm còn lại: điểm nằm cao hơn so với trục
    khoé–khoé là giữa mí trên. Báo ValueError (tiếng Việt) khi 4 điểm không giống một con mắt.
    """
    if len(pts) != 4:
        raise ValueError("cần đúng 4 điểm cho mỗi mắt")
    pair = max(((i, j) for i in range(4) for j in range(i + 1, 4)), key=lambda ij: math.dist(pts[ij[0]], pts[ij[1]]))
    a, b = pts[pair[0]], pts[pair[1]]
    first, last = (a, b) if a[0] <= b[0] else (b, a)
    width = math.dist(first, last)
    if width < 8:
        raise ValueError("hai khoé mắt quá gần nhau, hãy bấm lại")
    others = [p for k, p in enumerate(pts) if k not in pair]
    ux, uy = (last[0] - first[0]) / width, (last[1] - first[1]) / width
    if abs(uy) > 0.7:                                   # lệch quá 45 độ so với phương ngang (bộ ảnh VF-50 chỉ từ -21 đến +5 độ)
        raise ValueError("trục hai khoé mắt quá dốc, hãy bấm lại")
    vx, vy = -uy, ux                                    # pháp tuyến hướng xuống (trục y của ảnh hướng xuống)
    proj = [((p[0] - first[0]) * ux + (p[1] - first[1]) * uy) / width for p in others]
    if not all(0.1 < t < 0.9 for t in proj):
        raise ValueError("điểm giữa mí nằm ngoài khoảng giữa hai khoé, hãy bấm lại")
    h = [(p[0] - first[0]) * vx + (p[1] - first[1]) * vy for p in others]
    upper, lower = (others[0], others[1]) if h[0] <= h[1] else (others[1], others[0])
    return {spec.first: first, spec.last: last, spec.up: upper, spec.lo: lower}


def validate_four(spec: EyeSpec, four: dict[int, Point]) -> None:
    """Kiểm 4 điểm ghim đã biết vai trò (không gán lại vai trò như `assign_roles`): báo ValueError tiếng Việt nếu không giống một con mắt."""
    first, last, up, lo = four[spec.first], four[spec.last], four[spec.up], four[spec.lo]
    if first[0] >= last[0]:
        raise ValueError("khoé đầu phải nằm bên trái khoé cuối")
    width = math.dist(first, last)
    if width < 8:
        raise ValueError("hai khoé mắt quá gần nhau")
    ux, uy = (last[0] - first[0]) / width, (last[1] - first[1]) / width
    if abs(uy) > 0.7:
        raise ValueError("trục hai khoé mắt quá dốc")
    for p in (up, lo):
        t = ((p[0] - first[0]) * ux + (p[1] - first[1]) * uy) / width
        if not 0.1 < t < 0.9:
            raise ValueError("điểm giữa mí nằm ngoài khoảng giữa hai khoé")
    h = [(p[0] - first[0]) * -uy + (p[1] - first[1]) * ux for p in (up, lo)]
    if h[0] > h[1]:
        raise ValueError("giữa mí trên đang nằm dưới giữa mí dưới")


def four_in_box(spec: EyeSpec, box: tuple[float, float, float, float]) -> dict[int, Point]:
    """Mắt mẫu nằm trong khung (x0, y0, x1, y1): hai khoé ở giữa hai cạnh bên, giữa mí trên chạm cạnh trên, giữa mí dưới chạm cạnh dưới,
    vị trí dọc trục theo tỉ lệ của guideline. Dùng khi người dùng kéo một khung để vẽ mắt (như vẽ skeleton bằng khung trong CVAT)."""
    x0, x1 = sorted((box[0], box[2]))
    y0, y1 = sorted((box[1], box[3]))
    w, cy = x1 - x0, (y0 + y1) / 2
    return {spec.first: (x0, cy), spec.last: (x1, cy), spec.up: (x0 + spec.up_mid * w, y0), spec.lo: (x0 + spec.lo_mid * w, y1)}


def split_eyes(pts: list[Point]) -> tuple[list[Point], list[Point]]:
    """Chia 8 điểm thành bốn điểm của mắt trái khung hình (x nhỏ) và bốn điểm của mắt phải."""
    if len(pts) != 8:
        raise ValueError("cần đúng 8 điểm (4 điểm mỗi mắt)")
    s = sorted(pts, key=lambda p: p[0])
    left, right = s[:4], s[4:]
    gap = min(p[0] for p in right) - max(p[0] for p in left)
    wide = max(max(p[0] for p in g) - min(p[0] for p in g) for g in (left, right))
    if gap < 0.3 * wide:                                # hai mắt thật cách nhau cỡ 1,5–3 lần bề rộng một mắt
        raise ValueError("hai mắt bị lẫn nhau: các điểm của hai mắt không tách rời nhau, hãy bấm lại")
    return left, right


HIDDEN_ERR_PX = 4.5        # vòng sai số hiển thị quanh khoé được ước lượng (90% dưới 4,4 px trên 198 frame công khai)


def assign_three(spec: EyeSpec, pts: list[Point]):
    """3 điểm bấm (một khoé và hai điểm giữa mí, thứ tự tuỳ ý) của mắt có một khoé bị che.

    Trả về (điểm đã biết {id: toạ độ}, id khoé bị che, toạ độ khoé ước lượng). ValueError nếu không giống một con mắt.
    """
    if len(pts) != 3:
        raise ValueError("cần đúng 3 điểm cho mắt bị che khoé")
    best = None
    for k in range(3):
        others = [p for j, p in enumerate(pts) if j != k]
        mid = ((others[0][0] + others[1][0]) / 2, (others[0][1] + others[1][1]) / 2)
        d = math.dist(pts[k], mid)
        if best is None or d > best[0]:
            best = (d, k, others, mid)
    d, k, others, mid = best
    corner = pts[k]
    if d < 6:
        raise ValueError("khoảng cách từ khoé tới giữa mắt quá nhỏ, hãy bấm lại")
    ux, uy = (mid[0] - corner[0]) / d, (mid[1] - corner[1]) / d
    if abs(uy) > 0.7:
        raise ValueError("trục mắt quá dốc, hãy bấm lại")
    along = [((p[0] - mid[0]) * ux + (p[1] - mid[1]) * uy) for p in others]
    if max(abs(a) for a in along) > 0.25 * d:
        raise ValueError("hai điểm giữa mí lệch nhau theo chiều ngang quá nhiều so với khoảng cách tới khoé, hãy bấm lại")
    upper, lower = (others[0], others[1]) if others[0][1] <= others[1][1] else (others[1], others[0])
    corner_is_first = corner[0] < mid[0]
    known = {spec.up: upper, spec.lo: lower}
    if corner_is_first:
        known[spec.first] = corner
        hidden = spec.last
    else:
        known[spec.last] = corner
        hidden = spec.first
    return known, hidden, estimate_hidden_corner(spec, known, hidden)


def hidden_neighbours(spec: EyeSpec, hidden: int) -> tuple[int, int]:
    """Hai điểm suy ra kề khoé bị che (sẽ cùng được coi là ước lượng)."""
    if hidden == spec.last:
        return tuple(i for i, (w, t) in spec.derived.items() if t > 0.7)
    return tuple(i for i, (w, t) in spec.derived.items() if t < 0.3)


def split_seven(pts: list[Point]):
    """7 điểm bấm: một mắt đủ 4 điểm và mắt kia 3 điểm. Thử cả hai cách chia theo x, chọn cách cả hai nhóm đều hợp lệ.

    Trả về {"full": (nhãn mắt, 4 điểm), "partial": (nhãn mắt, known, hidden, estimate)}.
    """
    if len(pts) != 7:
        raise ValueError("cần đúng 7 điểm (4 điểm mắt đủ + 3 điểm mắt bị che khoé)")
    s = sorted(pts, key=lambda p: p[0])
    options = []
    for n_left in (3, 4):
        left, right = s[:n_left], s[n_left:]
        gap = min(p[0] for p in right) - max(p[0] for p in left)
        try:
            if n_left == 3:
                options.append((gap, "matphai", right, "mattrai", left))
            else:
                options.append((gap, "mattrai", left, "matphai", right))
        except ValueError:
            pass
    errors = []
    for gap, full_label, full_pts, part_label, part_pts in sorted(options, key=lambda o: -o[0]):
        try:
            full = assign_roles(EYES[full_label], full_pts)
            known, hidden, est = assign_three(EYES[part_label], part_pts)
            return {"full": (full_label, full), "partial": (part_label, known, hidden, est)}
        except ValueError as err:
            errors.append(str(err))
    raise ValueError("không chia được thành một mắt đủ 4 điểm và một mắt 3 điểm: " + errors[0])
