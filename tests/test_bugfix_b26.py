"""B26 (buglist.md): `Session.drag_points` (kéo một điểm, cả mắt, đổi kích thước, xoay) và `paste_points` một mắt (Ctrl+V) còn lỗi kiểu B03:
kéo/dán một mắt ở frame chưa ghim làm mắt kia cũng thành keyframe; ở frame chỉ có keyframe của mắt kia thì lần kéo bị mất (điểm lẻ trong
`pins`, nhãn không đổi, một bước hoàn tác rỗng); dán một mắt xoá cờ Occluded/Outside của mắt kia. Như CVAT (mỗi đối tượng có keyframe riêng):
chỉ mắt được kéo/dán thành keyframe, mắt kia và cờ của nó giữ nguyên; một bước hoàn tác.

Ảnh giả của `test_tracking` (không dùng dữ liệu công ty)."""
import os
import shutil
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402

ML, MR = EYES["mattrai"], EYES["matphai"]


class DragPasteOneEyeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b26_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    # ---- tiện ích ----
    def pin_both(self, s, frame):
        truth = T.pins_at(frame)
        for label, spec in EYES.items():
            s.add_pin(frame, label, {i: truth[i] for i in spec.pins})

    def session(self):
        s = Session(self.dir)
        self.pin_both(s, 0)
        return s

    @staticmethod
    def eye_labels(s, spec):
        return {f: {i: r.points[i] for i in spec.ids} for f, r in s.labels.items() if all(i in r.points for i in spec.ids)}

    @staticmethod
    def shown(s, f, spec):
        return {i: s.labels[f].points[i] for i in spec.ids}

    @staticmethod
    def state(s):
        return {"pins": {f: dict(p) for f, p in s.pins.items()}, "flags": {f: dict(fl) for f, fl in s.flags.items()},
                "estimates": {f: dict(e) for f, e in s.estimates.items()}}

    @staticmethod
    def shift(pts, dx, dy):
        return {i: (x + dx, y + dy) for i, (x, y) in pts.items()}

    # ---- (1) frame chưa ghim ----
    def test_drag_point_on_unpinned_frame_pins_only_that_eye(self):
        for spec, other in ((ML, MR), (MR, ML)):
            with self.subTest(eye=spec.label):
                s = self.session()
                label, other_label = spec.label, other.label
                other_before = self.eye_labels(s, other)
                was = self.shown(s, 25, spec)
                n = len(s._undo)
                x, y = was[spec.up]
                self.assertTrue(s.drag_point(25, spec.up, (x + 3, y)))
                self.assertEqual(len(s._undo), n + 1)
                self.assertEqual(set(s.pins[25]), set(spec.ids))             # trước khi sửa: cả 16 điểm
                self.assertEqual(s.eye_keyframes(other_label), [0])
                self.assertEqual(s.eye_keyframes(label), [0, 25])
                self.assertEqual(s.pins[25][spec.up], (x + 3, y))
                self.assertEqual({i: p for i, p in s.pins[25].items() if i != spec.up}, {i: p for i, p in was.items() if i != spec.up})
                self.assertEqual(self.eye_labels(s, other), other_before)

    def test_drag_whole_eye_on_unpinned_frame(self):
        s = self.session()
        right_before = self.eye_labels(s, MR)
        new = self.shift(self.shown(s, 25, ML), 4, -2)
        self.assertTrue(s.drag_points(25, new))
        self.assertEqual(s.pins[25], new)
        self.assertEqual(s.eye_keyframes("matphai"), [0])
        self.assertEqual(self.eye_labels(s, MR), right_before)

    def test_drag_inherits_flags_of_dragged_eye_only(self):
        s = self.session()
        s.toggle_flag(0, ML.ids[1], "occluded")
        s.toggle_flag(0, MR.ids[2], "outside")
        x, y = s.labels[25].points[ML.up]
        s.drag_point(25, ML.up, (x + 2, y))
        self.assertEqual(s.flags.get(25), {ML.ids[1]: "occluded"})
        self.assertEqual(s.flags_at(25), {ML.ids[1]: "occluded", MR.ids[2]: "outside"})

    # ---- (2) frame chỉ có keyframe của mắt kia ----
    def test_drag_on_frame_with_only_other_eye_keyframe(self):
        s = self.session()
        s.toggle_eye_key("matphai", 20)
        s.toggle_flag(20, MR.ids[0], "occluded")
        right_pin = {i: s.pins[20][i] for i in MR.ids}
        right_before = self.eye_labels(s, MR)
        was = self.shown(s, 20, ML)
        x, y = was[ML.up]
        n = len(s._undo)
        self.assertTrue(s.drag_point(20, ML.up, (x + 3, y)))
        self.assertEqual(len(s._undo), n + 1)
        self.assertEqual(s.eye_keyframes("mattrai"), [0, 20])                # trước khi sửa: [0] và điểm lẻ trong pins
        self.assertEqual(s.labels[20].points[ML.up], (x + 3, y))             # lần kéo không bị mất
        self.assertEqual({i: s.pins[20][i] for i in MR.ids}, right_pin)
        self.assertEqual(s.flags[20], {MR.ids[0]: "occluded"})
        self.assertEqual(self.eye_labels(s, MR), right_before)

    def test_drag_whole_eye_on_frame_with_only_other_eye_keyframe(self):
        s = self.session()
        s.toggle_eye_key("matphai", 20)
        new = self.shift(self.shown(s, 20, ML), -3, 1)
        s.drag_points(20, new)
        self.assertEqual({i: s.pins[20][i] for i in ML.ids}, new)
        self.assertEqual(self.shown(s, 20, ML), new)
        self.assertEqual(s.eye_keyframes("matphai"), [0, 20])

    def test_unchanged_drag_is_noop(self):
        s = self.session()
        s.toggle_eye_key("matphai", 20)
        st, n = self.state(s), len(s._undo)
        self.assertFalse(s.drag_point(20, ML.up, s.labels[20].points[ML.up]))
        self.assertFalse(s.drag_points(25, self.shown(s, 25, MR)))
        self.assertEqual(self.state(s), st)
        self.assertEqual(len(s._undo), n)

    # ---- (3) frame có cả hai mắt ----
    def test_drag_on_frame_with_both_eyes(self):
        s = self.session()
        self.pin_both(s, 30)
        s.toggle_flag(30, MR.ids[0], "occluded")
        before = dict(s.pins[30])
        x, y = before[ML.up]
        self.assertFalse(s.drag_point(30, ML.up, (x + 3, y)))
        self.assertEqual(s.pins[30], {**before, ML.up: (x + 3, y)})
        self.assertEqual(s.flags[30], {MR.ids[0]: "occluded"})

    def test_drag_unlabelled_frame_refused_without_undo_step(self):
        s = Session(self.dir)
        self.pin_both(s, 10)
        n = len(s._undo)
        with self.assertRaises(ValueError):
            s.drag_point(5, ML.up, (1, 1))
        self.assertEqual(len(s._undo), n)
        self.assertNotIn(5, s.pins)

    # ---- (4) dán một mắt ----
    def test_paste_one_eye_on_unpinned_frame(self):
        s = self.session()
        s.toggle_flag(0, MR.ids[0], "outside")
        right_before = self.eye_labels(s, MR)
        pts = self.shift(self.shown(s, 25, ML), 2, 2)
        s.paste_points(25, pts)
        self.assertEqual(s.pins[25], pts)
        self.assertEqual(s.eye_keyframes("matphai"), [0])                    # trước khi sửa: [0, 25]
        self.assertEqual(self.eye_labels(s, MR), right_before)
        self.assertEqual(s.flags_at(25), {MR.ids[0]: "outside"})

    def test_paste_one_eye_keeps_other_eye_flags(self):
        s = self.session()
        self.pin_both(s, 30)
        s.toggle_flag(30, MR.ids[0], "occluded")
        s.toggle_flag(30, ML.ids[0], "occluded")
        right_pin = {i: s.pins[30][i] for i in MR.ids}
        pts = self.shift({i: s.pins[30][i] for i in ML.ids}, 1, 0)
        n = len(s._undo)
        s.paste_points(30, pts)
        self.assertEqual(len(s._undo), n + 1)
        self.assertEqual(s.flags.get(30), {MR.ids[0]: "occluded"})           # trước khi sửa: cờ của matphai bị xoá
        self.assertEqual({i: s.pins[30][i] for i in MR.ids}, right_pin)
        self.assertEqual({i: s.pins[30][i] for i in ML.ids}, pts)

    def test_paste_one_eye_on_frame_with_only_other_eye_keyframe(self):
        s = self.session()
        s.toggle_eye_key("matphai", 20)
        right_pin = {i: s.pins[20][i] for i in MR.ids}
        pts = self.shift(self.shown(s, 20, ML), 1, 1)
        s.paste_points(20, pts)
        self.assertEqual(s.pins[20], {**right_pin, **pts})
        self.assertEqual(s.eye_keyframes("mattrai"), [0, 20])

    def test_paste_both_eyes_unchanged(self):
        s = self.session()
        s.toggle_flag(0, MR.ids[0], "outside")
        pts = {**self.shown(s, 25, ML), **self.shown(s, 25, MR)}
        s.paste_points(25, pts)
        self.assertEqual(s.pins[25], pts)
        self.assertEqual(s.eye_keyframes("matphai"), [0, 25])
        self.assertNotIn(25, s.flags)

    # ---- (5) hoàn tác / làm lại ----
    def test_undo_redo(self):
        for case in ("unpinned", "other_eye_key", "paste"):
            with self.subTest(case=case):
                s = self.session()
                f = 25
                if case == "other_eye_key":
                    s.toggle_eye_key("matphai", 20)
                    f = 20
                st0 = self.state(s)
                lab0 = {g: dict(r.points) for g, r in s.labels.items()}
                if case == "paste":
                    s.paste_points(f, self.shift(self.shown(s, f, ML), 2, 0))
                else:
                    x, y = s.labels[f].points[ML.up]
                    s.drag_point(f, ML.up, (x + 3, y))
                st1 = self.state(s)
                lab1 = {g: dict(r.points) for g, r in s.labels.items()}
                self.assertTrue(s.undo())
                self.assertEqual(self.state(s), st0)
                self.assertEqual({g: dict(r.points) for g, r in s.labels.items()}, lab0)
                self.assertTrue(s.redo())
                self.assertEqual(self.state(s), st1)
                self.assertEqual({g: dict(r.points) for g, r in s.labels.items()}, lab1)

    # ---- (6) người thứ 2 ----
    def test_second_person(self):
        s = self.session()
        s.add_layer()
        self.assertEqual(s.cur, 1)
        self.pin_both(s, 5)
        layer0 = {f: dict(p) for f, p in s.layers[0].pins.items()}
        right_before = self.eye_labels(s, MR)
        st0 = self.state(s)
        x, y = s.labels[30].points[ML.up]
        self.assertTrue(s.drag_point(30, ML.up, (x + 3, y)))
        s.paste_points(35, self.shift(self.shown(s, 35, ML), 1, 0))
        self.assertEqual(s.cur, 1)
        self.assertEqual(s.eye_keyframes("matphai"), [5])
        self.assertEqual(s.eye_keyframes("mattrai"), [5, 30, 35])
        self.assertEqual(self.eye_labels(s, MR), right_before)
        self.assertEqual({f: dict(p) for f, p in s.layers[0].pins.items()}, layer0)
        self.assertTrue(s.undo())
        self.assertTrue(s.undo())
        self.assertEqual(self.state(s), st0)


if __name__ == "__main__":
    unittest.main()
