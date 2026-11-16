import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES, MATPHAI, MATTRAI, derive, estimate_hidden_corner, four_in_box, validate_four  # noqa: E402


def lens_eye(spec, cx, cy, rx, ry, tilt_deg=0.0, scale_x=1.0):
    """Mắt giả hình thấu kính: hai mí là parabol đối xứng; có thể xoay và co theo trục x (như quay đầu)."""
    t = math.radians(tilt_deg)
    pts = {}
    for pid in spec.ids:
        if pid in (spec.first, spec.last):
            u, h = (0.0, 0.0) if pid == spec.first else (1.0, 0.0)
        else:
            if pid == spec.up:
                u, sign = spec.up_mid, -1
            elif pid == spec.lo:
                u, sign = spec.lo_mid, 1
            else:
                which, u = spec.derived[pid]
                sign = -1 if which == "up" else 1
            h = sign * ry * 4 * u * (1 - u)
        x, y = (u - 0.5) * 2 * rx, h
        pts[pid] = (cx + scale_x * (x * math.cos(t) - y * math.sin(t)), cy + x * math.sin(t) + y * math.cos(t))
    return pts


class DeriveTests(unittest.TestCase):
    def test_exact_on_parabolic_eye(self):
        for spec in EYES.values():
            full = lens_eye(spec, 300, 200, 20, 7, tilt_deg=6)
            got = derive(spec, {i: full[i] for i in spec.pins})
            for pid in spec.ids:
                self.assertAlmostEqual(math.dist(got[pid], full[pid]), 0, delta=1e-6, msg=f"{spec.label} {pid}")

    def test_closed_eye_gives_a_line(self):
        pins = {14: (100, 100), 18: (140, 100), 16: (119.2, 100), 20: (120, 100)}
        got = derive(MATTRAI, pins)
        self.assertTrue(all(abs(got[i][1] - 100) < 1e-6 for i in MATTRAI.ids))

    def test_pins_are_kept_untouched(self):
        pins = {22: (10, 10), 26: (50, 12), 24: (30, 5), 28: (30, 18)}
        got = derive(MATPHAI, pins)
        for i in pins:
            self.assertEqual(got[i], pins[i])

    def test_rejects_coincident_corners(self):
        with self.assertRaises(ValueError):
            derive(MATTRAI, {14: (1, 1), 18: (1, 1), 16: (1, 0), 20: (1, 2)})


class HiddenCornerTests(unittest.TestCase):
    def test_recovers_corner_on_symmetric_eye(self):
        for spec in EYES.values():
            full = lens_eye(spec, 300, 200, 20, 7, tilt_deg=-5)
            for hidden in (spec.first, spec.last):
                vis = {i: full[i] for i in spec.pins if i != hidden}
                est = estimate_hidden_corner(spec, vis, hidden)
                self.assertLess(math.dist(est, full[hidden]), 0.5, msg=f"{spec.label} {hidden}")

    def test_survives_head_turn_foreshortening(self):
        # co theo trục x rồi lấy trung điểm: tính chất affine, nên vẫn khôi phục được
        for spec in EYES.values():
            full = lens_eye(spec, 300, 200, 20, 7, tilt_deg=0, scale_x=0.55)
            hidden = spec.last
            est = estimate_hidden_corner(spec, {i: full[i] for i in spec.pins if i != hidden}, hidden)
            self.assertLess(math.dist(est, full[hidden]), 0.5)

    def test_rejects_non_corner(self):
        with self.assertRaises(ValueError):
            estimate_hidden_corner(MATTRAI, {14: (0, 0), 16: (1, 1), 20: (1, 2), 18: (3, 3)}, 16)


class DrawTemplateTests(unittest.TestCase):
    def test_four_in_box_puts_corners_on_the_sides_and_lids_on_top_and_bottom(self):
        four = four_in_box(MATPHAI, (110.0, 90.0, 10.0, 70.0))          # góc nào trước cũng được
        self.assertEqual(four[MATPHAI.first], (10.0, 80.0))
        self.assertEqual(four[MATPHAI.last], (110.0, 80.0))
        self.assertEqual(four[MATPHAI.up], (10.0 + MATPHAI.up_mid * 100, 70.0))
        self.assertEqual(four[MATPHAI.lo], (10.0 + MATPHAI.lo_mid * 100, 90.0))
        validate_four(MATPHAI, four)

    def test_validate_four_keeps_roles_and_rejects_bad_shapes(self):
        good = four_in_box(MATTRAI, (0.0, 0.0, 60.0, 20.0))
        validate_four(MATTRAI, good)
        for change, text in (({MATTRAI.up: (30.0, 25.0)}, "nằm dưới"), ({MATTRAI.up: (90.0, 0.0)}, "ngoài khoảng"),
                             ({MATTRAI.first: (70.0, 10.0)}, "bên trái"), ({MATTRAI.last: (5.0, 10.0)}, "gần nhau")):
            with self.assertRaises(ValueError) as cm:
                validate_four(MATTRAI, {**good, **change})
            self.assertIn(text, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
