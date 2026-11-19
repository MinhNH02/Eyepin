"""Nạp shape mắt có sẵn của job CVAT thành shape sửa được (`eyepin.adopt`, `Session.adopt`; design/2026-11-19-qc-edit-design.md).

`adopt.check` quyết định job nạp được hay không (không mất gì khi gửi lại), `adopt.eye_shapes` đọc shape mắt từ JSON của
`GET /api/jobs/{id}/annotations`, `Session.adopt` đưa chúng vào phiên: mọi mắt của phiên đã nạp là shape.
JSON và `labels` dựng tay theo `test_shape_sync.server_shapes_json` và `FakeJob.default_labels()`; ảnh giả của `test_tracking`."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml, qc  # noqa: E402
from eyepin.adopt import AdoptedShape, check, eye_shapes, saved_shape_count, shapes_from_ann  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import ADOPTED_TRACK_MSG, Session  # noqa: E402
from fake_cvat import FakeJob  # noqa: E402
import test_tracking as T  # noqa: E402

NON_EYE = {"id": 40, "name": "face", "type": "rectangle", "sublabels": []}
LABELS = FakeJob.default_labels() + [NON_EYE]
LABEL_ID = {lb["name"]: lb["id"] for lb in LABELS}
SUB = {lb["name"]: {int(x["name"]): x["id"] for x in lb["sublabels"]} for lb in LABELS if lb["name"] in EYES}
NUMS = list(range(T.N))                                  # số frame của job = chỉ số EyePin (job bắt đầu từ frame 0)


# ---- JSON dựng tay ----
def skeleton(label, frame, pts=None, *, flags=None, drop=(), **skel):
    """Shape skeleton của `label` ở số frame `frame` của job, đủ 8 phần tử. `flags` {điểm: "occluded" | "outside" | "both"}; `drop`: điểm bỏ;
    `skel`: ghi đè trường của chính skeleton (ví dụ `group=2`)."""
    pts = pts or {i: p for i, p in T.pins_at(frame).items() if i in EYES[label].ids}
    flags = flags or {}
    els = []
    for pid in EYES[label].ids:
        if pid in drop:
            continue
        x, y = pts[pid]
        els.append({"id": 1000 + pid, "type": "points", "label_id": SUB[label][pid], "frame": frame, "group": 0, "source": "file",
                    "occluded": flags.get(pid) in ("occluded", "both"), "outside": flags.get(pid) in ("outside", "both"),
                    "z_order": 0, "rotation": 0.0, "attributes": [], "points": [x, y]})
    sk = {"id": 100 + frame, "type": "skeleton", "label_id": LABEL_ID[label], "frame": frame, "group": 0, "source": "file",
          "occluded": False, "outside": False, "z_order": 0, "rotation": 0.0, "attributes": [], "points": [], "elements": els}
    sk.update(skel)
    return sk


def edited(sk, fn):
    fn(sk)
    return sk


def box(frame):
    return {"id": 300 + frame, "type": "rectangle", "label_id": NON_EYE["id"], "frame": frame, "group": 0, "source": "file", "occluded": False,
            "outside": False, "z_order": 0, "rotation": 0.0, "attributes": [], "points": [10.0, 10.0, 50.0, 50.0]}


def tag(frame):
    return {"id": 500 + frame, "label_id": NON_EYE["id"], "frame": frame, "group": 0, "source": "file", "attributes": []}


def box_track(frames):
    return {"id": 900, "label_id": NON_EYE["id"], "frame": frames[0], "group": 0, "source": "file", "attributes": [],
            "shapes": [{"type": "rectangle", "frame": f, "points": [10.0, 10.0, 50.0, 50.0], "outside": False, "occluded": False, "z_order": 0,
                        "rotation": 0.0, "keyframe": True, "attributes": []} for f in frames], "elements": []}


def element_track(frame):
    """Track của nhãn không phải mắt mà các shape nằm trong `elements` (như skeleton track): shape ở `frame`."""
    return {"id": 901, "label_id": NON_EYE["id"], "frame": frame, "group": 0, "source": "file", "attributes": [], "shapes": [],
            "elements": [{"id": 1, "label_id": 1, "shapes": [{"type": "points", "frame": frame, "points": [1.0, 2.0], "outside": False,
                                                              "occluded": False, "keyframe": True}]}]}


def eye_track(label, frames):
    return {"id": 700, "label_id": LABEL_ID[label], "frame": frames[0], "group": 0, "source": "file", "attributes": [], "shapes": [], "elements": []}


def job(*, shapes=(), tracks=(), tags=()):
    return {"version": 1, "tags": list(tags), "shapes": list(shapes), "tracks": list(tracks)}


# ---- câu lý do (chuỗi chính xác của kế hoạch) ----
def r1(n):
    return f"Job có {n} track mắt (EyePin chưa sửa trực tiếp track có sẵn)."


R2 = "Job có cả shape lẫn track của nhãn không phải mắt (gửi sẽ đổi shape của nhãn khác thành track)."


def r3(fr):
    return f"Shape mắt không đủ 8 điểm đúng tên ở frame {fr}."


def r4(fr):
    return f"Có hai shape cùng nhãn mắt ở cùng frame (hai người) ở frame {fr}."


def r5(fr):
    return f"Shape mắt mang thuộc tính EyePin chưa ghi lại được (cờ cả skeleton, attributes, group, z_order, rotation) ở frame {fr}."


def r6(fr):
    return f"Điểm vừa Outside vừa Occluded ở frame {fr}."


def r7(fr):
    return f"Shape mắt nằm trên frame đã xoá hoặc ngoài job ở frame {fr}."


R8 = "Job có tag và track của nhãn không phải mắt (gửi sẽ xoá tag)."


def r9(fr):
    return f"Nhãn không phải mắt nằm trên frame đã xoá trong CVAT ở frame {fr} (gửi sẽ xoá chúng)."


def run_check(aj, nums=NUMS, deleted=()):
    return check(aj, LABELS, nums, set(deleted))


class CheckTests(unittest.TestCase):
    def test_check_ok_for_shape_only_job(self):
        aj = job(shapes=[skeleton("mattrai", 12), skeleton("matphai", 12, flags={22: "outside", 23: "occluded"})])
        self.assertEqual(run_check(aj), [])

    def test_check_allows_other_labels_that_prepare_can_send(self):
        """Nhãn không phải mắt (shape, tag hay track riêng lẻ) không cản việc nạp; chỉ các tổ hợp `prepare` từ chối mới cản."""
        for name, aj in [("shape + tag", job(shapes=[skeleton("mattrai", 12), box(3)], tags=[tag(4)])),
                         ("track không phải mắt", job(shapes=[skeleton("mattrai", 12)], tracks=[box_track([3, 4])])),
                         ("không có nhãn mắt nào", job(shapes=[box(3)]))]:
            with self.subTest(name):
                self.assertEqual(run_check(aj), [])

    def test_check_reasons_in_order(self):
        """Một JSON vi phạm cả 9 điều: đúng 9 chuỗi theo thứ tự; frame là số frame của job, tăng dần, tối đa 3 rồi ' …'."""
        aj = job(
            shapes=[skeleton("mattrai", f, drop=(15,)) for f in (50, 12, 41, 40)]                     # 3: bốn frame
                   + [skeleton("matphai", 20), skeleton("matphai", 20)]                                  # 4
                   + [skeleton("matphai", 21, group=2),
                      edited(skeleton("matphai", 22), lambda sk: sk["elements"][0].update(attributes=[{"spec_id": 1, "value": "x"}]))]   # 5
                   + [skeleton("matphai", 23, flags={25: "both"})]                                     # 6
                   + [skeleton("matphai", 30), skeleton("matphai", 99)]                                  # 7: frame 30 đã xoá, 99 ngoài job
                   + [box(30)],                                                                          # 2 (cùng track không phải mắt) và 9
            tracks=[eye_track("mattrai", [5]), box_track([3])],                                          # 1 và 2, 8
            tags=[tag(3)])                                                                               # 8
        self.assertEqual(run_check(aj, deleted={30}),
                         [r1(1), R2, r3("12, 40, 41 …"), r4("20"), r5("21, 22"), r6("23"), r7("30, 99"), R8, r9("30")])

    def test_each_reason_alone(self):
        def bad_point(sk):
            sk["elements"][2]["points"] = []

        def other_eye(sk):                                  # đủ 8 phần tử nhưng một phần tử thuộc mắt kia
            sk["elements"][0]["label_id"] = SUB["matphai"][22]

        def repeated(sk):                                   # đủ 8 phần tử nhưng một điểm lặp, một điểm vắng
            sk["elements"][0]["label_id"] = sk["elements"][1]["label_id"]

        def not_a_skeleton(sk):
            sk.update(type="rectangle", points=[1.0, 2.0, 3.0, 4.0], elements=[])

        def el(key, value):
            return lambda sk: sk["elements"][3].update({key: value})

        two_shapes = [skeleton("mattrai", 12), skeleton("mattrai", 12)]
        cases = [
            ("track mắt", job(tracks=[eye_track("mattrai", [5])]), (), [r1(1)]),
            ("hai track mắt", job(tracks=[eye_track("mattrai", [5]), eye_track("matphai", [5])]), (), [r1(2)]),
            ("shape lẫn track không phải mắt", job(shapes=[box(3)], tracks=[box_track([4])]), (), [R2]),
            ("thiếu một điểm", job(shapes=[skeleton("mattrai", 12, drop=(15,))]), (), [r3("12")]),
            ("điểm không toạ độ", job(shapes=[edited(skeleton("mattrai", 12), bad_point)]), (), [r3("12")]),
            ("phần tử của mắt kia", job(shapes=[edited(skeleton("mattrai", 12), other_eye)]), (), [r3("12")]),
            ("điểm lặp", job(shapes=[edited(skeleton("mattrai", 12), repeated)]), (), [r3("12")]),
            ("shape mắt không phải skeleton", job(shapes=[edited(skeleton("mattrai", 12), not_a_skeleton)]), (), [r3("12")]),
            ("hai shape cùng frame", job(shapes=two_shapes), (), [r4("12")]),
            ("skeleton occluded", job(shapes=[skeleton("mattrai", 12, occluded=True)]), (), [r5("12")]),
            ("skeleton outside", job(shapes=[skeleton("mattrai", 12, outside=True)]), (), [r5("12")]),
            ("skeleton attributes", job(shapes=[skeleton("mattrai", 12, attributes=[{"spec_id": 1, "value": "x"}])]), (), [r5("12")]),
            ("skeleton group", job(shapes=[skeleton("mattrai", 12, group=3)]), (), [r5("12")]),
            ("skeleton z_order", job(shapes=[skeleton("mattrai", 12, z_order=2)]), (), [r5("12")]),
            ("skeleton rotation", job(shapes=[skeleton("mattrai", 12, rotation=15.0)]), (), [r5("12")]),
            ("phần tử attributes", job(shapes=[edited(skeleton("mattrai", 12), el("attributes", [{"spec_id": 1, "value": "x"}]))]), (), [r5("12")]),
            ("phần tử group", job(shapes=[edited(skeleton("mattrai", 12), el("group", 1))]), (), [r5("12")]),
            ("phần tử z_order", job(shapes=[edited(skeleton("mattrai", 12), el("z_order", 1))]), (), [r5("12")]),
            ("phần tử rotation", job(shapes=[edited(skeleton("mattrai", 12), el("rotation", 5.0))]), (), [r5("12")]),
            ("thuộc tính rỗng/None không cản", job(shapes=[edited(skeleton("mattrai", 12, group=None, z_order=None, rotation=None, attributes=None),
                                                                   lambda sk: sk["elements"][0].update(group=None, rotation=None))]), (), []),
            ("điểm vừa outside vừa occluded", job(shapes=[skeleton("mattrai", 12, flags={16: "both"})]), (), [r6("12")]),
            ("shape trên frame đã xoá", job(shapes=[skeleton("mattrai", 30)]), {30}, [r7("30")]),
            ("shape ngoài job", job(shapes=[skeleton("mattrai", 99)]), (), [r7("99")]),
            ("ba frame không có ' …'", job(shapes=[skeleton("matphai", f) for f in (32, 30, 31)]), {30, 31, 32}, [r7("30, 31, 32")]),
            ("năm frame có ' …'", job(shapes=[skeleton("matphai", f) for f in (14, 10, 13, 11, 12)]), set(range(10, 15)), [r7("10, 11, 12 …")]),
            ("tag và track không phải mắt", job(tags=[tag(3)], tracks=[box_track([4])]), (), [R8]),
            ("shape không phải mắt trên frame xoá", job(shapes=[box(30)]), {30}, [r9("30")]),
            ("tag trên frame xoá", job(tags=[tag(30)]), {30}, [r9("30")]),
            ("track không phải mắt có shape trên frame xoá", job(tracks=[box_track([29, 30])]), {30}, [r9("30")]),
            ("shape trong elements của track trên frame xoá", job(tracks=[element_track(30)]), {30}, [r9("30")]),
            ("nhãn mắt trên frame xoá chỉ là điều 7", job(shapes=[skeleton("mattrai", 30), box(31)]), {30}, [r7("30")]),
        ]
        for name, aj, deleted, want in cases:
            with self.subTest(name):
                self.assertEqual(run_check(aj, deleted=deleted), want)

    def test_check_uses_job_frame_numbers(self):
        """Frame trong câu báo là số frame của job (như JSON ghi), không phải chỉ số EyePin."""
        nums = list(range(10, 70))
        aj = job(shapes=[skeleton("mattrai", 12, drop=(15,)), skeleton("mattrai", 5)])
        self.assertEqual(check(aj, LABELS, nums, set()), [r3("12"), r7("5")])
        self.assertEqual(check(job(shapes=[skeleton("mattrai", 12)]), LABELS, nums, set()), [])


class EyeShapesTests(unittest.TestCase):
    def test_eye_shapes_exact_values(self):
        pts = {i: (100.1234 + i, 50.5678 + 2 * i) for i in EYES["mattrai"].ids}
        pts[18] = (101, 52)                                     # số nguyên trong JSON vẫn ra đúng giá trị
        flags = {15: "outside", 17: "occluded"}
        other = {i: (200.9876 + i, 60.4321 + i) for i in EYES["matphai"].ids}
        aj = job(shapes=[skeleton("mattrai", 14, pts, flags=flags), skeleton("matphai", 12, other), skeleton("mattrai", 12),
                         box(3)])
        nums = list(range(10, 70))                              # job bắt đầu ở frame 10: frame 12 của job = chỉ số 2
        got = eye_shapes(aj, LABELS, nums)
        self.assertEqual([(s.frame, s.label) for s in got], [(2, "matphai"), (2, "mattrai"), (4, "mattrai")])
        by = {(s.frame, s.label): s for s in got}
        s = by[(4, "mattrai")]
        self.assertEqual(s.points, pts)
        self.assertEqual(s.points[14], (100.1234 + 14, 50.5678 + 28))
        self.assertEqual(s.flags, {15: "outside", 17: "occluded"})
        self.assertEqual(by[(2, "matphai")].points, other)
        self.assertEqual(by[(2, "matphai")].flags, {})
        self.assertEqual(by[(2, "mattrai")].flags, {})
        self.assertEqual(set(s.points), set(EYES["mattrai"].ids))

    def test_outside_wins_when_a_point_is_both(self):
        """Điều 6 của `check` đã chặn trường hợp này; `eye_shapes` chỉ cần xác định: outside trước, rồi occluded."""
        aj = job(shapes=[skeleton("mattrai", 3, flags={16: "both", 17: "occluded"})])
        self.assertEqual(eye_shapes(aj, LABELS, NUMS)[0].flags, {16: "outside", 17: "occluded"})

    def test_shapes_from_ann(self):
        ann = cvatxml.parse_bytes(ann_xml().encode())
        got = shapes_from_ann(ann)
        self.assertEqual([(s.frame, s.label) for s in got], [(3, "matphai"), (3, "mattrai"), (8, "mattrai")])
        self.assertEqual(got[1].flags, {15: "outside", 17: "occluded"})
        self.assertEqual(got[1].points[14], (114.25, 64.5))
        self.assertEqual(got[0].flags, {})
        self.assertEqual(set(got[0].points), set(EYES["matphai"].ids))


def sk_xml(label, x0, flags=None):
    flags = flags or {}
    return "".join(f'<points label="{i}" outside="{int(flags.get(i) == "outside")}" occluded="{int(flags.get(i) == "occluded")}" '
                   f'points="{x0 + i}.25,{50 + i}.5"/>' for i in EYES[label].ids)


def ann_xml():
    """File "CVAT for images": ba shape mắt (frame 3: hai mắt, cờ ở mattrai; frame 8: mattrai) và một box không phải mắt ở frame 3."""
    inner = {3: ('<box label="face" occluded="0" xtl="10" ytl="10" xbr="50" ybr="50" source="manual" z_order="0"/>'
                 f'<skeleton label="mattrai" outside="0">{sk_xml("mattrai", 100, {15: "outside", 17: "occluded"})}</skeleton>'
                 f'<skeleton label="matphai" outside="0">{sk_xml("matphai", 200)}</skeleton>'),
             8: f'<skeleton label="mattrai" outside="0">{sk_xml("mattrai", 100)}</skeleton>'}
    images = "".join(f'<image id="{f}" name="f{f:03d}.png" width="{T.W}" height="{T.H}">{inner.get(f, "")}</image>' for f in range(T.N))
    return f'<annotations><version>1.1</version><meta><job><size>{T.N}</size></job></meta>{images}</annotations>'


def adopted(label, frame, flags=None, pts=None):
    pts = pts or {i: p for i, p in T.pins_at(frame).items() if i in EYES[label].ids}
    return AdoptedShape(label, frame, dict(pts), dict(flags or {}))


def four(label, t):
    truth = T.pins_at(t)
    return {i: truth[i] for i in EYES[label].pins}


class SessionAdoptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_adopt_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def session(self, *shapes) -> Session:
        """Phiên mở như `open_job` mở job đã có nhãn mắt (qc bật) rồi nạp `shapes`."""
        s = Session(self.dir)
        s.qc = True
        s.adopt(list(shapes))
        return s

    def test_adopt_fills_session(self):
        ann = cvatxml.parse_bytes(ann_xml().encode())
        s = Session(self.dir, ann=ann)
        s.qc, s.dirty, s.unsent = True, True, True               # nạp phải xoá hết các cờ này
        s.findings = ["cũ"]
        shapes = shapes_from_ann(ann)
        s.adopt(shapes)
        self.assertEqual(s.kind, {"mattrai": "shape", "matphai": "shape"})
        self.assertTrue(s.adopted)
        self.assertFalse(s.qc)
        self.assertFalse(s.dirty)
        self.assertFalse(s.unsent)
        self.assertEqual(s.findings, [])
        self.assertIsNone(s._old_eyes)
        self.assertEqual((len(s.layers), s.cur), (1, 0))
        self.assertEqual((s._undo, s._redo), ([], []))
        for sh in shapes:
            self.assertEqual({i: s.pins[sh.frame][i] for i in EYES[sh.label].ids}, sh.points)
            self.assertTrue(s.has_shape(sh.label, sh.frame))
            self.assertIn(sh.frame, s.labels)
        self.assertEqual(s.flags, {3: {15: "outside", 17: "occluded"}})
        self.assertEqual(sorted(s.pins), [3, 8])
        given = [n for label in EYES for n in s.shape_ids[label].values()]
        self.assertEqual(len(given), 3)
        self.assertEqual(len(set(given)), 3)
        self.assertEqual(s.shape_ids["mattrai"].keys(), {3, 8})
        self.assertEqual(s.shape_ids["matphai"].keys(), {3})
        self.assertEqual(s.obj_ids, {})
        self.assertTrue(qc.eye_labels(s.ann).empty())             # ann không còn mắt, nhãn khác còn
        self.assertEqual(s.ann.other_objects, ann.other_objects)
        self.assertEqual(len(s.ann.tree.getroot().findall(".//box")), 1)
        self.assertFalse(qc.eye_labels(ann).empty())              # ann gốc không bị đổi
        s.pin_eye(10, "mattrai", four("mattrai", 10))             # không còn chặn như chế độ QC
        self.assertTrue(s.has_shape("mattrai", 10))

    def test_export_after_adopt_is_identical(self):
        ann = cvatxml.parse_bytes(ann_xml().encode())
        shapes = shapes_from_ann(ann)
        s = Session(self.dir, ann=ann)
        s.qc = True
        s.adopt(shapes)
        built = {(b.key.frame, b.label): b for b in s.build_shapes()}
        self.assertEqual(len(built), len(shapes))
        for sh in shapes:
            key = built[(sh.frame, sh.label)].key
            self.assertEqual(set(key.points), set(EYES[sh.label].ids))
            for pid, ps in key.points.items():
                self.assertEqual(ps.xy, sh.points[pid])
                self.assertEqual(ps.outside, sh.flags.get(pid) == "outside")
                self.assertEqual(ps.occluded, sh.flags.get(pid) == "occluded")
        with tempfile.TemporaryDirectory(prefix="eyepin_adopt_out_") as tmp:                  # file import: cùng shape, XML làm tròn 2 chữ số
            out = os.path.join(tmp, "out.xml")
            s.export(out)
            back = cvatxml.parse(out)
        again = {(b.frame, b.label): b for b in shapes_from_ann(back)}
        self.assertEqual(set(again), set(built))
        for sh in shapes:
            got = again[(sh.frame, sh.label)]
            self.assertEqual(got.flags, sh.flags)
            for pid, (x, y) in sh.points.items():
                self.assertLessEqual(abs(got.points[pid][0] - x), 0.005 + 1e-9)
                self.assertLessEqual(abs(got.points[pid][1] - y), 0.005 + 1e-9)

    def test_adopt_refuses_when_pinned(self):
        s = Session(self.dir)
        s.pin_eye(3, "mattrai", four("mattrai", 3))
        before = (dict(s.pins), s.adopted, list(s._undo))
        with self.assertRaises(ValueError) as cm:
            s.adopt([adopted("mattrai", 5)])
        self.assertEqual(str(cm.exception), "Phiên đã có nhãn nên không nạp được")
        self.assertEqual((dict(s.pins), s.adopted, list(s._undo)), before)
        self.assertEqual(s.kind["mattrai"], "track")              # phiên không đổi gì
        t = Session(self.dir)                                    # ghim của người khác cũng tính
        t.add_layer()
        t.pin_eye(3, "mattrai", four("mattrai", 3))
        t.select_layer(0)
        with self.assertRaises(ValueError):
            t.adopt([adopted("mattrai", 5)])
        self.assertFalse(t.adopted)

    def test_eye_without_shapes_is_still_shape(self):
        s = self.session(adopted("matphai", 6))
        self.assertEqual(s.kind["mattrai"], "shape")
        self.assertEqual(s.pins.keys(), {6})
        s.pin_eye(8, "mattrai", four("mattrai", 8))                # không truyền kind: shape
        self.assertEqual(s.kind["mattrai"], "shape")
        self.assertTrue(s.has_shape("mattrai", 8))
        self.assertIn(8, s.shape_ids["mattrai"])
        self.assertNotIn("mattrai", s.obj_ids)
        before, undo = dict(s.pins), len(s._undo)
        with self.assertRaises(ValueError) as cm:
            s.pin_eye(9, "mattrai", four("mattrai", 9), kind="track")
        self.assertEqual(str(cm.exception), ADOPTED_TRACK_MSG)
        self.assertEqual(ADOPTED_TRACK_MSG, "Job này đã nạp shape mắt từ CVAT nên chỉ vẽ được shape "
                                            "(track mắt sẽ làm job thành chỉ xem ở lần mở sau).")
        self.assertEqual((dict(s.pins), len(s._undo)), (before, undo))
        with self.assertRaises(ValueError) as cm:                  # mắt đã có shape cũng báo câu này, không phải câu "đang là shape"
            s.pin_eye(9, "matphai", four("matphai", 9), kind="track")
        self.assertEqual(str(cm.exception), ADOPTED_TRACK_MSG)
        s.pin_eye(9, "mattrai", four("mattrai", 9), kind="shape")  # nói rõ shape thì được
        self.assertTrue(s.has_shape("mattrai", 9))

    def test_kind_stays_shape_after_deleting_last_shape(self):
        s = self.session(adopted("mattrai", 3), adopted("matphai", 3))
        s.delete_shape("mattrai", 3)
        self.assertEqual(s.kind["mattrai"], "shape")
        self.assertEqual(s.shape_ids["mattrai"], {})
        s.delete_shape("matphai", 3)                               # hết nhãn cả hai mắt
        self.assertEqual(s.kind, {"mattrai": "shape", "matphai": "shape"})
        self.assertEqual(s.pins, {})
        eight = {i: p for i, p in T.pins_at(5).items() if i in EYES["mattrai"].ids}
        s.paste_points(8, eight)                                   # dán 8 điểm vào frame trống: shape
        self.assertTrue(s.has_shape("mattrai", 8))
        self.assertIn(8, s.shape_ids["mattrai"])
        s.undo()                                                   # hoàn tác trả đúng kiểu
        self.assertEqual(s.kind, {"mattrai": "shape", "matphai": "shape"})

    def test_new_layer_is_shape(self):
        s = self.session(adopted("mattrai", 3))
        n = s.add_layer()
        self.assertEqual((n, s.cur), (1, 1))
        self.assertEqual(s.kind, {"mattrai": "shape", "matphai": "shape"})
        s.pin_eye(5, "matphai", four("matphai", 5))
        self.assertTrue(s.has_shape("matphai", 5))
        s.undo()
        s.undo()                                                   # bỏ ghim rồi bỏ người mới
        self.assertEqual(len(s.layers), 1)
        s.redo()
        self.assertEqual(s.kind, {"mattrai": "shape", "matphai": "shape"})

    def test_non_adopted_session_keeps_old_behaviour(self):
        s = Session(self.dir)
        self.assertFalse(s.adopted)
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        s.delete_shape("mattrai", 3)
        self.assertEqual(s.kind["mattrai"], "track")              # mắt hết nhãn về track như trước
        s.add_layer()
        self.assertEqual(s.kind, {"mattrai": "track", "matphai": "track"})
        s.pin_eye(4, "mattrai", four("mattrai", 4), kind="track")  # vẫn vẽ được track
        self.assertEqual(s.kind["mattrai"], "track")
        self.assertNotIn("adopted", s.state())

    def test_state_roundtrip_keeps_adopted(self):
        s = self.session(adopted("mattrai", 3, {15: "occluded"}), adopted("matphai", 3))
        st = json.loads(json.dumps(s.state()))
        self.assertIs(st["adopted"], True)
        self.assertEqual(st["version"], 3)
        t = Session(self.dir)
        t.adopted = True                                          # lúc mở quyết định `adopted`, không phải file phiên
        t.load_state(st)
        self.assertTrue(t.adopted)
        self.assertEqual(t.pins, s.pins)
        self.assertEqual(t.flags, s.flags)
        self.assertEqual(t.kind, {"mattrai": "shape", "matphai": "shape"})
        self.assertEqual(t.shape_ids, s.shape_ids)
        wrong = copy.deepcopy(st)                                 # file ghi track (hoặc bản cũ không có kind): phiên đã nạp ép về shape
        wrong["layers"][0]["kind"] = {"mattrai": "track", "matphai": "track"}
        old = copy.deepcopy(st)
        old["version"] = 2
        del old["layers"][0]["kind"], old["layers"][0]["shape_ids"]
        for name, data in (("kind track", wrong), ("bản cũ", old)):
            with self.subTest(name):
                u = Session(self.dir)
                u.adopted = True
                u.load_state(data)
                self.assertEqual(u.kind, {"mattrai": "shape", "matphai": "shape"})
                self.assertTrue(u.has_shape("mattrai", 3))
                self.assertTrue(u.adopted)
        v = Session(self.dir)                                     # phiên không nạp: tải file không bật `adopted`
        v.load_state(st)
        self.assertFalse(v.adopted)
        plain = Session(self.dir)
        plain.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        self.assertNotIn("adopted", plain.state())

    def test_saved_shape_count(self):
        s = Session(self.dir)
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        s.pin_eye(5, "mattrai", four("mattrai", 5), kind="shape")
        s.pin_eye(5, "matphai", four("matphai", 5), kind="track")           # track không tính
        s.add_layer()
        s.pin_eye(7, "matphai", four("matphai", 7), kind="shape")
        st = json.loads(json.dumps(s.state()))
        self.assertEqual(saved_shape_count(st), 3)
        partial = copy.deepcopy(st)                                          # frame 3 của người 1 thiếu một điểm: không còn là shape đủ
        del partial["layers"][0]["pins"]["3"]["16"]
        self.assertEqual(saved_shape_count(partial), 2)
        self.assertEqual(saved_shape_count({"version": 2, "layers": [{"pins": {"3": {str(i): [1, 2] for i in EYES["mattrai"].ids}}}]}), 0)
        self.assertEqual(saved_shape_count({"version": 1, "pins": {"3": {str(i): [1, 2] for i in EYES["mattrai"].ids}}}), 0)
        a = self.session(adopted("mattrai", 3), adopted("matphai", 3), adopted("mattrai", 9))
        self.assertEqual(saved_shape_count(a.state()), 3)

    def test_scan_reads_session_shapes(self):
        good = {i: p for i, p in T.pins_at(5).items() if i in EYES["mattrai"].ids}
        bad = dict(good)
        bad[14], bad[18] = good[18], good[14]                      # hai khoé đổi chỗ: sai thứ tự khoé
        s = self.session(adopted("mattrai", 5, pts=bad))
        found = s.run_scan()
        self.assertIs(found, s.findings)
        reds = [f for f in found if f.level == "red" and f.frame <= 5 <= f.last]
        self.assertIn("corner_order", {f.code for f in reds})
        self.assertTrue(all(f.label == "mattrai" for f in reds))
        s.drag_points(5, {14: good[14], 18: good[18]})             # sửa lại hai khoé
        self.assertEqual(s.pins[5][14], good[14])
        self.assertEqual([f for f in s.run_scan() if f.level == "red"], [])

    def test_scan_of_plain_session_still_reads_ann(self):
        s = Session(self.dir)
        s.pin_eye(5, "mattrai", four("mattrai", 5), kind="shape")
        s.drag_points(5, {14: (300.0, 80.0)})                      # sai thứ tự khoé, nhưng không nạp nên quét không thấy
        self.assertEqual(s.run_scan(), [])                         # quét `ann` (không có nhãn), không quét ghim của phiên

    def test_scan_prefers_first_shape_when_two_people_share_a_frame(self):
        """Hai người cùng nhãn cùng frame: quét lấy shape của người đầu (shape có ID nhỏ hơn, `build_shapes` xếp trước)."""
        good = {i: p for i, p in T.pins_at(5).items() if i in EYES["mattrai"].ids}
        bad = dict(good)
        bad[14], bad[18] = good[18], good[14]
        for first, second, want in (("good", "bad", False), ("bad", "good", True)):
            with self.subTest(first=first):
                s = self.session(adopted("mattrai", 5, pts=good if first == "good" else bad))
                s.add_layer()
                s.pin_eye(5, "mattrai", four("mattrai", 5))
                if second == "bad":
                    s.drag_points(5, {14: good[18], 18: good[14]})
                s.select_layer(0)
                codes = {f.code for f in s.run_scan() if f.level == "red"}
                self.assertEqual("corner_order" in codes, want)

    def test_degenerate_shape_is_handled(self):
        base = {i: p for i, p in T.pins_at(5).items() if i in EYES["mattrai"].ids}
        same_corners = dict(base)
        same_corners[18] = same_corners[14]                       # hai khoé trùng nhau
        one_point = {i: (100.0, 80.0) for i in EYES["mattrai"].ids}
        for name, pts in (("hai khoé trùng", same_corners), ("cả 8 điểm trùng", one_point)):
            with self.subTest(name):
                s = self.session(adopted("mattrai", 5, pts=pts), adopted("matphai", 5))
                self.assertTrue(s.has_shape("mattrai", 5))
                s.run_scan()
                built = s.build_shapes()
                self.assertEqual(len(built), 2)
                s.recompute()
                s.state()
                self.assertEqual({i: s.pins[5][i] for i in EYES["mattrai"].ids}, pts)


if __name__ == "__main__":
    unittest.main()
