"""Gửi nhãn mắt về CVAT (eyepin.cvatsync) với server giả; ảnh tổng hợp, không chạm server thật."""
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatsync  # noqa: E402
from eyepin.cvatapi import CvatError, LoginNeeded  # noqa: E402
from eyepin.cvatsource import open_job  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402
from test_cvatsource import (FACE, IMAGES, MATTRAI, VIDEO, Base, ann_json, box_image, eye_shape_image,  # noqa: E402
                             eye_track, xml_of)
from fake_cvat import FakeJob  # noqa: E402
import test_tracking as T  # noqa: E402


def pin_frames(s, frames):
    """Ghim cả hai mắt ở các chỉ số frame (ảnh của chỉ số i là render(số frame của job))."""
    for f in frames:
        t = s.source.frame_numbers[f]
        for label, spec in EYES.items():
            s.pin_eye(f, label, {i: T.pins_at(t)[i] for i in spec.pins})


def server_video_xml(s, skip=(), job_numbers=None, edit=None, drop=None, flags=True):
    """XML "CVAT for video" như CVAT thật trả về: mỗi frame từ keyframe đầu tới hết job có một <skeleton> (keyframe=1 ở keyframe), cờ chép
    từ keyframe bên trái. Để mô phỏng CVAT lưu sai: `edit(tr, f, pid, x, y, occluded, outside)` trả bộ mới hoặc None (bỏ thẻ điểm);
    `drop(tr)` True thì bỏ cả track; `flags=False` xoá mọi cờ."""
    nums = job_numbers or list(range(s.n_frames))
    out = []
    per_layer = []
    for li, layer in enumerate(s.layers):                                     # nhãn và cờ là của từng người (Layer)
        if layer.pins:
            with s.layer_ctx(li):
                for tr in s.build_tracks().values():
                    per_layer.append((tr, dict(s.labels), {f: s.flags_at(f) for f in range(min(tr.keys), s.n_frames)}))
    for tid, (tr, labels, flag_at) in enumerate(per_layer):
        if drop and drop(tr):
            continue
        sk = []
        for f in range(min(tr.keys), s.n_frames):
            if f in skip or f not in labels:
                continue
            fl = flag_at[f] if flags else {}
            pts = []
            for i in EYES[tr.label].ids:
                row = (labels[f].points[i][0], labels[f].points[i][1], fl.get(i) == "occluded", fl.get(i) == "outside")
                if edit:
                    row = edit(tr, f, i, *row)
                    if row is None:
                        continue
                x, y, occ, out_ = row
                pts.append(f'<points label="{i}" keyframe="{int(f in tr.keys)}" outside="{int(out_)}" occluded="{int(occ)}" points="{x:.2f},{y:.2f}"/>')
            sk.append(f'<skeleton frame="{nums[f]}" keyframe="{int(f in tr.keys)}" outside="0" occluded="0">{"".join(pts)}</skeleton>')
        out.append(f'<track id="{tid}" label="{tr.label}" source="manual">{"".join(sk)}</track>')
    return xml_of(tracks="".join(out), job_size=s.n_frames)


def server_tracks(job):
    root = ET.fromstring(job.xml)
    return [(tr.get("label"), sorted(int(sk.get("frame")) for sk in tr.findall("skeleton"))) for tr in root.findall("track")]


class Sync(Base):
    def setup_job(self, n=8, **kw):
        job = self.serve(n_frames=n, **kw)
        self.session = open_job(self.cl, 7)
        return job


class TestSend(Sync):
    def test_send_roundtrip_ok(self):
        base = xml_of(images=box_image(1), job_size=8)
        job = self.serve(n_frames=8, xml=base)
        job.export_xml_by_format[IMAGES] = base
        job.annotations_json = ann_json(shapes=[FACE])
        s = open_job(self.cl, 7)
        pin_frames(s, [0, 3, 6])
        before = s.ann
        plan = cvatsync.prepare(s, self.cl)
        self.assertEqual(plan.base_format, IMAGES)
        want = sorted((t.label, sorted(t.keys)) for t in s.build_all_tracks())
        self.assertTrue(all({0, 3, 6} <= set(k) for _, k in want))        # frame ghim luôn là keyframe
        self.assertEqual(plan.keyframes, sum(len(k) for _, k in want))
        self.assertTrue(plan.replaced.empty())
        self.assertFalse(plan.mixed_types)
        self.assertFalse(plan.changed_on_server)
        self.assertFalse(plan.needs_warning())
        self.assertIn("thay toàn bộ nhãn của job", plan.text())
        res = cvatsync.send(s, self.cl, plan)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(res.mismatches, [])
        self.assertEqual(res.snapshot, base)
        self.assertEqual(sorted(server_tracks(job)), want)
        root = ET.fromstring(job.xml)
        self.assertEqual(root.find("image/box").get("label"), "face")      # nhãn không phải mắt còn nguyên
        self.assertEqual(self.srv.import_formats, ["CVAT 1.1"])
        self.assertTrue(all("filename" not in r["query"] for r in self.srv.requests if r["method"] == "POST" and r["path"].endswith("/annotations")))
        self.assertIs(s.ann, before)                                       # phiên trả về như cũ
        self.assertEqual(self.srv.export_formats[-1], VIDEO)               # đối chiếu bằng bản video

    def test_replaced_counts_come_from_json_not_from_the_images_export(self):
        n = 210
        job = self.serve(n_frames=n)
        job.export_xml_by_format[IMAGES] = xml_of(images="".join(eye_shape_image(f) for f in range(n)), job_size=n)   # 210 shape mắt do CVAT trải
        job.annotations_json = {"version": 1, "tags": [], "shapes": [
            {"id": k, "label_id": MATTRAI, "type": "skeleton", "frame": k, "elements": []} for k in range(30)],
            "tracks": [{"id": 37, "label_id": MATTRAI, "frame": 5, "shapes": [{"frame": 5, "outside": False}, {"frame": 120, "outside": False}],
                        "elements": []}]}
        s = open_job(self.cl, 7)
        plan = cvatsync.prepare(s, self.cl)
        msg = plan.replaced.message()
        self.assertIn("1 track mắt #37", msg)
        self.assertIn("mattrai, frame 5–120", msg)
        self.assertIn("30 shape mắt", msg)
        self.assertNotIn("210", msg)
        self.assertTrue(plan.needs_warning())
        self.assertIn("sẽ xoá", plan.text())
        self.assertIn("thay toàn bộ nhãn của job", plan.text())
        self.assertEqual(plan.keyframes, 0)                               # chưa ghim gì

    def test_mixed_non_eye_types_warn(self):
        job = self.serve(n_frames=8)
        job.annotations_json = ann_json(shapes=[FACE], tracks=[FACE])
        s = open_job(self.cl, 7)
        plan = cvatsync.prepare(s, self.cl)
        self.assertTrue(plan.mixed_types)
        self.assertEqual(plan.base_format, VIDEO)
        self.assertTrue(plan.needs_warning())
        self.assertIn("shape sẽ thành track một frame", plan.text())

    def test_only_one_non_eye_kind_does_not_warn_about_mixing(self):
        job = self.serve(n_frames=8)
        job.annotations_json = ann_json(tracks=[FACE])
        plan = cvatsync.prepare(open_job(self.cl, 7), self.cl)
        self.assertFalse(plan.mixed_types)
        self.assertEqual(plan.base_format, VIDEO)
        self.assertFalse(plan.needs_warning())
        job.annotations_json = ann_json(shapes=[FACE])
        plan = cvatsync.prepare(open_job(self.cl, 7), self.cl)
        self.assertFalse(plan.mixed_types)
        self.assertEqual(plan.base_format, IMAGES)

    def test_changed_on_server_is_detected_and_saved_in_session(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        opened = job.updated_date
        job.version += 1                                                   # ai đó sửa job trên CVAT sau khi mở
        plan = cvatsync.prepare(s, self.cl)
        self.assertTrue(plan.changed_on_server)
        self.assertTrue(plan.needs_warning())
        self.assertIn("đã bị sửa", plan.text())
        res = cvatsync.send(s, self.cl, plan)
        self.assertTrue(res.ok, res.message)
        self.assertNotEqual(job.updated_date, opened)
        self.assertEqual(s.state()["cvat"], {"job": 7, "updated": job.updated_date})
        self.assertEqual(s.cvat["updated"], job.updated_date)
        again = cvatsync.prepare(s, self.cl)
        self.assertFalse(again.changed_on_server)                          # mốc đã theo lần gửi vừa rồi

    def test_server_changing_between_prepare_and_send_is_refused(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        plan = cvatsync.prepare(s, self.cl)
        job.version += 1
        res = cvatsync.send(s, self.cl, plan)
        self.assertFalse(res.ok)
        self.assertIn("vừa thay đổi", res.message)
        self.assertEqual(self.srv.import_formats, [])
        self.assertIsNone(res.snapshot)                                     # chưa gửi gì: không có gì để khôi phục

    def test_failures_before_the_import_carry_no_snapshot(self):
        self.setup_job()
        s = self.session
        plan = cvatsync.prepare(s, self.cl)
        res = cvatsync.send(s, self.cl, plan)                               # chưa ghim gì: không dựng được file
        self.assertFalse(res.ok)
        self.assertIsNone(res.snapshot)
        pin_frames(s, [0, 4])
        plan = cvatsync.prepare(s, self.cl)
        self.srv.fail_500 = True                                            # đọc lại job lỗi trước khi gửi
        res = cvatsync.send(s, self.cl, plan)
        self.assertIn("Chưa gửi gì", res.message)
        self.assertIsNone(res.snapshot)
        self.srv.fail_500 = False
        self.srv.fail_import = "hỏng"                                       # đã gọi import: giữ bản chụp
        res = cvatsync.send(s, self.cl, plan)
        self.assertEqual(res.snapshot, plan.base_xml)

    def test_mismatch_is_reported_and_restore_puts_the_snapshot_back(self):
        base = xml_of(images=box_image(1), job_size=8)
        job = self.serve(n_frames=8, xml=base)
        job.export_xml_by_format[IMAGES] = base
        s = open_job(self.cl, 7)
        pin_frames(s, [0, 3, 6])
        plan = cvatsync.prepare(s, self.cl)
        self.srv.shift_on_import = 5.0
        res = cvatsync.send(s, self.cl, plan)
        self.assertFalse(res.ok)
        self.assertTrue(res.mismatches)
        first = res.mismatches[0]
        self.assertIn("frame 0", first)
        self.assertIn("điểm", first)
        self.assertIn("5.0", first)
        self.assertNotEqual(job.xml, base)
        self.assertEqual(res.snapshot, base)
        self.srv.shift_on_import = 0
        cvatsync.restore(self.cl, 7, res.snapshot)
        self.assertEqual(job.xml, res.snapshot)

    def test_lost_connection_while_waiting_for_import(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        plan = cvatsync.prepare(s, self.cl)
        self.srv.drop_on_poll = True
        res = cvatsync.send(s, self.cl, plan)
        self.assertFalse(res.ok)
        self.assertIn("chưa rõ", res.message)
        self.assertIn(job.updated_date, res.message)
        self.assertEqual(res.snapshot, plan.base_xml)
        self.assertEqual(s.cvat["updated"], plan.opened_updated)           # chưa chắc đã nạp: giữ mốc cũ để lần sau còn cảnh báo
        self.assertIsNotNone(s.ann)

    def test_failed_import_leaves_session_and_server_alone(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        before, xml = s.ann, job.xml
        plan = cvatsync.prepare(s, self.cl)
        self.srv.fail_import = "file hỏng"
        res = cvatsync.send(s, self.cl, plan)
        self.assertFalse(res.ok)
        self.assertIn("file hỏng", res.message)
        self.assertNotIn("chưa rõ", res.message)
        self.assertIs(s.ann, before)
        self.assertEqual(job.xml, xml)

    def test_deleted_frames_are_skipped_in_comparison(self):
        job = self.serve(n_frames=8, deleted_frames=[3])
        s = open_job(self.cl, 7)
        self.assertIn(3, s.deleted)
        pin_frames(s, [0, 3, 6])
        job.export_xml_by_format[VIDEO] = server_video_xml(s, skip={3})   # CVAT không xuất frame đã xoá
        plan = cvatsync.prepare(s, self.cl)
        res = cvatsync.send(s, self.cl, plan)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(res.mismatches, [])
        # đối chứng: nếu không biết frame 3 đã xoá thì keyframe thiếu đó bị báo
        s.source.deleted.clear()
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertTrue(any("frame 3" in m for m in res.mismatches), res.mismatches)

    def test_comparison_skips_only_frames_deleted_in_cvat(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        s.deleted = {0}                                                     # tập xoá của phiên lệch CVAT (CVAT không xoá frame 0)
        plan = cvatsync.prepare(s, self.cl)
        self.srv.shift_on_import = 5.0                                      # CVAT dời một điểm ở keyframe frame 0
        res = cvatsync.send(s, self.cl, plan)
        self.assertFalse(res.ok)
        self.assertTrue(any("frame 0" in m for m in res.mismatches), res.mismatches)

    def test_job_start_frame_10_sends_job_frame_numbers(self):
        base = xml_of(images=box_image(11), job_size=5)
        job = self.serve(start_frame=10, n_frames=5, xml=base)
        job.export_xml_by_format[IMAGES] = base
        s = open_job(self.cl, 7)
        pin_frames(s, [0, 2, 4])
        plan = cvatsync.prepare(s, self.cl)
        res = cvatsync.send(s, self.cl, plan)
        self.assertTrue(res.ok, res.message)
        want = sorted((t.label, [10 + f for f in sorted(t.keys)]) for t in s.build_all_tracks())      # chỉ số -> số frame của job
        self.assertEqual(sorted(server_tracks(job)), want)
        self.assertTrue(all({10, 12, 14} <= set(k) for _, k in want))
        self.assertEqual([im.get("id") for im in ET.fromstring(job.xml).findall("image")], ["11"])

    def test_per_frame_video_export_is_compared_at_every_frame(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        job.export_xml_by_format[VIDEO] = server_video_xml(s)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, res.message)
        job.export_xml_by_format[VIDEO] = server_video_xml(s).replace(b'keyframe="1"', b'keyframe="0"', 1)   # CVAT mất một keyframe
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertTrue(any("keyframe" in m for m in res.mismatches), res.mismatches)

    def test_two_people_are_matched_per_label(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        s.add_layer()
        pin_frames(s, [2, 6])
        plan = cvatsync.prepare(s, self.cl)
        want = sorted((t.label, sorted(t.keys)) for t in s.build_all_tracks())
        self.assertEqual(len(want), 4)
        self.assertEqual(plan.keyframes, sum(len(k) for _, k in want))
        res = cvatsync.send(s, self.cl, plan)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(sorted(server_tracks(job)), want)

    def test_video_base_keeps_a_non_eye_track_as_a_track(self):
        face = ('<track id="5" label="face" source="manual"><box frame="1" outside="0" occluded="0" keyframe="1" xtl="1" ytl="1" xbr="9" ybr="9" '
                'z_order="0"/><box frame="2" outside="1" occluded="0" keyframe="1" xtl="1" ytl="1" xbr="9" ybr="9" z_order="0"/></track>')
        job = self.serve(n_frames=8, xml=xml_of(tracks=face, job_size=8))
        job.annotations_json = ann_json(tracks=[FACE])
        s = open_job(self.cl, 7)
        pin_frames(s, [0, 4])
        plan = cvatsync.prepare(s, self.cl)
        self.assertEqual(plan.base_format, VIDEO)
        self.assertEqual(self.srv.export_formats[:2], [VIDEO, VIDEO])        # mở job và prepare đều xuất nền bằng video
        self.assertEqual(plan.base_xml, job.xml)
        res = cvatsync.send(s, self.cl, plan)
        self.assertTrue(res.ok, res.message)
        root = ET.fromstring(job.xml)                                        # đúng XML CVAT nhận được
        self.assertEqual([tr.get("label") for tr in root.findall("track")], ["face", "mattrai", "matphai"])
        self.assertEqual([b.get("frame") for b in root.find("track[@label='face']").findall("box")], ["1", "2"])
        self.assertEqual(root.findall("image"), [])                          # không có shape nào thay cho track

    def test_flags_that_cvat_does_not_keep_are_reported(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        s.toggle_flag(0, EYES["mattrai"].ids[0], "occluded")
        s.toggle_flag(0, EYES["matphai"].ids[0], "outside")
        job.export_xml_by_format[VIDEO] = server_video_xml(s)                # CVAT lưu đúng cờ (chép sang các frame giữa)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, res.message)
        job.export_xml_by_format[VIDEO] = server_video_xml(s, flags=False)   # CVAT làm mất cờ
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertTrue(any("frame 0" in m and "điểm 14" in m and "occluded" in m for m in res.mismatches), res.mismatches)
        self.assertTrue(any("frame 0" in m and "điểm 22" in m and "outside" in m for m in res.mismatches), res.mismatches)

    def test_point_cvat_drops_is_seen_as_outside(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        job.export_xml_by_format[VIDEO] = server_video_xml(s, edit=lambda tr, f, pid, x, y, occ, out: None if (f == 2 and pid == 14) else (x, y, occ, out))
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertTrue(any("frame 2" in m and "điểm 14" in m and "outside" in m for m in res.mismatches), res.mismatches)

    def test_interpolated_position_off_by_more_than_the_keyframe_tolerance_is_reported(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        self.assertNotIn(2, [f for t in s.build_all_tracks() for f in t.keys])      # frame 2 do CVAT nội suy

        def moved(dx):
            return lambda tr, f, pid, x, y, occ, out: (x + dx, y, occ, out) if (f == 2 and pid == 14) else (x, y, occ, out)
        job.export_xml_by_format[VIDEO] = server_video_xml(s, edit=moved(1.5))      # trong ngưỡng 2 px: không báo
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, res.message)
        job.export_xml_by_format[VIDEO] = server_video_xml(s, edit=moved(3.0))
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertTrue(any("frame 2" in m and "điểm 14" in m and "giữa hai keyframe" in m for m in res.mismatches), res.mismatches)

    def test_cvat_keeping_only_one_of_two_tracks_of_a_label_is_not_a_success(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        s.add_layer()
        pin_frames(s, [2, 6])
        job.export_xml_by_format[VIDEO] = server_video_xml(s)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, res.message)
        job.export_xml_by_format[VIDEO] = server_video_xml(s, drop=lambda tr: tr.label == "mattrai" and min(tr.keys) == 2)
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertTrue(any("mattrai" in m and "2 track" in m and "1 track" in m for m in res.mismatches), res.mismatches)

    def test_session_ann_is_restored_when_building_the_file_fails(self):
        self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        before = s.ann
        plan = cvatsync.prepare(s, self.cl)
        seen = []

        def boom(path, *a, **k):
            seen.append(s.ann is plan.ann)                                    # đang ở nền đã bỏ nhãn mắt
            raise ValueError("hỏng giữa chừng")
        with mock.patch.object(s, "export", side_effect=boom):
            res = cvatsync.send(s, self.cl, plan)
        self.assertEqual(seen, [True])
        self.assertFalse(res.ok)
        self.assertIs(s.ann, before)
        self.assertEqual(self.srv.import_formats, [])

        def disk_full(path, *a, **k):
            raise OSError("disk full")
        with mock.patch.object(s, "export", side_effect=disk_full):
            with self.assertRaises(OSError):
                cvatsync.send(s, self.cl, plan)
        self.assertIs(s.ann, before)                                          # lỗi không lường trước cũng trả phiên về như cũ

    def test_prepare_refuses_a_base_with_labels_outside_the_job(self):
        base = xml_of(images=box_image(1) + box_image(40), job_size=8)          # box ở frame 40: ngoài job 0..7
        job = self.serve(n_frames=8, xml=base)
        job.annotations_json = ann_json(shapes=[FACE, FACE])
        s = open_job(self.cl, 7)
        pin_frames(s, [0, 4])
        with self.assertRaises(CvatError) as cm:
            cvatsync.prepare(s, self.cl)
        self.assertIn("ngoài phạm vi frame của job", str(cm.exception))
        self.assertEqual(self.srv.import_formats, [])

    def test_non_eye_objects_lost_by_the_import_are_a_mismatch(self):
        face = {"id": FACE, "name": "face", "type": "rectangle", "sublabels": []}
        base = xml_of(images=box_image(1) + box_image(2), job_size=8)
        job = self.serve(n_frames=8, xml=base, labels=FakeJob.default_labels() + [face])
        job.annotations_json = ann_json(shapes=[FACE, FACE], tracks=[FACE])
        s = open_job(self.cl, 7)
        pin_frames(s, [0, 4])
        plan = cvatsync.prepare(s, self.cl)
        self.srv.lose_non_eye_on_import = True                                   # CVAT nạp file nhưng mất một box
        res = cvatsync.send(s, self.cl, plan)
        self.assertFalse(res.ok)
        self.assertNotIn("khớp", res.message)
        self.assertTrue(any("face" in m and "3" in m and "2" in m for m in res.mismatches), res.mismatches)
        self.assertEqual(res.snapshot, plan.base_xml)                            # đã gửi: có bản chụp để khôi phục
        self.assertNotIn("có thể khôi phục", res.message)                       # bản chụp có thể không chứa nhãn đã mất: không hứa khôi phục
        self.assertIn("kiểm trên CVAT", res.message)
        self.assertIn("không phải mắt", res.message)

    def test_eye_only_mismatch_still_mentions_restore(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        plan = cvatsync.prepare(s, self.cl)
        self.srv.shift_on_import = 5.0
        res = cvatsync.send(s, self.cl, plan)
        self.assertFalse(res.ok)
        self.assertIn("có thể khôi phục", res.message)

    def test_non_eye_counts_unchanged_is_still_ok(self):
        job = self.serve(n_frames=8)
        job.annotations_json = ann_json(shapes=[FACE], tags=[{"id": 1, "label_id": FACE, "frame": 0}])      # nền images: tag đi được
        s = open_job(self.cl, 7)
        pin_frames(s, [0, 4])
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, res.message)
        job.annotations_json = ann_json(shapes=[FACE], tracks=[FACE])                                         # nền video, không có tag
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, res.message)

    def _face_job(self, deleted=(3,)):
        face = {"id": FACE, "name": "face", "type": "rectangle", "sublabels": []}
        job = self.serve(n_frames=8, deleted_frames=list(deleted), labels=FakeJob.default_labels() + [face])
        return job

    def test_prepare_refuses_non_eye_labels_on_frames_deleted_in_cvat(self):
        # CVAT xuất (cả images lẫn video) bỏ nhãn trên frame đã xoá, nên import xoá chúng và bản chụp cũng không có chúng
        cases = {
            "shape": {"version": 1, "tags": [], "tracks": [], "shapes": [{"id": 1, "label_id": FACE, "type": "rectangle", "frame": 3}]},
            "tag": {"version": 1, "shapes": [], "tracks": [], "tags": [{"id": 1, "label_id": FACE, "frame": 3}]},
            "track": {"version": 1, "shapes": [], "tags": [], "tracks": [{"id": 5, "label_id": FACE, "frame": 1, "elements": [],
                                                                          "shapes": [{"frame": 1, "outside": False}, {"frame": 3, "outside": False}]}]},
        }
        job = self._face_job()
        s = open_job(self.cl, 7)
        pin_frames(s, [0, 4])
        for kind, aj in cases.items():
            with self.subTest(kind):
                job.annotations_json = aj
                with self.assertRaises(CvatError) as cm:
                    cvatsync.prepare(s, self.cl)
                msg = str(cm.exception)
                self.assertIn("face", msg)
                self.assertIn("frame 3", msg)
                self.assertIn("đã xoá", msg)
        self.assertEqual(self.srv.import_formats, [])

    def test_eye_labels_or_other_frames_do_not_block_on_deleted_frames(self):
        job = self._face_job()
        job.annotations_json = {"version": 1, "tags": [{"id": 1, "label_id": FACE, "frame": 2}],
                                "shapes": [{"id": 1, "label_id": FACE, "type": "rectangle", "frame": 4},
                                           {"id": 2, "label_id": MATTRAI, "type": "skeleton", "frame": 3, "elements": []}], "tracks": []}
        s = open_job(self.cl, 7)
        s.clear_old_eyes() if s.qc else None
        pin_frames(s, [0, 4])
        cvatsync.prepare(s, self.cl)                                         # nhãn mắt trên frame xoá sẽ bị thay dù sao: không chặn

    def test_prepare_refuses_tags_when_the_base_is_video(self):
        job = self._face_job(deleted=())
        job.annotations_json = ann_json(tracks=[FACE], tags=[{"id": 1, "label_id": FACE, "frame": 0}])
        s = open_job(self.cl, 7)
        pin_frames(s, [0, 4])
        with self.assertRaises(CvatError) as cm:
            cvatsync.prepare(s, self.cl)
        self.assertIn("tag", str(cm.exception))
        self.assertIn("CVAT for video", str(cm.exception))
        self.assertEqual(self.srv.import_formats, [])

    def test_stale_labels_block_prepare_until_a_successful_recompute(self):
        self.setup_job()
        s = self.session
        pin_frames(s, [0])
        self.assertFalse(s.stale)
        s._gray.clear()
        s._cache.clear()
        self.srv.fail_500 = True                                                 # mất kết nối đúng lúc bám
        with self.assertRaises(CvatError):
            pin_frames(s, [4])
        self.assertTrue(s.stale)
        self.assertIn(4, s.pins)                                                 # ghim mới đã lưu nhưng nhãn chưa bám lại
        self.assertNotIn("stale", s.state())                                     # không lưu vào file phiên
        self.srv.fail_500 = False
        with self.assertRaises(CvatError) as cm:
            cvatsync.prepare(s, self.cl)
        self.assertIn("Nhãn tool tính đang cũ", str(cm.exception))
        s.stale = True                                                           # nhãn cũ đi sau lúc prepare: send cũng từ chối, chưa gửi gì
        res = cvatsync.send(s, self.cl, cvatsync.SendPlan(False, cvatsync.EyeLabels([], {}), False, 0, IMAGES, job_id=7))
        self.assertFalse(res.ok)
        self.assertIn("Nhãn tool tính đang cũ", res.message)
        self.assertIsNone(res.snapshot)
        self.assertEqual(self.srv.import_formats, [])
        pin_frames(s, [4])                                                       # làm lại thao tác, lần này bám được
        self.assertFalse(s.stale)
        self.assertTrue(cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl)).ok)

    def test_nothing_pinned_sends_nothing(self):
        self.setup_job()
        plan = cvatsync.prepare(self.session, self.cl)
        res = cvatsync.send(self.session, self.cl, plan)
        self.assertFalse(res.ok)
        self.assertIn("Chưa có", res.message)
        self.assertEqual(self.srv.import_formats, [])

    def test_session_not_from_cvat_is_refused(self):
        self.setup_job()
        self.session.cvat = None
        with self.assertRaises(CvatError):
            cvatsync.prepare(self.session, self.cl)

    def test_login_needed_propagates_from_prepare(self):
        self.setup_job()
        self.srv.fail_401 = True
        with self.assertRaises(LoginNeeded):
            cvatsync.prepare(self.session, self.cl)

    def test_export_file_is_not_left_behind_and_no_image_is_written(self):
        self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        plan = cvatsync.prepare(s, self.cl)
        import tempfile
        seen = []
        real = tempfile.TemporaryDirectory

        class Spy(real):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                seen.append(self.name)
        tempfile.TemporaryDirectory = Spy
        try:
            res = cvatsync.send(s, self.cl, plan)
        finally:
            tempfile.TemporaryDirectory = real
        self.assertTrue(res.ok, res.message)
        self.assertTrue(seen and not any(os.path.exists(p) for p in seen))


class _Src:
    names = ["a", "b", "c"]
    width, height = 100, 50
    deleted = set()
    key, title = "k", "t"


class TestSessionCvatField(Sync):
    def test_defaults_on_a_session_not_from_cvat(self):
        s = Session(source=_Src())
        self.assertIsNone(s.cvat)
        self.assertIsNone(s.base_format)
        self.assertIsNone(s.display_format)
        self.assertNotIn("cvat", s.state())

    def test_state_has_cvat_and_old_files_without_it_still_load(self):
        job = self.setup_job()
        s = self.session
        pin_frames(s, [0, 4])
        d = s.state()
        self.assertEqual(d["cvat"], {"job": 7, "updated": job.updated_date})
        old = dict(d)
        del old["cvat"]
        s.cvat = {"job": 7, "updated": "newer"}
        s.load_state(old)
        self.assertEqual(s.cvat, {"job": 7, "updated": "newer"})            # file cũ không đụng tới mốc cập nhật
        s.load_state(d)
        self.assertEqual(s.cvat, {"job": 7, "updated": job.updated_date})   # mốc của bản đã làm việc trên đó
        s.cvat = {"job": 8, "updated": "x"}
        s.load_state(d)
        self.assertEqual(s.cvat, {"job": 8, "updated": "x"})                # job khác: không nhận
        f = Session(source=_Src())
        f.load_state({**Session(source=_Src()).state(), "cvat": {"job": 7, "updated": "z"}})
        self.assertIsNone(f.cvat)                                            # phiên mở từ thư mục không có cvat

    def test_cvat_deleted_frames_win_over_the_session_file(self):
        self.serve(n_frames=8, deleted_frames=[3])
        s = open_job(self.cl, 7)
        pin_frames(s, [0])
        d = s.state()
        d["deleted"] = [5]                                                   # file phiên cũ ghi tập xoá khác CVAT
        s.load_state(d)
        self.assertEqual(s.deleted, {3})
        f = Session(source=_Src())                                           # phiên mở từ thư mục: tập xoá theo file phiên như cũ
        f.load_state({**f.state(), "deleted": [1]})
        self.assertEqual(f.deleted, {1})

    def test_failed_load_state_leaves_the_session_as_it_was(self):
        self.setup_job()
        s = self.session
        pin_frames(s, [0])
        d = s.state()
        fresh = open_job(self.cl, 7)
        fresh._gray.clear()
        fresh._cache.clear()
        self.srv.fail_500 = True
        with self.assertRaises(CvatError):
            fresh.load_state(d)
        self.assertEqual(fresh.pins, {})                                     # không nửa vời: ghim của file chưa vào phiên
        self.assertEqual(len(fresh.layers), 1)
        self.assertFalse(fresh.stale)

    def test_mark_synced_reads_the_job_date(self):
        job = self.setup_job()
        job.version += 3
        d = cvatsync.mark_synced(self.session, self.cl)
        self.assertEqual(d, job.updated_date)
        self.assertEqual(self.session.cvat["updated"], job.updated_date)


if __name__ == "__main__":
    unittest.main()
