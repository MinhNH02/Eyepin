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
