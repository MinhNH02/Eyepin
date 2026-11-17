"""B03 (buglist.md): `Session.end_eye_here` ("Kết thúc nhãn từ frame này") chép cả hai mắt vào `pins[frame]`, nên mắt kia thành
keyframe ngoài ý muốn ở frame đó (bám lại từ đó, thêm keyframe khi xuất). Như CVAT, mỗi đối tượng có keyframe riêng: kết thúc MỘT mắt chỉ
đánh Outside cả 8 điểm của mắt đó và chỉ mắt đó thành keyframe; mắt kia giữ nguyên (không có ghim/keyframe mới, nhãn do tool tính không đổi).

Ảnh giả của `test_tracking` (không dùng dữ liệu công ty)."""
import os
import shutil
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.scan import scan  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402

ML, MR = EYES["mattrai"], EYES["matphai"]
OUT_L = {i: "outside" for i in ML.ids}


class EndEyeHereTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b03_")
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
        """Nhãn do tool tính của một mắt ở mọi frame (để so trước/sau)."""
        return {f: {i: r.points[i] for i in spec.ids} for f, r in s.labels.items() if all(i in r.points for i in spec.ids)}

    @staticmethod
    def state(s):
        return {"pins": {f: dict(p) for f, p in s.pins.items()}, "flags": {f: dict(fl) for f, fl in s.flags.items()},
                "estimates": {f: dict(e) for f, e in s.estimates.items()}}

    def export(self, s):
        out = os.path.join(tempfile.mkdtemp(prefix="eyepin_b03_out_"), "o.xml")
        try:
            s.export(out)
            ann = cvatxml.parse(out)
        finally:
            shutil.rmtree(os.path.dirname(out), ignore_errors=True)
        return ann

    @staticmethod
    def track_keys(ann, label):
        tr = ann.tracks[label][0]
        return {f: {i: (round(ps.xy[0], 2), round(ps.xy[1], 2), ps.outside, ps.occluded) for i, ps in k.points.items()}
                for f, k in tr.keys.items()}

    @staticmethod
    def findings(ann, s, label):
        return [(fd.level, fd.code, fd.frame, fd.last, fd.points)
                for fd in scan(ann, s.n_frames, width=s.width, height=s.height) if fd.label == label]

    # ---- (1) mắt kia có ghim ở frame khác ----
    def test_other_eye_pinned_elsewhere_gets_no_keyframe_at_end_frame(self):
        s = self.session()
        s.toggle_eye_key("matphai", 20)                          # matphai có keyframe riêng ở 20
        self.assertEqual(s.eye_keyframes("matphai"), [0, 20])
        right_before = self.eye_labels(s, MR)
        s.end_eye_here("mattrai", 30)
        self.assertEqual(s.eye_keyframes("matphai"), [0, 20])    # trước khi sửa: [0, 20, 30]
        self.assertEqual(s.eye_keyframes("mattrai"), [0, 30])
        self.assertEqual(set(s.pins[30]), set(ML.ids))           # frame 30 chỉ chứa mắt được kết thúc
        self.assertEqual(s.flags[30], OUT_L)
        self.assertEqual(s.flags_at(45), OUT_L)                  # cờ chép sang các frame sau
        self.assertEqual(s.flags_at(29), {})                     # trước đó không đổi
        self.assertEqual(self.eye_labels(s, MR), right_before)   # mắt kia: nhãn do tool tính không đổi

    # ---- (2) frame chưa có ghim nào ----
    def test_frame_without_any_pin(self):
        for label, other in (("mattrai", "matphai"), ("matphai", "mattrai")):
            with self.subTest(label=label):
                s = self.session()
                other_before = self.eye_labels(s, EYES[other])
                shown = {i: s.labels[25].points[i] for i in EYES[label].ids}
                self.assertNotIn(25, s.pins)
                s.end_eye_here(label, 25)
                self.assertEqual(set(s.pins[25]), set(EYES[label].ids))
                self.assertEqual(s.eye_keyframes(other), [0])
                self.assertEqual(s.eye_keyframes(label), [0, 25])
                self.assertEqual(s.flags[25], {i: "outside" for i in EYES[label].ids})
                self.assertEqual({i: s.pins[25][i] for i in EYES[label].ids}, shown)   # toạ độ = nhãn đang hiển thị lúc đó
                self.assertEqual(self.eye_labels(s, EYES[other]), other_before)

    def test_export_and_scan_of_other_eye_unchanged(self):
        s = self.session()
        s.toggle_eye_key("matphai", 20)
        before = self.export(s)
        s.end_eye_here("mattrai", 30)
        after = self.export(s)
        self.assertEqual(self.track_keys(after, "matphai"), self.track_keys(before, "matphai"))
        self.assertEqual(self.findings(after, s, "matphai"), self.findings(before, s, "matphai"))
        keys_l = self.track_keys(after, "mattrai")
        self.assertIn(30, keys_l)
        self.assertTrue(all(v[2] for v in keys_l[30].values()))  # keyframe 30 của mattrai: 8 điểm Outside
        self.assertFalse(any(v[2] for f, k in keys_l.items() if f < 30 for v in k.values()))

    # ---- (3) cả hai mắt cùng có ghim ở frame đó ----
    def test_both_eyes_pinned_at_frame(self):
        s = self.session()
        self.pin_both(s, 30)
        s.toggle_flag(30, MR.ids[0], "occluded")                 # cờ có sẵn của mắt kia ở frame này phải giữ nguyên
        pins_before = dict(s.pins[30])
        right_before = self.eye_labels(s, MR)
        s.end_eye_here("mattrai", 30)
        self.assertEqual(s.pins[30], pins_before)                # không đổi toạ độ nào
        self.assertEqual(s.flags[30], {**OUT_L, MR.ids[0]: "occluded"})
        self.assertEqual(s.eye_keyframes("matphai"), [0, 30])
        self.assertEqual(self.eye_labels(s, MR), right_before)

    def test_only_other_eye_pinned_at_frame(self):
        """Frame 20 là keyframe riêng của matphai, mattrai ở đó do tool tính: kết thúc mattrai ở 20 phải được (trước khi sửa: ValueError
        "frame này chưa có nhãn của mắt đó") và matphai giữ nguyên ghim của nó."""
        s = self.session()
        s.toggle_eye_key("matphai", 20)
        right_pin = {i: s.pins[20][i] for i in MR.ids}
        left_shown = {i: s.labels[20].points[i] for i in ML.ids}
        right_before = self.eye_labels(s, MR)
        s.end_eye_here("mattrai", 20)
        self.assertEqual({i: s.pins[20][i] for i in MR.ids}, right_pin)
        self.assertEqual({i: s.pins[20][i] for i in ML.ids}, left_shown)
        self.assertEqual(s.eye_keyframes("mattrai"), [0, 20])
        self.assertEqual(s.eye_keyframes("matphai"), [0, 20])
        self.assertEqual(s.flags[20], OUT_L)
        self.assertEqual(self.eye_labels(s, MR), right_before)

    def test_frame_without_label_is_refused_without_undo_step(self):
        s = Session(self.dir)
        self.pin_both(s, 10)
        n = len(s._undo)
        with self.assertRaises(ValueError):
            s.end_eye_here("mattrai", 5)                         # trước frame ghim đầu: chưa có nhãn
        self.assertEqual(len(s._undo), n)
        self.assertNotIn(5, s.pins)

    # ---- (4) hoàn tác / làm lại ----
    def test_undo_redo_frame_without_pin(self):
        s = self.session()
        st0, lab0 = self.state(s), {f: dict(r.points) for f, r in s.labels.items()}
        s.end_eye_here("mattrai", 25)
        st1, lab1 = self.state(s), {f: dict(r.points) for f, r in s.labels.items()}
        self.assertTrue(s.undo())
        self.assertEqual(self.state(s), st0)
        self.assertNotIn(25, s.pins)                             # frame trước đó chưa có ghim nào: bỏ hẳn
        self.assertEqual({f: dict(r.points) for f, r in s.labels.items()}, lab0)
        self.assertTrue(s.redo())
        self.assertEqual(self.state(s), st1)
        self.assertEqual(s.eye_keyframes("matphai"), [0])
        self.assertEqual({f: dict(r.points) for f, r in s.labels.items()}, lab1)

    def test_undo_redo_frame_with_other_eye_pin(self):
        s = self.session()
        s.toggle_eye_key("matphai", 20)
        st0 = self.state(s)
        s.end_eye_here("mattrai", 20)
        st1 = self.state(s)
        self.assertTrue(s.undo())
        self.assertEqual(self.state(s), st0)
        self.assertEqual(set(s.pins[20]), set(MR.ids))           # về lại frame chỉ có ghim của matphai
        self.assertTrue(s.redo())
        self.assertEqual(self.state(s), st1)

    # ---- (5) người thứ 2 (Layer 1) ----
    def test_second_person(self):
        s = self.session()
        s.add_layer()
        self.assertEqual(s.cur, 1)
        self.pin_both(s, 5)
        s.toggle_eye_key("matphai", 15)
        layer0 = {f: dict(p) for f, p in s.layers[0].pins.items()}
        right_before = self.eye_labels(s, MR)
        st0 = self.state(s)
        s.end_eye_here("mattrai", 30)
        self.assertEqual(s.cur, 1)
        self.assertEqual(s.eye_keyframes("matphai"), [5, 15])
        self.assertEqual(s.eye_keyframes("mattrai"), [5, 30])
        self.assertEqual(set(s.pins[30]), set(ML.ids))
        self.assertEqual(self.eye_labels(s, MR), right_before)
        self.assertEqual({f: dict(p) for f, p in s.layers[0].pins.items()}, layer0)    # người thứ nhất không đổi
        self.assertEqual(s.layers[0].flags, {})
        self.assertTrue(s.undo())
        self.assertEqual(self.state(s), st0)
        self.assertNotIn(30, s.pins)


if __name__ == "__main__":
    unittest.main()
