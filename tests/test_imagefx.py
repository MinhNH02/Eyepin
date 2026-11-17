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


class GridTests(unittest.TestCase):
    @staticmethod
    def view(x0, y0, k):
        from eyepin.render import View
        return View(x0, y0, k, 400, 300)

    def test_grid_step_thins_out(self):
        self.assertEqual(imagefx.grid_step(100, 1.0), 100)
        self.assertEqual(imagefx.grid_step(1, 8.0), 1)
        self.assertEqual(imagefx.grid_step(1, 1.0), 10)
        self.assertEqual(imagefx.grid_step(1, 0.2), 50)
        self.assertEqual(imagefx.grid_step(5, 0.5), 25)

    def test_grid_lines_on_pixel_edges(self):
        img = np.zeros((300, 400, 3), np.uint8)
        self.assertEqual(imagefx.draw_grid(img, self.view(0, 0, 8), 40, 30, 5, "White", 100), 5)
        self.assertTrue((img[0:240, 40] == 255).all())          # đường dọc tại u = 5: mép trái pixel 5
        self.assertTrue((img[1:40, 41] == 0).all())             # cột kế bên đen (trừ chỗ đường ngang cắt qua: hàng 0, 40, 80…)
        self.assertTrue((img[40, 0:320] == 255).all())          # đường ngang tại v = 5
        self.assertEqual(img[100, 350].tolist(), [0, 0, 0])      # ngoài ảnh: không vẽ
        self.assertEqual(img[260, 100].tolist(), [0, 0, 0])

    def test_grid_line_column_is_floor_of_screen_position(self):
        img = np.zeros((300, 400, 3), np.uint8)
        imagefx.draw_grid(img, self.view(0.3, 0, 8), 40, 30, 5, "Red", 100)
        self.assertEqual(img[100, 37].tolist(), [0, 0, 255])     # (5 − 0,3)·8 = 37,6 → cột 37; màu BGR

    def test_grid_opacity_blends(self):
        img = np.zeros((300, 400, 3), np.uint8)
        imagefx.draw_grid(img, self.view(0, 0, 8), 40, 30, 5, "White", 50)
        self.assertIn(int(img[100, 40, 0]), (127, 128))

    def test_zoomed_out_size_one_does_not_gray_the_image(self):
        img = np.zeros((300, 400, 3), np.uint8)
        self.assertEqual(imagefx.draw_grid(img, self.view(0, 0, 0.2), 1024, 576, 1, "White", 100), 50)
        region = img[0:116, 0:205]
        self.assertLess(float((region.max(axis=2) > 0).mean()), 0.25)

    def test_tiny_grid_turns_off_smoothing(self):
        from eyepin.render import Look, View, render_base

        class Stub:
            width, height = 40, 30

            def bgr(self, f):
                rng = np.random.default_rng(0)
                return rng.integers(0, 255, (30, 40, 3), dtype=np.uint8)

        v = View(0, 0, 8, 320, 240)
        on = render_base(Stub(), 0, (320, 240), v, Look(grid=True, grid_size=2, smooth=True, grid_opacity=0))
        sharp = render_base(Stub(), 0, (320, 240), v, Look(smooth=False))
        self.assertTrue((on == sharp).all())                     # Opacity 0: chỉ còn ảnh, và ảnh không làm mịn


class ReadoutTests(unittest.TestCase):
    EYE = {14: (100.0, 100.0), 18: (160.0, 100.0), 16: (130.0, 90.0)}

    def test_readout_coordinates(self):
        self.assertEqual(imagefx.readout((412.371, 288.049), 1024, 576, None), "x 412,37 · y 288,05")

    def test_readout_outside_image(self):
        self.assertEqual(imagefx.readout((-3, 10), 1024, 576, None), "ngoài ảnh")
        self.assertEqual(imagefx.readout((1024.0, 10), 1024, 576, None), "ngoài ảnh")      # pixel cuối là [1023, 1024)

    def test_readout_nearest_point_and_eye_width(self):
        self.assertEqual(imagefx.readout((130, 93.2), 1024, 576, self.EYE),
                         "x 130,00 · y 93,20 · tới điểm 16: 3,2 px (5% bề rộng mắt)")

    def test_readout_without_both_corners(self):
        self.assertEqual(imagefx.readout((130, 93.2), 1024, 576, {16: (130.0, 90.0)}),
                         "x 130,00 · y 93,20 · tới điểm 16: 3,2 px")

    def test_readout_empty_points(self):
        self.assertEqual(imagefx.readout((130, 93.2), 1024, 576, {}), "x 130,00 · y 93,20")


class AxisGuideTests(unittest.TestCase):
    @staticmethod
    def spec():
        from eyepin.geometry import MATTRAI
        return MATTRAI

    def find(self, segs, x0):
        hits = [s for s in segs[1:] if abs(s[0][0] - x0) < 1e-6]
        self.assertEqual(len(hits), 1, segs)
        return hits[0]

    def test_axis_guides_ticks_at_guideline_ratios(self):
        pts = {14: (100.0, 100.0), 18: (160.0, 100.0), 16: (130.0, 90.0), 20: (130.0, 110.0)}
        segs = imagefx.axis_guides(self.spec(), pts)
        self.assertEqual(len(segs), 7)                           # trục + 3 vạch mí trên (0,21 · 0,48 · 0,76) + 3 vạch mí dưới (0,24 · 0,50 · 0,76)
        self.assertEqual(segs[0], ((100.0, 100.0), (160.0, 100.0)))
        up = self.find(segs, 128.8)                              # 0,48 · 60 = 28,8; vạch dài 0,35 · 60 = 21 về phía điểm 16
        self.assertAlmostEqual(up[1][0], 128.8)
        self.assertAlmostEqual(up[1][1], 79.0)
        lo = self.find(segs, 130.0)
        self.assertAlmostEqual(lo[1][1], 121.0)

    def test_axis_guides_follow_a_slanted_eye(self):
        pts = {14: (100.0, 100.0), 18: (160.0, 130.0), 16: (128.0, 105.0)}
        segs = imagefx.axis_guides(self.spec(), pts)
        ax, ay = 60.0, 30.0
        for (a, b) in segs[1:]:
            self.assertLess(abs((b[0] - a[0]) * ax + (b[1] - a[1]) * ay), 1e-6)

    def test_axis_guides_degenerate(self):
        self.assertIsNone(imagefx.axis_guides(self.spec(), {14: (100.0, 100.0), 18: (100.0, 100.0)}))
        self.assertIsNone(imagefx.axis_guides(self.spec(), {14: (100.0, 100.0), 16: (130.0, 90.0)}))


class MigrateTests(unittest.TestCase):
    def test_migrate_drops_old_keys_and_reports_changed_values(self):
        d = {"brightness": 30, "contrast": 1.2, "saturation": 1.0, "size": 1.5}
        self.assertTrue(imagefx.migrate_display(d))
        self.assertEqual(d, {"size": 1.5})

    def test_migrate_is_silent_when_old_values_were_defaults(self):
        d = {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0}
        self.assertFalse(imagefx.migrate_display(d))
        self.assertEqual(d, {})

    def test_migrate_keeps_new_keys(self):
        d = {"brightness_pct": 150.0, "gamma": 1.4}
        self.assertFalse(imagefx.migrate_display(d))
        self.assertEqual(d, {"brightness_pct": 150.0, "gamma": 1.4})

    def test_store_keys_differ_from_old_keys(self):
        self.assertEqual(imagefx.STORE_KEYS, {"brightness": "brightness_pct", "contrast": "contrast_pct", "saturation": "saturation_pct"})


if __name__ == "__main__":
    unittest.main()
