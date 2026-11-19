"""Tạo shape mới và xem lại: chép shape gần nhất, điền đoạn thiếu bằng bám tiến, shape điền tự động chưa xem, Occluded cả đoạn
(`Session.copy_nearest_shape`, `fill_gap`, `unreviewed`, `mark_reviewed`, `shape_run`, `set_occluded_range`;
design/2026-11-19-qc-edit-design.md mục 6.4, 6.5).

Phiên dựng bằng `Session.adopt` với `AdoptedShape` viết tay trên 30 ảnh giả của `test_tracking`: frame 0–19 đứng yên (bám luôn khớp 1,0 nên
chỉ dùng cho test không đo độ chính xác), frame 20–39 chuyển động nên test đo độ chính xác điền đoạn dùng frame 21–26. Test gửi dùng server giả
`FakeCvat` qua `AdoptedJob` của `test_adopt_send`."""
import json
import math
import os
import shutil
import sys
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatsync  # noqa: E402
from eyepin.adopt import AdoptedShape  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import FILL_NO_SOURCE_MSG, MATCH_FLAG, Session  # noqa: E402
import test_adopt as A  # noqa: E402
import test_tracking as T  # noqa: E402
from test_adopt_send import MOVE, AdoptedJob, server_of  # noqa: E402

N = 30
ALL = range(N)
SHAPE_ONLY = "Lệnh này chỉ dùng cho mắt kiểu shape"


def eight(label, t):
    """8 điểm đúng của mắt `label` ở frame t của ảnh giả."""
    return {i: p for i, p in T.pins_at(t).items() if i in EYES[label].ids}


def shape(label, frame, flags=None, dx=0.0):
    """Shape của `label` ở `frame`: vị trí đúng của ảnh giả dời `dx` theo x (để hai shape ở frame đứng yên vẫn khác nhau)."""
    return AdoptedShape(label, frame, {i: (x + dx, y) for i, (x, y) in eight(label, frame).items()}, dict(flags or {}))


def without(frames, *drop):
    return [f for f in frames if f not in drop]


class FillCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_fill_")
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

    def track_session(self) -> Session:
        """Phiên thường (không nạp) có mattrai kiểu track."""
        s = Session(self.dir)
        s.pin_eye(2, "mattrai", {i: T.pins_at(2)[i] for i in EYES["mattrai"].pins})
        self.assertEqual(s.kind["mattrai"], "track")
        return s

    def blank_out(self, s, frame):
        """Ảnh xám của `frame` bị che hẳn (đen) với bộ bám."""
        real = s.gray
        s.gray = lambda f: np.zeros_like(real(f)) if f == frame else real(f)

    def worst(self, s, label, frame):
        truth = eight(label, frame)
        return max(math.dist(s.pins[frame][i], truth[i]) for i in truth)


class TestCopyNearest(FillCase):
    def test_copy_nearest_by_distance(self):
        flags9 = {16: "outside", 18: "occluded"}
        s = Session(self.dir)
        s.adopt([shape("mattrai", 2, {14: "occluded"}, dx=0), shape("mattrai", 9, flags9, dx=5), shape("matphai", 2)])
        self.assertEqual(s.copy_nearest_shape("mattrai", 7), 9)                      # 9 cách 2 frame, 2 cách 5 frame
        self.assertEqual(s.pins[7], s.pins[9])
        self.assertIsNot(s.pins[7], s.pins[9])
        self.assertEqual(s.flags[7], flags9)
        self.assertNotEqual(s.pins[7][14], s.pins[2][14])
        self.assertTrue(s.has_shape("mattrai", 7))

    def test_copy_equidistant_takes_the_earlier_frame(self):
        s = Session(self.dir)
        s.adopt([shape("mattrai", 2, dx=0), shape("mattrai", 8, dx=5), shape("matphai", 2)])
        self.assertEqual(s.copy_nearest_shape("mattrai", 5), 2)                      # 5 cách 2 và 8 đều 3 frame
        self.assertEqual(s.pins[5][14], s.pins[2][14])

    def test_copy_keeps_the_other_eye_and_is_one_undo_step_with_a_new_id(self):
        s = self.session(mattrai=without(ALL, 7))
        other = {i: s.pins[7][i] for i in EYES["matphai"].ids}                       # matphai đã có shape ở frame 7
        ids_before = set(s.shape_ids["mattrai"].values())
        depth = len(s._undo)
        s.copy_nearest_shape("mattrai", 7)
        self.assertEqual(len(s._undo), depth + 1)
        new_id = s.object_id("mattrai", 7)
        self.assertIsNotNone(new_id)
        self.assertNotIn(new_id, ids_before)
        self.assertEqual({i: s.pins[7][i] for i in EYES["matphai"].ids}, other)      # mắt kia ở frame 7 giữ nguyên
        self.assertTrue(s.undo())
        self.assertFalse(s.has_shape("mattrai", 7))

    def test_copy_errors(self):
        s = self.session(mattrai=[2, 9], matphai=[3])
        with self.assertRaises(ValueError) as ctx:
            s.copy_nearest_shape("mattrai", 9)
        self.assertEqual(str(ctx.exception), "frame này đã có shape của mattrai")
        only = self.session(mattrai=[], matphai=[3])
        with self.assertRaises(ValueError) as ctx:
            only.copy_nearest_shape("mattrai", 5)
        self.assertEqual(str(ctx.exception), "mattrai chưa có shape nào để chép")
        with self.assertRaises(ValueError) as ctx:
            self.track_session().copy_nearest_shape("mattrai", 5)
        self.assertEqual(str(ctx.exception), SHAPE_ONLY)
        self.assertEqual(len(s._undo), 0)                                            # lỗi thì không có bước hoàn tác

    def test_copied_shape_is_not_listed_as_unreviewed(self):
        s = self.session(mattrai=without(ALL, 7))
        s.copy_nearest_shape("mattrai", 7)
        self.assertEqual(s.unreviewed("mattrai"), [])


class TestFillGap(FillCase):
    def test_fill_full_gap(self):
        s = self.session(mattrai=without(ALL, 22, 23, 24, 25, 26))
        depth = len(s._undo)
        res = s.fill_gap("mattrai", 22, 26)
        self.assertEqual(res.created, [22, 23, 24, 25, 26])
        self.assertIsNone(res.stopped_at)
        self.assertIsNone(res.score)
        for f in res.created:
            self.assertLess(self.worst(s, "mattrai", f), 1.0, f"frame {f}")
        self.assertEqual(len(s._undo), depth + 1)                                    # cả đoạn là một bước hoàn tác
        self.assertTrue(s.undo())
        self.assertEqual([f for f in range(22, 27) if s.has_shape("mattrai", f)], [])
        self.assertEqual(s.unreviewed("mattrai"), [])                                # shape đã mất thì không còn "chưa xem"

    def test_fill_stops_on_low_match(self):
        s = self.session(mattrai=without(ALL, 22, 23, 24, 25, 26))
        self.blank_out(s, 24)
        res = s.fill_gap("mattrai", 22, 26)
        self.assertEqual(res.created, [22, 23])
        self.assertEqual(res.stopped_at, 24)
        self.assertLess(res.score, MATCH_FLAG)
        self.assertEqual([f for f in range(22, 27) if s.has_shape("mattrai", f)], [22, 23])

    def test_fill_creating_nothing_changes_nothing(self):
        s = self.session(mattrai=without(ALL, 22, 23, 24))
        self.blank_out(s, 22)
        before, depth = {f: dict(p) for f, p in s.pins.items()}, len(s._undo)
        res = s.fill_gap("mattrai", 22, 24)
        self.assertEqual((res.created, res.stopped_at), ([], 22))
        self.assertLess(res.score, MATCH_FLAG)
        self.assertEqual(s.pins, before)
        self.assertEqual(len(s._undo), depth)

    def test_fill_skips_deleted_frames(self):
        s = self.session(mattrai=without(ALL, 22, 23, 24, 25, 26))
        s.delete_frame(23)
        res = s.fill_gap("mattrai", 22, 26)
        self.assertEqual(res.created, [22, 24, 25, 26])
        self.assertFalse(s.has_shape("mattrai", 23))
        self.assertLess(self.worst(s, "mattrai", 24), 1.0)                           # bám đi qua frame đã xoá nên frame sau vẫn đúng chỗ

    def test_fill_source_steps_back_over_deleted_frames(self):
        s = self.session(mattrai=without(ALL, 21, 22, 23))
        s.delete_frame(21)                                                           # frame 21 đã xoá: nguồn là shape ở 20
        res = s.fill_gap("mattrai", 22, 23)
        self.assertEqual(res.created, [22, 23])
        self.assertLess(self.worst(s, "mattrai", 23), 1.0)

    def test_fill_skips_frames_that_already_have_a_shape(self):
        s = self.session(mattrai=without(ALL, 22, 24))                               # 23 đã có shape
        before = s.pins[23]
        res = s.fill_gap("mattrai", 22, 24)
        self.assertEqual(res.created, [22, 24])
        self.assertIs(s.pins[23], before)

    def test_fill_copies_the_flags_of_the_source(self):
        s = Session(self.dir)
        s.adopt([shape("mattrai", f, {16: "occluded"} if f == 21 else None) for f in ALL if f not in (22, 23)]
                + [shape("matphai", f) for f in ALL])
        res = s.fill_gap("mattrai", 22, 23)
        self.assertEqual(res.created, [22, 23])
        self.assertEqual(s.flags[22], {16: "occluded"})
        self.assertEqual(s.flags[23], {16: "occluded"})

    def test_fill_needs_source_before(self):
        s = self.session(mattrai=without(ALL, 0, 1, 2, 3))
        depth = len(s._undo)
        with self.assertRaises(ValueError) as ctx:
            s.fill_gap("mattrai", 0, 3)
        self.assertEqual(str(ctx.exception), FILL_NO_SOURCE_MSG)
        self.assertEqual(FILL_NO_SOURCE_MSG, "Không có shape ngay trước đoạn này: vẽ hoặc chép shape ở frame đầu đoạn rồi điền tiếp.")
        self.assertEqual(len(s._undo), depth)

    def test_fill_needs_source_when_the_frame_before_is_also_missing(self):
        s = self.session(mattrai=without(ALL, 4, 5, 6))
        with self.assertRaises(ValueError) as ctx:
            s.fill_gap("mattrai", 6, 6)                                              # frame 5 ngay trước cũng thiếu
        self.assertEqual(str(ctx.exception), FILL_NO_SOURCE_MSG)

    def test_fill_read_error_changes_nothing(self):
        s = self.session(mattrai=without(ALL, 3, 4, 5, 6, 7))
        real = s.gray

        def failing(f):
            if f == 5:
                raise OSError("không đọc được ảnh")
            return real(f)

        s.gray = failing
        before, depth = {f: dict(p) for f, p in s.pins.items()}, len(s._undo)
        with self.assertRaises(OSError):
            s.fill_gap("mattrai", 3, 7)
        self.assertEqual(s.pins, before)
        self.assertEqual(len(s._undo), depth)
        self.assertEqual(s.unreviewed("mattrai"), [])

    def test_fill_only_for_shape_eyes(self):
        with self.assertRaises(ValueError) as ctx:
            self.track_session().fill_gap("mattrai", 3, 5)
        self.assertEqual(str(ctx.exception), SHAPE_ONLY)

    def test_fill_rejects_a_reversed_range(self):
        s = self.session(mattrai=without(ALL, 5, 6))
        with self.assertRaises(ValueError) as ctx:
            s.fill_gap("mattrai", 6, 5)
        self.assertEqual(str(ctx.exception), "Frame bắt đầu phải nhỏ hơn hoặc bằng frame kết thúc")


class TestUnreviewed(FillCase):
    def test_unreviewed_lifecycle(self):
        s = self.session(mattrai=without(ALL, 3, 4, 5, 6))
        self.assertEqual(s.unreviewed("mattrai"), [])
        self.assertNotIn("auto", s.state()["layers"][0])                             # chưa điền gì: file phiên không có khoá "auto"
        s.fill_gap("mattrai", 3, 6)
        self.assertEqual(s.unreviewed("mattrai"), [3, 4, 5, 6])
        self.assertEqual(s.unreviewed("matphai"), [])
        x, y = s.pins[4][14]
        s.move_point(4, 14, (x + 1.0, y))                                            # sửa một điểm: shape không còn "chưa xem"
        self.assertEqual(s.unreviewed("mattrai"), [3, 5, 6])
        self.assertTrue(s.undo())                                                    # hoàn tác về đúng như lúc điền: tính lại
        self.assertEqual(s.unreviewed("mattrai"), [3, 4, 5, 6])
        s.mark_reviewed("mattrai", [3, 4])
        self.assertEqual(s.unreviewed("mattrai"), [5, 6])
        saved = json.loads(json.dumps(s.state()))
        self.assertIn("auto", saved["layers"][0])
        again = Session(self.dir)
        again.load_state(saved)
        self.assertEqual(again.unreviewed("mattrai"), [5, 6])

    def test_editing_a_flag_or_deleting_the_shape_removes_it_from_the_list(self):
        s = self.session(mattrai=without(ALL, 3, 4, 5, 6))
        s.fill_gap("mattrai", 3, 6)
        s.toggle_flag(3, 16, "occluded")
        s.delete_shape("mattrai", 5)
        self.assertEqual(s.unreviewed("mattrai"), [4, 6])

    def test_unreviewed_belongs_to_the_selected_person(self):
        s = self.session(mattrai=without(ALL, 3, 4))
        s.fill_gap("mattrai", 3, 4)
        s.add_layer()
        self.assertEqual(s.unreviewed("mattrai"), [])
        s.select_layer(0)
        self.assertEqual(s.unreviewed("mattrai"), [3, 4])


class TestOccludedRange(FillCase):
    def test_occluded_range_sets_and_clears(self):
        s = self.session(mattrai=without(range(0, 10), 4))
        depth = len(s._undo)
        self.assertEqual(s.set_occluded_range("mattrai", [14], 0, 9, True), (9, 0))
        self.assertEqual(len(s._undo), depth + 1)
        for f in without(range(0, 10), 4):
            self.assertEqual(s.flags_at(f), {14: "occluded"}, f"frame {f}")
        self.assertEqual(s.flags_at(4), {})                                          # frame không có shape: bỏ qua
        self.assertEqual(s.set_occluded_range("mattrai", [14], 0, 9, False), (9, 0))
        self.assertEqual(len(s._undo), depth + 2)
        for f in range(0, 10):
            self.assertEqual(s.flags_at(f), {})
        self.assertTrue(s.undo())                                                    # mỗi lần là một bước: hoàn tác trả về Occluded
        self.assertEqual(s.flags_at(0), {14: "occluded"})

    def test_occluded_range_with_nothing_to_change_adds_no_undo_step(self):
        s = self.session(mattrai=range(0, 5))
        self.assertEqual(s.set_occluded_range("mattrai", [14], 0, 4, False), (0, 0))      # chưa có Occluded nào để bỏ
        self.assertEqual(s.set_occluded_range("mattrai", [14], 10, 12, True), (0, 0))     # khoảng không có shape nào
        self.assertEqual(len(s._undo), 0)
        s.set_occluded_range("mattrai", [14], 0, 4, True)
        depth = len(s._undo)
        self.assertEqual(s.set_occluded_range("mattrai", [14], 0, 4, True), (0, 0))       # đã Occluded hết
        self.assertEqual(len(s._undo), depth)

    def test_occluded_range_keeps_outside(self):
        s = self.session(mattrai=without(range(0, 10), 4))
        s.toggle_flag(2, 14, "outside")
        self.assertEqual(s.set_occluded_range("mattrai", [14], 0, 9, True), (8, 1))
        self.assertEqual(s.flags_at(2), {14: "outside"})
        self.assertEqual(s.flags_at(3), {14: "occluded"})
        self.assertEqual(s.set_occluded_range("mattrai", [14], 0, 9, False), (8, 1))      # "Bỏ" cũng không đụng Outside
        self.assertEqual(s.flags_at(2), {14: "outside"})
        self.assertEqual(s.flags_at(3), {})

    def test_occluded_range_whole_eye_and_errors(self):
        s = self.session(mattrai=range(0, 4))
        self.assertEqual(s.set_occluded_range("mattrai", None, 1, 2, True), (2, 0))
        self.assertEqual(s.flags_at(1), {i: "occluded" for i in EYES["mattrai"].ids})
        self.assertEqual(s.flags_at(0), {})
        with self.assertRaises(ValueError) as ctx:
            s.set_occluded_range("mattrai", None, 3, 2, True)
        self.assertEqual(str(ctx.exception), "Frame bắt đầu phải nhỏ hơn hoặc bằng frame kết thúc")
        with self.assertRaises(ValueError) as ctx:
            self.track_session().set_occluded_range("mattrai", None, 0, 5, True)
        self.assertEqual(str(ctx.exception), SHAPE_ONLY)
        with self.assertRaises(ValueError):
            s.set_occluded_range("mattrai", [22], 0, 3, True)                        # điểm 22 thuộc mắt kia

    def test_occluded_range_keeps_filled_shapes_unreviewed(self):
        s = self.session(mattrai=without(ALL, 3, 4, 5, 6))
        s.fill_gap("mattrai", 3, 6)
        self.assertEqual(s.unreviewed("mattrai"), [3, 4, 5, 6])
        depth = len(s._undo)
        self.assertEqual(s.set_occluded_range("mattrai", [14], 0, 9, True), (10, 0))
        self.assertEqual(len(s._undo), depth + 1)                                    # vẫn một bước hoàn tác
        self.assertEqual(s.flags_at(4), {14: "occluded"})
        self.assertEqual(s.unreviewed("mattrai"), [3, 4, 5, 6])                      # đổi cờ hàng loạt không làm shape điền thành "đã xem"
        self.assertTrue(s.undo())                                                    # hoàn tác trả cả cờ lẫn danh sách
        self.assertEqual(s.flags_at(4), {})
        self.assertEqual(s.unreviewed("mattrai"), [3, 4, 5, 6])
        self.assertTrue(s.redo())
        self.assertEqual(s.flags_at(4), {14: "occluded"})
        self.assertEqual(s.unreviewed("mattrai"), [3, 4, 5, 6])

    def test_occluded_range_does_not_revive_reviewed_fills(self):
        s = self.session(mattrai=without(ALL, 3, 4, 5, 6))
        s.fill_gap("mattrai", 3, 6)
        x, y = s.pins[4][14]
        s.move_point(4, 14, (x + 1.0, y))                                            # shape 4 đã được sửa tay: "đã xem"
        s.mark_reviewed("mattrai", [6])                                              # shape 6 đã đánh dấu xem
        s.set_occluded_range("mattrai", [14], 0, 9, True)
        self.assertEqual(s.unreviewed("mattrai"), [3, 5])                            # chỉ shape còn "chưa xem" trước đó giữ nguyên danh sách
        self.assertTrue(s.undo())
        self.assertEqual(s.unreviewed("mattrai"), [3, 5])                            # hoàn tác không đưa shape đã xem trở lại danh sách

    def test_single_flag_toggle_still_marks_reviewed(self):
        s = self.session(mattrai=without(ALL, 3, 4, 5, 6))
        s.fill_gap("mattrai", 3, 6)
        s.toggle_flag(4, 14, "occluded")                                             # sửa tay một cờ: shape đó ra khỏi danh sách
        self.assertEqual(s.unreviewed("mattrai"), [3, 5, 6])

    def test_occluded_range_does_not_touch_the_other_eye(self):
        s = self.session()
        s.set_occluded_range("mattrai", None, 0, 5, True)
        self.assertEqual([f for f in ALL if any(i in EYES["matphai"].ids for i in s.flags_at(f))], [])


class TestShapeRun(FillCase):
    def test_shape_run(self):
        s = self.session(mattrai=[2, 3, 4, 6, 7, 8, 9])
        self.assertEqual(s.shape_run("mattrai", 3), (2, 4))
        self.assertEqual(s.shape_run("mattrai", 2), (2, 4))
        self.assertEqual(s.shape_run("mattrai", 4), (2, 4))
        self.assertEqual(s.shape_run("mattrai", 8), (6, 9))
        self.assertEqual(s.shape_run("mattrai", 5), (5, 5))                          # frame không có shape
        self.assertEqual(s.shape_run("mattrai", 0), (0, 0))

    def test_deleted_frame_cuts_the_run(self):
        s = self.session(mattrai=[2, 3, 4, 5, 6])
        s.delete_frame(4)
        self.assertEqual(s.shape_run("mattrai", 3), (2, 3))
        self.assertEqual(s.shape_run("mattrai", 5), (5, 6))
        self.assertEqual(s.shape_run("mattrai", 4), (4, 4))

    def test_run_of_a_whole_job(self):
        self.assertEqual(self.session().shape_run("mattrai", 10), (0, N - 1))


class TestSendAfterAllEdits(AdoptedJob):
    """Job 8 frame toàn shape (mattrai ở 0, 1, 2, 5; matphai ở mọi frame) trên server giả: sửa, xoá, chép, điền, Occluded cả đoạn, rồi gửi."""

    def test_send_roundtrip_after_all_edits(self):
        shapes = [A.skeleton("mattrai", f) for f in (0, 1, 2, 5)] + [A.skeleton("matphai", f) for f in range(8)]
        s = self.open(shapes)
        x, y = s.pins[1][14]
        s.move_point(1, 14, (x + MOVE, y))                                           # sửa mattrai frame 1
        s.delete_shape("matphai", 7)                                                 # xoá matphai frame 7
        self.assertEqual(s.copy_nearest_shape("mattrai", 7), 5)                      # chép mattrai frame 7
        res_fill = s.fill_gap("mattrai", 3, 4)                                       # điền mattrai frame 3, 4 từ frame 2
        self.assertEqual((res_fill.created, res_fill.stopped_at), ([3, 4], None))
        self.assertEqual(s.set_occluded_range("matphai", [22], 0, 6, True), (7, 0))  # Occluded điểm 22 của matphai frame 0–6
        plan = cvatsync.prepare(s, self.cl)
        self.assertEqual(plan.counts, {"server": 12, "kept": 3, "edited": 8, "added": 3, "removed": 1})
        self.cvat_stores()
        res = cvatsync.send(s, self.cl, plan)
        self.assertTrue(res.ok, (res.message, res.mismatches))
        self.assertEqual(res.mismatches, [])
        self.assertIs(s.unsent, False)
        stored = {(name, frame): pts for name, frame, pts in server_of(self.job.annotations_json)}
        sent = {(sh.label, sh.key.frame): sh for sh in s.build_shapes()}
        self.assertEqual(sorted(stored), sorted(sent))
        self.assertEqual(sorted(stored), sorted([("mattrai", f) for f in (0, 1, 2, 3, 4, 5, 7)] + [("matphai", f) for f in range(7)]))
        for key, sh in sent.items():
            for pid, ps in sh.key.points.items():
                (px, py), occluded, outside = stored[key][pid]
                self.assertAlmostEqual(px, ps.xy[0], delta=0.02, msg=f"{key} điểm {pid}")
                self.assertAlmostEqual(py, ps.xy[1], delta=0.02, msg=f"{key} điểm {pid}")
                self.assertEqual((occluded, outside), (ps.occluded, ps.outside), f"{key} điểm {pid}")
        self.assertTrue(stored[("matphai", 3)][22][1])                               # điểm 22 của matphai frame 3 là Occluded trên CVAT
        self.assertFalse(stored[("matphai", 3)][23][1])


if __name__ == "__main__":
    unittest.main()
