"""Gửi shape mắt lên CVAT và đối chiếu sau import (eyepin.cvatsync) với server giả; ảnh tổng hợp, không chạm server thật.

Server giả không tự cập nhật JSON annotations sau import, nên mỗi test đặt trước `job.annotations_json` (trạng thái CVAT sau import, dựng
bằng `server_shapes_json`) và bản xuất "CVAT for video" (dựng bằng `video_with_shapes`: track mắt như CVAT xuất cộng track một frame mà
CVAT sinh ra từ mỗi shape)."""
import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatsync, cvatxml  # noqa: E402
from eyepin.cvatsource import open_job  # noqa: E402
from eyepin.cvatsync import _Want  # noqa: E402
from eyepin.cvatxml import EyeKey, EyeShape, PointState  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from test_cvatsource import VIDEO, xml_of  # noqa: E402
from test_cvatsync import Sync, pin_frames, server_video_xml  # noqa: E402
from fake_cvat import FakeJob  # noqa: E402
import test_tracking as T  # noqa: E402


def shape_at(s, f, label="mattrai"):
    """Vẽ shape `label` ở chỉ số frame f (ảnh của chỉ số f là render(số frame của job))."""
    t = s.source.frame_numbers[f]
    s.pin_eye(f, label, {i: T.pins_at(t)[i] for i in EYES[label].pins}, kind="shape")


def server_shapes_json(s, edit=None, drop=None):
    """JSON `GET /api/jobs/{id}/annotations` như CVAT trả về sau khi nhận đúng các shape của `s.build_shapes()`: mỗi shape một skeleton
    (`frame` là số frame của job) có `elements` là 8 điểm, `label_id` của điểm là id nhãn con (tên nhãn con là số điểm).
    `edit(sh, pid, x, y, occluded, outside)` trả bộ mới hoặc None (bỏ điểm); `drop(sh)` True thì bỏ cả shape."""
    labels = {lb["name"]: lb for lb in FakeJob.default_labels()}
    shapes = []
    for k, sh in enumerate(s.build_shapes()):
        if drop and drop(sh):
            continue
        lb = labels[sh.label]
        sub = {int(x["name"]): x["id"] for x in lb["sublabels"]}
        frame = s.source.frame_numbers[sh.key.frame]
        els = []
        for pid in EYES[sh.label].ids:
            ps = sh.key.points[pid]
            row = (ps.xy[0], ps.xy[1], ps.occluded, ps.outside)
            if edit:
                row = edit(sh, pid, *row)
                if row is None:
                    continue
            x, y, occ, out = row
            els.append({"id": 1000 * (k + 1) + pid, "type": "points", "label_id": sub[pid], "frame": frame, "group": 0, "source": "file",
                        "occluded": bool(occ), "outside": bool(out), "z_order": 0, "rotation": 0.0, "attributes": [],
                        "points": [round(x, 2), round(y, 2)]})
        shapes.append({"id": 100 + k, "type": "skeleton", "label_id": lb["id"], "frame": frame, "group": 0, "source": "file",
                       "occluded": False, "outside": False, "z_order": 0, "rotation": 0.0, "attributes": [], "points": [],
                       "elements": els})
    return {"version": 1, "tags": [], "shapes": shapes, "tracks": []}


def video_with_shapes(s):
    """Bản xuất "CVAT for video": track mắt (như test_cvatsync.server_video_xml) cộng mỗi shape thành một track một frame, đúng như CVAT 2.75
    xuất (design/cvat-api-notes.md, "Shape mắt (2026-11-18)", câu 5): `<skeleton>` ở frame của shape, rồi `<skeleton>` ở frame kế với cả
    8 `<points outside="1">`; thẻ `<skeleton>` KHÔNG có thuộc tính `outside`. Shape ở frame cuối của job chỉ có một `<skeleton>`."""
    nums = s.source.frame_numbers
    extra = []
    for k, sh in enumerate(s.build_shapes()):
        f = nums[sh.key.frame]
        sk = [f'<skeleton frame="{f}" keyframe="1" z_order="0">{shape_points(sh.key, sh.label)}</skeleton>']
        if f != nums[-1]:
            sk.append(f'<skeleton frame="{f + 1}" keyframe="1" z_order="0">{shape_points(sh.key, sh.label, all_outside=True)}</skeleton>')
        extra.append(f'<track id="{500 + k}" label="{sh.label}" source="file">{"".join(sk)}</track>')
    return server_video_xml(s, job_numbers=nums).replace(b"</annotations>", "".join(extra).encode() + b"</annotations>")


def shape_points(key, label, all_outside=False):
    """8 thẻ `<points>` của một shape như CVAT xuất; `all_outside`: frame kế của track sinh từ shape (mọi điểm Outside, giữ toạ độ)."""
    return "".join(f'<points label="{i}" keyframe="1" outside="{int(all_outside or key.points[i].outside)}" '
                   f'occluded="{int(key.points[i].occluded)}" points="{key.points[i].xy[0]:.2f},{key.points[i].xy[1]:.2f}"></points>'
                   for i in EYES[label].ids)


def eye_skeletons_in_images(job):
    root = ET.fromstring(job.xml)
    return [(int(im.get("id")), sk.get("label")) for im in root.findall("image") for sk in im.findall("skeleton") if sk.get("label") in EYES]


def eye_tracks(job):
    return [tr for tr in ET.fromstring(job.xml).findall("track") if tr.get("label") in EYES]


class TestShapeSend(Sync):
    def two_shapes(self):
        job = self.setup_job()
        s = self.session
        shape_at(s, 1)
        shape_at(s, 3)
        return job, s

    def serve_after_import(self, job, s, **kw):
        job.annotations_json = server_shapes_json(s, **kw)
        job.export_xml_by_format[VIDEO] = video_with_shapes(s)

    def test_plan_counts_shapes(self):
        job, s = self.two_shapes()
        plan = cvatsync.prepare(s, self.cl)
        self.assertEqual(plan.shapes, 2)
        self.assertEqual(plan.keyframes, 0)
        self.assertIn("2 shape", plan.text())
        self.assertEqual({lb["name"] for lb in plan.labels}, set(EYES))

    def test_send_shape_only_job_ok(self):
        job, s = self.two_shapes()
        self.assertTrue(s.unsent)
        self.serve_after_import(job, s)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, (res.message, res.mismatches))
        self.assertIn("2 shape", res.message)
        self.assertEqual(sorted(eye_skeletons_in_images(job)), [(1, "mattrai"), (3, "mattrai")])
        self.assertEqual(eye_tracks(job), [])
        self.assertIs(s.unsent, False)

    def test_send_mixed_job_has_no_false_mismatch(self):
        job = self.setup_job()
        s = self.session
        for f in (0, 4):
            t = s.source.frame_numbers[f]
            s.pin_eye(f, "matphai", {i: T.pins_at(t)[i] for i in EYES["matphai"].pins})
        shape_at(s, 1)
        shape_at(s, 3)
        self.serve_after_import(job, s)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, (res.message, res.mismatches))
        self.assertEqual(res.mismatches, [])
        self.assertEqual([tr.get("label") for tr in eye_tracks(job)], ["matphai"])
        self.assertEqual(sorted(eye_skeletons_in_images(job)), [(1, "mattrai"), (3, "mattrai")])

    def test_track_and_shape_of_the_same_label_from_two_people(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 3, 6])                                            # người 1: track hai mắt, keyframe ở 3
        s.add_layer()
        shape_at(s, 3)                                                       # người 2: shape mattrai cũng ở frame 3
        self.serve_after_import(job, s)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, (res.message, res.mismatches))
        self.assertIn("1 shape", res.message)

    def test_shape_moved_on_server_is_reported(self):
        job, s = self.two_shapes()
        self.serve_after_import(job, s, edit=lambda sh, pid, x, y, occ, out: (x + 3, y, occ, out) if (sh.key.frame == 3 and pid == 14)
                                else (x, y, occ, out))
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertEqual(len([m for m in res.mismatches if "frame 3" in m and "điểm 14" in m]), 1, res.mismatches)
        self.assertTrue(s.unsent)

    def test_shape_missing_on_server_is_reported(self):
        job, s = self.two_shapes()
        self.serve_after_import(job, s, drop=lambda sh: sh.key.frame == 1)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertTrue(any("tool gửi 2 shape" in m and "CVAT có 1 shape" in m for m in res.mismatches), res.mismatches)
        self.assertTrue(any("frame 1" in m and "thiếu shape" in m for m in res.mismatches), res.mismatches)

    def test_shape_flag_lost_is_reported(self):
        job, s = self.two_shapes()
        s.toggle_flag(3, 16, "occluded")
        self.serve_after_import(job, s, edit=lambda sh, pid, x, y, occ, out: (x, y, False, out))
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertTrue(any("frame 3" in m and "điểm 16" in m and "cờ occluded" in m for m in res.mismatches), res.mismatches)

    def test_shape_on_the_last_frame(self):
        job = self.setup_job()
        s = self.session
        shape_at(s, 2)
        shape_at(s, s.n_frames - 1)                                          # CVAT xuất track một <skeleton>, không có frame kế
        self.serve_after_import(job, s)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, (res.message, res.mismatches))

    def test_job_frame_numbers_differ_from_indices(self):
        job = self.serve(start_frame=10, n_frames=5)
        s = open_job(self.cl, 7)
        shape_at(s, 1)
        shape_at(s, 3)
        self.serve_after_import(job, s)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, (res.message, res.mismatches))
        self.assertEqual(sorted(eye_skeletons_in_images(job)), [(11, "mattrai"), (13, "mattrai")])     # chỉ số -> số frame của job
        self.serve_after_import(job, s, edit=lambda sh, pid, x, y, occ, out: (x + 3, y, occ, out) if (sh.key.frame == 3 and pid == 14)
                                else (x, y, occ, out))
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertTrue(any("frame 3 (số 13 của job)" in m and "điểm 14" in m for m in res.mismatches), res.mismatches)

    def test_track_only_job_text_unchanged(self):
        self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        plan = cvatsync.prepare(s, self.cl)
        self.assertEqual(plan.shapes, 0)
        self.assertEqual(plan.text(), f"EyePin sẽ thay toàn bộ nhãn của job #7 trên CVAT bằng nhãn nền hiện có cộng {plan.keyframes} keyframe mắt mới.")
        res = cvatsync.send(s, self.cl, plan)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(res.message, f"Đã gửi {plan.keyframes} keyframe mắt lên job #7; CVAT lưu khớp với EyePin.")


class TestCompareDropsShapeTracks(unittest.TestCase):
    """`_compare` bỏ track một frame mà bản xuất video sinh ra từ shape, mỗi shape đã gửi bỏ nhiều nhất một track, không bỏ track thật.
    Job 8 frame (0..7). Track thật của tool: một keyframe ở frame f, mắt đứng yên, CVAT xuất mọi frame f..7. Shape của người khác cùng nhãn
    ở frame f, lệch 30 px so với track thật."""
    N = 8
    DX = 30

    @staticmethod
    def pts(dx, keyframe=1):
        return "".join(f'<points label="{i}" keyframe="{keyframe}" outside="0" occluded="0" points="{10 + i + dx},{20 + i}"/>'
                       for i in EYES["mattrai"].ids)

    def real_track(self, f):
        sk = "".join(f'<skeleton frame="{g}" keyframe="{int(g == f)}" outside="0" occluded="0">{self.pts(0, int(g == f))}</skeleton>'
                     for g in range(f, self.N))
        return f'<track id="1" label="mattrai" source="manual">{sk}</track>'

    def shape_track(self, f, dx=None, tid=2):
        """Track CVAT 2.75 sinh từ shape (design/cvat-api-notes.md câu 5): frame f, rồi frame f+1 có cả 8 điểm Outside mà thẻ <skeleton>
        không có `outside`; shape ở frame cuối chỉ có frame f."""
        key = EyeKey(f, {i: PointState((10.0 + i + (self.DX if dx is None else dx), 20.0 + i)) for i in EYES["mattrai"].ids})
        sk = f'<skeleton frame="{f}" keyframe="1" z_order="0">{shape_points(key, "mattrai")}</skeleton>'
        if f < self.N - 1:
            sk += f'<skeleton frame="{f + 1}" keyframe="1" z_order="0">{shape_points(key, "mattrai", all_outside=True)}</skeleton>'
        return f'<track id="{tid}" label="mattrai" source="file">{sk}</track>'

    def want(self, f):
        key = EyeKey(f, {i: PointState((10.0 + i, 20.0 + i)) for i in EYES["mattrai"].ids})
        frames = {g: ({i: (10.0 + i, 20.0 + i) for i in EYES["mattrai"].ids}, {}) for g in range(f, self.N)}
        return {"mattrai": [_Want(1, {f: key}, frames)], "matphai": []}

    def shapes(self, *frames):
        return {"mattrai": [EyeShape("mattrai", EyeKey(f, {i: PointState((10.0 + i + self.DX, 20.0 + i)) for i in EYES["mattrai"].ids}),
                                     {"id": "19"}) for f in frames], "matphai": []}

    def compare(self, tracks, want, shapes):
        video = cvatxml.parse_bytes(xml_of(tracks=tracks, job_size=self.N))
        return cvatsync._compare(video, want, set(), list(range(self.N)), shapes)

    def test_real_single_keyframe_track_and_shape_on_the_same_frame(self):
        out = self.compare(self.real_track(3) + self.shape_track(3), self.want(3), self.shapes(3))
        self.assertEqual(out, [])

    def test_real_single_keyframe_track_and_shape_on_the_last_frame(self):
        last = self.N - 1
        for order in ((self.real_track(last), self.shape_track(last)), (self.shape_track(last), self.real_track(last))):
            with self.subTest(order=order[0][:30]):
                self.assertEqual(self.compare("".join(order), self.want(last), self.shapes(last)), [])

    def test_real_track_lost_by_cvat_on_the_last_frame_is_still_a_count_mismatch(self):
        last = self.N - 1
        out = self.compare(self.shape_track(last), self.want(last), self.shapes(last))
        self.assertEqual(out, ["mattrai: tool gửi 1 track, CVAT có 0 track"])

    def test_at_most_one_track_is_dropped_per_shape(self):
        last = self.N - 1
        out = self.compare(self.real_track(last) + self.shape_track(last), {"mattrai": [], "matphai": []}, self.shapes(last))
        self.assertEqual(out, ["mattrai: tool gửi 0 track, CVAT có 1 track"])

    def test_shape_tracks_alone_are_all_dropped(self):
        for f in (3, self.N - 1):                                            # dưới frame cuối (có frame f+1 toàn điểm Outside) và frame cuối
            with self.subTest(frame=f):
                self.assertEqual(self.compare(self.shape_track(f), {"mattrai": [], "matphai": []}, self.shapes(f)), [])

    def test_shape_with_all_points_outside_is_dropped(self):
        key = EyeKey(3, {i: PointState((10.0 + i, 20.0 + i), outside=True) for i in EYES["mattrai"].ids})
        sk = (f'<skeleton frame="3" keyframe="1" z_order="0">{shape_points(key, "mattrai")}</skeleton>'
              f'<skeleton frame="4" keyframe="1" z_order="0">{shape_points(key, "mattrai", all_outside=True)}</skeleton>')
        out = self.compare(f'<track id="2" label="mattrai" source="file">{sk}</track>', {"mattrai": [], "matphai": []},
                           {"mattrai": [EyeShape("mattrai", key, {"id": "19"})], "matphai": []})
        self.assertEqual(out, [])

    def test_two_shapes_on_one_frame_and_a_real_track(self):
        sent = self.shapes(3)
        sent["mattrai"].append(EyeShape("mattrai", EyeKey(3, {i: PointState((60.0 + i, 20.0 + i)) for i in EYES["mattrai"].ids}), {"id": "28"}))
        tracks = self.real_track(3) + self.shape_track(3) + self.shape_track(3, dx=50, tid=3)
        self.assertEqual(self.compare(tracks, self.want(3), sent), [])

    def test_single_keyframe_track_without_a_shape_is_not_dropped(self):
        out = self.compare(self.shape_track(2), {"mattrai": [], "matphai": []}, self.shapes(5))
        self.assertEqual(out, ["mattrai: tool gửi 0 track, CVAT có 1 track"])


if __name__ == "__main__":
    unittest.main()
