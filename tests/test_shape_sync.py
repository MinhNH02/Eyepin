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
from eyepin.cvatsync import _Want  # noqa: E402
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
    """Bản xuất "CVAT for video": track mắt (như test_cvatsync.server_video_xml) cộng mỗi shape thành một track một frame như CVAT
    (`ShapeManager.to_tracks`: keyframe ở frame của shape, rồi keyframe Outside ở frame kế)."""
    nums = s.source.frame_numbers
    extra = []
    for k, sh in enumerate(s.build_shapes()):
        f = nums[sh.key.frame]
        pts = "".join(f'<points label="{i}" keyframe="1" outside="{int(sh.key.points[i].outside)}" occluded="{int(sh.key.points[i].occluded)}" '
                      f'points="{sh.key.points[i].xy[0]:.2f},{sh.key.points[i].xy[1]:.2f}"/>' for i in EYES[sh.label].ids)
        extra.append(f'<track id="{500 + k}" label="{sh.label}" source="file">'
                     f'<skeleton frame="{f}" keyframe="1" outside="0" occluded="0">{pts}</skeleton>'
                     f'<skeleton frame="{f + 1}" keyframe="1" outside="1" occluded="0">{pts}</skeleton></track>')
    return server_video_xml(s, job_numbers=nums).replace(b"</annotations>", "".join(extra).encode() + b"</annotations>")


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
    """`_compare` chỉ bỏ track một frame khi nó có thể là track CVAT sinh ra từ shape, không bỏ track thật của tool."""

    def video(self, frame):
        pts = "".join(f'<points label="{i}" keyframe="1" outside="0" occluded="0" points="{10 + i},{20 + i}"/>' for i in EYES["mattrai"].ids)
        tr = f'<track id="1" label="mattrai" source="manual"><skeleton frame="{frame}" keyframe="1" outside="0" occluded="0">{pts}</skeleton></track>'
        return cvatxml.parse_bytes(xml_of(tracks=tr, job_size=8))

    def test_genuine_single_keyframe_track_on_a_shape_frame_is_kept(self):
        video = self.video(7)
        tr = video.tracks["mattrai"][0]
        want = {"mattrai": [_Want(1, dict(tr.keys), {7: ({p: ps.xy for p, ps in tr.keys[7].points.items()}, {})})], "matphai": []}
        out = cvatsync._compare(video, want, set(), list(range(8)), {"mattrai": {7}, "matphai": set()})
        self.assertEqual(out, [])

    def test_single_keyframe_track_without_a_shape_is_not_dropped(self):
        out = cvatsync._compare(self.video(2), {"mattrai": [], "matphai": []}, set(), list(range(8)), {"mattrai": {5}, "matphai": set()})
        self.assertEqual(out, ["mattrai: tool gửi 0 track, CVAT có 1 track"])


if __name__ == "__main__":
    unittest.main()
