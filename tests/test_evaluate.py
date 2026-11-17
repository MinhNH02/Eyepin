import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import evaluate as E  # noqa: E402
from eyepin import overlap as O  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_headturn as TH  # noqa: E402
import test_tracking as T  # noqa: E402

LINE, FWD, BI = E.METHODS


class EvaluateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_eval_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def pin_both(self, s, frame):
        truth = T.pins_at(frame)
        for label, spec in EYES.items():
            s.add_pin(frame, label, {i: truth[i] for i in spec.pins})

    def session(self, frames):
        s = Session(self.dir)
        for f in frames:
            self.pin_both(s, f)
        return s

    def test_straight_line_error_equals_the_built_curve_and_forward_is_near_zero(self):
        ev = E.evaluate(self.session((0, 20, 40)))
        self.assertEqual(len(ev.samples), 2)                 # một mẫu mỗi mắt, tại frame ghim giữa
        self.assertEqual((ev.untestable, ev.spacing, ev.pins), (4, 20, 3))
        for smp in ev.samples:
            self.assertEqual((smp.frame, smp.prev, smp.next), (20, 0, 40))
            self.assertAlmostEqual(smp.errors[LINE], 15.0, delta=0.01)      # đầu đứng yên tới frame 20, đường thẳng đoán 15 px
            self.assertLess(smp.errors[FWD], 1.0)
            self.assertLess(smp.errors[BI], 1.0)                            # dời thuần: bám lùi cũng đúng, trộn hai phía vẫn đúng
            self.assertGreater(smp.width, 10)
            self.assertFalse(smp.closed)
            self.assertFalse(smp.in_turn)
            self.assertGreater(smp.overlaps[FWD].iou, 0.85)
            self.assertGreater(smp.overlaps[BI].iou, 0.85)
            self.assertLess(smp.overlaps[LINE].iou, 0.6)                   # lệch ngang 15 px trên mắt rộng 48 px
            self.assertTrue(0.3 < smp.ref_iou < 0.95)                       # mốc: chính nhãn đúng dời 1 px vuông góc trục mắt

    def test_report_never_changes_the_tool_labels(self):
        s = self.session((0, 20, 40))
        before = {f: dict(r.points) for f, r in s.labels.items()}
        E.evaluate(s)
        self.assertEqual({f: dict(r.points) for f, r in s.labels.items()}, before)

    def test_two_way_choice_rule(self):
        fwd, back = {1: (0.0, 0.0)}, {1: (10.0, 20.0)}
        self.assertEqual(E.choose(fwd, 0.9, back, 0.5, 0.5), fwd)           # chỉ phía tiến đủ khớp
        self.assertEqual(E.choose(fwd, 0.5, back, 0.9, 0.5), back)          # chỉ phía lùi đủ khớp
        self.assertEqual(E.choose(fwd, 0.9, back, 0.9, 0.25), {1: (2.5, 5.0)})   # cả hai đủ khớp: trộn theo thời gian
        self.assertEqual(E.choose(fwd, 0.1, back, 0.2, 0.75), {1: (7.5, 15.0)})  # cả hai kém: cũng trộn

    def test_two_way_recovers_when_the_forward_side_is_wrong(self):
        s = Session(self.dir)
        t0 = T.pins_at(0)
        s.add_pin(0, "mattrai", {i: (t0[i][0], t0[i][1] - 12) for i in EYES["mattrai"].pins})     # ghim đầu của mattrai lệch 12 px lên trên
        s.add_pin(0, "matphai", {i: t0[i] for i in EYES["matphai"].pins})
        self.pin_both(s, 20)
        self.pin_both(s, 40)
        ev = E.evaluate(s)
        left = next(x for x in ev.samples if x.label == "mattrai")
        self.assertGreater(left.errors[FWD], 8.0)                          # bám tiến mang theo chỗ lệch của ghim đầu
        self.assertLess(left.errors[BI], left.errors[FWD])                 # bám lùi từ ghim sau kéo về gần đúng
        self.assertGreater(left.overlaps[BI].iou, left.overlaps[FWD].iou)

    def test_no_iou_when_the_true_label_has_estimated_or_outside_points(self):
        s = self.session((0, 20, 40))
        s.estimates[20] = {14: 4.5}                                         # khoé ước lượng của mattrai
        s.flags[20] = {26: "outside"}                                       # một điểm Outside của matphai
        ev = E.evaluate(s)
        self.assertEqual(len(ev.samples), 2)
        self.assertEqual([x.overlaps for x in ev.samples], [{}, {}])
        self.assertEqual(ev.no_region, 2)
        self.assertIn("2 mẫu không tính IoU", E.format_table(ev, "x.json"))

    def test_pins_that_are_not_four_hand_placed_points_are_excluded(self):
        s = self.session((0, 40))
        s.toggle_pin_here(20)                                # phím K: ghim đúng vị trí bộ bám tính
        ev = E.evaluate(s)
        self.assertEqual(ev.samples, [])
        self.assertEqual(ev.excluded_manual, 2)
        self.assertEqual(ev.untestable, 4)

    def test_closed_eye_pin_goes_to_the_blink_group(self):
        s = self.session((0, 40))
        truth = T.pins_at(20)
        for label, spec in EYES.items():
            a, b = truth[spec.first], truth[spec.last]
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            s.add_pin(20, label, {spec.first: a, spec.last: b, spec.up: mid, spec.lo: mid})    # hai mí khép lại trên đường nối hai khoé
        ev = E.evaluate(s)
        self.assertEqual([x.closed for x in ev.samples], [True, True])
        groups = dict(E.groups(ev))
        self.assertEqual(len(groups[E.GROUP_BLINK]), 2)
        self.assertEqual(len(groups[E.GROUP_ALL]), 0)
        for x in ev.samples:                                                # mắt nhắm hẳn mà đoán mở: vùng không chung chút nào
            self.assertEqual(x.overlaps[FWD].iou, 0.0)
            self.assertIsNone(x.ref_iou)                                    # mắt nhắm không có vùng để làm mốc
        E.format_table(ev, "x.json")                                        # in được, không lỗi

    def test_turn_membership_comes_from_the_session_turns(self):
        s = self.session((0, 20, 40))
        from eyepin.headturn import Turn, TurnReport
        s.turns = [TurnReport("ok", 100.0, (Turn(15, 25, 20, 0.3, "mạnh", "mattrai", 1, 0, 0, 0),), 0, 3)]
        ev = E.evaluate(s)
        self.assertTrue(all(x.in_turn for x in ev.samples))
        groups = dict(E.groups(ev))
        self.assertEqual((len(groups[E.GROUP_IN]), len(groups[E.GROUP_OUT])), (2, 0))

    def test_estimates_and_outside_points_are_left_out_of_the_mean(self):
        s = self.session((0, 20, 40))
        base = {x.label: x.errors[LINE] for x in E.evaluate(s).samples}
        s.estimates[20] = {14: 4.5}
        s.flags[20] = {26: "outside"}
        ev = E.evaluate(s)
        self.assertEqual(len(ev.samples), 2)
        for x in ev.samples:
            self.assertAlmostEqual(x.errors[LINE], base[x.label], delta=0.01)    # cảnh dời thuần: bỏ điểm nào sai số vẫn như nhau

    def test_single_point_error_helper_ignores_skipped_ids(self):
        pred = {1: (0.0, 0.0), 2: (10.0, 0.0), 3: (0.0, 6.0)}
        truth = {1: (3.0, 4.0), 2: (10.0, 0.0), 3: (0.0, 6.0)}
        self.assertAlmostEqual(E.mean_error(pred, truth, [1, 2, 3]), 5.0 / 3)
        self.assertAlmostEqual(E.mean_error(pred, truth, [1]), 5.0)
        self.assertIsNone(E.mean_error(pred, truth, []))

    def test_stats(self):
        st = E.stats([float(i) for i in range(1, 11)], [10.0] * 10)
        self.assertEqual((st.n, st.mean, st.median, st.p90), (10, 5.5, 5.5, 9.0))
        self.assertAlmostEqual(st.mean_pct, 55.0)
        self.assertEqual((st.ok5, st.ok10), (0, 1))          # 5% của 10 px = 0,5 px; 10% = 1 px (tính cả bằng)
        self.assertIsNone(E.stats([], []))

    def test_table_marks_small_groups_and_carries_context(self):
        smp = [E.Sample(0, "mattrai", 20 + i, 10, 30, 50.0, {LINE: 10.0, FWD: 2.0}, False, False) for i in range(3)]
        ev = E.Evaluation(smp, 4, 1, 0, 10.0, 6)
        text = E.format_table(ev, "ghim_thu.json")
        for part in ("nguồn điểm ghim: ghim_thu.json", "khoảng cách ghim trung vị 10 frame", "chưa đủ mẫu (3 mẫu)", "đo tại frame ghim bị giấu",
                     "không phải mọi frame", LINE, FWD, "3 mẫu", "4 ghim không kiểm được", "1 ghim không phải"):
            self.assertIn(part, text)
        empty = E.format_table(E.Evaluation([], 4, 0, 0, None, 2), "x.json")
        self.assertIn("Chưa có mẫu nào", empty)

    def test_table_prints_rates_when_enough_samples(self):
        smp = [E.Sample(0, "mattrai", 20 + i, 10, 30, 50.0, {LINE: 20.0, FWD: float(i)}, i % 2 == 0, False) for i in range(10)]
        text = E.format_table(E.Evaluation(smp, 0, 0, 0, 10.0, 12), "x.json")
        self.assertNotIn("chưa đủ mẫu (10", text)
        self.assertIn("≤5%", text)
        self.assertIn("≤10%", text)

    def test_table_puts_iou_first_and_lists_the_secondary_metrics(self):
        def ov(iou):
            return O.Overlap(iou, 2 * iou / (1 + iou), iou / 2, iou, iou, 1.0)
        smp = [E.Sample(0, "mattrai", 20 + i, 10, 30, 50.0, {LINE: 20.0, FWD: 2.0, BI: 1.0}, False, False,
                        {LINE: ov(0.2), FWD: ov(0.6 + 0.02 * i), BI: ov(0.8)}, 0.74) for i in range(10)]
        text = E.format_table(E.Evaluation(smp, 0, 0, 0, 10.0, 12), "x.json")
        for part in ("Chỉ số chính: IoU", "Dice", "Boundary IoU", "Precision", "Recall", "≥0.5", "≥0.75", BI,
                     "dời 1 px vuông góc trục mắt còn IoU 0.74", "IoU tb 0.69", "≥0.75 10/10 (100%)"):
            self.assertIn(part, text)
        block = text[text.index(FWD):]
        self.assertLess(block.index("IoU tb"), block.index("lệch điểm ghim"))   # IoU đứng trước sai số px của cùng cách đoán


class ReportCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_rep_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))
        cls.good = os.path.join(cls.dir, "ghim.json")
        with open(cls.good, "w", encoding="utf-8") as fh:
            json.dump(TH.pins_json((0, 20, 40)), fh)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "eyepin", *args], cwd=TH.ROOT, capture_output=True, encoding="utf-8")

    def test_report_prints_table(self):
        p = self.run_cli("report", self.dir, "--pins", self.good)
        self.assertEqual(p.returncode, 0, p.stderr)
        for part in (LINE, FWD, "nguồn điểm ghim: ghim.json", "đo tại frame ghim bị giấu", "2 mẫu"):
            self.assertIn(part, p.stdout)

    def test_report_rejects_bad_pins(self):
        p = self.run_cli("report", self.dir, "--pins", os.path.join(self.dir, "khong_co.json"))
        self.assertEqual(p.returncode, 2)
        self.assertNotIn("Traceback", p.stderr)


@unittest.skipUnless(os.path.isdir(TH.CASE01) and os.path.exists(TH.PINS_CASE01), "thiếu ảnh case 01 hoặc file ghim thô")
class RealCase01Tests(unittest.TestCase):
    def test_straight_line_is_worse_than_forward_tracking(self):
        raw = TH.read_json(TH.PINS_CASE01)
        keep = {k: v for k, v in raw.items() if k.startswith("_") or int(k) % 20 == 0 or int(k) == 209}
        s = Session(TH.CASE01)
        s.load_pins(keep)
        ev = E.evaluate(s)
        self.assertGreaterEqual(len(ev.samples), 5)
        line = E.stats([x.errors[LINE] for x in ev.samples], [x.width for x in ev.samples])
        fwd = E.stats([x.errors[FWD] for x in ev.samples], [x.width for x in ev.samples])
        self.assertGreater(line.mean, fwd.mean, E.format_table(ev, "pins_case01_ai.json"))
        self.assertTrue(any(x.in_turn for x in ev.samples))   # case 01 có đoạn quay đầu và có ghim bên trong

    def test_two_way_is_not_worse_than_forward_tracking(self):
        """Tiêu chí MVP 3 (spec mục 3): trên case 01, hai chiều chọn theo độ khớp không kém bám tiến, theo IoU (chỉ số chính) lẫn sai số px."""
        raw = TH.read_json(TH.PINS_CASE01)
        keep = {k: v for k, v in raw.items() if k.startswith("_") or int(k) % 20 == 0 or int(k) == 209}
        s = Session(TH.CASE01)
        s.load_pins(keep)
        ev = E.evaluate(s)
        open_eyes = dict(E.groups(ev))[E.GROUP_ALL]
        iou = {m: E.region_stats([x.overlaps[m] for x in open_eyes]).iou_mean for m in (FWD, BI)}
        px = {m: E.stats([x.errors[m] for x in open_eyes], [x.width for x in open_eyes]).mean for m in (FWD, BI)}
        self.assertGreaterEqual(iou[BI], iou[FWD], E.format_table(ev, "pins_case01_ai.json"))
        self.assertLessEqual(px[BI], px[FWD])


if __name__ == "__main__":
    unittest.main()
