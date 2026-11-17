"""Kiểm bộ icon PNG dựng từ SVG của CVAT và Ant Design (cả hai MIT)."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "eyepin" / "assets" / "icons"
# Nét mảnh (dấu cộng, ba chấm, mũi tên) phủ ít điểm hơn hình đặc: ngưỡng 2%.
MIN_COVER = 0.02


def _load_build():
    spec = importlib.util.spec_from_file_location(
        "build_icons", ROOT / "tools" / "build_icons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = _load_build()


class IconAssetsTest(unittest.TestCase):
    def test_build_script_loads_without_pymupdf(self):
        """Đọc ICON_SOURCES không cần PyMuPDF: thư viện đó chỉ cần khi dựng icon (máy chạy test có thể không cài)."""
        with mock.patch.dict(sys.modules, {"fitz": None, "pymupdf": None}):   # None trong sys.modules = import thất bại
            mod = _load_build()
        self.assertIn("eye", mod.ICON_SOURCES)
        self.assertEqual(mod.SIZES, (16, 20, 24))

    def test_every_icon_has_all_sizes(self):
        for name in build.ICON_SOURCES:
            for px in build.SIZES:
                with self.subTest(icon=name, px=px):
                    path = ICON_DIR / f"{name}-{px}.png"
                    self.assertTrue(path.exists(), f"thiếu {path.name}")
                    im = Image.open(path)
                    self.assertEqual(im.mode, "RGBA")
                    self.assertEqual(im.size, (px, px))
                    alpha = list(im.getchannel("A").getdata())
                    n = len(alpha)
                    solid = sum(1 for a in alpha if a > 128) / n
                    empty = sum(1 for a in alpha if a == 0) / n
                    self.assertGreaterEqual(solid, MIN_COVER, "ảnh rỗng")
                    self.assertGreaterEqual(empty, MIN_COVER, "ô vuông đặc")

    def test_icons_are_white_masks(self):
        for name in build.ICON_SOURCES:
            for px in build.SIZES:
                with self.subTest(icon=name, px=px):
                    im = Image.open(ICON_DIR / f"{name}-{px}.png")
                    for r, g, b, a in im.getdata():
                        if a > 0:
                            self.assertGreaterEqual(min(r, g, b), 240)

    def test_notice_has_both_mit_licenses(self):
        text = (ICON_DIR / "NOTICE.md").read_text(encoding="utf-8")
        for s in ("cvat-ai/cvat", "v2.75.0", "@ant-design/icons-svg", "4.4.2"):
            self.assertIn(s, text)
        self.assertGreaterEqual(text.count("MIT"), 2)
        for lic in ("cvat", "ant"):
            first = (ROOT / "tools" / "icon_src" / lic / "LICENSE").read_text(
                encoding="utf-8")
            for line in first.splitlines():
                if line.startswith("Copyright"):
                    self.assertIn(line.strip(), text)


if __name__ == "__main__":
    unittest.main()
