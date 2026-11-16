"""Kiểm nút biểu tượng: vẽ PNG (không chữ cố định), rơi về chữ khi thiếu PNG, tắt/bật, chú thích hiện nhanh."""
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from eyepin import icons
from eyepin.icons import IconButton, Tooltip


def _labels(widget):
    out = []
    for c in widget.winfo_children():
        if isinstance(c, tk.Label):
            out.append(c)
        out.extend(_labels(c))
    return out


class IconButtonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_button_shows_image_not_text(self):
        b = IconButton(self.root, "lock", None, tip="Khoá (l)", caption="Khoá")
        self.assertNotEqual(str(b.icon.cget("image")), "")
        self.assertIsNone(b.cap)
        for lb in _labels(b):
            self.assertEqual(lb.cget("text"), "")

    def test_set_icon_swaps_image(self):
        b = IconButton(self.root, "lock", None, tip="Khoá")
        before = str(b.icon.cget("image"))
        b.set_icon("unlock")
        self.assertNotEqual(str(b.icon.cget("image")), before)

    def test_missing_png_falls_back_to_text(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(icons, "ICON_DIR", Path(d)):
            b = IconButton(self.root, "lock", None, tip="Khoá")
            self.assertNotEqual(b.icon.cget("text"), "")
            b.set_icon("unlock")
            self.assertNotEqual(b.icon.cget("text"), "")

    def test_disabled_ignores_click(self):
        calls = []
        b = IconButton(self.root, "lock", lambda btn: calls.append(1), tip="Khoá")
        b._click(None)
        self.assertEqual(calls, [1])
        b.set_enabled(False)
        b._click(None)
        self.assertEqual(calls, [1])
        b.set_enabled(True)
        b._click(None)
        self.assertEqual(calls, [1, 1])

    def test_disabled_uses_muted_color_image(self):
        b = IconButton(self.root, "lock", None, tip="Khoá")
        normal = str(b.icon.cget("image"))
        b.set_enabled(False)
        self.assertNotEqual(str(b.icon.cget("image")), normal)
        b.set_enabled(True)
        self.assertEqual(str(b.icon.cget("image")), normal)

    def test_tooltip_delay_is_short(self):
        self.assertLessEqual(Tooltip.DELAY_MS, 200)

    def test_every_caller_name_resolves(self):
        names = ("kf_prev kf_next rot_ccw rot_cw zoom_in zoom_out pin pin_hidden keyframe collapse open search window "
                 "eye eye_off lock trash more copy add scan export settings keyboard display info filter fullscreen "
                 "menu save undo redo first last back10 fwd10 prev next play pause check link pinned cursor hand fit").split()
        for n in names:
            with self.subTest(name=n):
                b = IconButton(self.root, n, None, tip="x")
                b.set_icon(n)
                self.assertTrue(str(b.icon.cget("image")) or b.icon.cget("text"))

    def test_rot_ccw_is_flipped_rotate(self):
        a = IconButton(self.root, "rot_cw", None)
        b = IconButton(self.root, "rot_ccw", None)
        self.assertNotEqual(str(a.icon.cget("image")), str(b.icon.cget("image")))

    def test_size_picks_png_px(self):
        self.assertEqual([icons._px(s) for s in (12, 16, 17, 20, 21, 24, 30)], [16, 16, 20, 20, 24, 24, 24])

    def test_icon_image_none_when_missing(self):
        self.assertIsNotNone(icons.icon_image(self.root, "lock", 16, "#1F1F1F"))
        self.assertIsNone(icons.icon_image(self.root, "khong_co_icon", 16, "#1F1F1F"))


if __name__ == "__main__":
    unittest.main()
