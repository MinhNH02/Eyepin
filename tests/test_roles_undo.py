import itertools
import math
import os
import random
import shutil
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES, assign_roles, split_eyes  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402
from test_geometry import lens_eye  # noqa: E402

MATTRAI, MATPHAI = EYES["mattrai"], EYES["matphai"]


def four(spec, **kw):
    full = lens_eye(spec, 200, 180, 24, 7, **kw)
    return {i: full[i] for i in spec.pins}, full


class RolesTests(unittest.TestCase):
    def test_any_click_order_gives_the_same_assignment(self):
        for spec in EYES.values():
            truth, _ = four(spec, tilt_deg=8)
            for perm in itertools.permutations(list(truth.values())):
                got = assign_roles(spec, list(perm))
                self.assertEqual(got, truth)

    def test_tilted_and_foreshortened_eyes(self):
        for tilt in (-20, -8, 0, 12, 21):
            for sx in (1.0, 0.6):
                truth, _ = four(MATTRAI, tilt_deg=tilt, scale_x=sx)
                pts = list(truth.values())
                random.Random(tilt).shuffle(pts)
                got = assign_roles(MATTRAI, pts)
                for i in truth:
                    self.assertLess(math.dist(got[i], truth[i]), 1e-9, msg=f"tilt {tilt} sx {sx} point {i}")

    def test_top_of_eye_clicked_first_is_still_the_upper_lid(self):
        # ví dụ của người dùng: bấm điểm trên cùng của mắt trước (định là 14)
        truth, _ = four(MATTRAI)
        order = [truth[16], truth[14], truth[18], truth[20]]
        got = assign_roles(MATTRAI, order)
        self.assertEqual(got[16], truth[16])
        self.assertEqual(got[14], truth[14])

    def test_closed_eye_is_accepted(self):
        pts = [(100, 100), (140, 100), (120, 100), (120, 100.0)]
        got = assign_roles(MATTRAI, pts)
        self.assertEqual((got[14], got[18]), ((100, 100), (140, 100)))

    def test_rejects_points_that_do_not_look_like_an_eye(self):
        with self.assertRaises(ValueError):
            assign_roles(MATTRAI, [(100, 100), (103, 100), (101, 95), (101, 105)])        # hai khoé quá gần
        with self.assertRaises(ValueError):
            assign_roles(MATTRAI, [(100, 100), (140, 100), (99, 95), (101, 105)])         # giữa mí sát khoé
        with self.assertRaises(ValueError):
            assign_roles(MATTRAI, [(0, 0), (1, 1)])

    def test_split_eyes_by_x_in_any_order(self):
        a, _ = four(MATTRAI)
        b = {i: (x + 150, y) for i, (x, y) in four(MATPHAI)[0].items()}
        pts = list(a.values()) + list(b.values())
        random.Random(1).shuffle(pts)
        left, right = split_eyes(pts)
        self.assertEqual(sorted(left), sorted(a.values()))
        self.assertEqual(sorted(right), sorted(b.values()))


class UndoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_undo_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def pin(self, s, frame):
        truth = T.pins_at(frame)
        clicks = [truth[i] for spec in EYES.values() for i in spec.pins]
        random.Random(frame).shuffle(clicks)
        return s.add_pin_free(frame, clicks)

    def test_unordered_clicks_make_the_same_pin_as_ordered(self):
        s = Session(self.dir)
        self.pin(s, 0)
        truth = T.pins_at(0)
        for spec in EYES.values():
            for i in spec.pins:
                self.assertLess(math.dist(s.pins[0][i], truth[i]), 1e-6)

    def test_stray_clicks_on_one_eye_are_rejected_and_create_no_pin(self):
        s = Session(self.dir)
        left, _ = four(MATTRAI)
        right = four(MATPHAI)[0]
        r = [(x + 100, y) for x, y in right.values()]
        clicks = list(left.values()) + [r[0], r[1], (500.0, 30.0), (30.0, 300.0)]   # chỉ 2 điểm mắt phải + 2 điểm lạc
        with self.assertRaises(ValueError):
            s.add_pin_free(0, clicks)
        self.assertEqual((s.pins, s.pending), ({}, {}))

    def test_vertical_eye_is_rejected(self):
        with self.assertRaises(ValueError):
            assign_roles(MATTRAI, [(100, 100), (103, 100), (101, 95), (101, 105)])

    def test_bad_clicks_do_not_create_a_pin(self):
        s = Session(self.dir)
        with self.assertRaises(ValueError):
            s.add_pin_free(0, [(10, 10)] * 8)
        self.assertEqual(s.pins, {})

    def test_undo_and_redo_restore_pins_and_labels(self):
        s = Session(self.dir)
        self.pin(s, 0)
        self.pin(s, 30)
        labels_two = {f: dict(r.points) for f, r in s.labels.items()}
        self.assertTrue(s.undo())
        self.assertEqual(sorted(s.pins), [0])
        self.assertEqual(sorted(s.labels), list(range(T.N)))        # frame 0 còn bám tới hết job
        self.assertTrue(s.redo())
        self.assertEqual(sorted(s.pins), [0, 30])
        self.assertEqual({f: dict(r.points) for f, r in s.labels.items()}, labels_two)

    def test_undo_a_moved_point(self):
        s = Session(self.dir)
        self.pin(s, 0)
        before = s.pins[0][14]
        s.move_point(0, 14, (before[0] + 8, before[1]))
        self.assertTrue(s.undo())
        self.assertEqual(s.pins[0][14], before)

    def test_drag_on_a_tracked_frame_pins_it_in_one_undo_step(self):
        s = Session(self.dir)
        self.pin(s, 0)
        was = s.labels[10].points[16]
        self.assertTrue(s.drag_point(10, 16, (was[0] + 5, was[1])))
        self.assertIn(10, s.pins)
        self.assertEqual(s.pins[10][16], (was[0] + 5, was[1]))
        self.assertEqual(s.pins[10][14], s.labels[10].points[14])
        self.assertTrue(s.undo())
        self.assertEqual(sorted(s.pins), [0])
        with self.assertRaises(ValueError):
            Session(self.dir).drag_point(3, 16, (1, 1))

    def test_drag_whole_eye_moves_all_its_points(self):
        s = Session(self.dir)
        self.pin(s, 0)
        before = {i: s.labels[10].points[i] for i in MATTRAI.ids}
        s.drag_points(10, {i: (x + 4, y - 2) for i, (x, y) in before.items()})
        for i, (x, y) in before.items():
            self.assertEqual(s.pins[10][i], (x + 4, y - 2))
        self.assertTrue(s.undo())
        self.assertEqual(sorted(s.pins), [0])

    def test_undo_a_removed_pin(self):
        s = Session(self.dir)
        self.pin(s, 0)
        s.remove_pin(0)
        self.assertEqual(s.pins, {})
        self.assertTrue(s.undo())
        self.assertIn(0, s.pins)

    def test_new_change_clears_redo_and_empty_undo_is_false(self):
        s = Session(self.dir)
        self.assertFalse(s.undo())
        self.assertFalse(s.redo())
        self.pin(s, 0)
        s.undo()
        self.pin(s, 5)
        self.assertFalse(s.redo())


if __name__ == "__main__":
    unittest.main()
