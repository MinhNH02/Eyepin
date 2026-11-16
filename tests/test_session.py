import math
import os
import shutil
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.preview import position_at  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402


class SessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_frames_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def pin_both(self, s, frame):
        truth = T.pins_at(frame)
        done = False
        for label, spec in EYES.items():
            done = s.add_pin(frame, label, {i: truth[i] for i in spec.pins})
        return done

    def test_pin_needs_both_eyes(self):
        s = Session(self.dir)
        spec = EYES["mattrai"]
        truth = T.pins_at(0)
        self.assertFalse(s.add_pin(0, "mattrai", {i: truth[i] for i in spec.pins}))
        self.assertEqual(s.pins, {})
        self.assertTrue(s.add_pin(0, "matphai", {i: truth[i] for i in EYES["matphai"].pins}))
        self.assertIn(0, s.pins)

    def test_labels_follow_the_eye_and_frames_before_first_pin_are_empty(self):
        s = Session(self.dir)
        self.pin_both(s, 10)
        self.assertNotIn(5, s.labels)
        worst = max(max(math.dist(s.labels[f].points[i], T.pins_at(f)[i]) for i in s.labels[f].points)
                    for f in range(10, T.N))
        self.assertLess(worst, 1.0)

    def test_export_roundtrips_through_the_xml_reader_and_matches_labels(self):
        s = Session(self.dir)
        self.pin_both(s, 0)
        out = os.path.join(self.dir, "out.xml")
        info = s.export(out)
        self.assertLess(info["keyframes"], 10)              # đường đi gồm vài đoạn thẳng, không cần 60 keyframe
        ann = cvatxml.parse(out)
        for label, spec in EYES.items():
            tr = ann.tracks[label][0]
            for k in tr.keys.values():
                self.assertEqual(len(k.points), 8)
            for f in range(T.N):
                k = position_at(tr.keys, f, spec.ids)
                for i in spec.ids:
                    self.assertLessEqual(math.dist(k.points[i].xy, s.labels[f].points[i]), 2.0 + 0.02)

    def test_moving_a_pin_changes_only_later_frames(self):
        s = Session(self.dir)
        self.pin_both(s, 0)
        self.pin_both(s, 30)
        before = {f: dict(s.labels[f].points) for f in range(30)}
        s.move_point(30, 14, (s.pins[30][14][0] + 6, s.pins[30][14][1]))
        for f in range(30):
            self.assertEqual(s.labels[f].points, before[f])
        self.assertAlmostEqual(s.labels[30].points[14][0], s.pins[30][14][0], delta=1e-6)

    def test_remove_pin_clears_labels(self):
        s = Session(self.dir)
        self.pin_both(s, 0)
        s.remove_pin(0)
        self.assertEqual(s.labels, {})

    def test_image_cache_is_bounded(self):
        s = Session(self.dir)
        for f in range(T.N):
            s.bgr(f)
        self.assertLessEqual(len(s._cache), 40)

    def test_export_without_pins_is_refused(self):
        with self.assertRaises(ValueError):
            Session(self.dir).export(os.path.join(self.dir, "x.xml"))


if __name__ == "__main__":
    unittest.main()
