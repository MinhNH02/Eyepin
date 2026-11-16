import math
import os
import random
import shutil
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml  # noqa: E402
from eyepin.geometry import EYES, MATPHAI, MATTRAI, assign_three, hidden_neighbours, split_seven  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402
from test_geometry import lens_eye  # noqa: E402

MATTRAI, MATPHAI = EYES["mattrai"], EYES["matphai"]


def pins4(spec, cx=200, tilt=0.0, sx=1.0):
    full = lens_eye(spec, cx, 180, 24, 7, tilt_deg=tilt, scale_x=sx)
    return {i: full[i] for i in spec.pins}, full


class AssignThreeTests(unittest.TestCase):
    def test_any_order_hides_either_corner(self):
        for spec in EYES.values():
            truth, _ = pins4(spec, tilt=5, sx=0.7)
            for hidden in (spec.first, spec.last):
                vis = [truth[i] for i in spec.pins if i != hidden]
                random.Random(hidden).shuffle(vis)
                known, h, est = assign_three(spec, vis)
                self.assertEqual(h, hidden)
                self.assertEqual(set(known), set(spec.pins) - {hidden})
                self.assertLess(math.dist(est, truth[hidden]), 0.6)

    def test_neighbours_of_the_hidden_corner(self):
        self.assertEqual(sorted(hidden_neighbours(MATTRAI, 18)), [17, 19])
        self.assertEqual(sorted(hidden_neighbours(MATTRAI, 14)), [15, 21])
        self.assertEqual(sorted(hidden_neighbours(MATPHAI, 26)), [25, 27])
        self.assertEqual(sorted(hidden_neighbours(MATPHAI, 22)), [23, 29])

    def test_rejects_three_unrelated_points(self):
        with self.assertRaises(ValueError):
            assign_three(MATTRAI, [(0, 0), (100, 100), (3, 200)])
        with self.assertRaises(ValueError):
            assign_three(MATTRAI, [(100, 100), (101, 100), (102, 100)])


class SplitSevenTests(unittest.TestCase):
    def test_both_splits_are_found(self):
        for hidden_eye, hidden_pid in (("mattrai", 18), ("matphai", 22)):
            a, _ = pins4(MATTRAI, cx=150)
            b, _ = pins4(MATPHAI, cx=330)
            spec_h = EYES[hidden_eye]
            hide = a if hidden_eye == "mattrai" else b
            full = b if hidden_eye == "mattrai" else a
            pts = [hide[i] for i in spec_h.pins if i != hidden_pid] + list(full.values())
            random.Random(2).shuffle(pts)
            r = split_seven(pts)
            self.assertEqual(r["partial"][0], hidden_eye)
            self.assertEqual(r["partial"][2], hidden_pid)
            self.assertEqual(r["full"][0], "matphai" if hidden_eye == "mattrai" else "mattrai")

    def test_wrong_count_and_garbage_are_rejected(self):
        with self.assertRaises(ValueError):
            split_seven([(1, 1)] * 6)
        with self.assertRaises(ValueError):
            split_seven([(100 + k, 100) for k in range(7)])


class SessionHiddenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_hidden_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def hidden_clicks(self, frame=0, hidden=18):
        truth = T.pins_at(frame)
        pts = [truth[i] for i in MATTRAI.pins if i != hidden] + [truth[i] for i in MATPHAI.pins]
        random.Random(5).shuffle(pts)
        return pts, truth

    def test_hidden_pin_flags_the_corner_and_its_neighbours_and_estimates_it(self):
        s = Session(self.dir)
        pts, truth = self.hidden_clicks()
        info = s.add_pin_hidden(0, pts)
        self.assertEqual((info["eye"], info["hidden"]), ("mattrai", 18))
        self.assertEqual(sorted(info["occluded"]), [17, 18, 19])
        self.assertEqual({i for i, k in s.flags[0].items() if k == "occluded"}, {17, 18, 19})
        self.assertLess(math.dist(s.pins[0][18], truth[18]), 1.5)
        self.assertEqual(set(s.estimates[0]), {17, 18, 19})

    def test_moving_an_estimated_point_makes_it_hand_placed_but_keeps_occluded(self):
        s = Session(self.dir)
        s.add_pin_hidden(0, self.hidden_clicks()[0])
        x, y = s.pins[0][18]
        s.move_point(0, 18, (x + 3, y))
        self.assertNotIn(18, s.estimates[0])
        self.assertEqual(s.flags[0][18], "occluded")

    def test_flags_follow_the_left_pin_and_export_carries_them(self):
        s = Session(self.dir)
        s.add_pin_hidden(0, self.hidden_clicks()[0])
        truth = T.pins_at(30)
        s.add_pin_free(30, [truth[i] for spec in EYES.values() for i in spec.pins])      # frame 30: mắt thấy đủ
        self.assertEqual(s.flags_at(15).get(18), "occluded")
        self.assertEqual(s.flags_at(31), {})
        out = os.path.join(self.dir, "o.xml")
        s.export(out)
        tr = cvatxml.parse(out).tracks["mattrai"][0]
        self.assertTrue(tr.keys[0].points[18].occluded)
        self.assertFalse(tr.keys[0].points[16].occluded)
        self.assertFalse(tr.keys[30].points[18].occluded)
        from eyepin.preview import position_at
        self.assertTrue(position_at(tr.keys, 15, MATTRAI.ids).points[18].occluded)       # chép từ keyframe bên trái

    def test_toggle_flag_and_undo_it(self):
        s = Session(self.dir)
        s.add_pin_free(0, [T.pins_at(0)[i] for spec in EYES.values() for i in spec.pins])
        self.assertEqual(s.toggle_flag(0, 16, "occluded"), "occluded")
        self.assertEqual(s.toggle_flag(0, 16, "outside"), "outside")
        self.assertIsNone(s.toggle_flag(0, 16, "outside"))
        self.assertEqual(s.toggle_flag(5, 16, "occluded"), "occluded")     # frame tool tính: như CVAT, thành keyframe của riêng mắt đó
        self.assertEqual((s.eye_keyframes("mattrai"), s.eye_keyframes("matphai")), ([0, 5], [0]))
        self.assertTrue(s.undo())                                            # một bước hoàn tác bỏ cả keyframe lẫn cờ
        self.assertEqual(s.eye_keyframes("mattrai"), [0])
        s.toggle_flag(0, 14, "occluded")
        self.assertTrue(s.undo())
        self.assertNotIn(14, s.flags[0])

    def test_flags_follow_each_eyes_own_keyframes(self):
        from eyepin.preview import position_at
        s = Session(self.dir)
        s.add_pin_free(0, [T.pins_at(0)[i] for spec in EYES.values() for i in spec.pins])
        s.toggle_flag(0, 16, "occluded")
        s.pin_eye(30, "matphai", {i: s.points_at(30)[i] for i in MATPHAI.pins})       # chỉ mắt phải có keyframe ở frame 30
        self.assertEqual(s.flags_at(40).get(16), "occluded")                          # cờ mắt trái vẫn theo keyframe 0 của chính nó
        tr = s.build_tracks()["mattrai"]
        self.assertTrue(position_at(tr.keys, 40, MATTRAI.ids).points[16].occluded)    # file xuất cũng vậy

    def test_flag_on_a_tool_frame_keyframes_only_that_eye_and_keeps_inherited_flags(self):
        s = Session(self.dir)
        s.add_pin_free(0, [T.pins_at(0)[i] for spec in EYES.values() for i in spec.pins])
        s.toggle_flag(0, 23, "occluded")
        self.assertEqual(s.toggle_flag(5, 22, "outside"), "outside")
        self.assertEqual((s.eye_keyframes("matphai"), s.eye_keyframes("mattrai")), ([0, 5], [0]))
        self.assertEqual((s.flags_at(5).get(22), s.flags_at(5).get(23)), ("outside", "occluded"))
        self.assertTrue(s.undo())
        self.assertEqual(s.eye_keyframes("matphai"), [0])
        self.assertIsNone(s.flags_at(5).get(22))
        self.assertIsNone(Session(self.dir).toggle_flag(3, 16, "occluded"))           # chưa có nhãn: không làm gì

    def test_toggle_eye_flag_marks_or_clears_all_eight_points(self):
        s = Session(self.dir)
        s.add_pin_free(0, [T.pins_at(0)[i] for spec in EYES.values() for i in spec.pins])
        self.assertEqual(s.toggle_eye_flag(0, "matphai", "occluded"), "occluded")
        self.assertEqual({i for i, k in s.flags_at(0).items() if k == "occluded"}, set(MATPHAI.ids))
        self.assertIsNone(s.toggle_eye_flag(0, "matphai", "occluded"))
        self.assertEqual(s.flags_at(0), {})
        self.assertEqual(s.toggle_eye_flag(8, "mattrai", "outside"), "outside")       # frame tool tính: thành keyframe của mắt đó
        self.assertEqual(s.eye_keyframes("mattrai"), [0, 8])
        self.assertEqual(s.flags_at(12), {i: "outside" for i in MATTRAI.ids})

    def test_undo_restores_a_hidden_pin_completely(self):
        s = Session(self.dir)
        s.add_pin_hidden(0, self.hidden_clicks()[0])
        s.remove_pin(0)
        self.assertTrue(s.undo())
        self.assertEqual(sorted(s.flags[0]), [17, 18, 19])
        self.assertEqual(sorted(s.estimates[0]), [17, 18, 19])


if __name__ == "__main__":
    unittest.main()
