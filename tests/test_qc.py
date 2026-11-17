import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml, qc  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import QC_MSG, Session  # noqa: E402
import test_tracking as T  # noqa: E402
from test_frames import FakeSource  # noqa: E402


def _sk_points(label, x0=100.0):
    return "".join(f'<points label="{i}" outside="0" occluded="0" points="{x0 + i},{50 + i}"/>' for i in EYES[label].ids)


def build_xml(*, with_box=True, n_shapes=30):
    keys = "".join(f'<skeleton frame="{f}" keyframe="1" outside="0" occluded="0">{_sk_points("mattrai")}</skeleton>' for f in (0, 120))
    images = ""
    for f in range(T.N):
        inner = ""
        if f < n_shapes:
            inner += f'<skeleton label="matphai" outside="0">{_sk_points("matphai", 200.0)}</skeleton>'
        if with_box and f == 3:
            inner += '<box label="face" occluded="0" xtl="10" ytl="10" xbr="50" ybr="50" source="manual" z_order="0"/>'
        images += f'<image id="{f}" name="f{f:03d}" width="{T.W}" height="{T.H}">{inner}</image>'
    return (f'<annotations><version>1.1</version><meta><job><size>{T.N}</size></job></meta>'
            f'<track id="37" label="mattrai" source="manual">{keys}</track>{images}</annotations>')


def load(xml):
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as fh:
        fh.write(xml)
    try:
        return cvatxml.parse(fh.name)
    finally:
        os.unlink(fh.name)


class QcTests(unittest.TestCase):
    def test_counts_tracks_and_shapes(self):
        labels = qc.eye_labels(load(build_xml()))
        self.assertFalse(labels.empty())
        self.assertEqual(labels.tracks, [("mattrai", 37, 0, 120)])
        self.assertEqual(labels.shapes, {"matphai": 30})
        self.assertEqual(labels.message(), "1 track mắt #37 (mattrai, frame 0–120) và 30 shape mắt")
        self.assertTrue(qc.has_eye_labels(load(build_xml())))

    def test_empty_has_empty_message(self):
        from eyepin.session import empty_annotations
        labels = qc.eye_labels(empty_annotations())
        self.assertTrue(labels.empty())
        self.assertEqual(labels.message(), "")
        self.assertFalse(qc.has_eye_labels(empty_annotations()))

    def test_without_eyes_keeps_other_labels(self):
        ann = load(build_xml())
        before = ann.other_objects
        clean = qc.without_eyes(ann)
        self.assertTrue(qc.eye_labels(clean).empty())
        self.assertEqual(clean.other_objects, before)
        self.assertEqual(len(clean.tree.getroot().findall(".//box")), 1)
        self.assertEqual(clean.tree.getroot().findall("track"), [])
        self.assertEqual(clean.tree.getroot().findall(".//skeleton"), [])
        self.assertFalse(qc.eye_labels(ann).empty())            # bản gốc không bị đổi

    def test_qc_blocks_edits(self):
        s = Session(source=FakeSource(), ann=load(build_xml()))
        self.assertFalse(s.qc)                                  # mặc định không phải QC
        truth = T.pins_at(0)
        four = {i: truth[i] for i in EYES["mattrai"].pins}
        donor = Session(source=FakeSource())
        for label, spec in EYES.items():
            donor.add_pin(5, label, {i: truth[i] for i in spec.pins})
        other_state = donor.state()
        s.qc = True
        calls = [lambda: s.add_pin(0, "mattrai", four),
                 lambda: s.toggle_flag(0, 14, "occluded"),
                 lambda: s.drag_points(0, {14: (1.0, 1.0)}),
                 lambda: s.pin_eye(0, "mattrai", four),
                 lambda: s.remove_pin(0),
                 lambda: s.move_point(0, 14, (1.0, 1.0)),
                 lambda: s.clear_all(),
                 lambda: s.add_layer(),
                 lambda: s.load_state(other_state),
                 lambda: s.undo(),
                 lambda: s.redo(),
                 lambda: s.load_pins({"0": {str(i): list(p) for i, p in four.items()}})]
        for k, call in enumerate(calls):
            with self.assertRaises(ValueError, msg=str(k)) as cm:
                call()
            self.assertIn("chế độ QC", str(cm.exception))
        self.assertEqual((s.pins, s.flags, s.pending, len(s.layers)), ({}, {}, {}, 1))
        self.assertEqual(s._undo, [])

    def test_clear_then_label_then_export_has_only_new_eyes(self):
        s = Session(source=FakeSource(), ann=load(build_xml()))
        s.qc = qc.has_eye_labels(s.ann)
        self.assertTrue(s.qc)
        gone = s.clear_old_eyes()
        self.assertFalse(gone.empty())
        self.assertFalse(s.qc)
        self.assertTrue(qc.eye_labels(s.ann).empty())
        for f in (0, 30):
            truth = T.pins_at(f)
            for label, spec in EYES.items():
                s.add_pin(f, label, {i: truth[i] for i in spec.pins})
        out = os.path.join(tempfile.mkdtemp(prefix="eyepin_qc_"), "out.xml")
        try:
            s.export(out)
            root = ET.parse(out).getroot()
            self.assertEqual(sorted(t.get("label") for t in root.findall("track")), ["matphai", "mattrai"])
            self.assertEqual(len(root.findall(".//box")), 1)
            self.assertEqual(root.findall("image/skeleton"), [])
        finally:
            os.unlink(out)
            os.rmdir(os.path.dirname(out))

    def test_restore_old_eyes_only_before_new_pins(self):
        ann = load(build_xml())
        s = Session(source=FakeSource(), ann=ann)
        s.qc = True
        s.clear_old_eyes()
        self.assertTrue(s.restore_old_eyes())
        self.assertTrue(s.qc)
        self.assertIs(s.ann, ann)
        self.assertFalse(qc.eye_labels(s.ann).empty())
        s.clear_old_eyes()
        truth = T.pins_at(0)
        for label, spec in EYES.items():
            s.add_pin(0, label, {i: truth[i] for i in spec.pins})
        pins = dict(s.pins)
        self.assertFalse(s.restore_old_eyes())
        self.assertFalse(s.qc)
        self.assertEqual(s.pins, pins)
        self.assertTrue(qc.eye_labels(s.ann).empty())

    def test_restore_without_clear_is_false(self):
        s = Session(source=FakeSource(), ann=load(build_xml()))
        self.assertFalse(s.restore_old_eyes())

    def test_json_has_eyes_shape_track_empty_outside(self):
        ids = {14, 22}
        self.assertTrue(qc.json_has_eyes({"shapes": [{"label_id": 14, "elements": []}]}, ids))
        self.assertTrue(qc.json_has_eyes({"tracks": [{"label_id": 22, "shapes": [], "elements": []}]}, ids))          # track rỗng
        self.assertTrue(qc.json_has_eyes({"tracks": [{"label_id": 14, "shapes": [{"outside": True}]}]}, ids))      # toàn Outside
        self.assertFalse(qc.json_has_eyes({"shapes": [{"label_id": 1}], "tracks": [{"label_id": 2}]}, ids))
        self.assertFalse(qc.json_has_eyes({}, ids))

    def test_json_has_eyes_without_ids_uses_eight_point_skeleton(self):
        sk = {"label_id": 99, "elements": [{}] * 8}
        self.assertTrue(qc.json_has_eyes({"tracks": [sk]}))
        self.assertFalse(qc.json_has_eyes({"tracks": [dict(sk, elements=[{}] * 5)]}))

    def test_json_has_eyes_tolerates_null_lists(self):
        self.assertFalse(qc.json_has_eyes({"shapes": None, "tracks": None}, {14}))
        self.assertTrue(qc.json_has_eyes({"shapes": None, "tracks": [{"label_id": 14}]}, {14}))

    def test_is_eye_obj_empty_set_is_not_unknown(self):
        self.assertFalse(qc.is_eye_obj({"label_id": 99, "elements": [{}] * 8}, set()))      # set() = biết mà không có id nào; chưa biết thì truyền None

    def test_is_eye_obj_by_id_and_by_shape(self):
        self.assertTrue(qc.is_eye_obj({"label_id": 14}, {14, 22}))
        self.assertFalse(qc.is_eye_obj({"label_id": 99, "elements": [{}] * 8}, {14, 22}))     # biết id thì chỉ theo id
        self.assertTrue(qc.is_eye_obj({"label_id": 99, "elements": [{}] * qc.EYE_POINTS}, None))
        self.assertFalse(qc.is_eye_obj({"label_id": 99}, None))


if __name__ == "__main__":
    unittest.main()
