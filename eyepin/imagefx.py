"""Hộp Image setups như CVAT: chỉnh màu ảnh nền, lưới ảnh, thước theo trục mắt, chữ đo dưới con trỏ.

Chỉ để nhìn: không đổi ảnh gốc, không đổi toạ độ nhãn. Không đụng Tk nên test được không cần cửa sổ.

Màu theo đúng CVAT (design/cvat-api-notes.md, mục "Quy ước pixel"): gamma của fabric 5.x (bảng tra pow(v/255, 1/gamma)) áp trước, rồi
bộ lọc CSS `brightness() contrast() saturate()` theo thứ tự đó, giá trị phần trăm chia 100.
"""
from __future__ import annotations

import cv2
import numpy as np

COLOR_DEFAULTS = {"brightness": 100.0, "contrast": 100.0, "saturation": 100.0, "gamma": 1.0}
COLOR_RANGES = {"brightness": (50, 200), "contrast": (50, 200), "saturation": (0, 300), "gamma": (0.2, 2.6)}
OLD_SCALE_KEYS = ("brightness", "contrast", "saturation")


def _tone_lut(brightness: float, contrast: float, gamma: float) -> np.ndarray:
    """Bảng tra 256 giá trị cho phần theo từng kênh: gamma, rồi nhân độ sáng, rồi tương phản quanh mức xám giữa."""
    v = np.arange(256, dtype=np.float64)
    v = np.power(v / 255.0, 1.0 / gamma) * 255.0
    v = np.clip(v * (brightness / 100.0), 0, 255)                    # mỗi hàm của CSS filter kẹp kết quả về 0..1
    v = np.clip((v - 127.5) * (contrast / 100.0) + 127.5, 0, 255)
    return np.rint(v).astype(np.uint8)


def _saturate_matrix(saturation: float) -> np.ndarray:
    """Ma trận saturate() của Filter Effects (viết theo RGB) đổi sang thứ tự kênh BGR của OpenCV."""
    s = saturation / 100.0
    rgb = np.array([[0.213 + 0.787 * s, 0.715 - 0.715 * s, 0.072 - 0.072 * s],
                    [0.213 - 0.213 * s, 0.715 + 0.285 * s, 0.072 - 0.072 * s],
                    [0.213 - 0.213 * s, 0.715 - 0.715 * s, 0.072 + 0.928 * s]])
    order = [2, 1, 0]                                                  # BGR <-> RGB
    return rgb[np.ix_(order, order)]


def apply_color(img: np.ndarray, brightness: float, contrast: float, saturation: float, gamma: float) -> np.ndarray:
    """Ảnh BGR uint8 sau khi chỉnh như CVAT. Đủ bốn giá trị mặc định thì trả về chính `img` (không chép)."""
    if (brightness, contrast, saturation, gamma) == (100, 100, 100, 1):
        return img
    out = img
    if (brightness, contrast, gamma) != (100, 100, 1):
        out = cv2.LUT(out, _tone_lut(brightness, contrast, gamma))
    if saturation != 100:
        mixed = cv2.transform(out.astype(np.float32), _saturate_matrix(saturation).astype(np.float32))
        out = np.rint(np.clip(mixed, 0, 255)).astype(np.uint8)
    return out


GRID_COLORS = {"White": (255, 255, 255), "Black": (0, 0, 0), "Red": (0, 0, 255), "Green": (0, 255, 0), "Blue": (255, 0, 0)}   # BGR
GRID_SIZE_RANGE = (1, 1000)            # CVAT cho 5–1000; EyePin cho xuống 1 (lưới từng pixel)
GRID_MIN_PX = 8.0                      # hai đường gần nhau hơn thế trên màn hình thì lưới tự thưa ra (nét 1 px cách 4 px vẫn phủ ~40% ảnh)


def grid_step(size: int, k: float, min_px: float = GRID_MIN_PX) -> int:
    """Bước lưới thật sự vẽ (pixel ảnh): `size` nhân lần lượt ×1, ×5, ×10, ×50, ×100… tới khi hai đường cách nhau ít nhất `min_px` px màn hình."""
    size = max(1, int(size))
    if k <= 0:
        return size
    m, five = 1, True
    while size * m * k < min_px:
        m *= 5 if five else 2
        five = not five
    return size * m


def draw_grid(img: np.ndarray, view, img_w: int, img_h: int, size: int, color: str, opacity: float) -> int:
    """Vẽ lưới vuông lên ảnh màn hình `img` (tại chỗ), như Image grid của CVAT: đường tại toạ độ ảnh nguyên chia hết cho bước, từ góc ảnh,
    nên trùng mép pixel (pixel i phủ [i, i+1)); nét 1 px; chỉ trong khung ảnh. `view` có x0, y0, k (render.View). Trả bước đã vẽ."""
    step = grid_step(size, view.k)
    h, w = img.shape[:2]
    a = max(0.0, min(1.0, float(opacity) / 100.0))
    if a <= 0:
        return step
    col = np.array(GRID_COLORS.get(color, GRID_COLORS["White"]), np.float32)

    def screen(u, origin):
        return np.floor((np.asarray(u, np.float64) - origin) * view.k).astype(np.int64)

    c0, c1 = max(0, int(screen(0, view.x0))), min(w, int(np.ceil((img_w - view.x0) * view.k)))
    r0, r1 = max(0, int(screen(0, view.y0))), min(h, int(np.ceil((img_h - view.y0) * view.k)))
    if c0 >= c1 or r0 >= r1:
        return step
    cols = screen(np.arange(0, img_w + 1, step), view.x0)
    rows = screen(np.arange(0, img_h + 1, step), view.y0)
    cols = np.unique(cols[(cols >= 0) & (cols < w)])
    rows = np.unique(rows[(rows >= 0) & (rows < h)])

    def blend(block):
        return np.rint(block.astype(np.float32) * (1 - a) + col * a).astype(np.uint8)

    if cols.size:
        img[r0:r1, cols] = blend(img[r0:r1, cols])
    if rows.size:
        img[rows, c0:c1] = blend(img[rows, c0:c1])
    return step


GUIDE_TICK = 0.35                      # độ dài vạch thước theo bề rộng mắt


def axis_guides(spec, pts: dict, tick: float = GUIDE_TICK):
    """Thước theo trục mắt (toạ độ ảnh): đoạn đầu là trục khoé–khoé, rồi một vạch vuông góc tại mỗi tỉ lệ guideline v1.3 mục 3.3 của mắt
    `spec` (EyeSpec: `up_mid`, `lo_mid`, `derived`); vạch mí trên về phía điểm giữa mí trên (thiếu điểm đó thì về phía trên ảnh), vạch mí
    dưới về phía ngược lại. None khi thiếu một khoé hoặc hai khoé trùng nhau."""
    a, b = pts.get(spec.first), pts.get(spec.last)
    if a is None or b is None:
        return None
    ax, ay = b[0] - a[0], b[1] - a[1]
    length = float(np.hypot(ax, ay))
    if length < 1e-6:
        return None
    nx, ny = -ay / length, ax / length
    side = 0.0
    up = pts.get(spec.up)
    if up is not None:
        side = float(np.sign((up[0] - a[0]) * nx + (up[1] - a[1]) * ny))
    if side == 0:                                                    # thiếu điểm hoặc mắt nhắm (điểm nằm trên trục): phía trên ảnh
        side = -1.0 if ny > 0 else 1.0
    ux, uy = nx * side * tick * length, ny * side * tick * length
    upper = sorted({spec.up_mid} | {t for s, t in spec.derived.values() if s == "up"})
    lower = sorted({spec.lo_mid} | {t for s, t in spec.derived.values() if s == "lo"})
    segs = [((float(a[0]), float(a[1])), (float(b[0]), float(b[1])))]
    for ratios, sgn in ((upper, 1.0), (lower, -1.0)):
        for t in ratios:
            base = (a[0] + t * ax, a[1] + t * ay)
            segs.append(((float(base[0]), float(base[1])), (float(base[0] + sgn * ux), float(base[1] + sgn * uy))))
    return segs


def _num(v: float, digits: int) -> str:
    return f"{v:.{digits}f}".replace(".", ",")


def readout(u, img_w: int, img_h: int, pts: dict | None) -> str:
    """Chữ đo dưới con trỏ: toạ độ ảnh (2 chữ số lẻ) và khoảng cách tới điểm nhãn gần nhất (px; kèm % bề rộng mắt khi mắt đó đủ hai khoé).
    Ngoài ảnh (pixel i phủ [i, i+1), ảnh là [0, img_w) × [0, img_h)) thì ghi "ngoài ảnh"."""
    from .geometry import EYES
    x, y = float(u[0]), float(u[1])
    if not (0 <= x < img_w and 0 <= y < img_h):
        return "ngoài ảnh"
    text = f"x {_num(x, 2)} · y {_num(y, 2)}"
    if not pts:
        return text
    pid, p = min(pts.items(), key=lambda kv: (kv[1][0] - x) ** 2 + (kv[1][1] - y) ** 2)
    d = float(np.hypot(p[0] - x, p[1] - y))
    text += f" · tới điểm {pid}: {_num(d, 1)} px"
    spec = next((s for s in EYES.values() if pid in s.ids), None)
    if spec is not None and spec.first in pts and spec.last in pts:
        width = float(np.hypot(pts[spec.last][0] - pts[spec.first][0], pts[spec.last][1] - pts[spec.first][1]))
        if width > 1e-6:
            text += f" ({round(100 * d / width)}% bề rộng mắt)"
    return text


def migrate_display(display: dict) -> bool:
    """Giá trị độ sáng, tương phản, bão hoà lưu theo thang cũ của EyePin (cộng −100..100, nhân 0,3..3) không đổi được sang thang của CVAT,
    nên bỏ đi để về mặc định. Đánh dấu `color_scale = "cvat"`. Trả True khi có bỏ ít nhất một giá trị."""
    dropped = False
    if display.get("color_scale") != "cvat":
        for k in OLD_SCALE_KEYS:
            if k in display:
                del display[k]
                dropped = True
    display["color_scale"] = "cvat"
    return dropped
