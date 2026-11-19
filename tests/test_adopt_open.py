"""Mở job CVAT có shape mắt: nạp để sửa tiếp, hoặc ở chế độ QC kèm lý do; khôi phục phiên đã lưu của job đã nạp
(`cvatsource.open_job`, `gui_cvat._open_extras`, `gui.try_restore`, bảng Vẽ mắt; design/2026-11-19-qc-edit-design.md).

JSON và nhãn của job dựng tay bằng các hàm của `test_adopt`; server giả `FakeCvat`; ảnh giả của `test_tracking`.
Bỏ qua phần giao diện nếu máy không mở được cửa sổ Tk."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.cvatsource import open_job  # noqa: E402
from fake_cvat import FakeJob  # noqa: E402
import test_adopt as A  # noqa: E402
import test_gui_cvat as G  # noqa: E402
from test_cvatsource import IMAGES, Base, eye_shape_image, eye_track, xml_of  # noqa: E402

N = G.N
INTRO = "Đã nạp 2 shape mắt của job để sửa (mattrai 1, matphai 1); thiếu nhãn ở 0 đoạn."
OLD_FILE = "Bỏ qua phiên lưu cũ (lưu khi job còn ở chế độ chỉ xem)."
CHANGED = "\nJob đã bị sửa trên CVAT sau lúc lưu; khôi phục rồi gửi sẽ đè các thay đổi đó."


def two_shapes():
    return [A.skeleton("mattrai", 2), A.skeleton("matphai", 5)]


def two_shape_xml():
    return xml_of(images=eye_shape_image(2, "mattrai") + eye_shape_image(5, "matphai"), job_size=N)


def fake_job(shapes=(), tracks=(), tags=(), xml=None, job_id=7, **kw):
    """Job 8 frame có hai skeleton mắt và nhãn `face`; `annotations_json` là JSON tạo từ `shapes`, `tracks`, `tags`."""
    fj = FakeJob(job_id, task_id=3, task_name="clip", n_frames=N, xml=xml or xml_of(job_size=N), labels=A.LABELS, **kw)
    fj.annotations_json = A.job(shapes=shapes, tracks=tracks, tags=tags)
    return fj


class TestOpenJob(Base):
    def open(self, shapes=(), tracks=(), xml=None, **kw):
        """Dựng job 7 (8 frame, nhãn của `test_adopt`) trên server giả rồi `open_job`."""
        job = self.serve(n_frames=N, labels=A.LABELS, xml=xml or xml_of(job_size=N), **kw)
        job.annotations_json = A.job(shapes=shapes, tracks=tracks)
        return open_job(self.cl, 7)

    def test_shape_only_job_opens_adopted(self):
        s = self.open(shapes=two_shapes(), xml=two_shape_xml())
        self.assertTrue(s.adopted)
        self.assertFalse(s.qc)
        self.assertEqual(s.qc_reasons, [])
        self.assertEqual([(sh.label, sh.key.frame) for sh in s.build_shapes()], [("mattrai", 2), ("matphai", 5)])
        self.assertEqual(s.cvat["job"], 7)
        self.assertEqual((s.base_format, s.display_format), (IMAGES, IMAGES))
        self.assertEqual(self.srv.import_formats, [])                           # mở không gửi gì lên server

    def test_job_without_eyes_is_neither_adopted_nor_qc(self):
        s = self.open(shapes=[A.box(1)])
        self.assertFalse(s.adopted)
        self.assertFalse(s.qc)
        self.assertEqual(s.qc_reasons, [])

    def test_eye_track_job_stays_qc_with_reason(self):
        s = self.open(tracks=[A.eye_track("mattrai", [0])], xml=xml_of(tracks=eye_track(37, "mattrai", [0, 2]), job_size=N))
        self.assertTrue(s.qc)
        self.assertFalse(s.adopted)
        self.assertTrue(s.qc_reasons[0].startswith("Job có 1 track mắt"), s.qc_reasons)
        self.assertEqual(s.qc_reasons, [A.r1(1)])

    def test_mixed_non_eye_job_stays_qc(self):
        s = self.open(shapes=[A.skeleton("mattrai", 2), A.box(1)], tracks=[A.box_track([0, 1])], xml=two_shape_xml())
        self.assertTrue(s.qc)
        self.assertFalse(s.adopted)
        self.assertEqual(s.qc_reasons, [A.R2])

    def test_shape_on_deleted_frame_stays_qc(self):
        s = self.open(shapes=[A.skeleton("mattrai", 2)], xml=two_shape_xml(), deleted_frames=[2])
        self.assertTrue(s.qc)
        self.assertFalse(s.adopted)
        self.assertEqual(s.qc_reasons, [A.r7("2")])


class AdoptGuiCase(G.CvatGuiCase):
    def make_app(self):
        app = super().make_app()
        app.adopt_asked, app.adopt_answer = [], True
        app.ask_restore_adopted = lambda text: app.adopt_asked.append(text) or app.adopt_answer
        return app

    def serve_shapes(self, **kw):
        return self.serve(fake_job(shapes=two_shapes(), xml=two_shape_xml(), **kw))

    def save_edited(self):
        """Mở job 7 toàn shape, xoá shape mattrai ở frame 2 (còn 1 shape, có công chưa gửi) rồi lưu phiên. Trả về đường dẫn file phiên."""
        app = self.make_app()
        s = self.open_job(app)
        s.delete_shape("mattrai", 2)
        self.assertTrue(s.unsent)
        app.save_work()
        return app.state_path()


class TestGuiOpen(AdoptGuiCase):
    def test_gui_notice_after_adopt(self):
        self.serve_shapes()
        app = self.make_app()
        s = self.open_job(app)
        self.assertTrue(s.adopted)
        self.assertIn("Đã nạp 2 shape mắt của job để sửa", app.notice)
        self.assertIn(INTRO, app.notice)
        self.assertEqual(app.qc_bar.winfo_manager(), "")                      # không có thanh QC
        self.assertTrue(app.cvat_send_allowed())
        self.assertEqual(app.adopt_asked, [])

    def test_gui_qc_notice_has_reason(self):
        self.serve(fake_job(tracks=[A.eye_track("mattrai", [0])], xml=xml_of(tracks=eye_track(37, "mattrai", [0, 2]), job_size=N)))
        app = self.make_app()
        s = self.open_job(app)
        self.assertTrue(s.qc)
        self.assertIn("Chế độ QC", app.notice)
        self.assertIn("Lý do: Job có 1 track mắt", app.notice)
        self.assertTrue(app.notice.endswith(" Lý do: " + A.r1(1)), app.notice)

    def test_draw_kind_locked_to_shape(self):
        self.serve_shapes()
        app = self.make_app()
        self.open_job(app)
        self.assertEqual(app.draw_kind_choice("mattrai"), ("shape", True))
        self.assertEqual(app.draw_kind_choice("matphai"), ("shape", True))
        app.start_draw()
        self.assertEqual(app._draw_kind_var.get(), "shape")
        self.assertEqual(app._draw_kind_note.get(), "Job đã nạp từ CVAT chỉ có shape mắt.")
        self.assertIn("disabled", app._draw_radios["track"].state())

    def test_draw_kind_unchanged_for_plain_job(self):
        self.serve()
        app = self.make_app()
        self.open_job(app)
        self.assertEqual(app.draw_kind_choice("mattrai"), (app.draw_kind, False))


class TestGuiRestore(AdoptGuiCase):
    def test_reopen_after_send_does_not_offer_restore(self):
        self.serve_shapes()
        app1 = self.make_app()
        self.open_job(app1)
        app1.save_work()                                                       # phiên vừa nạp: "adopted": true, "unsent": false
        with open(app1.state_path(), encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertIs(saved["adopted"], True)
        self.assertIs(saved["unsent"], False)
        app2 = self.make_app()
        s2 = self.open_job(app2)
        self.assertEqual(app2.adopt_asked, [])
        self.assertEqual(len(s2.build_shapes()), 2)                            # giữ bản vừa nạp
        self.assertIn(INTRO, app2.notice)

    def test_restore_unsent_asks_with_counts(self):
        self.serve_shapes()
        self.save_edited()
        app = self.make_app()
        s = self.open_job(app)
        self.assertEqual(app.adopt_asked, ["Khôi phục sẽ thay 2 shape vừa nạp từ CVAT bằng bản đã lưu (1 shape, có sửa chưa gửi)."])
        self.assertEqual([(sh.label, sh.key.frame) for sh in s.build_shapes()], [("matphai", 5)])
        self.assertTrue(s.adopted)
        self.assertTrue(s.unsent)
        self.assertFalse(s.dirty)

    def test_restored_session_notice_not_adopted_text(self):
        self.serve_shapes()
        self.save_edited()
        app = self.make_app()
        self.open_job(app)
        self.assertIn("Đã khôi phục phiên làm việc: 1 shape.", app.notice)
        self.assertNotIn("Đã nạp", app.notice)

    def test_restore_warns_when_changed_on_server(self):
        job = self.serve_shapes()
        self.save_edited()
        job.version += 1                                                       # job đổi trên CVAT sau lúc lưu
        app = self.make_app()
        self.open_job(app)
        self.assertEqual(len(app.adopt_asked), 1)
        self.assertTrue(app.adopt_asked[0].endswith("(1 shape, có sửa chưa gửi)." + CHANGED), app.adopt_asked[0])

    def test_restore_does_not_warn_when_job_unchanged(self):
        self.serve_shapes()
        self.save_edited()
        app = self.make_app()
        self.open_job(app)
        self.assertNotIn("đã bị sửa trên CVAT", app.adopt_asked[0])

    def test_declined_restore_keeps_adopted_shapes_and_shows_intro(self):
        self.serve_shapes()
        self.save_edited()
        app = self.make_app()
        app.adopt_answer = False
        s = self.open_job(app)
        self.assertEqual(len(app.adopt_asked), 1)
        self.assertEqual(len(s.build_shapes()), 2)
        self.assertFalse(s.unsent)
        self.assertIn(INTRO, app.notice)
        self.assertNotIn("Đã khôi phục", app.notice)

    def test_failed_restore_keeps_adopted_shapes(self):
        self.serve_shapes()
        self.save_edited()
        app = self.make_app()
        with mock.patch("eyepin.session.Session.load_state", side_effect=ValueError("hỏng")):
            s = self.open_job(app)
        self.assertEqual(len(s.build_shapes()), 2)
        self.assertIn("Không khôi phục được phiên đã lưu: hỏng", app.notice)
        self.assertIn(INTRO, app.notice)

    def test_old_qc_session_file_is_skipped(self):
        self.serve_shapes()
        path = self.save_edited()
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh)
        del saved["adopted"]                                                   # file lưu lúc job còn ở chế độ chỉ xem
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(saved, fh)
        app = self.make_app()
        s = self.open_job(app)
        self.assertEqual(app.adopt_asked, [])
        self.assertTrue(app.notice.startswith(OLD_FILE + " "), app.notice)
        self.assertIn(INTRO, app.notice)
        self.assertEqual(len(s.build_shapes()), 2)

    def test_restore_file_with_unsent_not_true_is_silent(self):
        self.serve_shapes()
        path = self.save_edited()
        with open(path, encoding="utf-8") as fh:
            saved = json.load(fh)
        saved["unsent"] = False
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(saved, fh)
        app = self.make_app()
        s = self.open_job(app)
        self.assertEqual(app.adopt_asked, [])
        self.assertNotIn(OLD_FILE, app.notice)
        self.assertNotIn("Đã khôi phục", app.notice)
        self.assertEqual(len(s.build_shapes()), 2)

    def test_plain_session_restore_still_asks_the_old_question(self):
        self.serve()                                                           # job trống: không nạp, khôi phục như cũ
        app1 = self.make_app()
        self.open_job(app1)
        self.draw(app1)
        app1.save_work()
        app2 = self.make_app()
        asked = []
        app2.ask_restore = lambda n: asked.append(n) or True
        self.open_job(app2)
        n = len(app1.s.pins)
        self.assertEqual(asked, [n])
        self.assertEqual(app2.adopt_asked, [])
        self.assertIn(f"Đã khôi phục phiên làm việc: {n} frame ghim.", app2.notice)


if __name__ == "__main__":
    unittest.main()
