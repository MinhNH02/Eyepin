"""Cửa sổ EyePin nối với CVAT (eyepin.gui_cvat) bằng server giả FakeCvat và ảnh tổng hợp.

Không chạm server thật, không mở hộp thoại thật (xác nhận, báo lỗi, chọn file đều thay bằng hàm giả). Bỏ qua nếu máy không mở được cửa sổ Tk.
"""
import gc
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")

from eyepin import cvatsync  # noqa: E402
from eyepin import shortcuts as sc  # noqa: E402
from eyepin import theme  # noqa: E402
from eyepin.cvatapi import CvatClient  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import QC_MSG  # noqa: E402
from fake_cvat import FakeCvat, FakeJob  # noqa: E402
from test_cvatsource import FACE, MATTRAI, ann_json, eye_track, xml_of  # noqa: E402
import test_tracking as T  # noqa: E402

N = 8


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


def texts(w):
    """Mọi chữ hiện trong một cửa sổ: nhãn, nút, ô văn bản, danh sách."""
    out = []
    try:
        out.append(str(w.cget("text")))
    except tk.TclError:
        pass
    if isinstance(w, tk.Text):
        out.append(w.get("1.0", "end"))
    if isinstance(w, tk.Listbox):
        out.extend(w.get(0, "end"))
    for c in w.winfo_children():
        out.extend(texts(c))
    return out


def buttons(w, text):
    found = []
    for c in w.winfo_children():
        try:
            if str(c.cget("text")) == text and hasattr(c, "invoke"):
                found.append(c)
        except tk.TclError:
            pass
        found.extend(buttons(c, text))
    return found


class CvatGuiCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.addCleanup(gc.collect)          # chạy cuối cùng: rác của cửa sổ cũ (có biến Tk) bị dọn ở luồng chính, không phải ở luồng nền
        self.home = tempfile.mkdtemp(prefix="eyepin_home_")
        os.environ["EYEPIN_HOME"] = self.home
        self.addCleanup(shutil.rmtree, self.home, True)
        self.srv = self.cl = None

    # ---- máy chủ giả và cửa sổ ----
    def client_for(self, url):
        cl = CvatClient(url, timeout=5)
        cl.poll_interval = 0.01
        self.addCleanup(cl.close)
        return cl

    def serve(self, *jobs):
        self.srv = FakeCvat(jobs or [self.empty_job()])
        self.srv.start()
        self.addCleanup(self.srv.stop)
        self.cl = self.client_for(self.srv.url)
        self.cl.login("minh", "pw")
        return self.srv.jobs[7]

    @staticmethod
    def empty_job(job_id=7, **kw):
        kw.setdefault("n_frames", N)
        return FakeJob(job_id, task_id=3, task_name="clip", xml=xml_of(job_size=N), **kw)

    @staticmethod
    def json_only_qc_job(job_id=7):
        """Job có track mắt toàn Outside: JSON của CVAT còn thấy, bản xuất XML thì không (XML rỗng)."""
        job = FakeJob(job_id, task_id=3, task_name="clip", n_frames=N, xml=xml_of(job_size=N))
        job.annotations_json = dict(ann_json(), tracks=[{"id": 5, "label_id": MATTRAI, "frame": 0, "shapes": [{"frame": 0, "outside": True}], "elements": []}])
        return job

    @staticmethod
    def qc_job(job_id=7):
        job = FakeJob(job_id, task_id=3, task_name="clip", n_frames=N, xml=xml_of(tracks=eye_track(37, "mattrai", [0, 2]), job_size=N))
        job.annotations_json = ann_json(tracks=[MATTRAI])
        return job

    def make_app(self):
        from eyepin.gui import App
        app = App(self.root)
        app.ask_restore = lambda n: False
        app.errors, app.asked = [], []
        app.show_error = lambda text: app.errors.append(text)
        app.ask_send = lambda text, warn: app.asked.append(("send", text, warn)) or True
        app.ask_clear_eyes = lambda text: app.asked.append(("clear", text, None)) or True
        app.ask_restore_job = lambda text: app.asked.append(("restore", text, None)) or True
        app.new_client = self.client_for
        self.addCleanup(self.close_app, app)
        return app

    def close_app(self, app):
        for job in (app._autosave_job, app._thumb_job, getattr(app, "_motion_job", None)):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        for w in self.root.winfo_children():
            w.destroy()

    def wait(self, app, timeout=30):
        """Chạy vòng sự kiện Tk cho tới khi việc nền xong."""
        end = time.monotonic() + timeout
        gc.disable()      # biến Tk chỉ giải phóng được ở luồng chính; vòng update() của test không phải mainloop nên luồng nền sẽ chờ cả giây cho mỗi biến
        try:
            while app.busy and time.monotonic() < end:
                self.root.update()
                time.sleep(0.01)
        finally:
            gc.enable()
        self.root.update()
        self.assertFalse(app.busy, "việc nền chưa xong")

    def open_job(self, app, job_id=7):
        app.load_cvat(self.cl, job_id)
        self.wait(app)
        self.assertIsNotNone(app.s, app.errors)
        return app.s

    def draw(self, app, labels=tuple(EYES), frame=0):
        """Vẽ mắt bằng bảng Vẽ mắt như người dùng: bấm 4 điểm rồi Apply."""
        for label in labels:
            app.go(frame)
            app.begin_draw(label, "points")
            for pid in EYES[label].pins:
                sx, sy = app.view.to_screen(T.pins_at(frame)[pid])
                app.on_press(Ev(sx, sy))
            self.assertIsNotNone(app.draft, app.notice)
            app.apply_draft()
        self.assertTrue(app.s.pins, app.notice)

    def eye_point_on_screen(self, app, f=0):
        pts = app.s.points_at(f)
        self.assertTrue(pts)
        return app.view.to_screen(pts[14])


class TestOpen(CvatGuiCase):
    def test_open_empty_job_is_normal_labeling(self):
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        self.assertIs(s.qc, False)
        self.assertIn("CVAT job #7", app.root.title())
        self.assertNotIn("QC", app.root.title())
        self.assertNotIn("QC", app.status.get())
        self.assertEqual(app.qc_bar.winfo_manager(), "")                 # chưa có thanh QC
        self.assertEqual(app.side.select(), str(app.objects_tab))        # tab Đối tượng, không nhảy sang Issues
        self.assertTrue(app.cvat_send_allowed())

    def test_open_job_with_eyes_goes_to_qc_and_scans(self):
        self.serve(self.qc_job())
        app = self.make_app()
        s = self.open_job(app)
        self.assertTrue(s.qc)
        self.assertTrue(s.findings, "Quét tự chạy khi mở job đã có nhãn mắt")
        self.assertEqual(app.issues_var.get(), f"Items: {len(s.findings)}")
        self.assertIn("QC", app.status.get())
        self.assertIn("QC", app.root.title())
        self.assertIn("CVAT job #7", app.root.title())
        self.assertEqual(app.side.select(), str(app.issues_tab))
        self.assertEqual(app.qc_bar.winfo_manager(), "place")             # nút "Xoá nhãn mắt cũ và gán lại" hiện
        self.assertFalse(app.cvat_send_allowed())
        self.assertEqual(str(app.cvat_send_btn.icon.cget("fg")), theme.MUTED)   # nút Gửi tắt (mờ đi)
        self.assertEqual(app._menu.entrycget(app._cvat_menu["send"], "state"), "disabled")
        self.assertEqual(app._menu.entrycget(app._cvat_menu["clear"], "state"), "normal")

    def test_open_job_with_eyes_only_in_json_says_the_export_shows_none(self):
        self.serve(self.json_only_qc_job())
        app = self.make_app()
        s = self.open_job(app)
        self.assertTrue(s.qc)
        self.assertEqual(s.findings, [])
        self.assertIn("toàn Outside", app.notice)                          # nói thẳng: nhãn mắt rỗng/toàn Outside, bản xuất không hiện
        self.assertIn("không hiện", app.notice)
        self.assertNotIn("quét thấy", app.notice)                          # không phải "quét thấy 0 vấn đề"
        self.assertEqual(app.qc_bar.winfo_manager(), "place")

    def test_open_job_with_eyes_in_xml_keeps_the_scan_sentence(self):
        self.serve(self.qc_job())
        app = self.make_app()
        self.open_job(app)
        self.assertIn("quét thấy", app.notice)

    def test_qc_status_lists_the_eyes_as_from_file(self):
        self.serve(self.qc_job())
        app = self.make_app()
        self.open_job(app)
        app.refresh_objects()
        self.assertIn("từ file", [app.tree.set(i, "trang") for i in app.tree.get_children()])

    def test_open_failure_is_reported_and_keeps_the_old_session(self):
        bad = FakeJob(8, task_id=3, labels=[{"id": 1, "name": "face", "type": "rectangle", "sublabels": []}])
        self.serve(self.empty_job(), bad)
        app = self.make_app()
        old = self.open_job(app)
        app.load_cvat(self.cl, 8)
        self.wait(app)
        self.assertIs(app.s, old)
        self.assertTrue(app.errors and "mattrai" in app.errors[0], app.errors)

    def test_folder_open_still_works_after_a_cvat_job(self):
        import cv2
        d = tempfile.mkdtemp(prefix="eyepin_dir_")
        self.addCleanup(shutil.rmtree, d, True)
        for t in range(6):
            cv2.imwrite(os.path.join(d, f"f{t:03d}.png"), T.render(t))
        self.serve(self.qc_job())
        app = self.make_app()
        self.open_job(app)
        self.assertTrue(app.s.qc)
        app.load(d, None)
        self.assertIsNone(app.s.cvat)
        self.assertFalse(app.s.qc)
        self.assertEqual(app.root.title(), "EyePin — gán nhãn mắt cho CVAT")
        self.assertFalse(app.cvat_send_allowed())
        self.assertEqual(app.qc_bar.winfo_manager(), "")


class TestQc(CvatGuiCase):
    def test_qc_blocks_every_edit_path(self):
        self.serve(self.qc_job())
        app = self.make_app()
        s = self.open_job(app)
        app.go(0)
        self.assertTrue(s.qc)
        shown = s.points_at(0)

        def blocked(name, fn):
            app.notice = ""
            fn()
            self.assertIn("chế độ QC", app.notice, name)
            self.assertEqual((s.pins, s.flags, s.pending), ({}, {}, {}), name)
            self.assertTrue(s.qc, name)

        blocked("start_draw", app.start_draw)
        self.assertNotIn("draw", app._dialogs)                            # bảng Vẽ mắt không mở
        blocked("begin_draw", lambda: app.begin_draw("mattrai", "points"))
        self.assertIsNone(app.pinning)
        blocked("start_pin", app.start_pin)
        blocked("start_pin hidden", lambda: app.start_pin("hidden"))
        self.assertIsNone(app.pinning)

        def four_clicks():
            for pid in EYES["mattrai"].pins:
                app.on_press(Ev(*app.view.to_screen(shown[pid])))
        blocked("bấm 4 điểm", four_clicks)
        self.assertIsNone(app.draft)

        def drag():
            sx, sy = self.eye_point_on_screen(app)
            app.on_press(Ev(sx, sy))
            app.on_motion(Ev(sx + 25, sy))
            app.on_release(Ev(sx + 25, sy))
        blocked("kéo điểm", drag)
        self.assertEqual(s.points_at(0)[14], shown[14])
        self.assertIsNone(app.drag)
        blocked("toggle_flag", lambda: app.toggle_flag("occluded"))
        blocked("toggle_flag outside", lambda: app.toggle_flag("outside"))
        blocked("toggle_pin_here", app.toggle_pin_here)
        blocked("rotate_eye", lambda: app.rotate_eye(5))
        app.clipboard = {i: p for i, p in shown.items()}
        blocked("paste", lambda: app.handlers["paste"](None))
        blocked("undo", app.undo)
        blocked("redo", app.redo)
        blocked("new_object", app.new_object)
        blocked("delete_label", app.delete_label)
        blocked("end_label", app.end_label_here)
        blocked("object_remove", app.object_remove)
        blocked("propagate", lambda: app.object_propagate(count=2))
        blocked("swap_labels", app.swap_labels)
        blocked("remove_annotations", lambda: app.remove_annotations(confirmed=True))
        blocked("run_action clear_after", lambda: app.run_action("clear_after"))
        blocked("run_action swap", lambda: app.run_action("swap"))
        self.assertEqual(len(s.layers), 1)

    def test_qc_still_allows_looking_around(self):
        self.serve(self.qc_job())
        app = self.make_app()
        s = self.open_job(app)
        app.go(3)
        self.assertEqual(app.f, 3)
        app.zoom(1.25)
        app.scan()
        app.issue_step(-1)
        self.assertTrue(s.qc)
        sx, sy = 40, 40                                                   # chỗ trống: bấm-kéo vẫn dời ảnh được
        app.on_press(Ev(sx, sy))
        self.assertTrue(app._left_pan)
        app.on_release(Ev(sx, sy))

    def test_qc_clear_confirms_with_the_list_then_leaves_qc(self):
        self.serve(self.qc_job())
        app = self.make_app()
        s = self.open_job(app)
        app.qc_clear()
        kind, text, _ = app.asked[-1]
        self.assertEqual(kind, "clear")
        self.assertIn("1 track mắt #37", text)
        self.assertIn("mattrai", text)
        self.assertIn("Gửi lên CVAT", text)                               # nói rõ CVAT chưa đổi gì cho tới lúc gửi
        self.assertFalse(s.qc)
        self.assertEqual(app.qc_bar.winfo_manager(), "")
        self.assertNotIn("QC", app.root.title())
        self.assertTrue(app.cvat_send_allowed())
        self.assertEqual(self.srv.import_formats, [])                      # chưa ghi gì lên CVAT
        self.assertEqual(app._menu.entrycget(app._cvat_menu["clear"], "state"), "disabled")

    def test_qc_clear_with_eyes_only_in_json_says_a_true_sentence(self):
        self.serve(self.json_only_qc_job())
        app = self.make_app()
        s = self.open_job(app)
        self.assertTrue(s.qc)
        app.qc_clear()
        kind, text, _ = app.asked[-1]
        self.assertEqual(kind, "clear")
        self.assertNotIn(": .", text)                                      # không còn câu rỗng "…khỏi phiên làm việc: ."
        self.assertIn("toàn Outside", text)                                # nói đúng nhãn cũ là gì và vì sao phiên không thấy
        self.assertIn("chưa có gì để bỏ", text)
        self.assertIn("thay", text)                                        # khi Gửi, nhãn mắt cũ trên CVAT bị thay
        self.assertIn("Gửi lên CVAT", text)
        self.assertFalse(s.qc)
        self.assertEqual(self.srv.import_formats, [])                      # chưa ghi gì lên CVAT

    def test_qc_clear_declined_changes_nothing_and_undo_returns_to_qc(self):
        self.serve(self.qc_job())
        app = self.make_app()
        s = self.open_job(app)
        app.ask_clear_eyes = lambda text: False
        app.qc_clear()
        self.assertTrue(s.qc)
        app.ask_clear_eyes = lambda text: True
        app.qc_clear()
        self.assertFalse(s.qc)
        app.undo()                                                        # chưa ghim gì: Ctrl+Z đưa nhãn mắt cũ về, lại ở chế độ QC
        self.assertTrue(s.qc)
        self.assertIn("QC", app.status.get())
        self.assertEqual(app.qc_bar.winfo_manager(), "place")

    def test_qc_clear_is_refused_outside_qc(self):
        self.serve()
        app = self.make_app()
        self.open_job(app)
        app.qc_clear()
        self.assertEqual(app.asked, [])
        self.assertIn("ở chế độ QC", app.notice)

    def test_restore_on_qc_job_clears_old_eyes_first(self):
        job = self.serve()
        app1 = self.make_app()
        self.open_job(app1)
        self.draw(app1)
        app1.save_work()
        pins = dict(app1.s.pins)
        # sau đó job có nhãn mắt (người khác gán) và đổi trên CVAT
        job.xml = xml_of(tracks=eye_track(37, "mattrai", [0, 2]), job_size=N)
        job.annotations_json = ann_json(tracks=[MATTRAI])
        job.version += 1
        app2 = self.make_app()
        app2.ask_restore = lambda n: False
        s2 = self.open_job(app2)
        self.assertTrue(s2.qc)                                            # không khôi phục: vẫn QC
        app3 = self.make_app()
        app3.ask_restore = lambda n: True
        s3 = self.open_job(app3)
        self.assertFalse(s3.qc)
        self.assertEqual(s3.pins, pins)
        self.assertIn("hãn mắt cũ", app3.notice)
        self.assertIn("đã bị sửa trên CVAT", app3.notice)                  # mốc đã lưu khác updated_date hiện tại
        self.assertEqual(app3.qc_bar.winfo_manager(), "")

    def test_restore_question_names_the_source_and_warns_in_qc(self):
        self.serve(self.qc_job())
        app = self.make_app()
        self.open_job(app)
        asked = []
        with mock.patch("tkinter.messagebox.askyesno", side_effect=lambda title, text, **kw: asked.append(text) or False):
            self.assertFalse(app._ask_restore(3))
        self.assertIn("job CVAT", asked[0])
        self.assertIn("bỏ nhãn mắt cũ", asked[0])
        self.assertIn("3 frame ghim", asked[0])

    def test_failed_restore_on_qc_job_goes_back_to_qc(self):
        job = self.serve()
        app1 = self.make_app()
        self.open_job(app1)
        self.draw(app1)
        app1.save_work()
        job.xml = xml_of(tracks=eye_track(37, "mattrai", [0, 2]), job_size=N)
        job.annotations_json = ann_json(tracks=[MATTRAI])
        app2 = self.make_app()
        app2.ask_restore = lambda n: True
        with mock.patch("eyepin.session.Session.load_state", side_effect=ValueError("hỏng")):
            s2 = self.open_job(app2)
        self.assertTrue(s2.qc)                                            # khôi phục lỗi: nhãn mắt cũ còn nguyên, vẫn ở QC
        self.assertIn("Không khôi phục được", app2.notice)


class TestBusy(CvatGuiCase):
    def test_background_work_locks_edits_and_shows_progress(self):
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        gate, done = threading.Event(), []
        app._run_bg(lambda: gate.wait(10) and 5, lambda res, err: done.append((res, err)), "Đang thử việc nền…")
        self.assertEqual(app.busy, "Đang thử việc nền…")
        app.refresh()
        self.assertIn("Đang thử việc nền…", app.status.get())
        app.notice = ""
        app.toggle_pin_here()
        self.assertIn("Đang thử việc nền…", app.notice)
        app.start_draw()
        self.assertNotIn("draw", app._dialogs)
        app.on_press(Ev(50, 50))
        self.assertEqual(s.pins, {})
        self.assertIsNone(app._run_bg(lambda: 1, lambda r, e: done.append("lẻn vào"), "Việc thứ hai"))   # một việc nền một lúc
        gate.set()
        self.wait(app)
        self.assertEqual(done, [(5, None)])
        self.draw(app)                                                     # xong việc nền: sửa nhãn lại được
        self.assertTrue(s.pins)

    def test_star_click_in_the_objects_panel_is_blocked_while_busy(self):
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        self.draw(app)
        app.go(3)
        before = {f: dict(p) for f, p in s.pins.items()}
        keys = {l: list(s.eye_keyframes(l)) for l in EYES}
        app.select_eye("mattrai", quiet=True)
        gate = threading.Event()
        app._run_bg(lambda: gate.wait(10), lambda res, err: None, "Đang gửi thử…")
        app.notice = ""
        app.tree.buttons("eye:mattrai")["keyframe"]._click(None)            # ★ (nút Keyframe) trên thẻ của mattrai
        self.assertEqual({f: dict(p) for f, p in s.pins.items()}, before)
        self.assertEqual({l: list(s.eye_keyframes(l)) for l in EYES}, keys)
        self.assertIn("Đang gửi thử…", app.notice)
        gate.set()
        self.wait(app)
        app.tree.buttons("eye:mattrai")["keyframe"]._click(None)
        self.assertIn(3, s.eye_keyframes("mattrai"))                          # xong việc nền: bấm ★ lại hoạt động

    def test_job_started_while_the_frame_read_fails_still_clears_busy(self):
        from eyepin.cvatapi import CvatError
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        got = []
        s._cache.clear()
        app._base_key = None
        with mock.patch.object(s.source, "read", side_effect=CvatError("Không nối được CVAT (giả).")):
            app._run_bg(lambda: 5, lambda res, err: got.append((res, err)), "Đang thử việc nền…")
            self.wait(app)
            self.assertEqual(got, [(5, None)])                                 # kết quả của luồng nền vẫn được nhận
            self.assertIsNone(app.busy)
            self.assertIn("Không nối được CVAT", app.notice)                   # đọc frame lỗi thành thông báo, không ném ra Tk
            app.go(2)                                                          # điều hướng sang frame chưa có trong bộ đệm cũng không ném
            self.assertIn("Không nối được CVAT", app.notice)
        app.notice = ""
        app.go(3)
        self.assertEqual(app.notice, "")

    def test_frame_read_needing_login_opens_the_login_box(self):
        from eyepin.cvatapi import LoginNeeded
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        pins_before = dict(s.pins)
        s._cache.clear()
        with mock.patch.object(s.source, "read", side_effect=LoginNeeded("hết hạn")):
            app.go(4)
        self.assertTrue(app._dialogs["cvat"].winfo_exists())
        self.assertIn("đăng nhập", app._cvat_ui["status"].get().lower())
        self.assertEqual(s.pins, pins_before)

    def _break_frames_after(self, app, f):
        """Bỏ ảnh đã đệm của các frame sau f (frame f vẫn hiện được) để lần bám sau phải đọc lại từ CVAT."""
        s = app.s
        s._gray.clear()
        for g in list(s._cache):
            if g != f:
                del s._cache[g]

    def _click_eye(self, app, label, frame):
        app.begin_draw(label, "points")
        for pid in EYES[label].pins:
            sx, sy = app.view.to_screen(T.pins_at(frame)[pid])
            app.on_press(Ev(sx, sy))
        self.assertIsNotNone(app.draft, app.notice)

    def test_network_error_while_pinning_is_a_notice_and_blocks_send_until_redone(self):
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        self.draw(app, frame=0)
        app.go(4)
        self._break_frames_after(app, 4)
        self._click_eye(app, "mattrai", 4)
        self.srv.fail_500 = True                                            # mất kết nối đúng lúc bám
        app.notice = ""
        app.apply_draft()                                                   # không ném ra Tk
        self.assertTrue(s.stale)
        self.assertIn("500", app.notice)
        self.assertIn(4, s.pins)
        self.srv.fail_500 = False
        app.send_cvat()
        self.wait(app)
        self.assertTrue(app.errors and "Nhãn tool tính đang cũ" in app.errors[-1], app.errors)
        self.assertEqual(self.srv.import_formats, [])
        app.apply_draft()                                                   # làm lại thao tác: bám được
        self.assertFalse(s.stale)

    def test_network_error_while_pinning_with_mouse_clicks_is_a_notice(self):
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        self.draw(app, frame=0)
        app.go(4)
        self._break_frames_after(app, 4)
        app.start_pin("full")
        self.srv.fail_500 = True
        pts = T.pins_at(4)
        for label in EYES:
            for pid in EYES[label].pins:
                sx, sy = app.view.to_screen(pts[pid])
                app.on_press(Ev(sx, sy))                                    # lần bấm thứ 8 ghim và bám: lỗi CVAT không ném ra Tk
        self.assertTrue(s.stale)
        self.assertIn("500", app.notice)
        self.assertIsNone(app.pinning)                                     # ghim đã vào phiên: thoát chế độ bấm điểm
        self.assertEqual(app.clicks, [])

    def test_login_needed_while_pinning_opens_the_login_box_and_recomputes_after(self):
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        self.draw(app, frame=0)
        app.go(4)
        self._break_frames_after(app, 4)
        self._click_eye(app, "mattrai", 4)
        self.srv.fail_401 = True
        app.apply_draft()
        self.assertTrue(s.stale)
        self.assertTrue(app._dialogs["cvat"].winfo_exists())
        self.srv.fail_401 = False
        app._cvat_ui["user"].set("minh")
        app._cvat_ui["password"].set("pw")
        app.cvat_login()
        self.wait(app)
        self.assertFalse(s.stale)                                           # đăng nhập xong thì tính lại nhãn

    def test_network_error_while_restoring_the_session_file_keeps_the_new_job_usable(self):
        from eyepin.cvatapi import CvatError
        from eyepin.session import Session
        job = self.serve()
        app1 = self.make_app()
        self.open_job(app1)
        self.draw(app1)
        app1.save_work()
        job.xml = xml_of(tracks=eye_track(37, "mattrai", [0, 2]), job_size=N)     # sau đó job có nhãn mắt: mở lại là QC
        job.annotations_json = ann_json(tracks=[MATTRAI])
        app2 = self.make_app()
        app2.ask_restore = lambda n: True
        app2.f = N + 5                                                      # frame của phiên trước, ngoài phạm vi job mới
        with mock.patch.object(Session, "recompute", side_effect=CvatError("Không nối được CVAT (giả).")):
            s2 = self.open_job(app2)
        self.assertIs(app2.s, s2)
        self.assertEqual(app2.f, 0)                                         # _show_session đã chạy
        self.assertTrue(s2.qc)                                              # khôi phục lỗi: nhãn mắt cũ trở lại, vẫn ở QC
        self.assertEqual(s2.pins, {})
        self.assertIn("Không khôi phục được", app2.notice)
        self.assertIn("Không nối được CVAT", app2.notice)

    def test_closing_while_busy_asks_first_and_keeps_confirm_close(self):
        self.serve()
        app = self.make_app()
        self.open_job(app)
        gate = threading.Event()
        app._run_bg(lambda: gate.wait(10), lambda res, err: None, "Đang gửi nhãn lên CVAT…")
        asked = []
        with mock.patch("tkinter.messagebox.askyesno", side_effect=lambda title, text, **kw: asked.append((text, kw)) or False), \
                mock.patch.object(app.root, "destroy") as destroy, mock.patch.object(app, "confirm_close", return_value=True) as cc:
            app.on_close()
            self.assertFalse(destroy.called)                                 # trả lời Không: ở lại
            self.assertIn("Đang gửi nhãn lên CVAT…", asked[0][0])
            self.assertIn("Vẫn đóng?", asked[0][0])
            self.assertEqual(asked[0][1].get("default"), "no")
        with mock.patch("tkinter.messagebox.askyesno", return_value=True), \
                mock.patch.object(app.root, "destroy") as destroy, mock.patch.object(app, "confirm_close", return_value=False) as cc:
            app.on_close()                                                  # đồng ý đóng khi bận nhưng confirm_close (chưa lưu) giữ lại
            self.assertTrue(cc.called)
            self.assertFalse(destroy.called)
        gate.set()
        self.wait(app)
        with mock.patch("tkinter.messagebox.askyesno", side_effect=AssertionError("không bận thì không hỏi")), \
                mock.patch.object(app.root, "destroy") as destroy, mock.patch.object(app, "confirm_close", return_value=True):
            app.on_close()
            self.assertTrue(destroy.called)
        app.cvat_client = None                                              # đã đóng trong on_close

    def test_background_error_reaches_done_and_unlocks(self):
        self.serve()
        app = self.make_app()
        got = []

        def boom():
            raise RuntimeError("hỏng giữa chừng")
        app._run_bg(boom, lambda res, err: got.append((res, str(err))), "Đang thử…")
        self.wait(app)
        self.assertEqual(got, [(None, "hỏng giữa chừng")])
        self.assertIsNone(app.busy)


class TestDialog(CvatGuiCase):
    def login(self, app, url=None, user="minh", password="pw"):
        app.open_cvat()
        ui = app._cvat_ui
        ui["url"].set(url or self.srv.url)
        ui["user"].set(user)
        ui["password"].set(password)
        app.cvat_login()
        self.wait(app)
        return ui

    def test_login_lists_tasks_and_jobs_and_opens(self):
        self.serve()
        app = self.make_app()
        app.open_cvat()
        self.assertEqual(app._cvat_ui["url"].get(), "http://localhost:8080")      # mặc định
        ui = self.login(app)
        self.assertIsNotNone(app.cvat_client)
        rows = ui["tasks_lb"].get(0, "end")
        self.assertEqual(len(rows), 1)
        self.assertIn("clip", rows[0])
        ui["tasks_lb"].selection_set(0)
        app.cvat_pick_task()
        self.wait(app)
        jobs = ui["jobs_lb"].get(0, "end")
        self.assertEqual(len(jobs), 1)
        self.assertIn("#7", jobs[0])
        self.assertIn(f"{N} frame", jobs[0])
        ui["jobs_lb"].selection_set(0)
        d = app._dialogs["cvat"]
        app.cvat_open_selected()
        self.wait(app)
        self.assertFalse(d.winfo_exists())
        self.assertIn("CVAT job #7", app.root.title())
        self.assertIs(app.s.source.client, app.cvat_client)

    def test_url_and_user_are_remembered_but_not_the_password_or_key(self):
        self.serve()
        self.srv.password = "mat-khau-bi-mat"
        app = self.make_app()
        ui = self.login(app, password="mat-khau-bi-mat")
        self.assertEqual(ui["password"].get(), "")
        saved = json.loads(sc.settings_path().read_text(encoding="utf-8"))
        self.assertEqual(saved["cvat"], {"url": self.srv.url, "user": "minh"})
        raw = sc.settings_path().read_text(encoding="utf-8")
        self.assertNotIn("mat-khau-bi-mat", raw)
        self.assertNotIn(self.srv.token, raw)
        self.assertEqual(sc.load_settings()["cvat"]["user"], "minh")        # lần sau mở lại có sẵn
        app2 = self.make_app()
        app2.open_cvat()
        self.assertEqual(app2._cvat_ui["user"].get(), "minh")
        self.assertEqual(app2._cvat_ui["url"].get(), self.srv.url)
        # cả file phiên cũng không chứa khoá
        s = self.open_job(app)
        self.draw(app)
        app.save_work()
        for name in os.listdir(os.path.join(self.home, "sessions")):
            with open(os.path.join(self.home, "sessions", name), encoding="utf-8") as fh:
                body = fh.read()
            self.assertNotIn(self.srv.token, body)
            self.assertNotIn("mat-khau-bi-mat", body)

    def test_wrong_password_and_foreign_host_are_refused_in_the_box(self):
        self.serve()
        logins = self.srv.calls["POST /api/auth/login"]               # lần đăng nhập của chính test
        app = self.make_app()
        ui = self.login(app, password="sai")
        self.assertIn("Sai tên đăng nhập hoặc mật khẩu", ui["status"].get())
        self.assertIsNone(app.cvat_client)
        self.assertNotIn("cvat", json.loads(sc.settings_path().read_text(encoding="utf-8")) if sc.settings_path().exists() else {})
        ui["url"].set("http://example.com")
        ui["password"].set("pw")
        app.cvat_login()
        self.assertIn("localhost", ui["status"].get())
        self.assertFalse(app.busy)
        self.assertEqual(self.srv.calls["POST /api/auth/login"], logins + 1)   # chỉ lần đăng nhập sai mật khẩu tới server

    def test_cvat_url_and_job_from_the_command_line_open_after_login(self):
        self.serve()
        app = self.make_app()
        app.open_cvat(url=self.srv.url, job=7)
        ui = app._cvat_ui
        self.assertEqual(ui["url"].get(), self.srv.url)
        ui["user"].set("minh")
        ui["password"].set("pw")
        app.cvat_login()
        self.wait(app)
        self.wait(app)                                                     # đăng nhập xong thì tự mở job 7
        self.assertIsNotNone(app.s)
        self.assertIn("CVAT job #7", app.root.title())


class TestSend(CvatGuiCase):
    def labeled_app(self, job=None):
        self.serve(*([job] if job else []))
        app = self.make_app()
        s = self.open_job(app)
        if s.qc:
            app.qc_clear()
        self.draw(app)
        return app

    def test_qc_clear_then_label_then_send(self):
        job = self.qc_job()
        app = self.labeled_app(job)
        keyframes = cvatsync.prepare(app.s, self.cl).keyframes
        self.assertGreater(keyframes, 0)
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        self.assertEqual(self.srv.import_formats, ["CVAT 1.1"])
        self.assertIn(f"{keyframes} keyframe", app.notice)
        self.assertIn("đối chiếu khớp", app.notice)
        self.assertEqual(app.errors, [])
        self.assertEqual(app.s.cvat["updated"], job.updated_date)         # mốc mới sau khi gửi
        saved = os.listdir(os.path.join(self.home, "sessions"))
        self.assertTrue(saved)                                             # đã lưu phiên kèm mốc mới
        with open(os.path.join(self.home, "sessions", saved[0]), encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["cvat"]["updated"], job.updated_date)

    def test_send_asks_first_and_warns(self):
        job = self.qc_job()
        job.annotations_json = ann_json(tracks=[MATTRAI, FACE])           # có track không phải mắt: nền là video
        app = self.labeled_app(job)
        sent = []
        app.ask_send = lambda text, warn: sent.append((text, warn)) or False
        app.send_cvat()
        self.wait(app)
        self.assertEqual(len(sent), 1)
        text, warn = sent[0]
        self.assertTrue(warn)
        self.assertIn("thay toàn bộ nhãn của job", text)
        self.assertIn("sẽ xoá", text)                                      # nhãn mắt cũ trên CVAT sẽ mất
        self.assertIn("1 track mắt", text)
        self.assertNotIn("chưa kiểm", text)                                # job nền video có tag bị prepare từ chối: không còn lời "tag có thể mất"
        self.assertEqual(self.srv.import_formats, [])                      # trả lời Không: không gửi gì
        self.assertIn("chưa gửi", app.notice.lower())

    def test_send_confirmation_defaults_to_no_with_and_without_warning(self):
        self.serve()
        app = self.make_app()
        from eyepin.gui import App
        calls = []
        with mock.patch("tkinter.messagebox.askyesno", side_effect=lambda title, text, **kw: calls.append(kw) or False):
            self.assertFalse(App.ask_send(app, "Gửi?", True))
            self.assertFalse(App.ask_send(app, "Gửi?", False))
        self.assertEqual([c["default"] for c in calls], ["no", "no"])

    def test_send_without_warning_for_a_plain_empty_job(self):
        app = self.labeled_app()
        sent = []
        app.ask_send = lambda text, warn: sent.append((text, warn)) or False
        app.send_cvat()
        self.wait(app)
        text, warn = sent[0]
        self.assertFalse(warn)
        self.assertIn("thay toàn bộ nhãn của job", text)
        self.assertNotIn("tag", text)

    def test_send_needs_something_to_send_and_a_cvat_job(self):
        self.serve()
        app = self.make_app()
        app.send_cvat()                                                    # chưa mở gì
        self.assertIn("CVAT", app.notice)
        self.open_job(app)
        app.send_cvat()                                                    # chưa ghim gì
        self.wait(app)
        self.assertIn("Chưa có nhãn mắt", app.notice)
        self.assertEqual(app.asked, [])
        self.assertEqual(self.srv.import_formats, [])

    def test_send_is_refused_in_qc(self):
        self.serve(self.qc_job())
        app = self.make_app()
        self.open_job(app)
        app.send_cvat()
        self.assertIn("chế độ QC", app.notice)
        self.assertEqual(app.asked, [])
        self.assertEqual(self.srv.calls["POST /api/jobs/7/annotations"], 0)

    def test_login_needed_reopens_login_and_keeps_the_pins(self):
        app = self.labeled_app()
        pins = dict(app.s.pins)
        self.srv.fail_401 = True
        app.send_cvat()
        self.wait(app)
        self.assertEqual(app.s.pins, pins)                                 # ghim còn nguyên
        d = app._dialogs["cvat"]
        self.assertTrue(d.winfo_exists())
        self.assertIn("đăng nhập", app._cvat_ui["status"].get().lower())
        self.assertEqual(app.errors, [])
        self.assertEqual(app.asked, [])
        # đăng nhập lại thì gửi tiếp từ đầu (kiểm lại, hỏi lại), vẫn cùng một client của phiên
        self.srv.fail_401 = False
        app._cvat_ui["user"].set("minh")
        app._cvat_ui["password"].set("pw")
        client = app.s.source.client
        app.cvat_login()
        self.wait(app)
        self.wait(app)
        self.assertIs(app.cvat_client, client)
        self.assertEqual([a[0] for a in app.asked], ["send"])
        self.assertEqual(self.srv.import_formats, ["CVAT 1.1"])
        self.assertIn("đối chiếu khớp", app.notice)

    def test_mismatch_shows_the_box_and_restore_puts_the_snapshot_back(self):
        job = self.serve()
        app = self.make_app()
        self.open_job(app)
        self.draw(app)
        before = job.xml
        self.srv.shift_on_import = 3.0                                     # server giả dời một điểm khi import
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        d = app._dialogs["send_failed"]
        self.assertTrue(d.winfo_exists())
        body = "\n".join(texts(d))
        self.assertIn("CVAT lưu khác", body)
        self.assertIn("điểm", body)                                        # danh sách chỗ lệch
        self.assertIn("lệch", body)
        self.assertIn("nhãn mắt cũ", body)                                 # ghi chú giới hạn khôi phục
        self.assertNotIn("đối chiếu khớp", app.notice)
        self.assertTrue(buttons(d, "Khôi phục job về bản trước khi gửi"))
        self.assertTrue(buttons(d, "Lưu bản chụp…"))
        # lưu bản chụp
        out = os.path.join(self.home, "snap.xml")
        with mock.patch("tkinter.filedialog.asksaveasfilename", return_value=out):
            buttons(d, "Lưu bản chụp…")[0].invoke()
        with open(out, "rb") as fh:
            self.assertEqual(fh.read(), before)
        # khôi phục
        self.srv.shift_on_import = 0.0
        buttons(d, "Khôi phục job về bản trước khi gửi")[0].invoke()
        self.wait(app)
        self.assertEqual(app.asked[-1][0], "restore")
        self.assertEqual(job.xml, before)
        self.assertEqual(app.s.cvat["updated"], job.updated_date)          # mark_synced sau restore
        self.assertFalse(cvatsync.prepare(app.s, self.cl).changed_on_server)
        self.assertIn("Đã khôi phục", app.notice)

    def test_restore_declined_does_not_touch_the_job(self):
        job = self.serve()
        app = self.make_app()
        self.open_job(app)
        self.draw(app)
        self.srv.shift_on_import = 3.0
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        shifted = job.xml
        app.ask_restore_job = lambda text: False
        buttons(app._dialogs["send_failed"], "Khôi phục job về bản trước khi gửi")[0].invoke()
        self.wait(app)
        self.assertEqual(job.xml, shifted)

    def test_no_restore_button_when_nothing_was_sent(self):
        job = self.serve()
        app = self.make_app()
        self.open_job(app)
        self.draw(app)

        def someone_edits(text, warn):                                      # job đổi trên CVAT giữa lúc kiểm và lúc gửi
            job.version += 1
            return True
        app.ask_send = someone_edits
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        d = app._dialogs["send_failed"]
        self.assertIn("Chưa gửi gì", "\n".join(texts(d)))
        self.assertEqual(buttons(d, "Khôi phục job về bản trước khi gửi"), [])
        self.assertEqual(self.srv.import_formats, [])

    def test_restore_for_job_a_after_opening_job_b_leaves_b_alone(self):
        job_a = self.serve(self.empty_job(7), self.empty_job(8))
        job_b = self.srv.jobs[8]
        app = self.make_app()
        self.open_job(app, 7)
        self.draw(app)
        before = job_a.xml
        self.srv.shift_on_import = 3.0
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        d = app._dialogs["send_failed"]
        self.srv.shift_on_import = 0.0
        s_b = self.open_job(app, 8)                                         # người dùng mở job khác trước khi bấm Khôi phục
        opened_b = s_b.cvat["updated"]
        job_b.version += 1                                                  # ai đó sửa job B trên CVAT: EyePin phải còn biết
        buttons(d, "Khôi phục job về bản trước khi gửi")[0].invoke()
        self.wait(app)
        self.assertEqual(job_a.xml, before)                                 # job A vẫn được khôi phục
        self.assertIs(app.s, s_b)
        self.assertEqual(s_b.cvat["updated"], opened_b)                     # mốc của phiên B không đổi
        self.assertTrue(cvatsync.prepare(s_b, self.cl).changed_on_server)
        self.assertIn("#7", app.notice)
        self.assertIn("đang mở", app.notice)

    def test_import_failure_reports_the_server_message(self):
        self.serve()
        app = self.make_app()
        self.open_job(app)
        self.draw(app)
        self.srv.fail_import = "file không hợp lệ"
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        self.assertIn("file không hợp lệ", "\n".join(texts(app._dialogs["send_failed"])))
        self.assertTrue(app.s.pins)                                        # nhãn trong EyePin giữ nguyên

    def test_prepare_error_is_reported(self):
        self.serve()
        app = self.make_app()
        self.open_job(app)
        self.draw(app)
        self.srv.fail_500 = True
        app.send_cvat()
        self.wait(app)
        self.assertTrue(app.errors and "500" in app.errors[0], app.errors)
        self.assertEqual(self.srv.import_formats, [])


class TestOtherSources(CvatGuiCase):
    def test_delete_frame_is_disabled_for_cvat(self):
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        app.go(2)
        app.toggle_delete_frame()
        self.assertEqual(s.deleted, set())
        self.assertIn("CVAT", app.notice)
        app.handlers["delete_frame"](None)
        self.assertEqual(s.deleted, set())

    def test_frames_deleted_in_cvat_are_read_only(self):
        self.serve(self.empty_job(deleted_frames=[3]))
        app = self.make_app()
        s = self.open_job(app)
        self.assertEqual(s.deleted, {3})
        app.go(3)
        app.toggle_delete_frame()                                          # không khôi phục được
        self.assertEqual(s.deleted, {3})
        self.assertIn("(đã xoá)", app.name_var.get())

    def test_session_file_is_keyed_by_job(self):
        self.serve(self.empty_job(7), self.empty_job(8))
        app = self.make_app()
        self.open_job(app, 7)
        p7 = app.state_path()
        self.open_job(app, 8)
        p8 = app.state_path()
        self.assertNotEqual(p7, p8)
        self.open_job(app, 7)
        self.assertEqual(app.state_path(), p7)
        self.assertEqual(os.path.dirname(p7), os.path.join(self.home, "sessions"))
        # cùng số job ở server khác (cổng khác) là phiên khác
        other = FakeCvat([self.empty_job(7)])
        other.start()
        self.addCleanup(other.stop)
        cl2 = self.client_for(other.url)
        cl2.login("minh", "pw")
        app.load_cvat(cl2, 7)
        self.wait(app)
        self.assertNotEqual(app.state_path(), p7)
        # lưu rồi mở lại cùng job thì được hỏi khôi phục và khôi phục đúng
        app.load_cvat(self.cl, 7)
        self.wait(app)
        self.draw(app)
        pins = dict(app.s.pins)
        app.save_work()
        app2 = self.make_app()
        asked = []
        app2.ask_restore = lambda n: asked.append(n) or True
        self.open_job(app2, 7)
        self.assertEqual(asked, [1])
        self.assertEqual(app2.s.pins, pins)
        app3 = self.make_app()
        asked3 = []
        app3.ask_restore = lambda n: asked3.append(n) or True
        self.open_job(app3, 8)                                             # job khác: không có phiên
        self.assertEqual(asked3, [])

    def test_frames_dir_readers_do_not_crash_for_cvat(self):
        self.serve(self.qc_job())
        app = self.make_app()
        s = self.open_job(app)
        self.assertIsNone(s.frames_dir)
        app.go(2)
        app.copy_frame_path()
        self.assertIn(s.names[2], app.root.clipboard_get())
        app.select_eye("mattrai", quiet=True)
        app.object_url()
        self.assertIn("job7", app.root.clipboard_get())
        app.show_info()
        self.assertIn("CVAT job #7", "\n".join(texts(app._dialogs["info"])))
        app.notice = ""
        with mock.patch("tkinter.filedialog.askopenfilename", return_value="x.xml"):
            app.open_xml()                                                 # nhãn lấy từ job, không nạp file lên
        self.assertIn("CVAT", app.notice)
        self.assertIsNone(app.s.frames_dir)


class TestCommandLineAndShortcuts(unittest.TestCase):
    def run_main(self, argv):
        import io
        from eyepin.__main__ import main
        buf = io.BytesIO()
        out = io.TextIOWrapper(buf, encoding="utf-8")
        with mock.patch("sys.stdout", out):
            code = main(argv)
        out.flush()
        return code, buf.getvalue().decode("utf-8")

    def test_gui_cvat_options_are_checked_before_any_window(self):
        with mock.patch("eyepin.gui.run") as run:
            code, out = self.run_main(["gui", "--cvat", "http://example.com", "--job", "3"])
            self.assertEqual(code, 2)
            self.assertIn("localhost", out)
            code, out = self.run_main(["gui", "--job", "3"])
            self.assertEqual(code, 2)
            self.assertIn("--cvat", out)
            code, out = self.run_main(["gui", "somedir", "--cvat", "http://localhost:8080"])
            self.assertEqual(code, 2)
            with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
                self.run_main(["gui", "--cvat", "http://localhost:8080", "--job", "abc"])
            run.assert_not_called()

    def test_gui_cvat_options_reach_run(self):
        with mock.patch("eyepin.gui.run", return_value=0) as run:
            code, _ = self.run_main(["gui", "--cvat", "http://localhost:8080", "--job", "7"])
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args.kwargs.get("cvat"), "http://localhost:8080")
        self.assertEqual(run.call_args.kwargs.get("job"), 7)

    def test_three_new_actions_have_no_default_key(self):
        for aid in ("open_cvat", "send_cvat", "qc_clear"):
            self.assertIn(aid, sc.BY_ID)
            self.assertEqual(sc.BY_ID[aid].keys, ())
        self.assertIn("Gửi lên CVAT", sc.guide_markdown())
        self.assertEqual(sc.DEFAULT_SETTINGS["cvat"]["url"], "http://localhost:8080")


if __name__ == "__main__":
    unittest.main()
