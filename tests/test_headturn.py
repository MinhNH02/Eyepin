import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import headturn as H  # noqa: E402
from eyepin.geometry import EYES, MATPHAI, MATTRAI  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CASE01 = r"C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che"
FRONTAL = r"C:\Users\minhf\Downloads\dms_build\physdrive_seg"
PINS_CASE01 = os.path.join(ROOT, "spike", "out", "pins_case01_ai.json")
PINS_FRONTAL = os.path.join(ROOT, "spike", "out", "pins_ai.json")


def eye(spec, cx, width):
    """8 điểm của một mắt, tâm (cx, 100): hai khoé ở cx ∓ width/2, ba điểm mí trên và ba điểm mí dưới rải đều."""
    pts = {spec.first: (cx - width / 2, 100.0), spec.last: (cx + width / 2, 100.0)}
    for k, t in enumerate((0.25, 0.5, 0.75)):
        pts[spec.first + 1 + k] = (cx - width / 2 + t * width, 95.0)
        pts[spec.first + 7 - k] = (cx - width / 2 + t * width, 105.0)
    return pts


def clip(ratios, far=1.0, pins=None, low=(), no_left=(), empty=()):
    """(n_frames, points, scores, keys) của một clip: mắt matphai cách mattrai 150 * ratio px; ở frame ratio < 0,86 mattrai hẹp còn `far` lần.
    Frame ghim có độ khớp 1,0; frame thường 0,95; frame trong `low` 0,5."""
    n = len(ratios)
    pins = tuple(range(0, n, 10)) if pins is None else tuple(pins)
    points, scores = {}, {}
    for f, r in enumerate(ratios):
        if f in empty:
            continue
        pts = {}
        if f not in no_left:
            pts.update(eye(MATTRAI, 100.0, 60.0 * (far if r < 0.86 else 1.0)))
        pts.update(eye(MATPHAI, 100.0 + 150.0 * r, 60.0))
        points[f] = pts
        s = 1.0 if f in pins else (0.5 if f in low else 0.95)
        scores[f] = {"mattrai": s, "matphai": s}
    return n, points, scores, {"mattrai": set(pins), "matphai": set(pins)}


def dip(n, a, b, value):
    r = [1.0] * n
    for f in range(a, b):
        r[f] = value
    return r


class DetectTests(unittest.TestCase):
    def test_straight_clip_has_no_turn(self):
        rep = H.detect(*clip([1.0] * 60, pins=(0, 20, 40)))
        self.assertEqual(rep.status, "ok")
        self.assertEqual(rep.turns, ())
        self.assertAlmostEqual(rep.baseline, 150.0, places=6)

    def test_shrink_for_thirty_frames(self):
        rep = H.detect(*clip(dip(60, 20, 50, 0.68), far=0.5))
        self.assertEqual(len(rep.turns), 1)
        t = rep.turns[0]
        self.assertEqual((t.first, t.last), (20, 49))
        self.assertAlmostEqual(t.shrink, 0.32, delta=0.005)
        self.assertEqual(t.level, "mạnh")
        self.assertEqual(t.confirmed, 3)
        self.assertEqual(t.far_eye, "mattrai")
        self.assertEqual(t.unsure, 0)
        self.assertTrue(20 <= t.peak <= 49)

    def test_dip_shorter_than_five_frames_is_dropped(self):
        rep = H.detect(*clip(dip(60, 20, 24, 0.68), far=0.5))
        self.assertEqual(rep.turns, ())

    def test_untrusted_frames_hold_the_turn_and_do_not_set_shrink(self):
        r = dip(60, 20, 50, 0.68)
        for f in range(31, 40):
            r[f] = 0.01                       # bộ bám mất mắt: khoảng cách hai mắt vô nghĩa
        rep = H.detect(*clip(r, far=0.5, low=range(31, 40)))
        self.assertEqual(len(rep.turns), 1)
        t = rep.turns[0]
        self.assertEqual((t.first, t.last), (20, 49))
        self.assertEqual(t.unsure, 9)
        self.assertAlmostEqual(t.shrink, 0.32, delta=0.005)

    def test_untrusted_frames_never_start_a_turn(self):
        r = [1.0] * 60
        for f in range(31, 40):
            r[f] = 0.5
        rep = H.detect(*clip(r, low=range(31, 40)))
        self.assertEqual(rep.turns, ())
        self.assertEqual(rep.untrusted, 9)

    def test_one_eye_frames_count_as_turning(self):
        rep = H.detect(*clip([1.0] * 60, no_left=range(20, 40)))
        self.assertEqual(len(rep.turns), 1)
        t = rep.turns[0]
        self.assertEqual((t.first, t.last), (20, 39))
        self.assertEqual(t.one_eye, 20)
        self.assertIsNone(t.shrink)
        self.assertEqual(t.level, "một mắt")
        self.assertEqual(t.far_eye, "mattrai")

    def test_ratio_above_one_is_not_a_turn(self):
        wobble = [(0.95, 1.0, 1.05)[f % 3] for f in range(60)]
        rep = H.detect(*clip(wobble))
        self.assertEqual(rep.status, "ok")
        self.assertEqual(rep.turns, ())

    def test_fewer_than_three_two_eye_pins(self):
        rep = H.detect(*clip([1.0] * 60, pins=(0, 20)))
        self.assertEqual((rep.status, rep.turns, rep.baseline), ("few_pins", (), None))
        n, points, scores, keys = clip([1.0] * 60, pins=(0, 10, 20, 30))
        keys["matphai"] = {0}
        rep = H.detect(n, points, scores, keys)
        self.assertEqual((rep.status, rep.turns, rep.baseline), ("few_pins", (), None))
        self.assertEqual(rep.both_pins, 1)

    def test_levels(self):
        self.assertEqual(H.level_of(0.19), "nhẹ")
        self.assertEqual(H.level_of(0.20), "vừa")
        self.assertEqual(H.level_of(0.299), "vừa")
        self.assertEqual(H.level_of(0.30), "mạnh")
        self.assertEqual(H.level_of(None), "một mắt")

    def test_zero_baseline_does_not_divide(self):
        rep = H.detect(*clip([0.0] * 60))              # hai mắt trùng tâm ở mọi frame
        self.assertEqual(rep.status, "few_pins")
        self.assertEqual(rep.turns, ())

    def test_frames_without_any_eye_hold_state(self):
        rep = H.detect(*clip(dip(60, 20, 50, 0.68), far=0.5, pins=(0, 10, 20, 40, 50), empty=range(30, 35)))
        self.assertEqual(len(rep.turns), 1)
        t = rep.turns[0]
        self.assertEqual((t.first, t.last, t.unsure), (20, 49, 5))

    def test_turn_open_at_clip_end(self):
        rep = H.detect(*clip(dip(60, 40, 60, 0.68), far=0.5))
        self.assertEqual(len(rep.turns), 1)
        self.assertEqual((rep.turns[0].first, rep.turns[0].last), (40, 59))

    def test_deleted_frames_are_skipped(self):
        rep = H.detect(*clip(dip(60, 20, 50, 0.68), far=0.5, pins=(0, 10, 20, 40, 50)), skip={30, 31})
        self.assertEqual(len(rep.turns), 1)
        t = rep.turns[0]
        self.assertEqual((t.first, t.last, t.unsure), (20, 49, 0))

    def test_unconfirmed_turn_says_so(self):
        rep = H.detect(*clip(dip(60, 20, 50, 0.68), far=1.0))
        t = rep.turns[0]
        self.assertEqual(t.confirmed, 0)
        self.assertIsNone(t.far_eye)
        self.assertIn("chưa xác nhận (có thể do tiến/lùi)", t.message(1))

    def test_message_format(self):
        rep = H.detect(*clip(dip(60, 20, 50, 0.68), far=0.5), need_pin=[25, 26, 55])
        msg = rep.turns[0].message(1)
        self.assertTrue(msg.startswith("Quay đầu  #1  frame 20–49  co 32% (mạnh)  mắt xa: mattrai  xác nhận tại 3 ghim"), msg)
        self.assertIn("2 frame cần ghim", msg)


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def pins_json(frames):
    """Điểm ghim của cảnh tổng hợp ở dạng file --pins: {"frame": {"id": [x, y]}} (cả 16 điểm)."""
    return {str(f): {str(i): list(p) for i, p in T.pins_at(f).items()} for f in frames}


class SessionTurnTests(unittest.TestCase):
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
        for label, spec in EYES.items():
            s.add_pin(frame, label, {i: truth[i] for i in spec.pins})

    def test_turns_follow_recompute(self):
        s = Session(self.dir)
        self.assertEqual(len(s.turns), 1)
        self.assertEqual(s.turns[0].status, "few_pins")
        for f in (0, 20, 40):
            self.pin_both(s, f)
        self.assertEqual(s.turns[0].status, "ok")
        self.assertEqual(s.turns[0].both_pins, 3)
        self.assertEqual(s.turns[0].turns, ())             # cảnh tổng hợp chỉ dời, không quay đầu

    def test_turns_follow_undo(self):
        s = Session(self.dir)
        for f in (0, 20, 40):
            self.pin_both(s, f)
        self.assertTrue(s.undo())
        self.assertEqual((s.turns[0].both_pins, s.turns[0].status), (2, "few_pins"))
        self.assertTrue(s.redo())
        self.assertEqual(s.turns[0].status, "ok")

    def test_one_report_per_layer(self):
        s = Session(self.dir)
        for f in (0, 20, 40):
            self.pin_both(s, f)
        s.add_layer()
        s.recompute()
        self.assertEqual(len(s.turns), 2)
        self.assertEqual(s.turns[1].status, "few_pins")

    def test_load_pins(self):
        s = Session(self.dir)
        data = pins_json((0, 20, 40))
        data["_note"] = "ghim thô"
        self.assertEqual(s.load_pins(data), 3)
        self.assertEqual(sorted(s.pins), [0, 20, 40])
        for bad, text in (({"999": pins_json([0])["0"]}, "ngoài phạm vi"), ({"abc": pins_json([0])["0"]}, "không phải số")):
            s2 = Session(self.dir)
            with self.assertRaises(ValueError) as cm:
                s2.load_pins(bad)
            self.assertIn(text, str(cm.exception))
            self.assertEqual(s2.pins, {})
        short = pins_json([0, 20])
        del short["20"]["16"]                               # mattrai thiếu một điểm ghim
        s3 = Session(self.dir)
        with self.assertRaises(ValueError) as cm:
            s3.load_pins(short)
        self.assertIn("thiếu điểm", str(cm.exception))
        self.assertEqual(s3.pins, {})                       # sai thì không ghim gì

    def test_outside_points_are_left_out(self):
        s = Session(self.dir)
        for f in (0, 10, 20, 40):
            self.pin_both(s, f)
        for i in EYES["mattrai"].ids:
            s.toggle_flag(20, i, "outside")
        rep = H.for_session(s)[0]
        self.assertEqual(rep.both_pins, 3)
        self.assertEqual(len(rep.turns), 1)
        self.assertEqual((rep.turns[0].first, rep.turns[0].last), (20, 39))
        self.assertGreater(rep.turns[0].one_eye, 0)
        self.assertEqual(s.turns[0].turns, rep.turns)       # đổi cờ cũng cập nhật Session.turns


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_cli_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))
        cls.good = os.path.join(cls.dir, "ghim.json")
        cls.bad = os.path.join(cls.dir, "sai.json")
        with open(cls.good, "w", encoding="utf-8") as fh:
            json.dump(pins_json((0, 20, 40)), fh)
        with open(cls.bad, "w", encoding="utf-8") as fh:
            json.dump(pins_json([999]), fh)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "eyepin", *args], cwd=ROOT, capture_output=True, encoding="utf-8")

    def test_turns_prints_report(self):
        p = self.run_cli("turns", self.dir, "--pins", self.good)
        self.assertEqual(p.returncode, 0, p.stderr)
        for text in ("3 frame ghim", "nguồn điểm ghim: ghim.json", "Không có đoạn quay đầu.", "Giới hạn:", "khoảng cách ghim trung vị 20"):
            self.assertIn(text, p.stdout)

    def test_turns_reports_bad_pins_file(self):
        p = self.run_cli("turns", self.dir, "--pins", self.bad)
        self.assertEqual(p.returncode, 2)
        self.assertIn("ngoài phạm vi", p.stdout)
        self.assertNotIn("Traceback", p.stderr)
        p = self.run_cli("turns", self.dir, "--pins", os.path.join(self.dir, "khong_co.json"))
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)

    def test_pins_file_that_is_not_an_object_is_reported_not_crashed(self):
        for name, text in (("mang.json", "[1, 2]"), ("null.json", "null")):
            path = os.path.join(self.dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            p = self.run_cli("turns", self.dir, "--pins", path)
            self.assertEqual(p.returncode, 2, (name, p.stdout, p.stderr))
            self.assertNotIn("Traceback", p.stderr)
            self.assertIn("Lỗi", p.stdout)
            # cửa sổ cũng phải từ chối ngay, không được mở ở chế độ thường (tự lưu được) mà không báo gì
            p = self.run_cli("gui", self.dir, "--pins", path, "--selftest")
            self.assertEqual(p.returncode, 2, (name, p.stdout, p.stderr))
            self.assertNotIn("Traceback", p.stderr)

    def test_few_pins_message(self):
        with open(os.path.join(self.dir, "it.json"), "w", encoding="utf-8") as fh:
            json.dump(pins_json((0, 20)), fh)
        p = self.run_cli("turns", self.dir, "--pins", os.path.join(self.dir, "it.json"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("Chưa đủ ghim để phát hiện (cần ít nhất 3 frame ghim đủ hai mắt, đang có 2).", p.stdout)


@unittest.skipUnless(os.path.isdir(CASE01) and os.path.exists(PINS_CASE01), "thiếu ảnh case 01 hoặc file ghim thô")
class RealCase01Tests(unittest.TestCase):
    def test_case01_two_turns(self):
        raw = read_json(PINS_CASE01)
        keep = {k: v for k, v in raw.items() if k.startswith("_") or int(k) % 10 == 0 or int(k) == 209}
        s = Session(CASE01)
        self.assertEqual(s.load_pins(keep), 22)
        rep = s.turns[0]
        self.assertEqual(rep.status, "ok")
        self.assertEqual(len(rep.turns), 2, [t.message(i + 1) for i, t in enumerate(rep.turns)])
        a, b = rep.turns
        self.assertTrue(a.first <= 30 and a.last >= 65 and abs(a.first - 21) <= 10 and abs(a.last - 79) <= 10, a.message(1))
        self.assertTrue(b.first <= 105 and b.last >= 145 and abs(b.first - 100) <= 10 and abs(b.last - 160) <= 10, b.message(2))
        for t in rep.turns:
            self.assertEqual(t.far_eye, "mattrai")
            self.assertGreaterEqual(t.confirmed, 1)


@unittest.skipUnless(os.path.isdir(FRONTAL) and os.path.exists(PINS_FRONTAL), "thiếu ảnh đoạn mặt thẳng hoặc file ghim")
class RealFrontalTests(unittest.TestCase):
    def test_frontal_clip_has_no_turn(self):
        s = Session(FRONTAL)
        s.load_pins(read_json(PINS_FRONTAL))
        self.assertEqual(s.turns[0].status, "ok")
        self.assertEqual(s.turns[0].turns, ())


if __name__ == "__main__":
    unittest.main()
