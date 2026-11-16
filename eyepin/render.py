"""Vẽ khung nhìn của EyePin thành ảnh (numpy BGR). Giao diện Tkinter chỉ hiển thị ảnh này và đổi toạ độ chuột về toạ độ frame,
nên toàn bộ phần vẽ kiểm tra được mà không cần cửa sổ.

Chỉ dùng ký tự ASCII trong ảnh (số điểm); chữ tiếng Việt do giao diện hiển thị bằng widget.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import cv2
import numpy as np

from . import imagefx
from .geometry import EYES, Point
from .session import Session

COLORS = {"mattrai": (90, 220, 60), "matphai": (255, 170, 40)}        # BGR
PIN_IDS = {i for spec in EYES.values() for i in spec.pins}
INSTANCE_COLORS = [(60, 76, 231), (219, 152, 52), (113, 204, 46), (15, 196, 241), (182, 89, 155), (156, 188, 26)]   # BGR, mỗi đối tượng một màu
# BGR, mỗi VỊ TRÍ điểm trong mắt một màu (điểm thứ 1 của mắt nào cũng đỏ, thứ 2 xanh lá...). Hai mắt dùng chung bảng nên dễ đối chiếu.
POINT_PALETTE = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 230, 255), (255, 0, 255), (255, 255, 0), (200, 0, 140), (120, 60, 0)]
GROUP_COLOR = (170, 170, 170)                                  # chưa phân nhóm: một màu chung


@dataclass
class Look:
    """Các lớp hiển thị (như bảng Layers/Appearance của CVAT): bật tắt từng lớp, cỡ điểm, độ mờ của nhãn."""
    image: bool = True
    eyes: dict = None            # {nhãn mắt: bật/tắt}; None = cả hai
    outline: bool = True
    points: bool = True
    ids: bool = True
    size: float = 1.0            # hệ số cỡ điểm và chữ số
    opacity: float = 1.0         # độ đặc của toàn bộ nhãn (1 = đặc)
    brightness: float = 100.0    # % như Brightness của CVAT (50..200, nhân vào ảnh); xem imagefx.COLOR_RANGES
    contrast: float = 100.0      # % (50..200), quanh mức xám giữa
    saturation: float = 100.0    # % (0..300), 0 = đen trắng
    gamma: float = 1.0           # 0,2..2,6 như Gamma của CVAT (bảng tra pow(v, 1/gamma)), áp trước độ sáng
    grid: bool = False           # lưới ảnh (Image grid của CVAT); vẽ vào ảnh nền nên xoay theo ảnh
    grid_size: int = 100         # pixel ảnh, 1..1000 (CVAT 5..1000); tự thưa khi thu nhỏ (imagefx.grid_step)
    grid_color: str = "White"    # một khoá của imagefx.GRID_COLORS
    grid_opacity: float = 100.0  # %, 0..100
    axis_guide: bool = False     # thước theo trục mắt đang chọn (vạch tỉ lệ guideline v1.3 mục 3.3)
    smooth: bool = True          # làm mịn ảnh khi phóng to (tắt thì thấy từng pixel)
    bg: tuple = (40, 40, 40)     # màu nền ngoài ảnh (BGR)
    selected_opacity: float = 1.0   # độ đặc riêng của mắt đang chọn
    color_by: str = "label"      # label | instance | group
    outlined: bool = False       # viền ngoài quanh đường mắt và điểm
    outline_color: tuple = (0, 0, 0)
    point_colors: bool = True    # mỗi điểm một màu theo vị trí (POINT_PALETTE); tắt thì mọi điểm cùng màu mắt
    text_always: bool = False    # luôn hiện chữ cạnh mắt (không chỉ khi chọn)
    text_content: tuple = ("id", "label", "source")
    font_size: float = 1.0
    colors: dict = None          # màu riêng từng mắt (phím Enter đổi màu), BGR
    top: str = "matphai"         # mắt vẽ sau cùng (nằm trên)

    def order(self) -> list[str]:
        return [l for l in EYES if l != self.top] + [self.top]

    def adjust(self, img: np.ndarray) -> np.ndarray:
        """Chỉnh gamma, độ sáng, tương phản, bão hoà của ảnh nền như CVAT (chỉ để nhìn; không đổi ảnh gốc)."""
        return imagefx.apply_color(img, self.brightness, self.contrast, self.saturation, self.gamma)

    def color_of(self, label: str, index: int = 0) -> tuple:
        """Màu vẽ mắt `label` (index là thứ tự đối tượng, bắt đầu từ 0) theo cách tô màu đang chọn."""
        if self.colors and label in self.colors:
            return self.colors[label]
        if self.color_by == "instance":
            return INSTANCE_COLORS[index % len(INSTANCE_COLORS)]
        if self.color_by == "group":
            return GROUP_COLOR
        return COLORS[label]

    def eye_on(self, label: str) -> bool:
        return True if self.eyes is None else self.eyes.get(label, True)


@dataclass
class View:
    x0: float
    y0: float
    k: float                 # pixel màn hình trên mỗi pixel ảnh
    width: int
    height: int

    def to_screen(self, p: Point) -> tuple[int, int]:
        return int(round((p[0] - self.x0) * self.k)), int(round((p[1] - self.y0) * self.k))

    def to_frame(self, sx: float, sy: float) -> Point:
        return sx / self.k + self.x0, sy / self.k + self.y0

    def zoomed_at(self, sx: float, sy: float, factor: float, k_min: float = 0.2, k_max: float = 40.0) -> "View":
        """View mới sau khi phóng `factor` lần, giữ nguyên điểm ảnh đang nằm dưới (sx, sy)."""
        px, py = self.to_frame(sx, sy)
        k = min(max(self.k * factor, k_min), k_max)
        return View(px - sx / k, py - sy / k, k, self.width, self.height)

    def panned(self, dsx: float, dsy: float) -> "View":
        return View(self.x0 - dsx / self.k, self.y0 - dsy / self.k, self.k, self.width, self.height)


def eye_box(points: dict[int, Point] | None) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    xs = [p[0] for p in points.values()]
    ys = [p[1] for p in points.values()]
    return min(xs), min(ys), max(xs), max(ys)


def make_view(session: Session, f: int, size: tuple[int, int], anchor: tuple | None = None,
              manual: View | None = None) -> View:
    """Khung nhìn phóng vào hai mắt. `anchor` là hộp mắt dùng để giữ khung ổn định khi frame hiện tại chưa có nhãn.
    `manual`: khung người dùng đã phóng hoặc kéo tay; có thì dùng nguyên, không tự đổi theo nhãn."""
    if manual is not None:
        return manual
    w, h = size
    box = eye_box(session.points_at(f)) or anchor
    if box is None:
        k = min(w / session.width, h / session.height)
        return View(-(w / k - session.width) / 2, -(h / k - session.height) / 2, k, w, h)       # ảnh nằm giữa khung
    x0, y0, x1, y1 = box
    bw = max(x1 - x0, 60.0) * 1.7
    bh = bw * h / w
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return View(cx - bw / 2, cy - bh / 2, w / bw, w, h)


def marker_radii(eye_px: float, scale: float = 1.0) -> tuple[float, float]:
    """Bán kính điểm ghim (to) và điểm suy ra (nhỏ), tính theo bề rộng mắt trên màn hình để điểm không che mắt."""
    big = min(5.0, max(2.0, 0.045 * eye_px)) * scale
    return big, max(1.2, 0.6 * big)


OCCLUDED = (30, 200, 255)       # BGR vàng cam


class CvPainter:
    """Bút vẽ lên ảnh numpy BGR bằng OpenCV. Mọi hàm vẽ nhãn đi qua một bút vẽ, nên cùng một mã vẽ được ra ảnh (xem trước, test,
    và khi nhãn có độ mờ < 100%) hoặc ra đối tượng vector của Canvas trong cửa sổ (`gui.CanvasPainter`, nhanh hơn nhiều khi khung lớn)."""

    def __init__(self, img: np.ndarray):
        self.img = img

    def poly(self, pts, color, width, tag=None):
        cv2.polylines(self.img, [np.array(pts, np.int32)], True, color, width, cv2.LINE_AA)

    def line(self, a, b, color, width=1):
        cv2.line(self.img, a, b, color, width, cv2.LINE_AA)

    def circle(self, c, r, color, width=1, tag=None):
        """width = -1: tô đặc (như OpenCV)."""
        cv2.circle(self.img, c, r, color, width, cv2.LINE_AA)

    def dashed_circle(self, c, r, color):
        for a0 in range(0, 360, 40):
            cv2.ellipse(self.img, c, (r, r), 0, a0, a0 + 20, color, 1, cv2.LINE_AA)

    def text(self, org, txt, scale, color=(255, 255, 255), halo=True):
        """Chữ ASCII, `org` là góc trái đường chân chữ; halo = viền đen dày dưới chữ cho dễ đọc trên ảnh."""
        if halo:
            cv2.putText(self.img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(self.img, txt, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)

    @contextmanager
    def group(self, alpha: float):
        """Vẽ một nhóm nhãn với độ đặc `alpha` (trộn với ảnh bên dưới)."""
        if alpha >= 0.999:
            yield
            return
        under = self.img.copy()
        yield
        self.img[:] = cv2.addWeighted(self.img, alpha, under, 1 - alpha, 0)


def _painter(target):
    return target if hasattr(target, "circle") else CvPainter(target)


def _draw_eye(img, view: View, pts: dict[int, Point], label: str, *, pinned: bool, ids: bool, scale: float,
              flags: dict[int, str] | None = None, est: dict[int, float] | None = None, look: Look | None = None,
              index: int = 0, source: str = "", tagged: bool = False):
    """`img`: ảnh numpy hoặc bút vẽ. `tagged`: gắn nhãn "pt:<mắt>:<id>" cho điểm (để kiểm và tìm đối tượng trên Canvas)."""
    p = _painter(img)
    look = look or Look()
    if not look.eye_on(label):
        return
    spec = EYES[label]
    col = look.color_of(label, index)
    screen = [view.to_screen(pts[i]) for i in spec.ids if i in pts]
    if len(screen) == 8 and look.outline:
        if look.outlined:                                        # Outlined borders: viền ngoài dày hơn dưới đường màu
            p.poly(screen, look.outline_color, 3)
        p.poly(screen, col, 1, tag=f"outline:{label}" if tagged else None)
    if look.text_always and screen:                              # chữ cạnh mắt: ID, label, nguồn nhãn
        parts = [f"#{index + 1}" if "id" in look.text_content else "", label.upper() if "label" in look.text_content else "",
                 f"({source})" if "source" in look.text_content and source else ""]
        txt = " ".join(x for x in parts if x)
        if txt:
            org = (min(q[0] for q in screen), min(q[1] for q in screen) - 14)
            p.text(org, txt, 0.45 * look.font_size)
    eye_px = 0.0
    if spec.first in pts and spec.last in pts:
        a_, b_ = view.to_screen(pts[spec.first]), view.to_screen(pts[spec.last])
        eye_px = ((a_[0] - b_[0]) ** 2 + (a_[1] - b_[1]) ** 2) ** 0.5
    scale = scale * look.size
    rb, rs = marker_radii(eye_px, scale)
    font = max(0.3, min(0.5, eye_px / 380.0)) * scale
    if not look.points:
        return
    for pos, i in enumerate(spec.ids):
        if i not in pts:
            continue
        c = view.to_screen(pts[i])
        kind = (flags or {}).get(i)
        r = max(1, int(round(rb if i in PIN_IDS else rs)))
        tag = f"pt:{label}:{i}" if tagged else None
        pcol = POINT_PALETTE[pos % len(POINT_PALETTE)] if look.point_colors else col
        if kind == "outside":                                    # Outside: dấu x mờ, không vẽ điểm
            p.line((c[0] - r, c[1] - r), (c[0] + r, c[1] + r), (160, 160, 160))
            p.line((c[0] - r, c[1] + r), (c[0] + r, c[1] - r), (160, 160, 160))
            continue
        if look.outlined:
            p.circle(c, r + 1, look.outline_color, 1)
        if i in PIN_IDS:
            p.circle(c, r, pcol, -1, tag=tag)
            p.circle(c, r, (255, 255, 255), 1)
        else:
            p.circle(c, r, pcol, 1, tag=tag)
        if kind == "occluded":                                   # Occluded: viền vàng cam bao ngoài điểm
            p.circle(c, r + 2, OCCLUDED, 1)
        if est and i in est:                                     # điểm ước lượng: vòng nét đứt thể hiện sai số
            p.dashed_circle(c, max(3, int(round(est[i] * view.k))), OCCLUDED)
        if ids and look.ids and eye_px >= 80:
            p.text((c[0] + r + 2, c[1] - r - 1), str(i), font)


PREVIEW = (0, 102, 255)        # BGR của cam #FF6600: mắt đang ghim dở


def _draw_preview(img, view: View, pts8: dict[int, Point]) -> None:
    """Vẽ 8 điểm của một mắt đang ghim dở (chưa biết là mắt trái hay phải): viền cam, điểm rỗng, điểm ghim đặc."""
    p = _painter(img)
    ids = sorted(pts8)
    screen = [view.to_screen(pts8[i]) for i in ids]
    p.poly(screen, PREVIEW, 1)
    xs = [c[0] for c in screen]
    w = max(max(xs) - min(xs), 1)                           # bề rộng mắt trên màn hình (điểm đầu và cuối danh sách đều sát khoé đầu)
    rb, rs = marker_radii(float(max(w, 40)), 1.0)
    for i, c in zip(ids, screen):
        if i in PIN_IDS or i in (14, 16, 18, 20, 22, 24, 26, 28):
            p.circle(c, max(1, int(round(rb))), PREVIEW, -1)
            p.circle(c, max(1, int(round(rb))), (255, 255, 255), 1)
        else:
            p.circle(c, max(1, int(round(rs))), PREVIEW, 1)


def render_base(session: Session, f: int, size: tuple[int, int], view: View, look: Look | None = None) -> np.ndarray:
    """Ảnh nền của frame f theo khung nhìn `view` (chỉ ảnh đã chỉnh sáng và phóng, chưa vẽ nhãn). Dựng một lần rồi dùng lại
    trong lúc kéo điểm, xoay nhãn: những lúc đó chỉ phần nhãn đổi."""
    look = look or Look()
    src = look.adjust(session.bgr(f)) if look.image else np.full_like(session.bgr(f), look.bg)
    tiny_grid = look.grid and look.grid_size <= 2                    # lưới từng pixel: hiện pixel rõ để mỗi ô trùng một pixel
    out = warp_image(src, view, size, look.smooth and not tiny_grid, look.bg)
    if look.grid:
        imagefx.draw_grid(out, view, session.width, session.height, look.grid_size, look.grid_color, look.grid_opacity)
    return out


def warp_image(src: np.ndarray, view: View, size: tuple[int, int], smooth: bool, bg: tuple) -> np.ndarray:
    """Phóng và dời ảnh `src` theo khung nhìn `view` thành ảnh cỡ `size` (màn hình).

    Như CVAT, pixel ảnh i phủ toạ độ [i, i+1) (tâm ở i + 0,5); OpenCV đặt tâm pixel ở toạ độ nguyên, nên bù nửa pixel ở cả hai phía
    (ảnh và màn hình). Không bù thì điểm đặt bằng mắt trong EyePin hiện trên CVAT lệch (−0,5; −0,5) px (design/cvat-api-notes.md)."""
    k = view.k
    M = np.float32([[k, 0, k * (0.5 - view.x0) - 0.5], [0, k, k * (0.5 - view.y0) - 0.5]])
    return cv2.warpAffine(src, M, size, flags=cv2.INTER_CUBIC if smooth else cv2.INTER_NEAREST, borderValue=bg)


def render_main(session: Session, f: int, size: tuple[int, int] = (960, 460), *, anchor: tuple | None = None,
                clicks: list[tuple[int, Point]] | None = None, override: dict[int, Point] | None = None,
                manual: View | None = None, show_ids: bool = True, hide_labels: bool = False, look: Look | None = None,
                preview: dict[int, Point] | None = None,
                handle: tuple | None = None, selected: str | None = None, base: np.ndarray | None = None,
                ids: dict | None = None):
    """Ảnh khung chính cho frame f. Trả về (ảnh BGR, View). `clicks`: các điểm ghim đang được bấm dở; `override`: điểm đang kéo."""
    view = make_view(session, f, size, anchor, manual)
    look = look or Look()
    img = base.copy() if base is not None else render_base(session, f, size, view, look)
    p = CvPainter(img)
    draw_overlay(p, session, f, view, clicks=clicks, override=override, show_ids=show_ids, hide_labels=hide_labels, look=look,
                 preview=preview, handle=handle, selected=selected, ids=ids)
    return p.img, view


BOX_PAD = 16                   # px màn hình: khung chọn rộng hơn hộp bao các điểm, đủ xa để tay cầm không đè lên điểm ở khoé
ROTATE_DIST = 44               # px màn hình: tay cầm xoay cách cạnh trên khung
ROTATE_HIT = 14                # bán kính bấm trúng tay cầm xoay (px)
RESIZE_HIT = 12                # bán kính bấm trúng tay cầm đổi kích thước (px)
RESIZE_R = 6                   # bán kính tay cầm đổi kích thước khi vẽ (px), viền trắng 2 px ngoài viền tối
ROTATE_R = 9                   # bán kính tay cầm xoay khi vẽ (px)
GUIDE_COLOR = (255, 255, 0)    # BGR xanh lơ: thước theo trục mắt, khác màu mắt trái/phải


def resize_handles(view: View, box) -> dict[str, tuple[int, int]]:
    """8 tay cầm đổi kích thước (4 góc, 4 giữa cạnh) của khung chọn quanh hộp `box` (toạ độ frame), theo toạ độ khung vẽ."""
    bx0, by0 = view.to_screen((box[0], box[1]))
    bx1, by1 = view.to_screen((box[2], box[3]))
    bx0, by0, bx1, by1 = bx0 - BOX_PAD, by0 - BOX_PAD, bx1 + BOX_PAD, by1 + BOX_PAD
    mx, my = (bx0 + bx1) // 2, (by0 + by1) // 2
    return {"nw": (bx0, by0), "n": (mx, by0), "ne": (bx1, by0), "e": (bx1, my),
            "se": (bx1, by1), "s": (mx, by1), "sw": (bx0, by1), "w": (bx0, my)}


def draw_overlay(p, session: Session, f: int, view: View, *, clicks=None, override=None, show_ids: bool = True, hide_labels: bool = False,
                 look: Look | None = None, preview=None, handle=None, selected: str | None = None, ids: dict | None = None) -> None:
    """Vẽ mọi thứ nằm trên ảnh nền (nhãn các người, mắt đang chọn, tay cầm xoay, mắt đang ghim dở, điểm vừa bấm) bằng bút vẽ `p`."""
    look = look or Look()
    if not hide_labels:                                   # các bộ đối tượng khác (người khác): vẽ trước, mắt của bộ đang chọn nằm trên
        for v in session.other_views(f):
            with p.group(look.opacity):
                for label in look.order():
                    _draw_eye(p, view, v["points"], label, pinned=False, ids=show_ids, scale=1.0, flags=v["flags"], est=v["est"], look=look,
                              index=v["ids"].get(label, list(EYES).index(label) + 1) - 1, source=v["source"])
    pts = None if hide_labels else session.points_at(f)
    if pts:
        pts = dict(pts)
        if override:
            pts.update(override)
        pinned = f in session.pins
        flags = session.flags_at(f)
        est = session.estimates.get(f)
        source = "MANUAL" if f in session.pins else ("AUTO" if f in session.labels else "FILE")
        order = look.order()
        for alpha, group in ((look.opacity, [l for l in order if l != selected]), (look.selected_opacity, [l for l in order if l == selected])):
            if not group:
                continue
            with p.group(alpha):
                for label in group:
                    _draw_eye(p, view, pts, label, pinned=pinned, ids=show_ids, scale=1.0, flags=flags, est=est, look=look,
                              index=(ids or {}).get(label, list(EYES).index(label) + 1) - 1, source=source, tagged=True)
        if look.axis_guide and selected in EYES:                     # thước theo trục mắt đang chọn; dùng điểm sau `override` nên đi theo khi kéo
            for a, b in imagefx.axis_guides(EYES[selected], pts) or []:
                p.line(view.to_screen(a), view.to_screen(b), GUIDE_COLOR, 1)
    if handle and not hide_labels:                        # mắt đang chọn: khung góc nét đứt, tên, tay cầm xoay (như CVAT)
        if len(handle) >= 3 and handle[2]:
            bx0, by0 = view.to_screen((handle[2][0], handle[2][1]))
            bx1, by1 = view.to_screen((handle[2][2], handle[2][3]))
            bx0, by0, bx1, by1 = bx0 - BOX_PAD, by0 - BOX_PAD, bx1 + BOX_PAD, by1 + BOX_PAD
            arm = max(4, min(12, (bx1 - bx0) // 4, (by1 - by0) // 3))
            for (cx, cy, dx, dy) in ((bx0, by0, 1, 1), (bx1, by0, -1, 1), (bx0, by1, 1, -1), (bx1, by1, -1, -1)):
                p.line((cx, cy), (cx + dx * arm, cy), (40, 40, 40), 2)
                p.line((cx, cy), (cx, cy + dy * arm), (40, 40, 40), 2)
            for name, q in resize_handles(view, handle[2]).items():         # tay cầm đổi kích thước: kéo cạnh hoặc góc
                p.circle(q, RESIZE_R, (40, 40, 40), -1, tag=f"resize:{name}")     # lõi tối, viền trắng: nổi trên nền da sáng
                p.circle(q, RESIZE_R, (255, 255, 255), 2)
            if len(handle) >= 4 and handle[3]:
                p.text((bx1 + 8, by0 + 12), handle[3], 0.45)
        a, h = view.to_screen(handle[0]), view.to_screen(handle[1])
        p.line(a, h, (255, 255, 255), 2)
        p.circle(h, ROTATE_R, (31, 31, 31), -1, tag="handle")            # tay cầm xoay: lõi tối, viền trắng
        p.circle(h, ROTATE_R, (255, 255, 255), 2)
    if preview:
        _draw_preview(p, view, preview)
    for pid, q in (clicks or []):
        c = view.to_screen(q)
        p.circle(c, 4, (40, 200, 255), 1)
        p.text((c[0] + 6, c[1] - 6), str(pid), 0.5, (40, 200, 255), halo=False)


def render_thumb(session: Session, f: int, view: View, size: tuple[int, int] = (300, 140), hide_labels: bool = False, look: Look | None = None) -> np.ndarray | None:
    """Ảnh nhỏ của frame f cùng vùng nhìn với khung chính (để so sánh frame trước/sau)."""
    if not 0 <= f < session.n_frames:
        return None
    k = size[0] / (view.width / view.k)
    M = np.float32([[k, 0, -view.x0 * k], [0, k, -view.y0 * k]])
    look = look or Look()
    src = look.adjust(session.bgr(f)) if look.image else np.full_like(session.bgr(f), look.bg)
    img = cv2.warpAffine(src, M, size, flags=cv2.INTER_AREA, borderValue=look.bg)
    pts = None if hide_labels else session.points_at(f)
    if pts:
        sub = View(view.x0, view.y0, k, size[0], size[1])
        for label in look.order():
            _draw_eye(img, sub, pts, label, pinned=False, ids=False, scale=0.6, look=look, index=list(EYES).index(label))
    return img


def max_shift(a: dict[int, Point] | None, b: dict[int, Point] | None) -> tuple[int, float] | None:
    """Điểm dịch nhiều nhất giữa hai frame (id, pixel); None nếu thiếu nhãn."""
    if not a or not b:
        return None
    best = max(((i, ((a[i][0] - b[i][0]) ** 2 + (a[i][1] - b[i][1]) ** 2) ** 0.5) for i in a if i in b), default=None,
               key=lambda t: t[1])
    return best


TURN_BGR = (0, 102, 255)               # cam #FF6600 (theme): đoạn quay đầu đã xác nhận bằng bề rộng mắt tại frame ghim
TURN_UNSURE_BGR = (150, 200, 255)      # cam nhạt: đoạn quay đầu chưa xác nhận (có thể do tiến/lùi)


def render_timeline(session: Session, current: int, width: int = 960, height: int = 46, show_issues: bool = True) -> np.ndarray:
    """Dải thời gian: mỗi frame một cột. Xanh lá = frame ghim, xanh xám = tool tính, vàng = cần ghim, đỏ/cam = quét.
    Dải cam phía trên = đoạn quay đầu của người đang chọn (cam nhạt = chưa xác nhận)."""
    img = np.full((height, width, 3), 235, np.uint8)
    n = session.n_frames
    cw = width / n
    found = session.findings if show_issues else []
    red = {f for fd in found if fd.level == "red" for f in range(fd.frame, fd.last + 1)}
    yellow = {f for fd in found if fd.level == "yellow" for f in range(fd.frame, fd.last + 1)}
    need = set(session.need_pin)
    for f in range(n):
        x0, x1 = int(f * cw), max(int((f + 1) * cw), int(f * cw) + 1)
        if f in session.pins:
            col = (80, 190, 70)
        elif f in need:
            col = (40, 170, 240)
        elif f in session.labels:
            col = (200, 170, 130)
        else:
            col = (225, 225, 225)
        cv2.rectangle(img, (x0, 8), (x1, height - 16), col, -1)
        if f in red:
            cv2.rectangle(img, (x0, height - 12), (x1, height - 4), (60, 60, 220), -1)
        elif f in yellow:
            cv2.rectangle(img, (x0, height - 12), (x1, height - 4), (40, 180, 250), -1)
    if 0 <= session.cur < len(session.turns):
        for t in session.turns[session.cur].turns:
            x0, x1 = int(t.first * cw), max(int((t.last + 1) * cw), int(t.first * cw) + 1)
            cv2.rectangle(img, (x0, 0), (x1 - 1, 6), TURN_BGR if t.confirmed else TURN_UNSURE_BGR, -1)
    cx = int((current + 0.5) * cw)
    cv2.line(img, (cx, 0), (cx, height), (200, 80, 20), 2)
    return img


def status_text(session: Session, f: int) -> str:
    parts = [f"Frame {f}/{session.n_frames - 1} ({session.names[f]})"]
    if f in session.pins:
        parts.append("FRAME GHIM")
        marks = session.flags.get(f, {})
        if marks:
            parts.append("Occluded: " + ",".join(str(i) for i, k in sorted(marks.items()) if k == "occluded") if any(k == "occluded" for k in marks.values()) else "")
            if any(k == "outside" for k in marks.values()):
                parts.append("Outside: " + ",".join(str(i) for i, k in sorted(marks.items()) if k == "outside"))
        parts = [x for x in parts if x]
        d = session.drift_before(f)
        if d is not None:
            parts.append(f"đoạn trước trôi {d:.1f} px")
    elif f in session.labels:
        parts.append(f"tool tính, độ khớp {session.labels[f].score:.2f}" + (" — CẦN GHIM" if f in session.need_pin else ""))
    elif session.points_at(f):
        parts.append("nhãn từ file")
    else:
        parts.append("chưa có nhãn")
    return " · ".join(parts)
