"""Nút Đăng xuất đầy đủ (design/2026-11-16-cvat-home-design.md mục 4.6b, 9b): cờ "chưa gửi" của phiên, và App.logout kiểm công chưa gửi rồi dọn dữ liệu CVAT trên máy.

Dùng CVAT giả (tests/fake_cvat.py) và cửa sổ Tk thật nhưng ẩn; không chạm server thật, không mở hộp thoại thật. Bỏ qua nếu máy không mở được cửa sổ Tk.
"""
import gc
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatlogin  # noqa: E402
from eyepin import shortcuts as sc  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_gui_cvat as G  # noqa: E402
import test_tracking as T  # noqa: E402

win_only = unittest.skipUnless(sys.platform == "win32", "nhớ đăng nhập cần Windows DPAPI")


class UnsentFlagTests(unittest.TestCase):
    """`Session.unsent`: có thay đổi nhãn chưa gửi lên CVAT."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_unsent_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def session(self, cvat=True):
        s = Session(self.dir)
        if cvat:
            s.cvat = {"job": 7, "updated": "u"}
        return s

    def pin(self, s, frame=0):
        truth = T.pins_at(frame)
        for label, spec in EYES.items():
            s.add_pin(frame, label, {i: truth[i] for i in spec.pins})

    def test_a_fresh_session_has_nothing_unsent(self):
        self.assertFalse(self.session().unsent)

    def test_any_edit_makes_it_unsent(self):
        s = self.session()
        self.pin(s)
        self.assertTrue(s.unsent)

    def test_saving_to_the_session_file_does_not_mean_sent(self):
        s = self.session()
        self.pin(s)
        path = os.path.join(tempfile.mkdtemp(prefix="eyepin_unsent_f_"), "p.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(path), True)
        s.save_state(path)
        self.assertFalse(s.dirty)
        self.assertTrue(s.unsent)

    def test_undo_and_redo_are_edits_too(self):
        s = self.session()
        self.pin(s)
        s.unsent = False                                    # như sau một lần gửi thành công
        self.assertTrue(s.undo())
        self.assertTrue(s.unsent)
        s.unsent = False
        self.assertTrue(s.redo())
        self.assertTrue(s.unsent)

    def test_state_has_the_flag_for_cvat_jobs_only(self):
        s = self.session()
        self.pin(s)
        self.assertIs(s.state()["unsent"], True)
        s.unsent = False
        self.assertIs(s.state()["unsent"], False)
        folder = self.session(cvat=False)
        self.pin(folder)
        self.assertNotIn("unsent", folder.state())

    def test_flag_survives_a_round_trip_through_the_file(self):
        s = self.session()
        self.pin(s)
        path = os.path.join(tempfile.mkdtemp(prefix="eyepin_unsent_f_"), "p.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(path), True)
        for value in (True, False):
            s.unsent = value
            s.save_state(path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            again = self.session()
            again.load_state(data)
            self.assertIs(again.unsent, value)

    def test_an_old_file_without_the_flag_is_unsent_when_it_has_pins(self):
        s = self.session()
        self.pin(s)
        data = s.state()
        del data["unsent"]
        again = self.session()
        again.load_state(data)
        self.assertTrue(again.unsent)
        empty = self.session().state()
        del empty["unsent"]
        again = self.session()
        again.load_state(empty)
        self.assertFalse(again.unsent)

    def test_a_failed_load_leaves_the_flag_as_it_was(self):
        s = self.session()
        self.pin(s)
        data = s.state()
        s.unsent = False
        with mock.patch.object(Session, "_load_state", side_effect=ValueError("hỏng")):
            with self.assertRaises(ValueError):
                s.load_state(data)
        self.assertFalse(s.unsent)


class LogoutCase(G.CvatGuiCase):
    """Cửa sổ có job CVAT giả; hộp hỏi thay bằng hàm giả ghi lại câu hỏi và trả lời theo `self.answers`."""

    def setUp(self):
        super().setUp()
        self.sessions = Path(self.home) / "sessions"
        self.shut = []
        self.asked = []
        self.answers = {}

    def logout_app(self, open_job=True, draw=False, job=None):
        self.serve(*([job] if job else []))
        app = self.make_app()
        app.back_to_login = lambda: self.shut.append(1)                  # đã rời job sau khi dọn; không dựng lại màn đăng nhập trên cửa sổ Tk dùng chung của test
        app.ask_logout = lambda: self.asked.append(("generic",)) or self.answers.get("generic", True)
        app.ask_logout_open_job = lambda job_id, pins: self.asked.append(("open", job_id, pins)) or self.answers.get("open", "discard")
        app.ask_logout_others = lambda items: self.asked.append(("others", [(u.job, u.pins, u.known) for u in items])) or self.answers.get("others", True)
        if open_job:
            self.open_job(app)
            if draw:
                self.draw(app)
        app.settings["cvat"] = {"url": self.srv.url, "user": "minh"}
        return app

    def other_session(self, name, job, unsent=True, frames=(0, 2)):
        self.sessions.mkdir(parents=True, exist_ok=True)
        data = {"version": 2, "frames": 8, "cur": 0, "layers": [{"pins": {str(f): {"14": [1.0, 2.0]} for f in frames}}],
                "cvat": {"job": job, "updated": "t"}}
        if unsent is not None:
            data["unsent"] = unsent
        path = self.sessions / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def folder_session(self):
        self.sessions.mkdir(parents=True, exist_ok=True)
        path = self.sessions / "thu_muc_anh.json"
        path.write_text(json.dumps({"version": 2, "frames": 8, "cur": 0, "layers": [{"pins": {"0": {"14": [1.0, 2.0]}}}]}), encoding="utf-8")
        return path

    def session_files(self):
        return sorted(p.name for p in self.sessions.glob("*.json")) if self.sessions.exists() else []

    def requests(self):
        return [(r["method"], r["path"]) for r in self.srv.requests]


class TestSentFlag(LogoutCase):
    def test_opening_a_job_is_not_unsent_and_drawing_is(self):
        app = self.logout_app()
        self.assertFalse(app.s.unsent)
        self.draw(app)
        self.assertTrue(app.s.unsent)

    def test_a_successful_send_clears_it_and_the_session_file_says_so(self):
        app = self.logout_app(draw=True)
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        self.assertEqual(self.srv.import_formats, ["CVAT 1.1"])
        self.assertFalse(app.s.unsent)
        files = self.session_files()
        self.assertEqual(len(files), 1)
        with open(self.sessions / files[0], encoding="utf-8") as fh:
            self.assertIs(json.load(fh)["unsent"], False)

    def test_a_send_that_does_not_match_stays_unsent(self):
        app = self.logout_app(draw=True)
        self.srv.shift_on_import = 3.0                                    # CVAT lưu lệch: đối chiếu báo không khớp
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        self.assertTrue(app.s.unsent)

    def test_a_declined_or_failed_send_stays_unsent(self):
        app = self.logout_app(draw=True)
        app.ask_send = lambda text, warn: False
        app.send_cvat()
        self.wait(app)
        self.assertTrue(app.s.unsent)
        app.ask_send = lambda text, warn: True
        self.srv.fail_import = "file không hợp lệ"
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        self.assertTrue(app.s.unsent)

    def test_restoring_a_saved_session_follows_the_saved_flag(self):
        app = self.logout_app(draw=True)
        app.save_work()
        app2 = self.make_app()
        app2.ask_restore = lambda n: True
        self.open_job(app2)
        self.assertTrue(app2.s.unsent)                                     # file ghi chưa gửi
        app2.s.unsent = False
        app2.s.dirty = True
        app2.save_work()
        app3 = self.make_app()
        app3.ask_restore = lambda n: True
        self.open_job(app3)
        self.assertFalse(app3.s.unsent)                                    # file ghi đã gửi: không hỏi thừa khi Đăng xuất


class TestLogoutFlow(LogoutCase):
    def remember(self):
        self.assertTrue(cvatlogin.save_login(self.srv.url, "minh", self.srv.token, 8))

    def settle(self, app):
        self.wait(app)
        self.wait(app)

    # ---------- không có gì chưa gửi ----------
    @win_only
    def test_clean_logout_wipes_the_key_the_cvat_sessions_and_the_user_but_nothing_else(self):
        app = self.logout_app()
        sent = self.other_session("sent.json", 6, unsent=False)
        folder = self.folder_session()
        self.remember()
        app.logout()
        self.assertEqual(self.asked, [("generic",)])                       # không có gì chưa gửi: chỉ một hộp xác nhận
        self.assertFalse(sent.exists())
        self.assertTrue(folder.exists())                                   # phiên thư mục ảnh không bị xoá
        self.assertFalse(cvatlogin.login_path().exists())
        self.assertEqual(app.settings["cvat"], {"url": self.srv.url, "user": ""})
        self.assertEqual(json.loads(sc.settings_path().read_text(encoding="utf-8"))["cvat"]["user"], "")
        self.assertEqual(self.shut, [1])

    def test_declining_the_plain_question_changes_nothing(self):
        app = self.logout_app()
        sent = self.other_session("sent.json", 6, unsent=False)
        self.answers["generic"] = False
        app.logout()
        self.assertTrue(sent.exists())
        self.assertEqual(app.settings["cvat"]["user"], "minh")
        self.assertEqual(self.shut, [])

    def test_logout_never_calls_the_server_logout(self):
        app = self.logout_app()
        app.logout()
        self.assertEqual(self.shut, [1])
        self.assertNotIn("/api/auth/logout", [path for _, path in self.requests()])

    def test_a_cvat_job_never_gets_the_save_and_exit_question(self):
        app = self.logout_app()
        app.confirm_close = lambda **kw: self.asked.append(("close",)) or True
        app.logout()
        self.assertNotIn(("close",), self.asked)                           # bản lưu sắp bị xoá nên hỏi "lưu rồi thoát" là vô nghĩa

    def test_an_open_folder_session_is_asked_like_closing_the_window(self):
        app = self.logout_app(open_job=False)
        sent = self.other_session("sent.json", 6, unsent=False)
        from types import SimpleNamespace
        app.s = SimpleNamespace(cvat=None, unsent=False, dirty=True, layers=[])
        app.confirm_close = lambda **kw: self.asked.append(("close",)) or False
        app.logout()
        self.assertEqual(self.asked, [("close",)])
        self.assertTrue(sent.exists())
        self.assertEqual(self.shut, [])
        app.s = None

    def test_autosave_is_stopped_before_wiping_so_it_cannot_rewrite_a_deleted_file(self):
        app = self.logout_app()
        self.assertIsNotNone(app._autosave_job)
        app.logout()
        self.assertIsNone(app._autosave_job)

    # ---------- job đang mở còn công chưa gửi ----------
    def test_open_job_with_unsent_work_asks_send_discard_or_cancel_and_cancel_keeps_everything(self):
        app = self.logout_app(draw=True)
        app.save_work()
        mine = list(self.sessions.glob("*.json"))
        self.assertEqual(len(mine), 1)
        self.answers["open"] = "cancel"
        app.logout()
        pins = sum(len(L.pins) for L in app.s.layers)
        self.assertEqual(self.asked, [("open", 7, pins)])
        self.assertTrue(mine[0].exists())
        self.assertEqual(app.settings["cvat"]["user"], "minh")
        self.assertEqual(self.shut, [])

    def test_discarding_the_open_job_wipes_its_own_session_without_asking_again_about_it(self):
        app = self.logout_app(draw=True)
        app.save_work()
        mine = next(self.sessions.glob("*.json"))
        self.answers["open"] = "discard"
        app.logout()
        self.assertEqual([a[0] for a in self.asked], ["open"])             # file phiên của chính job này không bị hỏi lại ở danh sách "job khác"
        self.assertFalse(mine.exists())
        self.assertEqual(self.shut, [1])

    def test_send_then_logout_continues_only_after_the_send_matched(self):
        app = self.logout_app(draw=True)
        app.save_work()
        self.answers["open"] = "send"
        app.logout()
        self.assertEqual(self.shut, [])                                    # chưa xong: gửi chạy nền
        self.settle(app)
        self.assertEqual(self.srv.import_formats, ["CVAT 1.1"])
        self.assertEqual(self.shut, [1])
        self.assertEqual(self.session_files(), [])                         # xoá cả file phiên vừa lưu sau khi gửi
        self.assertEqual([a[0] for a in self.asked], ["open"])             # đã hỏi rồi thì không hỏi xác nhận chung nữa
        self.assertNotIn("/api/auth/logout", [path for _, path in self.requests()])

    def test_send_then_logout_with_the_real_teardown_inside_the_background_poll(self):
        """`_logout_after_send` chạy trong `poll` của `_run_bg`: teardown thật huỷ cửa sổ ngay trong đó, không được để lỗi hay hẹn giờ mồ côi."""
        app = self.logout_app(draw=True)
        del app.back_to_login                                              # dùng back_to_login thật
        made = []
        app.to_login = lambda r: made.append(r)                            # không dựng màn đăng nhập thật trên cửa sổ dùng chung
        app.save_work()
        self.answers["open"] = "send"
        errors = []
        self.root.report_callback_exception = lambda *a: errors.append(a)
        try:
            app.logout()
            end = time.monotonic() + 30
            gc.disable()
            try:
                while not made and time.monotonic() < end:
                    self.root.update()
                    time.sleep(0.01)
                for _ in range(10):
                    self.root.update()
                    time.sleep(0.01)
            finally:
                gc.enable()
        finally:
            del self.root.report_callback_exception
        self.assertEqual(errors, [])
        self.assertEqual(self.srv.import_formats, ["CVAT 1.1"])
        self.assertEqual(len(made), 1)
        self.assertIsNone(app.s)
        self.assertIsNone(app.cvat_client)
        self.assertEqual(self.root.winfo_children(), [])
        self.assertEqual(self.root.tk.splitlist(self.root.tk.call("after", "info")), ())
        self.assertEqual(self.session_files(), [])
        for seq in self.root.bind():
            self.root.unbind(seq)

    def test_a_failed_send_stops_the_logout_and_keeps_everything(self):
        app = self.logout_app(draw=True)
        app.save_work()
        self.srv.fail_import = "file không hợp lệ"
        self.answers["open"] = "send"
        with mock.patch.object(app, "show_send_failure"):
            app.logout()
            self.settle(app)
        self.assertEqual(self.shut, [])
        self.assertEqual(len(self.session_files()), 1)
        self.assertTrue(app.s.unsent)
        self.assertIn("Đăng xuất dừng", app.notice)

    def test_declining_the_send_box_stops_the_logout(self):
        app = self.logout_app(draw=True)
        app.save_work()
        app.ask_send = lambda text, warn: False
        self.answers["open"] = "send"
        app.logout()
        self.settle(app)
        self.assertEqual(self.shut, [])
        self.assertEqual(len(self.session_files()), 1)
        self.assertEqual(self.srv.import_formats, [])
        self.assertIn("Đăng xuất dừng", app.notice)

    def test_nothing_sendable_stops_the_logout_instead_of_hanging(self):
        app = self.logout_app(draw=True)
        while app.s.undo():
            pass
        self.assertTrue(app.s.unsent)
        self.assertFalse(any(L.pins for L in app.s.layers))
        self.answers["open"] = "send"
        app.logout()
        self.assertEqual(self.shut, [])
        self.assertIn("Đăng xuất dừng", app.notice)
        self.assertIsNone(app._after_send)                                 # không để lại việc chờ: lần gửi tay sau này không kéo theo đăng xuất

    def test_closing_the_relogin_box_forgets_the_waiting_logout(self):
        app = self.logout_app(draw=True)
        self.answers["open"] = "send"
        self.srv.fail_401 = True                                           # khoá hết hạn đúng lúc gửi
        app.logout()
        self.settle(app)
        self.assertTrue(app._cvat_dialog_alive())                          # hộp đăng nhập lại hiện ra
        self.assertIsNotNone(app._after_send)
        app._dialogs["cvat"].destroy()                                     # người dùng đóng hộp mà không đăng nhập
        self.root.update()
        self.assertIsNone(app._after_send)
        self.assertEqual(self.shut, [])

    # ---------- job khác còn công chưa gửi ----------
    def test_other_unsent_jobs_are_listed_and_cancel_keeps_everything(self):
        app = self.logout_app()
        a = self.other_session("a_job5.json", 5, unsent=True, frames=(0, 3))
        b = self.other_session("b_job9.json", 9, unsent=None, frames=(1, 2, 3))       # file cũ chưa có cờ
        self.other_session("c_job6.json", 6, unsent=False)
        self.answers["others"] = False
        app.logout()
        self.assertEqual(self.asked, [("others", [(5, 2, True), (9, 3, False)])])
        self.assertTrue(a.exists() and b.exists())
        self.assertEqual(self.shut, [])

    def test_confirming_the_list_wipes_them_too(self):
        app = self.logout_app()
        self.other_session("a_job5.json", 5, unsent=True)
        self.other_session("c_job6.json", 6, unsent=False)
        app.logout()
        self.assertEqual([a[0] for a in self.asked], ["others"])           # có danh sách chưa gửi thì hộp danh sách thay hộp xác nhận chung
        self.assertEqual(self.session_files(), [])
        self.assertEqual(self.shut, [1])

    def test_the_open_jobs_older_unsent_file_counts_as_another_when_the_open_job_is_clean(self):
        app = self.logout_app()
        self.sessions.mkdir(parents=True, exist_ok=True)
        old = Path(app.state_path())
        old.write_text(json.dumps({"version": 2, "frames": 8, "layers": [{"pins": {"0": {"14": [1.0, 2.0]}}}], "unsent": True,
                                   "cvat": {"job": 7, "updated": "t"}}), encoding="utf-8")        # lần trước chưa gửi, lần này không khôi phục
        self.answers["others"] = False
        app.logout()
        self.assertEqual(self.asked, [("others", [(7, 1, True)])])
        self.assertTrue(old.exists())

    def test_open_job_unsent_and_other_jobs_unsent_asks_both(self):
        app = self.logout_app(draw=True)
        self.other_session("a_job5.json", 5, unsent=True)
        self.answers["open"] = "discard"
        app.logout()
        self.assertEqual([a[0] for a in self.asked], ["open", "others"])
        self.assertEqual(self.session_files(), [])
        self.assertEqual(self.shut, [1])

    # ---------- xoá lỗi ----------
    def test_a_locked_file_is_named_and_the_window_stays_open(self):
        app = self.logout_app()
        keep = self.other_session("locked.json", 6, unsent=False)
        gone = self.other_session("free.json", 8, unsent=False)
        real = Path.unlink

        def locked(path, *args, **kw):
            if path.name == "locked.json":
                raise PermissionError("đang bị khoá")
            return real(path, *args, **kw)
        with mock.patch.object(Path, "unlink", locked):
            app.logout()
        self.assertEqual(self.shut, [])
        self.assertTrue(any("locked.json" in e for e in app.errors), app.errors)
        self.assertTrue(any("Chưa dọn sạch" in e for e in app.errors), app.errors)
        self.assertTrue(keep.exists())
        self.assertFalse(gone.exists())                                    # phần còn lại vẫn làm
        self.assertEqual(app.settings["cvat"]["user"], "")
        self.assertIsNotNone(app._autosave_job)                            # còn làm việc tiếp được: tự lưu bật lại

    # ---------- nút trên thanh trên ----------
    def test_the_button_is_the_rightmost_icon_of_the_top_bar_and_runs_logout(self):
        app = self.logout_app()
        btn = app.logout_btn
        self.assertEqual(btn.name, "logout")
        right = [w for w in app._top_bar.pack_slaves() if w.pack_info()["side"] == "right"]
        self.assertIs(right[0], btn)
        self.assertIs(right[1], app.quit_btn)                              # nút Thoát EyePin riêng, ngay cạnh Đăng xuất
        self.answers["generic"] = False
        btn._click(None)
        self.assertEqual(self.asked, [("generic",)])

class TestRealQuestions(LogoutCase):
    """Các hàm hỏi thật (không bị thay bằng hàm giả như ở TestLogoutFlow): tham số hợp lệ, mặc định an toàn, và đổi đúng câu trả lời."""

    def setUp(self):
        super().setUp()
        self.serve()
        self.app = self.make_app()

    def test_each_question_defaults_to_the_safe_answer(self):
        from eyepin.gui import App
        yn, ync = [], []
        with mock.patch("tkinter.messagebox.askyesno", side_effect=lambda title, text, **kw: yn.append((text, kw)) or False), \
                mock.patch("tkinter.messagebox.askyesnocancel", side_effect=lambda title, text, **kw: ync.append((text, kw)) or None):
            self.assertFalse(App.ask_logout(self.app))
            self.assertFalse(App.ask_logout_others(self.app, [cvatlogin.UnsentSession(Path("a.json"), 5, 2, True)]))
            self.assertEqual(App.ask_logout_open_job(self.app, 7, 3), "cancel")
        self.assertEqual([kw["default"] for _, kw in yn], ["no", "no"])
        self.assertEqual([kw["default"] for _, kw in ync], ["cancel"])
        self.assertIn("Job #5: 2 frame ghim", yn[1][0])
        self.assertIn("Job #7 có 3 frame ghim CHƯA gửi", ync[0][0])

    def test_the_three_answers_of_the_open_job_question_map_to_send_discard_cancel(self):
        from eyepin.gui import App
        for raw, want in ((True, "send"), (False, "discard"), (None, "cancel")):
            with mock.patch("tkinter.messagebox.askyesnocancel", return_value=raw):
                self.assertEqual(App.ask_logout_open_job(self.app, 7, 3), want)

    def test_the_plain_question_counts_the_cvat_sessions_on_disk(self):
        from eyepin.gui import App
        self.other_session("a.json", 5, unsent=False)
        self.other_session("b.json", 6, unsent=False)
        texts = []
        with mock.patch("tkinter.messagebox.askyesno", side_effect=lambda title, text, **kw: texts.append(text) or True):
            self.assertTrue(App.ask_logout(self.app))
        self.assertIn("2 phiên làm việc đã lưu của job CVAT", texts[0])


class TestDialogTexts(unittest.TestCase):
    def test_plain_question_says_what_goes_and_what_stays(self):
        from eyepin.gui_login import logout_text
        text = logout_text(3)
        for part in ("khoá đăng nhập", "tên đăng nhập", "3 phiên làm việc", "không đăng xuất khỏi CVAT", "máy này", "phiên của thư mục ảnh", "file bạn tự lưu"):
            self.assertIn(part, text)
        self.assertNotIn("0 phiên", logout_text(0))
        self.assertIn("không có phiên", logout_text(0))

    def test_open_job_question_names_the_job_and_the_three_answers(self):
        from eyepin.gui_login import open_job_text
        text = open_job_text(7, 12)
        for part in ("Job #7", "12 frame ghim", "CHƯA gửi", "Có:", "Không:", "Huỷ:"):
            self.assertIn(part, text)

    def test_others_question_lists_jobs_and_says_which_are_unclear(self):
        from eyepin.cvatlogin import UnsentSession
        from eyepin.gui_login import others_text
        items = [UnsentSession(Path("a.json"), 5, 2, True), UnsentSession(Path("b.json"), 9, 3, False), UnsentSession(Path("c.json"), None, 1, True)]
        text = others_text(items)
        self.assertIn("Job #5: 2 frame ghim", text)
        self.assertIn("Job #9: 3 frame ghim (phiên cũ, chưa rõ đã gửi hay chưa)", text)
        self.assertIn("Job ?: 1 frame ghim", text)
        many = others_text([UnsentSession(Path(f"{i}.json"), i, 1, True) for i in range(14)])
        self.assertIn("và 4 job nữa", many)


if __name__ == "__main__":
    unittest.main()
