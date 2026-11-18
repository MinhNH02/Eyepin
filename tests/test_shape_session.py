"""Mắt kiểu shape trong `Session` (design/2026-11-18-shape-design.md mục 6.1–6.2): mỗi frame ghim là một shape độc lập có ID riêng,
không bám, frame không ghim thì không có nhãn; mắt kiểu track tính y như cũ.

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


def four(label: str, t: int) -> dict:
    """4 điểm ghim của mắt `label` ở frame giả `t`."""
    truth = T.pins_at(t)
    return {i: truth[i] for i in EYES[label].pins}


class ShapeSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_shape_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def shapes_at(self, *frames: int) -> Session:
        """Phiên có mattrai kiểu shape ở từng frame trong `frames` (vẽ lần lượt)."""
        s = Session(self.dir)
        for f in frames:
            s.pin_eye(f, "mattrai", four("mattrai", f), kind="shape")
        return s

    @staticmethod
    def state(s: Session) -> dict:
        return {"pins": {f: dict(p) for f, p in s.pins.items()}, "flags": {f: dict(fl) for f, fl in s.flags.items()},
                "kind": dict(s.kind), "shape_ids": {l: dict(d) for l, d in s.shape_ids.items()},
                "obj_ids": dict(s.obj_ids), "next_id": s.next_id, "undo": len(s._undo)}

    def test_shape_exists_only_on_its_frame(self):
        s = Session(self.dir)
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        self.assertEqual(s.eye_kind("mattrai"), "shape")
        self.assertEqual(sorted(s.labels), [3])
        self.assertEqual(set(s.labels[3].points), set(ML.ids))
        self.assertEqual(s.need_pin, [])
        self.assertTrue(s.has_shape("mattrai", 3)); self.assertFalse(s.has_shape("mattrai", 4))
        self.assertEqual(s.object_id("mattrai", 3), 1); self.assertIsNone(s.object_id("mattrai", 4))
        self.assertEqual(s.arrival, {})
        self.assertEqual(s.eye_keyframes("mattrai"), [])           # shape không có keyframe
        self.assertNotIn("mattrai", s.obj_ids)                     # mắt shape không có ID của cả mắt
        self.assertEqual(s.labels[3].scores, {"mattrai": 1.0})

    def test_ids_are_per_shape_and_never_reused(self):
        s = self.shapes_at(3, 5)                          # mattrai shape ở frame 3 và 5
        self.assertEqual(s.shape_ids["mattrai"], {3: 1, 5: 10})
        s.delete_shape("mattrai", 3)
        s.pin_eye(7, "mattrai", four("mattrai", 7), kind="shape")
        self.assertEqual(s.shape_ids["mattrai"], {5: 10, 7: 19})
        self.assertEqual(sorted(s.labels), [5, 7])

    def test_track_eye_is_untouched_by_a_shape_eye(self):     # điểm soi 5
        s = Session(self.dir)
        s.pin_eye(0, "matphai", four("matphai", 0), kind="track")
        before = {f: dict(r.points) for f, r in s.labels.items()}
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        self.assertEqual(s.eye_keyframes("matphai"), [0])
        for f, pts in before.items():
            self.assertEqual({i: s.labels[f].points[i] for i in MR.ids}, pts)
        self.assertEqual(s.object_id("matphai"), 1); self.assertEqual(s.object_id("mattrai", 3), 10)

    def test_kind_is_fixed_while_eye_has_labels(self):
        s = self.shapes_at(3)
        was = self.state(s)
        with self.assertRaises(ValueError) as cm:
            s.pin_eye(8, "mattrai", four("mattrai", 8), kind="track")
        self.assertIn("đang là shape", str(cm.exception))
        self.assertIn("thêm người mới", str(cm.exception))
        self.assertEqual(self.state(s), was)                      # không đổi gì, không thêm bước hoàn tác
        s.pin_eye(8, "mattrai", four("mattrai", 8))               # không nói kiểu: giữ kiểu đang có
        self.assertEqual(s.eye_kind("mattrai"), "shape")
        self.assertEqual(sorted(s.labels), [3, 8])
        s.delete_shape("mattrai", 3)
        s.delete_shape("mattrai", 8)
        s.pin_eye(8, "mattrai", four("mattrai", 8), kind="track")
        self.assertEqual(s.eye_kind("mattrai"), "track")
        self.assertEqual(s.eye_keyframes("mattrai"), [8])
        self.assertEqual(sorted(s.labels), list(range(8, T.N)))     # mắt track bám sang sau như cũ
        self.assertEqual(s.shape_ids["mattrai"], {})

    def test_track_eye_refuses_shape(self):
        s = Session(self.dir)
        s.pin_eye(0, "mattrai", four("mattrai", 0))               # không nói kiểu: mắt chưa có nhãn là track
        self.assertEqual(s.eye_kind("mattrai"), "track")
        with self.assertRaises(ValueError) as cm:
            s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        self.assertIn("đang là track", str(cm.exception))
        self.assertEqual(s.eye_keyframes("mattrai"), [0])

    def test_shape_has_no_keyframe_and_no_whole_eye_outside(self):
        s = self.shapes_at(3)
        for call in (lambda: s.toggle_eye_key("mattrai", 3), lambda: s.end_eye_here("mattrai", 3),
                     lambda: s.toggle_eye_flag(3, "mattrai", "outside"), lambda: s.toggle_pin_here(3)):
            was = self.state(s)
            with self.assertRaises(ValueError):
                call()
            self.assertEqual(self.state(s), was)
        self.assertEqual(s.toggle_eye_flag(3, "mattrai", "occluded"), "occluded")
        self.assertEqual(s.toggle_flag(3, 14, "outside"), "outside")
        self.assertEqual(s.flags_at(3)[14], "outside")
        self.assertEqual(s.flags_at(3)[15], "occluded")

    def test_flags_stay_on_their_own_shape(self):
        s = self.shapes_at(3, 5)
        self.assertEqual(s.toggle_flag(3, 14, "occluded"), "occluded")
        self.assertEqual(s.flags_at(3), {14: "occluded"})
        self.assertNotIn(14, s.flags_at(5))
        self.assertEqual(s.flags_at(4), {})

    def test_drag_edits_only_that_shape(self):
        s = self.shapes_at(3, 5)
        five = dict(s.labels[5].points)
        x, y = s.labels[3].points[14]
        s.drag_points(3, {14: (x + 2.0, y)})
        self.assertEqual(s.labels[3].points[14], (x + 2.0, y))
        self.assertEqual(s.labels[5].points, five)
        self.assertEqual(sorted(s.labels), [3, 5])
        self.assertEqual(s.shape_ids["mattrai"], {3: 1, 5: 10})
        with self.assertRaises(ValueError):
            s.drag_points(4, {14: (x, y)})

    def test_delete_shape_missing_frame_raises(self):
        s = self.shapes_at(3)
        was = self.state(s)
        with self.assertRaises(ValueError) as cm:
            s.delete_shape("mattrai", 4)
        self.assertIn("frame này không có shape của mattrai", str(cm.exception))
        with self.assertRaises(ValueError):
            s.delete_shape("matphai", 3)                           # matphai chưa có nhãn nào
        self.assertEqual(self.state(s), was)

    def test_delete_shape_is_one_undo_step(self):
        s = self.shapes_at(3, 5)
        s.toggle_flag(3, 16, "occluded")
        s.delete_shape("mattrai", 3)
        self.assertEqual(sorted(s.labels), [5])
        self.assertNotIn(3, s.pins); self.assertNotIn(3, s.flags)
        self.assertTrue(s.undo())
        self.assertEqual(sorted(s.labels), [3, 5])
        self.assertEqual(s.shape_ids["mattrai"], {3: 1, 5: 10})    # hoàn tác trả đúng ID cũ
        self.assertEqual(s.eye_kind("mattrai"), "shape")
        self.assertEqual(s.flags_at(3), {16: "occluded"})
        self.assertTrue(s.redo())
        self.assertEqual(s.shape_ids["mattrai"], {5: 10})

    def test_delete_last_shape_drops_empty_person(self):
        s = Session(self.dir)
        s.pin_eye(0, "matphai", four("matphai", 0))
        s.add_layer()
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        self.assertEqual(s.object_id("mattrai", 3), 10)
        s.delete_shape("mattrai", 3)
        self.assertEqual(len(s.layers), 1)
        self.assertEqual(s.eye_keyframes("matphai"), [0])


if __name__ == "__main__":
    unittest.main()
