"""Thiếu nhãn của mắt kiểu shape (`eyepin.gaps`) và bộ lọc "Frame thiếu nhãn" của `Session` (design/2026-11-19-qc-edit-design.md mục 6.3).

Phiên dựng bằng `Session.adopt` với `AdoptedShape` viết tay trên 12 ảnh trống; điểm lấy từ ảnh giả của `test_tracking`."""
import os
import shutil
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.adopt import AdoptedShape  # noqa: E402
from eyepin.gaps import Gap, find_gaps, gap_at, gap_text, missing_frames  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402

N = 12
ALL = range(N)


def shape(label, frame):
    pts = {i: p for i, p in T.pins_at(frame).items() if i in EYES[label].ids}
    return AdoptedShape(label, frame, pts, {})


def four(label, t):
    truth = T.pins_at(t)
    return {i: truth[i] for i in EYES[label].pins}


def eight(label, t):
    return {i: p for i, p in T.pins_at(t).items() if i in EYES[label].ids}


class GapCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_gaps_")
        for t in range(N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def session(self, mattrai=ALL, matphai=ALL) -> Session:
        """Phiên đã nạp: mattrai có shape ở các frame `mattrai`, matphai ở các frame `matphai`."""
        s = Session(self.dir)
        s.adopt([shape("mattrai", f) for f in mattrai] + [shape("matphai", f) for f in matphai])
        return s

    def holes(self, **kw) -> Session:
        """mattrai thiếu frame 5, 6, 8, 9, 10; matphai đủ."""
        return self.session(mattrai=[f for f in ALL if f not in (5, 6, 8, 9, 10)], **kw)


class TestFindGaps(GapCase):
    def test_two_segments_split_by_labelled_frame(self):
        s = self.holes()
        self.assertEqual(find_gaps(s), [Gap(0, "mattrai", 5, 6, 2), Gap(0, "mattrai", 8, 10, 3)])
        self.assertEqual(missing_frames(s), {5, 6, 8, 9, 10})

    def test_complete_session_has_no_gaps(self):
        s = self.session()
        self.assertEqual(find_gaps(s), [])
        self.assertEqual(missing_frames(s), set())

    def test_deleted_frame_splits_and_is_not_missing(self):
        s = self.holes()
        s.delete_frame(9)
        self.assertEqual(find_gaps(s), [Gap(0, "mattrai", 5, 6, 2), Gap(0, "mattrai", 8, 8, 1), Gap(0, "mattrai", 10, 10, 1)])
        self.assertEqual(missing_frames(s), {5, 6, 8, 10})
        s.restore_frame(9)
        self.assertEqual(find_gaps(s)[1], Gap(0, "mattrai", 8, 10, 3))

    def test_deleted_frame_at_the_edge_shortens_the_segment(self):
        s = self.session(mattrai=[0, 1, 2, 3])
        s.delete_frame(11)
        s.delete_frame(4)
        self.assertEqual(find_gaps(s), [Gap(0, "mattrai", 5, 10, 6)])

    def test_eye_without_any_shape(self):
        s = self.session(mattrai=[], matphai=[2, 3])
        got = find_gaps(s)
        self.assertEqual(got, [Gap(0, "mattrai", -1, -1, 0), Gap(0, "matphai", 0, 1, 2), Gap(0, "matphai", 4, 11, 8)])
        self.assertEqual(gap_text(got[0], False), "mattrai chưa có nhãn nào")
        self.assertEqual(missing_frames(s), set(ALL))
        s.delete_frame(7)
        self.assertEqual(missing_frames(s), set(ALL) - {7})                 # mắt chưa có nhãn nào: mọi frame không bị xoá

    def test_both_eyes_without_shapes_have_no_entry(self):
        s = self.session(mattrai=[], matphai=[])
        self.assertEqual(find_gaps(s), [])
        self.assertEqual(missing_frames(s), set())

    def test_track_eyes_ignored(self):
        s = Session(self.dir)
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="track")
        s.pin_eye(3, "matphai", four("matphai", 3), kind="track")
        self.assertEqual(find_gaps(s), [])
        self.assertEqual(missing_frames(s), set())

    def test_only_shape_eyes_are_counted(self):
        s = Session(self.dir)
        s.pin_eye(3, "mattrai", four("mattrai", 3), kind="shape")
        s.pin_eye(3, "matphai", four("matphai", 3), kind="track")
        self.assertEqual(find_gaps(s), [Gap(0, "mattrai", 0, 2, 3), Gap(0, "mattrai", 4, 11, 8)])

    def test_order_across_people(self):
        """Mục "chưa có nhãn nào" trước (theo người, nhãn), rồi theo (frame đầu, người, nhãn)."""
        s = self.session(mattrai=range(10), matphai=range(10))
        s.add_layer()
        for f in range(10):
            s.paste_points(f, eight("matphai", f))                           # người 2: chỉ matphai có shape (frame 0–9)
        want = [
            Gap(1, "mattrai", -1, -1, 0),
            Gap(0, "matphai", 10, 11, 2),                                    # cùng frame đầu: theo người rồi theo tên nhãn (matphai < mattrai)
            Gap(0, "mattrai", 10, 11, 2),
            Gap(1, "matphai", 10, 11, 2),
        ]
        self.assertEqual(find_gaps(s), want)
        s.select_layer(0)
        self.assertEqual(find_gaps(s), want)                                 # kết quả không phụ thuộc người đang chọn
        self.assertEqual(s.cur, 0)

    def test_updates_after_edit(self):
        s = self.holes()
        s.paste_points(5, eight("mattrai", 5))                               # dán shape vào frame 5
        self.assertEqual(find_gaps(s), [Gap(0, "mattrai", 6, 6, 1), Gap(0, "mattrai", 8, 10, 3)])
        s.undo()
        self.assertEqual(find_gaps(s)[0], Gap(0, "mattrai", 5, 6, 2))
        s.delete_shape("mattrai", 7)                                         # xoá một shape nối hai đoạn
        self.assertEqual(find_gaps(s), [Gap(0, "mattrai", 5, 10, 6)])


class TestTexts(unittest.TestCase):
    def test_texts(self):
        cases = [
            (Gap(0, "mattrai", 5, 6, 2), "Thiếu nhãn mattrai · frame 5–6 (2 frame)"),
            (Gap(1, "matphai", 8, 8, 1), "Thiếu nhãn matphai · frame 8 (1 frame)"),
            (Gap(0, "mattrai", -1, -1, 0), "mattrai chưa có nhãn nào"),
        ]
        for gap, text in cases:
            with self.subTest(text):
                self.assertEqual(gap_text(gap, False), text)
                self.assertEqual(gap_text(gap, True), f"người {gap.layer + 1} · {text}")
        self.assertEqual(gap_text(Gap(2, "matphai", 108, 125, 18), True), "người 3 · Thiếu nhãn matphai · frame 108–125 (18 frame)")


class TestFilter(GapCase):
    def test_filter_missing(self):
        self.assertEqual(Session.FILTERS["missing"], "Frame thiếu nhãn")
        self.assertEqual(list(Session.FILTERS)[-1], "missing")
        s = self.holes()
        self.assertEqual(s.next_match(0, 1, "missing"), 5)
        self.assertEqual(s.next_match(5, 1, "missing"), 6)
        self.assertEqual(s.next_match(6, 1, "missing"), 8)
        self.assertEqual(s.next_match(10, 1, "missing"), None)
        self.assertEqual(s.next_match(11, -1, "missing"), 10)
        self.assertEqual(s.next_match(8, -1, "missing"), 6)
        self.assertFalse(s.matches(7, "missing"))
        self.assertTrue(s.matches(9, "missing"))
        self.assertTrue(s.matches(5, "missing"))
        self.assertFalse(s.matches(5, "nolabel"))                            # matphai vẫn có nhãn ở frame 5: chỉ thiếu một mắt

    def test_filter_missing_skips_deleted_frames(self):
        s = self.holes()
        s.delete_frame(5)
        self.assertEqual(s.next_match(0, 1, "missing"), 6)
        self.assertFalse(s.matches(5, "missing"))

    def test_filter_missing_without_gaps(self):
        s = self.session()
        self.assertEqual(s.next_match(0, 1, "missing"), None)


class TestGapAt(GapCase):
    def test_gap_at(self):
        s = self.holes()
        self.assertEqual(gap_at(s, "mattrai", 9), Gap(0, "mattrai", 8, 10, 3))
        self.assertEqual(gap_at(s, "mattrai", 8), Gap(0, "mattrai", 8, 10, 3))
        self.assertEqual(gap_at(s, "mattrai", 6), Gap(0, "mattrai", 5, 6, 2))
        self.assertIsNone(gap_at(s, "mattrai", 7))                           # frame có shape
        self.assertIsNone(gap_at(s, "mattrai", 0))
        self.assertIsNone(gap_at(s, "matphai", 9))                           # matphai không thiếu gì
        s.delete_frame(9)
        self.assertIsNone(gap_at(s, "mattrai", 9))                           # frame đã xoá
        self.assertEqual(gap_at(s, "mattrai", 10), Gap(0, "mattrai", 10, 10, 1))

    def test_gap_at_ignores_eye_without_any_shape(self):
        s = self.session(mattrai=[], matphai=[2])
        self.assertIsNone(gap_at(s, "mattrai", 5))

    def test_gap_at_is_for_the_selected_person(self):
        s = self.holes()
        s.add_layer()
        self.assertIsNone(gap_at(s, "mattrai", 9))                           # người 2 chưa có nhãn nào
        s.select_layer(0)
        self.assertEqual(gap_at(s, "mattrai", 9), Gap(0, "mattrai", 8, 10, 3))


if __name__ == "__main__":
    unittest.main()
