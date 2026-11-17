import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.render import View, marker_radii  # noqa: E402


class PixelConventionTests(unittest.TestCase):
    """Như CVAT (design/cvat-api-notes.md, "Quy ước pixel"): pixel ảnh i phủ toạ độ [i, i+1), tâm ở i + 0,5."""

    @staticmethod
    def one_white_pixel():
        import numpy as np
        src = np.zeros((40, 40, 3), np.uint8)
        src[10, 10] = 255
        return src

    def test_image_pixel_covers_i_to_i_plus_1(self):
        import numpy as np
        from eyepin.render import warp_image
        v = View(0, 0, 8, 40, 40)
        dst = warp_image(self.one_white_pixel(), v, (320, 320), smooth=False, bg=(0, 0, 0))
        cols = np.where(dst[84, :, 0] > 0)[0].tolist()
        rows = np.where(dst[:, 84, 0] > 0)[0].tolist()
        self.assertEqual(cols, list(range(80, 88)))
        self.assertEqual(rows, list(range(80, 88)))
        self.assertEqual(v.to_frame(80, 80), (10.0, 10.0))

    def test_smoothed_pixel_peak_is_centered(self):
        import numpy as np
        from eyepin.render import warp_image
        dst = warp_image(self.one_white_pixel(), View(0, 0, 8, 40, 40), (320, 320), smooth=True, bg=(0, 0, 0))
        self.assertIn(int(np.argmax(dst[84, :, 0])), (83, 84))


class PreviewMarkerTests(unittest.TestCase):
    def test_preview_pins_are_sized_by_the_eye_width(self):
        """Mắt đang vẽ dở: điểm ghim to theo bề rộng mắt trên màn hình (dễ nắm để kéo), như điểm của nhãn thật."""
        from eyepin.geometry import MATTRAI, derive, four_in_box
        from eyepin.render import _draw_preview

        class Rec:
            def __init__(self):
                self.radii = []

            def poly(self, *a, **k):
                pass

            def circle(self, c, r, color, width=1, tag=None):
                if width < 0:
                    self.radii.append(r)

        pts = derive(MATTRAI, four_in_box(MATTRAI, (100, 100, 160, 120)))       # rộng 60 px ảnh = 180 px màn hình ở k = 3
        rec = Rec()
        _draw_preview(rec, View(0, 0, 3.0, 960, 460), pts)
        self.assertEqual(set(rec.radii), {round(marker_radii(180.0)[0])})


class ViewTests(unittest.TestCase):
    def test_zoom_keeps_the_point_under_the_cursor_fixed(self):
        v = View(100.0, 50.0, 2.0, 960, 460)
        before = v.to_frame(300, 200)
        z = v.zoomed_at(300, 200, 1.5)
        self.assertAlmostEqual(z.k, 3.0)
        after = z.to_frame(300, 200)
        self.assertAlmostEqual(before[0], after[0], places=6)
        self.assertAlmostEqual(before[1], after[1], places=6)

    def test_zoom_is_clamped(self):
        v = View(0, 0, 1.0, 960, 460)
        self.assertEqual(v.zoomed_at(0, 0, 1e6).k, 40.0)
        self.assertEqual(v.zoomed_at(0, 0, 1e-6).k, 0.2)

    def test_zoom_out_then_in_returns_to_start(self):
        v = View(100.0, 50.0, 2.0, 960, 460)
        back = v.zoomed_at(400, 100, 0.8).zoomed_at(400, 100, 1 / 0.8)
        self.assertAlmostEqual(back.k, v.k)
        self.assertAlmostEqual(back.x0, v.x0, places=6)
        self.assertAlmostEqual(back.y0, v.y0, places=6)

    def test_pan_moves_the_image_with_the_cursor(self):
        v = View(100.0, 50.0, 2.0, 960, 460)
        p = v.to_frame(300, 200)
        moved = v.panned(40, -10)
        sx, sy = moved.to_screen(p)
        self.assertEqual((sx, sy), (340, 190))

    def test_markers_stay_small_relative_to_the_eye(self):
        for eye_px in (60, 120, 200, 400, 1200):
            big, small = marker_radii(eye_px)
            self.assertLessEqual(big, 5.0)
            self.assertGreaterEqual(big, 2.0)
            self.assertLess(small, big)
            if eye_px >= 120:
                self.assertLess(2 * big, 0.12 * eye_px)       # đường kính điểm ghim dưới 12% bề rộng mắt


if __name__ == "__main__":
    unittest.main()
