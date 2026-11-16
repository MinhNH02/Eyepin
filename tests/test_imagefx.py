"""Chỉnh màu ảnh nền như hộp Image setups của CVAT (thang 50–200%, gamma 0,2–2,6) và đổi giá trị đã lưu theo thang cũ."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import imagefx  # noqa: E402


def gray(v):
    return np.full((2, 2, 3), v, np.uint8)


def bgr(b, g, r):
    a = np.zeros((2, 2, 3), np.uint8)
    a[...] = (b, g, r)
    return a


class ColorTests(unittest.TestCase):
    def test_defaults_return_the_same_array(self):
        a = gray(100)
        self.assertIs(imagefx.apply_color(a, 100, 100, 100, 1.0), a)

    def test_brightness_multiplies_and_clips(self):
        self.assertEqual(int(imagefx.apply_color(gray(100), 150, 100, 100, 1.0)[0, 0, 0]), 150)
        self.assertEqual(int(imagefx.apply_color(gray(200), 200, 100, 100, 1.0)[0, 0, 0]), 255)

    def test_contrast_around_mid_gray(self):
        self.assertEqual(int(imagefx.apply_color(gray(100), 100, 200, 100, 1.0)[0, 0, 0]), 72)

    def test_saturation_zero_is_gray_by_luminance(self):
        out = imagefx.apply_color(bgr(0, 0, 200), 100, 100, 0, 1.0)
        self.assertEqual(out[0, 0].tolist(), [43, 43, 43])

    def test_saturation_max_clips_both_ends(self):
        out = imagefx.apply_color(bgr(50, 50, 200), 100, 100, 300, 1.0)
        self.assertEqual(int(out[0, 0, 2]), 255)                 # R
        self.assertEqual(int(out[0, 0, 1]), 0)                   # G
        self.assertEqual(out.dtype, np.uint8)

    def test_gamma_uses_one_over_gamma(self):
        self.assertEqual(int(imagefx.apply_color(gray(64), 100, 100, 100, 2.0)[0, 0, 0]), 128)
        self.assertEqual(int(imagefx.apply_color(gray(128), 100, 100, 100, 0.5)[0, 0, 0]), 64)

    def test_gamma_runs_before_brightness(self):
        self.assertEqual(int(imagefx.apply_color(gray(64), 50, 100, 100, 2.0)[0, 0, 0]), 64)

    def test_shape_is_kept(self):
        a = np.zeros((5, 7, 3), np.uint8)
        self.assertEqual(imagefx.apply_color(a, 120, 80, 150, 1.4).shape, (5, 7, 3))


class MigrateTests(unittest.TestCase):
    def test_migrate_drops_old_scale(self):
        d = {"brightness": 30, "contrast": 1.2, "saturation": 1.0, "size": 1.5}
        self.assertTrue(imagefx.migrate_display(d))
        self.assertEqual(d, {"size": 1.5, "color_scale": "cvat"})

    def test_migrate_keeps_new_scale(self):
        d = {"brightness": 150, "color_scale": "cvat"}
        self.assertFalse(imagefx.migrate_display(d))
        self.assertEqual(d, {"brightness": 150, "color_scale": "cvat"})

    def test_migrate_marks_an_empty_dict(self):
        d = {}
        self.assertFalse(imagefx.migrate_display(d))
        self.assertEqual(d, {"color_scale": "cvat"})


if __name__ == "__main__":
    unittest.main()
