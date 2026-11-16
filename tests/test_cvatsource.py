import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml  # noqa: E402
from eyepin.cvatapi import CvatClient, CvatError  # noqa: E402
from eyepin.cvatsource import CvatSource, base_format, open_job  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402
from fake_cvat import FakeCvat, FakeJob  # noqa: E402
import test_tracking as T  # noqa: E402

IMAGES, VIDEO = "CVAT for images 1.1", "CVAT for video 1.1"
MATTRAI, MATPHAI, FACE = 14, 22, 99          # id nhãn trong FakeJob.default_labels (14, 22) và một nhãn khác


def pts(label, x0=100.0):
    return "".join(f'<points label="{i}" outside="0" occluded="0" points="{x0 + i},{50 + i}"/>' for i in EYES[label].ids)


def xml_of(images="", tracks="", job_size=5):
    return (f'<?xml version="1.0" encoding="utf-8"?><annotations><version>1.1</version>'
            f'<meta><job><size>{job_size}</size></job></meta>{tracks}{images}</annotations>').encode()


def eye_track(tid, label, frames):
    keys = "".join(f'<skeleton frame="{f}" keyframe="1" outside="0" occluded="0">{pts(label)}</skeleton>' for f in frames)
    return f'<track id="{tid}" label="{label}" source="manual">{keys}</track>'


def box_image(f, name=None):
    return (f'<image id="{f}" name="{name or "frame_%06d.jpg" % f}" width="{T.W}" height="{T.H}">'
            f'<box label="face" occluded="0" xtl="10" ytl="10" xbr="50" ybr="50" source="manual" z_order="0"/></image>')


def eye_shape_image(f, label="mattrai"):
    return (f'<image id="{f}" name="frame_{f:06d}.jpg" width="{T.W}" height="{T.H}">'
            f'<skeleton label="{label}" outside="0">{pts(label)}</skeleton></image>')


def json_obj(label_id, kind="shape"):
    return {"id": 1, "label_id": label_id, "type": "skeleton" if label_id in (MATTRAI, MATPHAI) else "rectangle", "frame": 0}


def ann_json(shapes=(), tracks=(), tags=()):
    return {"version": 1, "tags": list(tags), "shapes": [json_obj(i) for i in shapes], "tracks": [json_obj(i) for i in tracks]}


class Base(unittest.TestCase):
    def serve(self, **kw):
        kw.setdefault("n_frames", 5)
        job = FakeJob(7, task_id=3, task_name="clip", **kw)
        self.srv = FakeCvat([job])
        self.srv.start()
        self.addCleanup(self.srv.stop)
        self.cl = CvatClient(self.srv.url, timeout=5)
        self.cl.poll_interval = 0.01
        self.cl.login("minh", "pw")
        self.addCleanup(self.cl.close)
        return job

    def data_calls(self):
        return self.srv.calls["GET /api/jobs/7/data"]


class TestBaseFormat(unittest.TestCase):
    def test_nothing_or_only_shapes_sends_images(self):
        self.assertEqual(base_format(ann_json(), {MATTRAI, MATPHAI}), (IMAGES, IMAGES))
        self.assertEqual(base_format(ann_json(shapes=[FACE]), {MATTRAI, MATPHAI}), (IMAGES, IMAGES))

    def test_non_eye_tracks_send_video(self):
        self.assertEqual(base_format(ann_json(tracks=[FACE]), {MATTRAI, MATPHAI}), (VIDEO, IMAGES))
        self.assertEqual(base_format(ann_json(shapes=[FACE], tracks=[FACE]), {MATTRAI, MATPHAI}), (VIDEO, IMAGES))

    def test_eye_tracks_are_displayed_as_video_but_do_not_force_video_base(self):
        self.assertEqual(base_format(ann_json(tracks=[MATTRAI]), {MATTRAI, MATPHAI}), (IMAGES, VIDEO))
        self.assertEqual(base_format(ann_json(shapes=[FACE], tracks=[MATTRAI, MATPHAI]), {MATTRAI, MATPHAI}), (IMAGES, VIDEO))
        self.assertEqual(base_format(ann_json(tracks=[MATPHAI, FACE]), {MATTRAI, MATPHAI}), (VIDEO, VIDEO))

    def test_eye_shapes_only_display_as_images(self):
        self.assertEqual(base_format(ann_json(shapes=[MATTRAI]), {MATTRAI, MATPHAI}), (IMAGES, IMAGES))

    def test_tags_do_not_force_video(self):
        self.assertEqual(base_format(ann_json(tags=[{"label_id": FACE, "frame": 0}]), {MATTRAI, MATPHAI}), (IMAGES, IMAGES))

    def test_without_label_ids_an_eight_point_skeleton_counts_as_an_eye(self):
        eye = {"label_id": 5, "elements": [{"label_id": i} for i in range(8)], "frame": 0}
        self.assertEqual(base_format({"shapes": [], "tags": [], "tracks": [eye]}), (IMAGES, VIDEO))
        other = {"label_id": 6, "type": "rectangle", "frame": 0}
        self.assertEqual(base_format({"shapes": [], "tags": [], "tracks": [other]}), (VIDEO, IMAGES))


class TestOpenJob(Base):
    def test_open_job_downloads_no_frame_until_asked(self):
        self.serve()
        s = open_job(self.cl, 7)
        self.assertLessEqual(self.data_calls(), 1)
        self.assertEqual(self.data_calls(), 0)
        s.bgr(2)
        self.assertEqual(self.data_calls(), 1)
        self.assertEqual(self.srv.frame_query[-1]["number"], "2")

    def test_frames_come_from_cvat_in_ram(self):
        self.serve()
        s = open_job(self.cl, 7)
        want = cv2.imdecode(cv2.imencode(".jpg", T.render(5 - 1))[1], cv2.IMREAD_COLOR)   # frame thứ 5 của job 5 frame
        self.assertEqual(s.n_frames, 5)
        self.assertTrue(np.array_equal(s.bgr(4), want))
        self.assertEqual(s.bgr(4).shape, (T.H, T.W, 3))
        self.assertIsNone(s.frames_dir)
        self.assertEqual((s.width, s.height), (T.W, T.H))

    def test_frames_never_touch_the_disk(self):
        self.serve()
        s = open_job(self.cl, 7)
        with mock.patch("builtins.open", side_effect=AssertionError("ghi/đọc file")), \
                mock.patch("tempfile.NamedTemporaryFile", side_effect=AssertionError("file tạm")), \
                mock.patch("tempfile.mkstemp", side_effect=AssertionError("file tạm")), \
                mock.patch("cv2.imwrite", side_effect=AssertionError("imwrite")):
            s.bgr(1)

    def test_frame_numbers_of_a_job_that_starts_at_10(self):
        job = self.serve(start_frame=10, xml=xml_of(images=box_image(11)), n_frames=5)
        s = open_job(self.cl, 7)
        src = s.source
        self.assertEqual(src.frame_numbers, [10, 11, 12, 13, 14])
        self.assertEqual(s.names[2], "frame_000012.jpg")
        # ảnh đi theo số frame của job
        self.assertTrue(np.array_equal(s.bgr(2), cv2.imdecode(cv2.imencode(".jpg", T.render(12))[1], cv2.IMREAD_COLOR)))
        self.assertEqual(self.srv.frame_query[-1]["number"], "12")
        # ghim ở chỉ số 2 -> file xuất mang số frame của job (12), nhãn khác (box ở <image id=11>) nguyên chỗ
        for label, spec in EYES.items():
            s.add_pin(2, label, {i: T.pins_at(12)[i] for i in spec.pins})
        out = os.path.join(tempfile.mkdtemp(prefix="eyepin_t3_"), "out.xml")
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        s.export(out)
        root = ET.parse(out).getroot()
        frames = sorted({int(sk.get("frame")) for tr in root.findall("track") for sk in tr.findall("skeleton")})
        self.assertEqual(frames[0], 12)
        self.assertTrue(all(12 <= f <= 14 for f in frames), frames)
        self.assertEqual([im.get("id") for im in root.findall("image")], ["11"])
        self.assertEqual(root.find("image/box").get("label"), "face")
        self.assertEqual(job.xml, xml_of(images=box_image(11)))          # không đụng gì lên server

    def test_xml_frames_are_reindexed_to_eyepin_indices(self):
        xml = xml_of(tracks=eye_track(37, "mattrai", [10, 12]) + eye_track(38, "matphai", [11]), images=box_image(13))
        ann = cvatxml.parse_bytes(xml, frame_numbers=[10, 11, 12, 13, 14])
        self.assertEqual(sorted(ann.tracks["mattrai"][0].keys), [0, 2])
        self.assertEqual(sorted(ann.tracks["matphai"][0].keys), [1])
        self.assertEqual(ann.frame_names, {3: "frame_000013.jpg"})
        self.assertEqual(ann.n_frames, 5)
        # chỉ số trong cây cũng đã đổi, nên mọi chỗ đọc cây thấy cùng một cách đánh số
        self.assertEqual([im.get("id") for im in ann.tree.getroot().findall("image")], ["3"])

    def test_frames_outside_the_job_are_dropped_when_reindexing(self):
        xml = xml_of(tracks=eye_track(37, "mattrai", [10, 15]), images=box_image(99))
        ann = cvatxml.parse_bytes(xml, frame_numbers=[10, 11, 12, 13, 14])
        self.assertEqual(sorted(ann.tracks["mattrai"][0].keys), [0])
        self.assertEqual(ann.tree.getroot().findall("image"), [])
        self.assertEqual(ann.dropped, 2)                                  # keyframe ở 15 và box ở <image id=99>

    def test_dropped_counts_only_annotations_and_is_zero_inside_the_job(self):
        empty_outside = '<image id="98" name="x.jpg" width="1" height="1"></image>'
        ann = cvatxml.parse_bytes(xml_of(images=box_image(11) + empty_outside), frame_numbers=[10, 11, 12])
        self.assertEqual(ann.dropped, 0)                                  # <image> trống ngoài job không mang nhãn nào
        tag = '<tag label="x" frame="40" source="manual"/>'
        self.assertEqual(cvatxml.parse_bytes(xml_of(tracks=tag), frame_numbers=[10, 11, 12]).dropped, 1)
        self.assertEqual(cvatxml.parse_bytes(xml_of(images=box_image(11))).dropped, 0)

    def test_sparse_job_with_included_frames_is_refused(self):
        self.serve(start_frame=10, n_frames=3, included_frames=[10, 14, 20])
        with self.assertRaises(CvatError) as cm:
            open_job(self.cl, 7)
        self.assertIn("thưa", str(cm.exception))
        self.assertEqual(self.data_calls(), 0)

    def test_video_task_is_refused(self):
        self.serve(n_frames=5, media="video")                      # meta.frames chỉ có một phần tử cho cả video
        with self.assertRaises(CvatError) as cm:
            open_job(self.cl, 7)
        self.assertIn("video", str(cm.exception))
        self.assertIn("5", str(cm.exception))

    def test_meta_size_not_matching_the_job_range_is_refused(self):
        job = self.serve(start_frame=10, n_frames=5)
        job.meta_overrides = {"size": 4}
        with self.assertRaises(CvatError) as cm:
            open_job(self.cl, 7)
        self.assertIn("4", str(cm.exception))
        self.assertIn("10", str(cm.exception))

    def test_frame_numbers_come_from_the_job_not_from_meta_start_frame(self):
        self.serve(start_frame=10, n_frames=5)
        src = CvatSource(self.cl, 7)
        self.assertEqual(src.frame_numbers, [10, 11, 12, 13, 14])
        self.assertEqual(len(src.names), 5)

    def test_task_whose_media_numbers_differ_from_task_numbers_is_refused(self):
        # data.start_frame = 5: số tuyệt đối của media (meta.start_frame = 15, số trong XML "CVAT 1.1" theo cvat/apps/dataset_manager/bindings.py
        # abs_frame_id) khác số tương đối của task (10, số của data?number=, deleted_frames, JSON): chưa hỗ trợ, từ chối thay vì gửi lệch frame
        self.serve(start_frame=10, n_frames=5, data_start_frame=5)
        with self.assertRaises(CvatError) as cm:
            open_job(self.cl, 7)
        self.assertIn("15", str(cm.exception))
        self.assertIn("10", str(cm.exception))
        self.assertEqual(self.data_calls(), 0)

    def test_task_with_frame_step_is_refused(self):
        self.serve(start_frame=0, n_frames=5, frame_step=2)
        with self.assertRaises(CvatError):
            open_job(self.cl, 7)

    def test_deleted_frames_are_read_only(self):
        self.serve(deleted_frames=[3])
        s = open_job(self.cl, 7)
        self.assertIn(3, s.deleted)

    def test_deleted_frames_use_job_numbers(self):
        self.serve(start_frame=10, deleted_frames=[12])
        s = open_job(self.cl, 7)
        self.assertEqual(s.deleted, {2})

    def test_job_without_eye_skeletons_is_refused(self):
        self.serve(labels=[{"id": 1, "name": "face", "type": "rectangle", "sublabels": []}])
        with self.assertRaises(CvatError) as cm:
            open_job(self.cl, 7)
        self.assertIn("mattrai", str(cm.exception))
        self.assertEqual(self.data_calls(), 0)

    def test_session_identity_and_cvat_fields(self):
        job = self.serve()
        s = open_job(self.cl, 7)
        self.assertEqual(s.source_key, f"cvat:{self.srv.url}|job7")
        self.assertEqual(s.title, "CVAT job #7 (clip)")
        self.assertEqual(s.cvat, {"job": 7, "updated": job.updated_date})
        self.assertFalse(s.qc)
        self.assertEqual((s.base_format, s.display_format), (IMAGES, IMAGES))
        self.assertIsInstance(s, Session)

    def test_empty_job_exports_only_the_base_format(self):
        self.serve()
        open_job(self.cl, 7)
        self.assertEqual(self.srv.export_formats, [IMAGES])

    def test_eye_tracks_show_with_keyframes_and_turn_qc_on(self):
        job = self.serve(start_frame=10, xml=xml_of(tracks=eye_track(37, "mattrai", [10, 12])))
        job.annotations_json = ann_json(tracks=[MATTRAI])
        s = open_job(self.cl, 7)
        self.assertTrue(s.qc)
        self.assertEqual((s.base_format, s.display_format), (IMAGES, VIDEO))
        self.assertEqual(self.srv.export_formats, [IMAGES, VIDEO])
        self.assertEqual(sorted(s.ann.tracks["mattrai"][0].keys), [0, 2])
        self.assertEqual(s.ann.frame_numbers, [10, 11, 12, 13, 14])

    def test_mixed_job_keeps_other_shapes_and_eye_keyframes(self):
        job = self.serve(start_frame=10)
        job.export_xml_by_format[IMAGES] = xml_of(images=box_image(11) + eye_shape_image(12))   # nhãn mắt bị trải thành shape
        job.export_xml_by_format[VIDEO] = xml_of(tracks=eye_track(37, "mattrai", [10, 14]))
        job.annotations_json = ann_json(shapes=[FACE], tracks=[MATTRAI])
        s = open_job(self.cl, 7)
        self.assertEqual((s.base_format, s.display_format), (IMAGES, VIDEO))
        self.assertTrue(s.qc)
        self.assertEqual(sorted(s.ann.tracks["mattrai"][0].keys), [0, 4])      # keyframe thật từ bản video
        self.assertEqual(s.ann.other_objects, 1)                               # box từ bản images
        # bỏ nhãn mắt cũ: cây nền (bản images) còn box ở chỉ số 1 và không còn skeleton mắt nào
        s.clear_old_eyes()
        self.assertFalse(s.qc)
        root = s.ann.tree.getroot()
        self.assertEqual(root.find("image[@id='1']/box").get("label"), "face")
        self.assertEqual(root.findall(".//skeleton"), [])

    def test_eye_shapes_next_to_non_eye_tracks_show_as_shapes(self):
        job = self.serve(start_frame=10)
        face_track = '<track id="5" label="face" source="manual"><box frame="10" outside="0" occluded="0" keyframe="1" xtl="1" ytl="1" xbr="9" ybr="9" z_order="0"/></track>'
        job.export_xml_by_format[VIDEO] = xml_of(tracks=face_track + eye_track(37, "mattrai", [12]))     # shape mắt thành track một frame
        job.export_xml_by_format[IMAGES] = xml_of(images=eye_shape_image(12))
        job.annotations_json = ann_json(shapes=[MATTRAI], tracks=[FACE])
        s = open_job(self.cl, 7)
        self.assertEqual((s.base_format, s.display_format), (VIDEO, IMAGES))
        self.assertEqual(list(s.ann.shapes["mattrai"]), [2])
        self.assertEqual(s.ann.tracks["mattrai"], [])
        self.assertEqual(s.ann.other_objects, 1)
        self.assertTrue(s.qc)

    def test_non_eye_tracks_choose_video_base(self):
        job = self.serve()
        job.annotations_json = ann_json(tracks=[FACE])
        s = open_job(self.cl, 7)
        self.assertEqual((s.base_format, s.display_format), (VIDEO, IMAGES))
        self.assertEqual(self.srv.export_formats, [VIDEO])

    def test_undecodable_frame_is_an_error(self):
        self.serve()
        s = open_job(self.cl, 7)
        with mock.patch.object(self.cl, "frame", return_value=b"not an image"):
            with self.assertRaises(CvatError):
                s.source.read(0)

    def test_job_without_frames_is_an_error(self):
        self.serve(n_frames=0)
        with self.assertRaises(CvatError):
            open_job(self.cl, 7)


class TestWriteEyesFrameNumbers(unittest.TestCase):
    def test_write_maps_new_tracks_and_old_objects_back_to_job_numbers(self):
        xml = xml_of(images=box_image(11) + box_image(14))
        ann = cvatxml.parse_bytes(xml, frame_numbers=[10, 11, 12, 13, 14])
        key = cvatxml.EyeKey(2, {i: cvatxml.PointState((1.0 * i, 2.0)) for i in EYES["mattrai"].ids})
        tr = cvatxml.EyeTrack("mattrai", keys={2: key})
        fd, out = tempfile.mkstemp(suffix=".xml")
        os.close(fd)
        self.addCleanup(os.unlink, out)
        cvatxml.write_eyes(ann, out, new_tracks=[tr])
        root = ET.parse(out).getroot()
        self.assertEqual([im.get("id") for im in root.findall("image")], ["11", "14"])
        self.assertEqual([sk.get("frame") for sk in root.find("track").findall("skeleton")], ["12"])
        self.assertEqual(ann.tree.getroot().findall("image")[0].get("id"), "1")      # cây trong RAM không bị đổi

    def test_write_shapes_use_job_numbers(self):
        ann = cvatxml.parse_bytes(xml_of(images=box_image(11) + box_image(12)), frame_numbers=[10, 11, 12])
        key = cvatxml.EyeKey(2, {i: cvatxml.PointState((1.0, 2.0)) for i in EYES["mattrai"].ids})
        fd, out = tempfile.mkstemp(suffix=".xml")
        os.close(fd)
        self.addCleanup(os.unlink, out)
        cvatxml.write_eyes(ann, out, new_shapes={"mattrai": {2: key}})
        root = ET.parse(out).getroot()
        self.assertEqual(root.findall("image")[1].get("id"), "12")
        self.assertEqual(len(root.findall("image")[1].findall("skeleton")), 1)

    def test_no_frame_numbers_changes_nothing(self):
        ann = cvatxml.parse_bytes(xml_of(images=box_image(3)))
        self.assertIsNone(ann.frame_numbers)
        self.assertEqual(ann.frame_names, {3: "frame_000003.jpg"})


if __name__ == "__main__":
    unittest.main()
