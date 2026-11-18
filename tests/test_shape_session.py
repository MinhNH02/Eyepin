"""Mắt kiểu shape trong `Session` (design/2026-11-18-shape-design.md mục 6.1–6.2): mỗi frame ghim là một shape độc lập có ID riêng,
không bám, frame không ghim thì không có nhãn; mắt kiểu track tính y như cũ.

Ảnh giả của `test_tracking` (không dùng dữ liệu công ty)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml, evaluate  # noqa: E402
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

    def test_remove_pin_refuses_a_frame_with_a_shape(self):
        """Bỏ cả frame ghim (`remove_pin`) mà frame có shape: từ chối, không đổi gì (bỏ cả frame sẽ xoá luôn một đối tượng shape)."""
        s = Session(self.dir)
        s.pin_eye(3, "matphai", four("matphai", 3), kind="track")
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        before = self.state(s)
        with self.assertRaises(ValueError) as cm:
            s.remove_pin(3)
        self.assertIn("shape", str(cm.exception))
        self.assertEqual(self.state(s), before)
        t = Session(self.dir)                                      # frame chỉ có track: bỏ như cũ
        t.pin_eye(3, "matphai", four("matphai", 3), kind="track")
        t.remove_pin(3)
        self.assertNotIn(3, t.pins)

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

    # ---- Task 4: hoàn tác, file phiên, dán, nhân, đổi label, đo ----
    def test_undo_redo_restore_kind_and_ids(self):             # điểm soi 4
        s = self.shapes_at(3, 5)
        s.delete_shape("mattrai", 3)
        self.assertTrue(s.undo())
        self.assertEqual(s.shape_ids["mattrai"], {3: 1, 5: 10})
        self.assertTrue(s.redo())
        self.assertEqual(s.shape_ids["mattrai"], {5: 10})
        fresh = Session(self.dir)
        fresh.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        self.assertTrue(fresh.undo())                              # hoàn tác lần vẽ đầu tiên: mắt trống, kiểu về track
        self.assertEqual(fresh.eye_kind("mattrai"), "track")
        self.assertEqual(fresh.shape_ids["mattrai"], {})

    def test_session_file_roundtrip_v3(self):
        s = self.shapes_at(3, 5)
        s.pin_eye(0, "matphai", four("matphai", 0))                # matphai là track: file phải phân biệt được
        s.toggle_flag(3, 14, "occluded")
        d = s.state()
        self.assertEqual(d["version"], 3)
        self.assertEqual(d["layers"][0]["kind"], {"mattrai": "shape", "matphai": "track"})
        self.assertEqual(d["layers"][0]["shape_ids"], {"mattrai": {"3": 1, "5": 10}, "matphai": {}})
        back = Session(self.dir)
        back.load_state(json.loads(json.dumps(d)))                 # qua JSON như file thật: khoá frame thành chuỗi
        self.assertEqual(back.kind, s.kind)
        self.assertEqual(back.shape_ids, s.shape_ids)
        self.assertEqual(sorted(back.labels), sorted(s.labels))
        for f, r in s.labels.items():
            self.assertEqual(back.labels[f].points, r.points)
        self.assertEqual(back.next_id, s.next_id)
        back.pin_eye(8, "mattrai", four("mattrai", 8))             # ID mới không trùng ID đã nạp
        self.assertEqual(back.shape_ids["mattrai"], {3: 1, 5: 10, 8: back.shape_ids["mattrai"][8]})
        self.assertNotIn(back.shape_ids["mattrai"][8], (1, 10, back.obj_ids["matphai"]))

    def test_load_without_next_id_stays_above_shape_ids(self):
        s = self.shapes_at(3, 5)
        d = s.state()
        del d["next_id"]
        back = Session(self.dir)
        back.load_state(d)
        back.pin_eye(8, "mattrai", four("mattrai", 8))
        self.assertEqual(back.shape_ids["mattrai"], {3: 1, 5: 10, 8: 19})

    def test_version_2_file_loads_as_tracks(self):             # điểm soi 1
        s = Session(self.dir)
        s.pin_eye(0, "mattrai", four("mattrai", 0))
        s.pin_eye(0, "matphai", four("matphai", 0))
        d = s.state()
        d["version"] = 2
        for L in d["layers"]:
            del L["kind"], L["shape_ids"]
        back = Session(self.dir)
        back.load_state(d)
        self.assertEqual(back.kind, {"mattrai": "track", "matphai": "track"})
        self.assertEqual(sorted(back.labels), sorted(s.labels))
        for f, r in s.labels.items():
            self.assertEqual(back.labels[f].points, r.points)
        d["version"] = 4
        with self.assertRaises(ValueError):
            Session(self.dir).load_state(d)

    def test_paste_one_shape_eye_onto_empty_frame(self):
        s = self.shapes_at(3)
        pts = {i: p for i, p in s.pins[3].items() if i in ML.ids}
        undo = len(s._undo)
        s.paste_points(8, pts)
        self.assertTrue(s.has_shape("mattrai", 8))
        self.assertEqual(s.object_id("mattrai", 8), 10)
        self.assertEqual(sorted(s.labels), [3, 8])
        self.assertEqual(len(s._undo), undo + 1)
        self.assertTrue(s.undo())
        self.assertEqual(sorted(s.labels), [3])

    def test_paste_one_track_eye_onto_empty_frame_still_refuses(self):
        s = Session(self.dir)
        s.pin_eye(10, "matphai", four("matphai", 10))             # track bám sang sau: frame 2 chưa có nhãn nào
        was = self.state(s)
        with self.assertRaises(ValueError):
            s.paste_points(2, four("mattrai", 2) | {i: (1.0, 1.0) for i in ML.ids if i not in ML.pins})
        self.assertEqual(self.state(s), was)

    def test_propagate_makes_new_shapes(self):
        s = self.shapes_at(3)
        s.toggle_flag(3, 15, "occluded")
        self.assertEqual(s.propagate(3, count=2), 2)
        self.assertEqual(sorted(s.labels), [3, 4, 5])
        self.assertEqual(len(set(s.shape_ids["mattrai"].values())), 3)
        self.assertEqual(s.flags_at(5), {15: "occluded"})
        self.assertEqual(s.eye_kind("mattrai"), "shape")

    def test_propagate_keeps_other_eyes_shapes(self):
        """C1: nhân shape mattrai ở frame 3 sang 4, 5 mà matphai có shape riêng ở 4, 5: shape matphai còn nguyên (cả ID); một bước hoàn tác."""
        s = self.shapes_at(3)
        for f in (4, 5):
            s.pin_eye(f, "matphai", four("matphai", f), kind="shape")
        right = {f: {i: s.pins[f][i] for i in MR.ids} for f in (4, 5)}
        rid = dict(s.shape_ids["matphai"])
        undo = len(s._undo)
        self.assertEqual(s.propagate(3, count=2), 2)
        self.assertEqual(len(s._undo), undo + 1)
        for f in (4, 5):
            self.assertTrue(s.has_shape("matphai", f))
            self.assertTrue(s.has_shape("mattrai", f))
            self.assertEqual({i: s.pins[f][i] for i in MR.ids}, right[f])
            self.assertEqual({i: s.pins[f][i] for i in ML.ids}, {i: s.pins[3][i] for i in ML.ids})
        self.assertEqual(s.shape_ids["matphai"], rid)
        self.assertEqual(s.eye_kind("matphai"), "shape")
        self.assertTrue(s.undo())
        self.assertEqual(sorted(s.shape_ids["mattrai"]), [3])
        self.assertEqual(s.shape_ids["matphai"], rid)

    def test_propagate_keeps_other_eyes_track_keyframes_and_outside(self):
        """C1: matphai track (keyframe 0, Outside cả mắt ở 6) + shape mattrai ở 3, nhân 4..9: keyframe 6 của matphai và cờ Outside còn nguyên."""
        s = Session(self.dir)
        s.pin_eye(0, "matphai", four("matphai", 0), kind="track")
        s.end_eye_here("matphai", 6)
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        self.assertEqual(s.eye_keyframes("matphai"), [0, 6])
        key6 = {i: s.pins[6][i] for i in MR.ids}
        self.assertEqual(s.propagate(3, start=4, end=9), 6)
        self.assertEqual(s.eye_keyframes("matphai"), [0, 6])
        self.assertEqual({i: s.pins[6][i] for i in MR.ids}, key6)
        for f in (6, 7, 9, 20):
            fl = s.flags_at(f)
            self.assertTrue(all(fl.get(i) == "outside" for i in MR.ids), f)
        self.assertEqual([f for f in range(T.N) if s.has_shape("mattrai", f)], [3, 4, 5, 6, 7, 8, 9])
        for f in range(4, 10):
            self.assertFalse(any(i in s.flags.get(f, {}) for i in ML.ids), f)   # shape mattrai ở 3 không có cờ

    def test_propagate_track_eye_keeps_other_eyes_shapes(self):
        """C1: mattrai track ghim riêng ở 2, matphai có shape ở 4, 5; nhân từ 2: shape matphai còn, kiểu vẫn là shape."""
        s = Session(self.dir)
        for f in (4, 5):
            s.pin_eye(f, "matphai", four("matphai", f), kind="shape")
        s.pin_eye(2, "mattrai", four("mattrai", 2), kind="track")
        rid = dict(s.shape_ids["matphai"])
        right = {f: {i: s.pins[f][i] for i in MR.ids} for f in (4, 5)}
        self.assertEqual(s.propagate(2, count=3), 3)
        self.assertEqual(s.eye_kind("matphai"), "shape")
        self.assertEqual(s.shape_ids["matphai"], rid)
        for f in (4, 5):
            self.assertEqual({i: s.pins[f][i] for i in MR.ids}, right[f])
        self.assertEqual(s.eye_keyframes("mattrai"), [2, 3, 4, 5])
        self.assertEqual(s.propagate_eyes(2), ["mattrai"])

    def test_swap_moves_kind_and_ids(self):
        s = self.shapes_at(3)
        s.pin_eye(0, "matphai", four("matphai", 0))
        was_ids = dict(s.shape_ids["mattrai"])
        s.swap_eyes()
        self.assertEqual(s.eye_kind("matphai"), "shape")
        self.assertEqual(s.eye_kind("mattrai"), "track")
        self.assertEqual(s.shape_ids["matphai"], was_ids)
        self.assertEqual(s.shape_ids["mattrai"], {})
        self.assertTrue(s.has_shape("matphai", 3))
        self.assertTrue(s.undo())
        self.assertEqual(s.eye_kind("mattrai"), "shape")
        self.assertEqual(s.shape_ids["mattrai"], was_ids)

    def test_headturn_and_report_ignore_shape_eyes(self):
        s = Session(self.dir)
        for f in (3, 10, 20):
            s.pin_eye(f, "mattrai", four("mattrai", f), kind="shape")
            s.pin_eye(f, "matphai", four("matphai", f), kind="shape")
        self.assertEqual(s.turns[0].turns, ())
        self.assertEqual(s.turns[0].both_pins, 0)
        ev = evaluate.evaluate(s)
        self.assertEqual(ev.samples, [])
        self.assertEqual(ev.pins, 0)

    def test_delete_shape_clears_stale_flags_of_emptied_frame(self):
        s = self.shapes_at(3, 5)
        s.flags[3] = {22: "occluded"}                              # cờ mồ côi của điểm không còn ghim ở frame này
        s.estimates[3] = {22: "x"}
        s.delete_shape("mattrai", 3)
        self.assertNotIn(3, s.pins); self.assertNotIn(3, s.flags); self.assertNotIn(3, s.estimates)

    # ---- xuất file có shape (Task 5) ----
    def out_path(self, name: str) -> str:
        p = os.path.join(self.dir, name)
        self.addCleanup(lambda: os.path.exists(p) and os.remove(p))
        return p

    def test_export_shape_only_job(self):
        s = self.shapes_at(3, 5)
        s.toggle_flag(5, 16, "occluded")
        out = self.out_path("shape_only.xml")
        info = s.export(out)
        self.assertEqual(info["shapes"], 2)
        self.assertEqual(info["keyframes"], 0)
        self.assertEqual(info["tracks"], [])
        ann = cvatxml.parse(out)
        self.assertEqual(ann.tracks["mattrai"], [])
        self.assertEqual(set(ann.shapes["mattrai"]), {3, 5})
        for f in (3, 5):
            for i, ps in ann.shapes["mattrai"][f].points.items():
                want = s.labels[f].points[i]
                self.assertLess(abs(ps.xy[0] - want[0]), 0.01)
                self.assertLess(abs(ps.xy[1] - want[1]), 0.01)
        self.assertTrue(ann.shapes["mattrai"][5].points[16].occluded)
        self.assertFalse(ann.shapes["mattrai"][3].points[16].occluded)
        self.assertEqual([sh.key.frame for sh in s.build_shapes()], [3, 5])
        self.assertEqual([sh.attrs for sh in s.build_shapes()], [{"id": "1"}, {"id": "10"}])

    def test_export_mixed_track_and_shape(self):
        s = Session(self.dir)
        s.pin_eye(0, "matphai", four("matphai", 0), kind="track")
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        out = self.out_path("mixed.xml")
        info = s.export(out)
        self.assertEqual(info["tracks"], ["matphai"])
        self.assertEqual(info["shapes"], 1)
        root = ET.parse(out).getroot()
        self.assertEqual([t.get("label") for t in root.findall("track")], ["matphai"])
        image = [im for im in root.findall("image") if im.get("id") == "3"]
        self.assertEqual(len(image), 1)
        self.assertEqual([sk.get("label") for sk in image[0].findall("skeleton")], ["mattrai"])
        only = Session(self.dir)
        only.pin_eye(0, "matphai", four("matphai", 0), kind="track")
        out2 = self.out_path("track_only.xml")
        only.export(out2)
        mine, ref = cvatxml.parse(out), cvatxml.parse(out2)
        self.assertEqual(len(mine.tracks["matphai"]), 1)
        self.assertEqual(mine.tracks["matphai"][0].keys, ref.tracks["matphai"][0].keys)
        self.assertEqual(sorted(s.build_tracks()), ["matphai"])

    def test_export_two_people_same_frame(self):             # điểm soi 3
        s = Session(self.dir)
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        s.add_layer()
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        out = self.out_path("two_people.xml")
        info = s.export(out)
        self.assertEqual(info["shapes"], 2)
        image = [im for im in ET.parse(out).getroot().findall("image") if im.get("id") == "3"]
        self.assertEqual(len(image), 1)
        self.assertEqual([sk.get("label") for sk in image[0].findall("skeleton")], ["mattrai", "mattrai"])
        self.assertEqual([sh.attrs["id"] for sh in s.build_shapes()], ["1", "10"])

    def test_export_nothing_still_raises(self):
        s = Session(self.dir)
        self.assertEqual(s.build_shapes(), [])
        with self.assertRaises(ValueError):
            s.export(self.out_path("nothing.xml"))
        with self.assertRaises(ValueError):
            s.build_tracks()
        with self.assertRaises(ValueError):
            s.build_all_tracks()

    def test_export_does_not_hide_track_errors(self):
        """I4: người 1 có shape, người 2 có track mà nhãn do tool tính bị mất (trạng thái cũ): xuất phải báo lỗi, không ghi file thiếu track."""
        s = Session(self.dir)
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        s.add_layer()
        s.pin_eye(0, "matphai", four("matphai", 0), kind="track")
        s.layers[1].labels = {}
        out = self.out_path("stale.xml")
        with self.assertRaises(ValueError):
            s.export(out)
        self.assertFalse(os.path.exists(out))

    def test_build_tracks_skips_shape_eyes(self):
        s = self.shapes_at(3, 5)
        self.assertEqual(s.build_tracks(), {})
        with self.assertRaises(ValueError):
            s.build_all_tracks()


if __name__ == "__main__":
    unittest.main()
