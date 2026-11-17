import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from eyepin.tracking import pin_jump, propagate, reduce_keyframes, track_backward, track_forward  # noqa: E402
from test_geometry import lens_eye  # noqa: E402

W, H, N = 320, 160, 60


def shift_at(t):
    """Đường đi của đầu: đứng yên, chạy sang phải, rồi quay lại và đi xuống (hai đoạn thẳng gấp khúc)."""
    if t < 20:
        return 0.0, 0.0
    if t < 40:
        return 1.5 * (t - 20), 0.0
    return 30 - 1.0 * (t - 40), 0.6 * (t - 40)


def render(t, seed=7):
    rng = np.random.default_rng(seed)
    bg = cv2_blur(rng.integers(0, 255, (H, W)).astype(np.float32))
    dx, dy = shift_at(t)
    img = bg.copy()
    for cx in (110, 210):
        yy, xx = np.mgrid[0:H, 0:W]
        d = ((xx - (cx + dx)) / 26.0) ** 2 + ((yy - (80 + dy)) / 9.0) ** 2
        img = np.where(d < 1, 30 + 60 * d, img)
        img += 8 * np.sin((xx - dx) / 3.0)[None, :][0] * (d < 1.8) * (d >= 1)
    return np.clip(img, 0, 255).astype(np.uint8)


def cv2_blur(a):
    import cv2
    return cv2.GaussianBlur(a, (0, 0), 2.0)


def pins_at(t):
    dx, dy = shift_at(t)
    pts = {}
    for spec, cx in zip(EYES.values(), (110, 210)):
        pts.update(lens_eye(spec, cx + dx, 80 + dy, 24, 7))
    return pts


class TrackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = [render(t) for t in range(N)]

    def get(self, f):
        return self.frames[f]

    def test_follows_motion_within_one_pixel(self):
        res = track_forward(self.get, 0, N, pins_at(0))
        worst = 0.0
        for r in res:
            truth = pins_at(r.frame)
            worst = max(worst, max(math.dist(r.points[i], truth[i]) for i in truth))
        self.assertLess(worst, 1.0)
        self.assertGreater(min(r.score for r in res), 0.8)

    def test_forward_only_rule(self):
        pins = {0: pins_at(0), 30: pins_at(30)}
        labels, arrival = propagate(self.get, N, pins)
        self.assertEqual(sorted(labels), list(range(N)))
        before = [labels[f].points for f in range(30)]
        pins2 = {0: pins_at(0), 30: {i: (x + 5, y + 5) for i, (x, y) in pins_at(30).items()}}
        labels2, _ = propagate(self.get, N, pins2)
        for f in range(30):                              # sửa frame ghim 30 không làm đổi frame nào trước nó
            self.assertEqual(labels2[f].points, before[f - 0] if False else labels[f].points)
        self.assertNotEqual(labels2[31].points[14], labels[31].points[14])    # còn frame sau thì đổi

    def test_frames_before_first_pin_have_no_label(self):
        labels, _ = propagate(self.get, N, {10: pins_at(10)})
        self.assertNotIn(5, labels)
        self.assertIn(10, labels)

    def test_pin_jump_reports_drift(self):
        pins = {0: pins_at(0), 30: {i: (x + 4, y) for i, (x, y) in pins_at(30).items()}}
        _, arrival = propagate(self.get, N, pins)
        self.assertAlmostEqual(pin_jump(arrival[30], pins[30]), 4.0, delta=1.0)

    def test_backward_follows_motion_and_keeps_real_frame_numbers(self):
        res = track_backward(self.get, 50, 15, pins_at(50))
        self.assertEqual([r.frame for r in res], list(range(50, 14, -1)))      # 50, 49, ..., 15 (tính cả frame cuối)
        self.assertEqual(res[0].points, pins_at(50))
        self.assertEqual(res[0].score, 1.0)
        worst = max(math.dist(r.points[i], pins_at(r.frame)[i]) for r in res for i in r.points)
        self.assertLess(worst, 1.0)

    def test_backward_tracks_only_the_eyes_it_is_given(self):
        one = {i: p for i, p in pins_at(40).items() if i in EYES["matphai"].ids}
        res = track_backward(self.get, 40, 30, one)
        self.assertEqual(set(res[-1].scores), {"matphai"})
        self.assertEqual(set(res[-1].points), set(EYES["matphai"].ids))


class ReduceKeyframesTests(unittest.TestCase):
    def positions(self, fn, n=61):
        return [{14: fn(t), 18: (fn(t)[0] + 40, fn(t)[1])} for t in range(n)]

    def test_linear_motion_needs_two_keyframes(self):
        pos = self.positions(lambda t: (100 + 2 * t, 50 + 0.5 * t))
        self.assertEqual(reduce_keyframes(pos, 0.5), [0, 60])

    def test_bend_adds_a_keyframe_at_the_bend(self):
        pos = self.positions(lambda t: (100 + 2 * t, 50) if t <= 30 else (160 - 3 * (t - 30), 50 + 2 * (t - 30)))
        keys = reduce_keyframes(pos, 0.5)
        self.assertEqual(keys, [0, 30, 60])

    def test_error_never_exceeds_tolerance(self):
        rng = np.random.default_rng(3)
        walk = np.cumsum(rng.normal(0, 1.2, (61, 2)), axis=0)
        pos = self.positions(lambda t: (100 + walk[t][0], 50 + walk[t][1]))
        tol = 1.0
        keys = reduce_keyframes(pos, tol)
        for a, b in zip(keys, keys[1:]):
            for t in range(a, b + 1):
                w = (t - a) / (b - a)
                x = pos[a][14][0] + w * (pos[b][14][0] - pos[a][14][0])
                y = pos[a][14][1] + w * (pos[b][14][1] - pos[a][14][1])
                self.assertLessEqual(math.hypot(x - pos[t][14][0], y - pos[t][14][1]), tol + 1e-9)

    def test_forced_frames_are_kept(self):
        pos = self.positions(lambda t: (100 + 2 * t, 50))
        self.assertEqual(reduce_keyframes(pos, 0.5, forced=[20, 45]), [0, 20, 45, 60])


if __name__ == "__main__":
    unittest.main()
