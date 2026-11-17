import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import overlap as O  # noqa: E402
from eyepin.geometry import EYES, derive  # noqa: E402

SPEC = EYES["mattrai"]          # điểm 14..21 theo thứ tự quanh mắt


def rect(x0, y0, x1, y1):
    """8 điểm của mattrai xếp thành hình chữ nhật (theo thứ tự id quanh viền): dễ tính tay diện tích."""
    xm = (x0 + x1) / 2
    return {14: (x0, y0), 15: ((x0 + xm) / 2, y0), 16: (xm, y0), 17: ((xm + x1) / 2, y0),
            18: (x1, y0), 19: (x1, y1), 20: (xm, y1), 21: (x0, y1)}


def moved(pts, dx, dy):
    return {i: (x + dx, y + dy) for i, (x, y) in pts.items()}


def eye(cx=100.0, cy=50.0, half_w=36.0, half_h=7.0):
    """Mắt thật hơn: 8 điểm suy từ 4 điểm ghim bằng parabol như tool."""
    return derive(SPEC, {SPEC.first: (cx - half_w, cy), SPEC.last: (cx + half_w, cy),
                         SPEC.up: (cx - 0.02 * half_w, cy - half_h), SPEC.lo: (cx, cy + half_h)})


class OverlapTests(unittest.TestCase):
    def test_identical_regions_score_one_everywhere(self):
        r = O.compare(SPEC, eye(), eye())
        for v in (r.iou, r.dice, r.boundary_iou, r.precision, r.recall):
            self.assertAlmostEqual(v, 1.0, places=9)

    def test_shifted_rectangle_matches_hand_computed_values(self):
        truth = rect(0, 0, 40, 10)                       # diện tích 400
        pred = moved(truth, 10, 0)                       # chung 30×10 = 300, hợp 500
        r = O.compare(SPEC, pred, truth, band=1.0)
        self.assertAlmostEqual(r.iou, 0.6, places=9)
        self.assertAlmostEqual(r.dice, 0.75, places=9)
        self.assertAlmostEqual(r.precision, 0.75, places=9)
        self.assertAlmostEqual(r.recall, 0.75, places=9)
        # dải viền rộng 1 px: mỗi vùng 400 - 38×8 = 96; chung hai dải trên và dưới dài 30 = 60; hợp 96 + 96 - 60 = 132
        self.assertAlmostEqual(r.boundary_iou, 60 / 132, places=9)
        self.assertLess(r.boundary_iou, r.iou)           # Boundary IoU khắt khe với đường viền hơn IoU
        self.assertEqual(r.band, 1.0)

    def test_vertical_shift_hurts_a_flat_shape_more(self):
        truth = rect(0, 0, 40, 10)
        down = O.compare(SPEC, moved(truth, 0, 5), truth)
        self.assertAlmostEqual(down.iou, 200 / 600, places=9)
        side = O.compare(SPEC, moved(truth, 5, 0), truth)
        self.assertGreater(side.iou, down.iou)           # cùng 5 px nhưng mắt dẹt: lệch dọc mất nhiều IoU hơn

    def test_precision_and_recall_tell_too_big_from_too_small(self):
        truth = rect(0, 0, 40, 10)
        small = O.compare(SPEC, rect(10, 0, 30, 10), truth)    # đoán nằm gọn trong vùng đúng, nhỏ bằng nửa
        self.assertAlmostEqual(small.precision, 1.0, places=9)
        self.assertAlmostEqual(small.recall, 0.5, places=9)
        self.assertAlmostEqual(small.iou, 0.5, places=9)
        self.assertAlmostEqual(small.dice, 2 * 200 / 600, places=9)
        big = O.compare(SPEC, truth, rect(10, 0, 30, 10))      # đảo vai: đoán to quá
        self.assertAlmostEqual(big.precision, 0.5, places=9)
        self.assertAlmostEqual(big.recall, 1.0, places=9)

    def test_dice_is_a_monotone_function_of_iou(self):
        truth = eye()
        for dx, dy in ((1, 0), (0, 1), (3, 2), (8, -3)):
            r = O.compare(SPEC, moved(truth, dx, dy), truth)
            self.assertAlmostEqual(r.dice, 2 * r.iou / (1 + r.iou), places=9)

    def test_far_apart_regions_score_zero(self):
        truth = eye()
        r = O.compare(SPEC, moved(truth, 500, 0), truth)
        self.assertEqual((r.iou, r.dice, r.boundary_iou, r.precision, r.recall), (0.0, 0.0, 0.0, 0.0, 0.0))

    def test_closed_eye_scores_zero_against_an_open_one_and_none_against_another_closed_one(self):
        flat = {i: (float(70 + 8 * (i - 14)), 50.0) for i in SPEC.ids}   # cả 8 điểm trên một đường: mắt nhắm hẳn, diện tích 0
        self.assertIsNone(O.compare(SPEC, flat, flat))                     # 0/0: không có gì để so
        for pred, truth in ((eye(), flat), (flat, eye())):                 # đoán mở khi mắt nhắm, hoặc ngược lại: sai hẳn
            r = O.compare(SPEC, pred, truth)
            self.assertEqual((r.iou, r.dice, r.boundary_iou, r.precision, r.recall), (0.0, 0.0, 0.0, 0.0, 0.0))

    def test_default_band_follows_the_true_eye_width(self):
        self.assertAlmostEqual(O.compare(SPEC, eye(half_w=100), eye(half_w=100)).band, O.BAND_FRAC * 200)
        self.assertAlmostEqual(O.compare(SPEC, eye(half_w=10), eye(half_w=10)).band, O.MIN_BAND_PX)

    def test_band_wider_than_the_eye_makes_boundary_iou_equal_iou(self):
        truth = eye()
        pred = moved(truth, 2, 1)
        r = O.compare(SPEC, pred, truth, band=50.0)
        self.assertAlmostEqual(r.boundary_iou, r.iou, places=9)

    def test_sampling_is_accurate_on_a_real_eye_shape(self):
        truth = eye()
        area = O.area(SPEC, truth)
        xs = [truth[i][0] for i in SPEC.ids]
        ys = [truth[i][1] for i in SPEC.ids]
        exact = 0.5 * abs(sum(xs[k] * ys[k - 1] - xs[k - 1] * ys[k] for k in range(8)))   # công thức dây giày
        self.assertAlmostEqual(area, exact, delta=0.01 * exact)

    def test_matphai_uses_its_own_ids(self):
        spec = EYES["matphai"]
        truth = {i + 8: p for i, p in rect(0, 0, 40, 10).items()}
        r = O.compare(spec, moved(truth, 10, 0), truth)
        self.assertAlmostEqual(r.iou, 0.6, places=9)


if __name__ == "__main__":
    unittest.main()
