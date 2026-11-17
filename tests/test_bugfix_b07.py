"""B07 (buglist.md, TASKS.md mục 8): `Session.load_pins` (đường nạp file `--pins`) không "tất cả hoặc không gì".

Đã tái hiện trên ảnh giả của `test_tracking` (không dùng dữ liệu công ty) trước khi sửa:
- NaN trong toạ độ: ghim frame trước rồi mới vỡ trong bộ bám ("cannot convert float NaN to integer", tiếng Anh), phiên đã đổi (pins, undo, stale);
- inf: OverflowError (không phải ValueError) nên lệnh `turns`/`report`/`gui --pins` in Traceback;
- chuỗi số ["86", "80"], điểm ba toạ độ, id điểm lạ (99), toạ độ ngoài ảnh: nhận im lặng;
- hai khoé trùng ở frame sau một frame hợp lệ: frame trước đã ghim, mắt kia của frame lỗi kẹt lại trong `pending`;
- frame chỉ có một mắt: bỏ im lặng (mắt đó kẹt trong `pending`, không thành keyframe), dù thiết kế mới cho phép frame ghim một mắt;
- hai khoá cùng một frame ("0" và "00"): nhận im lặng, để rác trong `pending`;
- mỗi frame một bước hoàn tác và một lần tính lại.

Hành vi sau khi sửa: kiểm hết mọi frame trước khi đổi gì; sai thì ValueError tiếng Việt nêu frame, mắt, điểm, lý do, và phiên y nguyên.
Frame một mắt được nạp như `Session.pin_eye` (keyframe của riêng mắt đó). Hợp lệ hết thì ghim trong một bước hoàn tác, tính lại một lần."""
import copy
import gc
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CASE01 = r"C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che"
PINS_CASE01 = os.path.join(ROOT, "spike", "out", "pins_case01_ai.json")
NAN, INF = float("nan"), float("inf")
DROP = object()                                             # bad_frame: xoá điểm này khỏi frame


def pj(f, label=None):
    """Điểm của frame f ở dạng file --pins (cả 8 điểm mỗi mắt, như test_headturn.pins_json); `label` thì chỉ mắt đó."""
    ids = EYES[label].ids if label else [i for spec in EYES.values() for i in spec.ids]
    return {str(i): list(p) for i, p in T.pins_at(f).items() if i in ids}


def four(f, label):
    truth = T.pins_at(f)
    return {i: truth[i] for i in EYES[label].pins}


def snapshot(s):
    """Mọi thứ load_pins có thể đổi: ghim, cờ, ước lượng, pending, hoàn tác/làm lại, keyframe từng mắt, nhãn do tool tính, ID, cờ dirty."""
    return {"pins": copy.deepcopy(s.pins), "flags": copy.deepcopy(s.flags), "estimates": copy.deepcopy(s.estimates),
            "pending": copy.deepcopy(s.pending), "undo": copy.deepcopy(s._undo), "redo": copy.deepcopy(s._redo),
            "keys": {l: s.eye_keyframes(l) for l in EYES}, "labels": sorted(s.labels), "ids": dict(s.obj_ids),
            "next_id": s.next_id, "dirty": s.dirty, "touched": dict(s.touched), "stale": s.stale, "layers": len(s.layers)}


class LoadPinsAllOrNothingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b07_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        self._busy = None                                   # một phiên "có việc" dùng chung trong một test (máy ít bộ nhớ ảo)

    def tearDown(self):
        self._busy = None
        gc.collect()

    def busy_session(self):
        """Phiên đã có việc: ghim frame 0 và 40, một cờ Occluded, một bước làm lại; để thấy được mọi thay đổi lén."""
        s = Session(self.dir)
        for f in (0, 40):
            for label in EYES:
                s.add_pin(f, label, four(f, label))
        s.toggle_flag(40, 23, "occluded")
        for label in EYES:
            s.add_pin(50, label, four(50, label))
        s.undo()                                            # bỏ frame 50 -> có một bước làm lại
        assert sorted(s.pins) == [0, 40] and s.flags == {40: {23: "occluded"}} and s._redo
        return s

    def assert_rejected(self, data, *parts):
        """load_pins(data) phải ném ValueError chứa mọi chuỗi `parts` và để phiên y nguyên. Mọi lần gọi trong một test dùng chung một phiên:
        lần bị từ chối trước mà lén đổi gì thì lần sau cũng thấy (so với bản chụp ngay trước mỗi lần gọi)."""
        if self._busy is None:
            self._busy = self.busy_session()
        s = self._busy
        before = snapshot(s)
        with self.assertRaises(ValueError) as cm:
            s.load_pins(data)
        msg = str(cm.exception)
        for p in parts:
            self.assertIn(p, msg)
        self.assertEqual(snapshot(s), before, msg)          # sai thì không đổi gì, kể cả hoàn tác
        return msg

    def bad_frame(self, f=30, **change):
        """Dữ liệu có frame 20 hợp lệ (đứng TRƯỚC frame lỗi) và frame `f` bị sửa theo `change` {id: giá trị | DROP (xoá)}."""
        data = {"_note": "ghi chú", "20": pj(20), str(f): pj(f)}
        for i, v in change.items():
            if v is DROP:
                del data[str(f)][i.lstrip("p")]
            else:
                data[str(f)][i.lstrip("p")] = v
        return data

    # ---- toạ độ ----
    def test_nan_is_rejected(self):
        self.assert_rejected(self.bad_frame(p14=[NAN, 80.0]), "frame 30", "mattrai", "điểm 14", "hữu hạn")
        self.assert_rejected(self.bad_frame(p26=[200.0, NAN]), "frame 30", "matphai", "điểm 26", "hữu hạn")

    def test_nan_from_json_text_is_rejected(self):
        text = json.dumps(self.bad_frame(p14=[NAN, 80.0]))
        self.assertIn("NaN", text)
        self.assert_rejected(json.loads(text), "frame 30", "hữu hạn")   # json của Python đọc được NaN / Infinity trong file

    def test_inf_is_rejected(self):
        self.assert_rejected(self.bad_frame(p18=[INF, 80.0]), "frame 30", "mattrai", "điểm 18", "hữu hạn")
        self.assert_rejected(self.bad_frame(p28=[200.0, -INF]), "frame 30", "matphai", "điểm 28", "hữu hạn")
        text = json.dumps(self.bad_frame(p14="MARK")).replace('"MARK"', "[1e400, 80]")
        self.assert_rejected(json.loads(text), "frame 30", "điểm 14", "hữu hạn")   # 1e400 trong file JSON thành inf
        self.assert_rejected(self.bad_frame(p14=[10 ** 400, 80]), "frame 30", "điểm 14", "hữu hạn")   # số nguyên quá lớn cho float

    def test_strings_and_bad_shapes_are_rejected(self):
        for v in (["86", "80"], "86,80", [86.0, "80"], [True, 80.0], [86.0], [86.0, 80.0, 1.0], None, {"x": 86, "y": 80}):
            self.assert_rejected(self.bad_frame(p14=v), "frame 30", "mattrai", "điểm 14", "hai số")

    def test_out_of_image_is_rejected(self):
        for v in ([-0.5, 80.0], [T.W + 0.5, 80.0], [100.0, -1.0], [100.0, T.H + 2.0], [T.W + 500.0, 80.0]):
            self.assert_rejected(self.bad_frame(p14=v), "frame 30", "mattrai", "điểm 14", "ngoài ảnh", f"{T.W}×{T.H}")
        self.assert_rejected(self.bad_frame(p17=[-3.0, 80.0]), "frame 30", "điểm 17", "ngoài ảnh")   # cả điểm suy ra có trong file

    def test_image_border_is_inside(self):
        """Mép ảnh (0 và đúng chiều rộng/cao) vẫn là trong ảnh, như luật "ngoài khung" của scan."""
        s = Session(self.dir)
        data = {"0": pj(0)}
        data["0"]["15"] = [0.0, 0.0]                        # điểm suy ra: được kiểm nhưng không dùng
        data["0"]["29"] = [float(T.W), float(T.H)]
        self.assertEqual(s.load_pins(data), 1)

    # ---- hình mắt ----
    def test_coincident_corners_are_rejected(self):
        d = self.bad_frame()
        d["30"]["18"] = list(d["30"]["14"])
        self.assert_rejected(d, "frame 30", "mattrai", "hai khoé mắt trùng nhau")
        d = self.bad_frame()
        d["30"]["26"] = list(d["30"]["22"])
        self.assert_rejected(d, "frame 30", "matphai", "hai khoé mắt trùng nhau")

    def test_shape_rules_of_validate_four(self):
        d = self.bad_frame()
        d["30"]["14"], d["30"]["18"] = d["30"]["18"], d["30"]["14"]
        self.assert_rejected(d, "frame 30", "mattrai", "khoé đầu phải nằm bên trái")
        d = self.bad_frame()
        d["30"]["24"], d["30"]["28"] = d["30"]["28"], d["30"]["24"]
        self.assert_rejected(d, "frame 30", "matphai", "giữa mí trên đang nằm dưới")

    def test_eye_missing_a_pin_is_rejected(self):
        self.assert_rejected(self.bad_frame(p16=DROP), "frame 30", "mattrai", "thiếu điểm ghim")
        only_derived = {"20": pj(20), "30": {"15": pj(30)["15"]}}
        self.assert_rejected(only_derived, "frame 30", "mattrai", "thiếu điểm ghim")

    # ---- frame và id ----
    def test_bad_frame_keys_are_rejected(self):
        for key, part in (("60", "ngoài phạm vi"), ("-1", "ngoài phạm vi"), ("999", "ngoài phạm vi"),
                          ("abc", "không phải số"), ("1.5", "không phải số"), ("", "không phải số")):
            self.assert_rejected({"20": pj(20), key: pj(30)}, part)

    def test_duplicate_frame_is_rejected(self):
        self.assert_rejected({"20": pj(20), "30": pj(30), "030": pj(30)}, "frame 30", "hai lần")

    def test_unknown_point_ids_are_rejected(self):
        for pid in ("99", "13", "30", "0", "abc", "1.5"):
            d = self.bad_frame()
            d["30"][pid] = [100.0, 80.0]
            self.assert_rejected(d, "frame 30", "id điểm")

    def test_empty_or_malformed_frame_is_rejected(self):
        self.assert_rejected({"20": pj(20), "30": {}}, "frame 30", "không có điểm")
        self.assert_rejected({"20": pj(20), "30": [[1, 2]]}, "frame 30", "sai định dạng")
        self.assert_rejected({"20": pj(20), "30": None}, "frame 30", "sai định dạng")

    def test_not_an_object_is_rejected(self):
        for data in ([1, 2], None, "abc"):
            self.assert_rejected(data, "đối tượng JSON")

    # ---- hợp lệ ----
    def test_one_eye_frame_is_loaded_like_pin_eye(self):
        s = Session(self.dir)
        self.assertEqual(s.load_pins({"0": pj(0), "20": pj(20, "mattrai"), "40": pj(40, "matphai")}), 3)
        self.assertEqual(s.eye_keyframes("mattrai"), [0, 20])
        self.assertEqual(s.eye_keyframes("matphai"), [0, 40])
        self.assertEqual(s.pending, {})                     # không còn mắt nào kẹt lại
        self.assertEqual(set(s.pins[20]), set(EYES["mattrai"].ids))
        self.assertTrue(set(EYES["matphai"].ids) <= set(s.labels[20].points))   # mắt kia ở frame 20 do tool bám từ frame 0
        ref = Session(self.dir)                              # cùng kết quả với ghim từng mắt bằng tay (pin_eye)
        for f, labels in ((0, EYES), (20, ["mattrai"]), (40, ["matphai"])):
            for label in labels:
                ref.pin_eye(f, label, four(f, label))
        self.assertEqual(s.pins, ref.pins)
        self.assertEqual({f: r.points for f, r in s.labels.items()}, {f: r.points for f, r in ref.labels.items()})

    def test_one_eye_frame_keeps_the_other_eye_and_its_flags(self):
        s = self.busy_session()
        ref = self.busy_session()
        s.load_pins({"40": pj(41, "mattrai")})
        ref.pin_eye(40, "mattrai", four(41, "mattrai"))
        self.assertEqual((s.pins, s.flags), (ref.pins, ref.flags))
        self.assertEqual(s.flags[40], {23: "occluded"})     # cờ của matphai ở frame 40 còn nguyên

    def test_whole_file_is_one_undo_step(self):
        s = Session(self.dir)
        self.assertEqual(s.load_pins({"_note": "x", "0": pj(0), "20": pj(20), "40": pj(40)}), 3)
        self.assertEqual(len(s._undo), 1)
        self.assertTrue(s.undo())
        self.assertEqual((s.pins, s.labels), ({}, {}))
        self.assertTrue(s.redo())
        self.assertEqual(sorted(s.pins), [0, 20, 40])

    def test_notes_only_changes_nothing(self):
        s = self.busy_session()
        before = snapshot(s)
        self.assertEqual(s.load_pins({"_note": "chỉ có ghi chú"}), 0)
        self.assertEqual(snapshot(s), before)


class CliTests(unittest.TestCase):
    """Lệnh dùng --pins: dữ liệu sai in một dòng "Lỗi: ..." và trả 2, không Traceback (trước khi sửa: inf ném OverflowError)."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b07_cli_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))
        cls.inf = os.path.join(cls.dir, "inf.json")
        data = {"0": pj(0), "20": pj(20)}
        data["20"]["14"] = [INF, 80.0]
        with open(cls.inf, "w", encoding="utf-8") as fh:
            json.dump(data, fh)                             # ghi chữ Infinity như json của Python

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_cli(self, *args):
        env = dict(os.environ, EYEPIN_HOME=tempfile.mkdtemp(prefix="eyepin_home_"))
        return subprocess.run([sys.executable, "-m", "eyepin", *args], cwd=ROOT, capture_output=True, encoding="utf-8", env=env)

    def test_turns_and_report_reject_inf(self):
        for cmd in ("turns", "report"):
            p = self.run_cli(cmd, self.dir, "--pins", self.inf)
            self.assertEqual(p.returncode, 2, (cmd, p.stdout, p.stderr))
            self.assertNotIn("Traceback", p.stderr)
            self.assertIn("Lỗi: frame 20, mắt mattrai, điểm 14", p.stdout)

    def test_gui_rejects_inf(self):
        p = self.run_cli("gui", self.dir, "--pins", self.inf, "--selftest")
        self.assertEqual(p.returncode, 2, (p.stdout, p.stderr))
        self.assertNotIn("Traceback", p.stderr)
        self.assertIn("hữu hạn", p.stdout)


@unittest.skipUnless(os.path.isdir(CASE01) and os.path.exists(PINS_CASE01), "thiếu ảnh case 01 hoặc file ghim thô")
class SampleFileTests(unittest.TestCase):
    def test_whole_case01_file_loads(self):
        with open(PINS_CASE01, encoding="utf-8") as fh:
            raw = json.load(fh)
        frames = sorted(int(k) for k in raw if not k.startswith("_"))
        s = Session(CASE01)
        self.assertEqual(s.load_pins(raw), len(frames))
        for label in EYES:
            self.assertEqual(s.eye_keyframes(label), frames)
        self.assertEqual(len(s._undo), 1)


if __name__ == "__main__":
    unittest.main()
