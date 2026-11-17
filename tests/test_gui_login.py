"""Màn đăng nhập là cửa trước của EyePin (eyepin.gui_login): LoginScreen, FrontDoor (nối với cửa sổ chính) và Đăng xuất.

Dùng CVAT giả (tests/fake_cvat.py) và cửa sổ Tk thật nhưng ẩn; không chạm server thật, không mở hộp thoại thật. Bỏ qua nếu máy không mở được cửa sổ Tk.
Các test nhớ đăng nhập cần Windows DPAPI.
"""
import gc
import json
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatlogin  # noqa: E402
from eyepin import shortcuts as sc  # noqa: E402
from eyepin.cvatapi import CvatClient  # noqa: E402
from eyepin.gui_login import FrontDoor, LoginScreen, logout_text  # noqa: E402
import test_gui_cvat as G  # noqa: E402

win_only = unittest.skipUnless(sys.platform == "win32", "nhớ đăng nhập cần Windows DPAPI")


class LoginCase(G.CvatGuiCase):
    def setUp(self):
        super().setUp()
        self.serve()
        self.entered, self.locals = [], []
        self.settings = sc.load_settings()

    def screen(self, **kw):
        kw.setdefault("url", self.srv.url)
        kw.setdefault("settings", self.settings)
        s = LoginScreen(self.root, on_login=lambda c, u: self.entered.append((c, u, s.frame.winfo_exists())),
                        on_local=lambda: self.locals.append(1), new_client=self.client_for, **kw)
        self.addCleanup(s.destroy)
        return s

    def pump(self, cond, timeout=15):
        """Chạy vòng sự kiện Tk cho tới khi `cond()` đúng (luồng nền của màn đăng nhập trả kết quả qua `root.after`)."""
        end = time.monotonic() + timeout
        gc.disable()                                   # xem CvatGuiCase.wait: biến Tk chỉ giải phóng được ở luồng chính
        try:
            while not cond() and time.monotonic() < end:
                self.root.update()
                time.sleep(0.01)
        finally:
            gc.enable()
        self.root.update()
        self.assertTrue(cond(), "chưa xong trong thời gian chờ")

    def type_in(self, s, user="minh", password="pw", url=None):
        s.url_var.set(url or self.srv.url)
        s.user_var.set(user)
        s.password_var.set(password)

    def calls(self, what):
        return self.srv.calls[what]


class TestForm(LoginCase):
    def test_form_has_the_fields_the_remember_box_and_the_local_link(self):
        s = self.screen()
        shown = " | ".join(G.texts(s.frame))
        for part in ("EyePin", "Địa chỉ CVAT", "Tên đăng nhập", "Mật khẩu", "Đăng nhập", "Làm việc không cần CVAT"):
            self.assertIn(part, shown)
        self.assertEqual(s.url_var.get(), self.srv.url)
        self.assertEqual(s.password_var.get(), "")
        self.assertTrue(s.remember_var.get())
        self.assertIn("8 giờ", " | ".join(G.texts(s.frame)))
        self.assertEqual(s.password_entry.cget("show"), "•")

    def test_address_and_user_default_to_the_last_ones_saved(self):
        st = sc.load_settings()
        st["cvat"] = {"url": "http://localhost:9999", "user": "nguoi.cu"}
        s = self.screen(url=None, settings=st)
        self.assertEqual(s.url_var.get(), "http://localhost:9999")
        self.assertEqual(s.user_var.get(), "nguoi.cu")
        self.assertEqual(self.screen(settings=st).url_var.get(), self.srv.url)            # địa chỉ từ dòng lệnh thắng địa chỉ đã lưu

    def test_empty_fields_do_not_reach_the_server(self):
        s = self.screen()
        before = self.calls("POST /api/auth/login")
        s.user_var.set("")
        s.password_var.set("pw")
        s.submit()
        self.assertIn("Nhập tên đăng nhập và mật khẩu", s.status_var.get())
        s.user_var.set("minh")
        s.password_var.set("")
        s.submit()
        self.assertEqual(self.calls("POST /api/auth/login"), before)
        self.assertFalse(s.busy)
        self.assertEqual(self.entered, [])

    def test_wrong_password_stays_on_the_form_and_clears_the_password(self):
        s = self.screen()
        self.type_in(s, password="sai")
        s.submit()
        self.pump(lambda: not s.busy)
        self.assertIn("Sai tên đăng nhập hoặc mật khẩu", s.status_var.get())
        self.assertEqual(s.password_var.get(), "")
        self.assertEqual(s.user_var.get(), "minh")
        self.assertEqual(self.entered, [])
        self.assertTrue(s.frame.winfo_exists())

    def test_foreign_host_is_refused_before_any_request(self):
        s = self.screen()
        before = len(self.srv.requests)
        self.type_in(s, url="http://example.com")
        s.submit()
        self.assertIn("localhost", s.status_var.get())
        self.assertFalse(s.busy)
        self.assertEqual(len(self.srv.requests), before)
        self.assertEqual(s.password_var.get(), "")

    def test_double_submit_sends_one_login(self):
        s = self.screen()
        before = self.calls("POST /api/auth/login")
        self.type_in(s)
        s.submit()
        s.submit()
        self.pump(lambda: self.entered)
        self.assertEqual(self.calls("POST /api/auth/login"), before + 1)
        self.assertEqual(len(self.entered), 1)


class TestLogin(LoginCase):
    def test_success_hands_over_the_client_after_the_screen_is_gone(self):
        s = self.screen()
        self.type_in(s)
        s.submit()
        self.pump(lambda: self.entered)
        client, user, frame_alive = self.entered[0]
        self.assertEqual(user, "minh")
        self.assertEqual(client.token, "k1")
        self.assertFalse(frame_alive)                      # on_login chạy khi màn đã đóng: nơi gọi dựng cửa sổ chính trên một cửa sổ sạch
        self.assertEqual(self.locals, [])

    def test_success_remembers_address_and_user_but_never_the_password(self):
        self.srv.password = "mat-khau-bi-mat"
        s = self.screen()
        self.type_in(s, password="mat-khau-bi-mat")
        s.submit()
        self.pump(lambda: self.entered)
        self.assertEqual(s.password_var.get(), "")
        raw = sc.settings_path().read_text(encoding="utf-8")
        saved = json.loads(raw)
        self.assertEqual((saved["cvat"]["url"], saved["cvat"]["user"]), (self.srv.url, "minh"))
        self.assertNotIn("mat-khau-bi-mat", raw)
        self.assertNotIn(self.srv.token, raw)

    @win_only
    def test_remember_saves_an_encrypted_key_and_still_not_the_password(self):
        self.srv.password = "mat-khau-bi-mat"
        self.srv.token = "khoa-bi-mat-9f3c2a77d1e04b5c"
        s = self.screen()
        self.type_in(s, password="mat-khau-bi-mat")
        s.submit()
        self.pump(lambda: self.entered)
        self.assertEqual(cvatlogin.load_login(self.srv.url), ("minh", "khoa-bi-mat-9f3c2a77d1e04b5c"))
        blob = cvatlogin.login_path().read_bytes()
        for secret in ("mat-khau-bi-mat", "khoa-bi-mat-9f3c2a77d1e04b5c", "minh"):
            self.assertNotIn(secret.encode("utf-8"), blob)
        self.assertNotIn("khoa-bi-mat", sc.settings_path().read_text(encoding="utf-8"))

    @win_only
    def test_without_remember_nothing_is_saved_and_an_older_key_is_removed(self):
        s = self.screen()
        cvatlogin.save_login(self.srv.url, "nguoi.cu", "khoa-cu", 8)                      # một khoá cũ còn trên máy (do lần chạy khác để lại)
        s.remember_var.set(False)
        self.type_in(s)
        s.submit()
        self.pump(lambda: self.entered)
        self.assertFalse(cvatlogin.login_path().exists())

    @win_only
    def test_zero_hours_turns_remember_off_and_ignores_a_leftover_key(self):
        cvatlogin.save_login(self.srv.url, "minh", self.srv.token, 8)                    # khoá còn hiệu lực nhưng người dùng đã tắt việc nhớ
        st = sc.load_settings()
        st["workspace"]["remember_login_hours"] = 0
        s = self.screen(settings=st)
        self.assertFalse(s.remember_var.get())
        self.assertIn("disabled", s.remember_btn.state())
        self.assertFalse(cvatlogin.login_path().exists())                                 # file thừa bị xoá
        self.root.update()
        self.assertEqual(self.entered, [])                                                # không tự vào
        self.type_in(s)
        s.submit()
        self.pump(lambda: self.entered)
        self.assertFalse(cvatlogin.login_path().exists())

    @win_only
    def test_a_key_that_cannot_be_saved_is_reported_not_fatal(self):
        s = self.screen()
        self.type_in(s)
        with mock.patch.object(cvatlogin, "save_login", return_value=False):
            s.submit()
            self.pump(lambda: self.entered)
        self.assertIn("Không nhớ được", s.notice)
        self.assertEqual(len(self.entered), 1)


@win_only
class TestRememberedKey(LoginCase):
    def remember(self, token=None, url=None, user="minh"):
        self.assertTrue(cvatlogin.save_login(url or self.srv.url, user, token or self.srv.token, 8))

    def test_a_valid_key_skips_the_form(self):
        self.remember()
        logins, selves = self.calls("POST /api/auth/login"), self.calls("GET /api/users/self")
        s = self.screen()
        self.pump(lambda: self.entered)
        client, user, frame_alive = self.entered[0]
        self.assertEqual((user, client.token, frame_alive), ("minh", "k1", False))
        self.assertEqual(self.calls("POST /api/auth/login"), logins)              # không gõ mật khẩu, không đăng nhập
        self.assertEqual(self.calls("GET /api/users/self"), selves + 1)
        self.assertTrue(cvatlogin.login_path().exists())                          # dùng xong vẫn nhớ tới khi hết hạn

    def test_a_revoked_key_is_forgotten_and_the_form_stays(self):
        self.remember()
        self.srv.token = "k2"                                                     # CVAT đã cấp khoá khác: khoá đã nhớ không còn dùng được
        s = self.screen()
        self.pump(lambda: not s.busy)
        self.assertEqual(self.entered, [])
        self.assertFalse(cvatlogin.login_path().exists())
        self.assertIn("không còn hiệu lực", s.status_var.get())
        self.assertEqual(s.user_var.get(), "minh")
        self.assertTrue(s.frame.winfo_exists())
        self.type_in(s)                                                           # đăng nhập lại bình thường
        s.submit()
        self.pump(lambda: self.entered)
        self.assertEqual(self.entered[0][0].token, "k2")
        self.assertEqual(cvatlogin.load_login(self.srv.url), ("minh", "k2"))

    def test_server_down_shows_the_error_and_keeps_the_key(self):
        self.remember()
        self.srv.stop()
        s = self.screen()
        self.pump(lambda: not s.busy)
        self.assertEqual(self.entered, [])
        self.assertTrue(cvatlogin.login_path().exists())
        self.assertIn("Không nối được CVAT", s.status_var.get())
        self.assertIn("vẫn được giữ", s.status_var.get())
        self.assertTrue(s.frame.winfo_exists())

    def test_a_key_saved_for_another_address_is_dropped_without_any_request(self):
        self.remember(url="http://localhost:8080")
        before = len(self.srv.requests)
        s = self.screen()
        self.root.update()
        self.assertFalse(s.busy)
        self.assertEqual(len(self.srv.requests), before)
        self.assertFalse(cvatlogin.login_path().exists())
        self.assertEqual(self.entered, [])

    def test_form_is_disabled_while_the_remembered_key_is_tried(self):
        self.remember()
        s = self.screen()
        self.assertTrue(s.busy)
        self.assertIn("đăng nhập đã nhớ", s.status_var.get())
        self.assertIn("minh", s.status_var.get())
        self.pump(lambda: self.entered)


class TestLocalAndClose(LoginCase):
    def test_local_link_enters_without_a_client(self):
        s = self.screen()
        s.go_local()
        self.assertEqual((self.locals, self.entered), ([1], []))
        self.assertFalse(s.frame.winfo_exists())

    def test_local_link_works_while_a_login_is_in_flight_and_the_late_result_is_dropped(self):
        s = self.screen()
        self.type_in(s)
        s.submit()
        s.go_local()
        end = time.monotonic() + 0.6
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)
        self.assertEqual((self.locals, self.entered), ([1], []))

    def test_closing_the_screen_drops_a_late_result(self):
        s = self.screen()
        self.type_in(s)
        s.submit()
        s.destroy()
        s.destroy()                                                               # gọi hai lần không lỗi
        end = time.monotonic() + 0.6
        while time.monotonic() < end:
            self.root.update()
            time.sleep(0.01)
        self.assertEqual((self.locals, self.entered), ([], []))

    def test_root_window_is_given_back_clean_for_the_main_window(self):
        s = self.screen()
        self.assertTrue(s.frame.winfo_exists())
        s.go_local()
        self.assertEqual(self.root.winfo_children(), [])


class TestFrontDoor(G.CvatGuiCase):
    def setUp(self):
        super().setUp()
        self.serve()

    def door(self, **kw):
        kw.setdefault("url", self.srv.url)
        d = FrontDoor(self.root, new_client=self.client_for, app_factory=lambda root: self.make_app(), settings=sc.load_settings(), **kw)
        self.addCleanup(d.screen.destroy)
        return d

    def pump(self, cond, timeout=15):
        end = time.monotonic() + timeout
        gc.disable()
        try:
            while not cond() and time.monotonic() < end:
                self.root.update()
                time.sleep(0.01)
        finally:
            gc.enable()
        self.root.update()
        self.assertTrue(cond(), "chưa xong trong thời gian chờ")

    def log_in(self, d):
        d.screen.user_var.set("minh")
        d.screen.password_var.set("pw")
        d.screen.submit()
        self.pump(lambda: d.app is not None)

    def test_nothing_is_built_before_the_login(self):
        d = self.door()
        self.assertIsNone(d.app)
        self.assertEqual(self.root.title(), "EyePin — đăng nhập")

    def test_login_opens_the_main_window_with_the_task_list(self):
        d = self.door()
        self.log_in(d)
        app = d.app
        self.assertEqual(app.cvat_client.token, "k1")
        self.wait(app)
        self.assertTrue(app._cvat_dialog_alive())                              # hộp "Mở từ CVAT…" đã đăng nhập sẵn, liệt kê task
        self.assertIn("clip", " ".join(app._cvat_ui["tasks_lb"].get(0, "end")))
        self.assertIsNone(app.s)

    def test_login_with_a_job_from_the_command_line_opens_that_job(self):
        d = self.door(job=7)
        self.log_in(d)
        self.wait(d.app)
        self.assertIsNotNone(d.app.s, d.app.errors)
        self.assertIn("CVAT job #7", d.app.root.title())
        self.assertFalse(d.app._dialogs.get("cvat") and d.app._dialogs["cvat"].winfo_exists())

    def test_local_link_opens_the_empty_window_as_before(self):
        d = self.door()
        d.screen.go_local()
        self.assertIsNotNone(d.app)
        self.assertIsNone(d.app.cvat_client)
        self.assertIsNone(d.app.s)
        self.assertNotIn("cvat", d.app._dialogs)

    @win_only
    def test_remembered_key_goes_straight_to_the_main_window(self):
        cvatlogin.save_login(self.srv.url, "minh", self.srv.token, 8)
        d = self.door()
        self.pump(lambda: d.app is not None)
        self.assertEqual(d.app.cvat_client.token, "k1")
        self.wait(d.app)                                                      # hộp "Mở từ CVAT…" đang lấy danh sách task: chờ xong rồi mới dọn cửa sổ

    @win_only
    def test_a_save_failure_notice_reaches_the_main_window(self):
        d = self.door()
        with mock.patch.object(cvatlogin, "save_login", return_value=False):
            self.log_in(d)
        self.assertIn("Không nhớ được", d.app.notice)
        self.wait(d.app)


class TestLogout(G.CvatGuiCase):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.shut = []
        self.app.shutdown = lambda: self.shut.append(1)               # không đóng cửa sổ Tk dùng chung của test
        self.asked = []
        self.app.ask_logout = lambda: self.asked.append(1) or self.answer
        self.answer = True
        self.app.settings["cvat"] = {"url": "http://localhost:8080", "user": "minh"}

    def remember(self):
        self.assertTrue(cvatlogin.save_login("http://localhost:8080", "minh", "k1", 8))

    @win_only
    def test_logout_forgets_the_key_and_the_user_name_then_shuts_down(self):
        self.remember()
        self.app.logout()
        self.assertEqual(self.asked, [1])
        self.assertFalse(cvatlogin.login_path().exists())
        self.assertEqual(self.app.settings["cvat"]["user"], "")
        self.assertEqual(self.app.settings["cvat"]["url"], "http://localhost:8080")          # giữ địa chỉ
        self.assertEqual(self.shut, [1])

    @win_only
    def test_declining_changes_nothing(self):
        self.remember()
        self.answer = False
        self.app.logout()
        self.assertTrue(cvatlogin.login_path().exists())
        self.assertEqual(self.app.settings["cvat"]["user"], "minh")
        self.assertEqual(self.shut, [])

    @win_only
    def test_cancelling_at_the_unsaved_changes_question_keeps_everything(self):
        self.remember()
        self.app.confirm_close = lambda: False
        self.app.logout()
        self.assertTrue(cvatlogin.login_path().exists())
        self.assertEqual(self.app.settings["cvat"]["user"], "minh")
        self.assertEqual(self.shut, [])

    @win_only
    def test_a_busy_window_is_asked_before_logging_out(self):
        self.remember()
        self.app.busy = "Đang gửi lên CVAT…"
        with mock.patch("eyepin.gui.messagebox.askyesno", return_value=False):
            self.app.logout()
        self.assertTrue(cvatlogin.login_path().exists())
        self.assertEqual(self.shut, [])
        self.app.busy = None

    @win_only
    def test_a_key_file_that_cannot_be_deleted_is_named_and_logout_stops(self):
        self.remember()
        with mock.patch.object(cvatlogin, "forget_login", return_value=r"C:\\x\\cvat_login.bin"):
            self.app.logout()
        self.assertTrue(any("cvat_login.bin" in e for e in self.app.errors), self.app.errors)
        self.assertEqual(self.shut, [])
        self.assertEqual(self.app.settings["cvat"]["user"], "")           # làm hết phần còn lại được (xoá tên đăng nhập), chỉ không đóng cửa sổ và báo tên file

    def test_logout_works_when_there_is_nothing_remembered(self):
        self.app.logout()
        self.assertEqual(self.shut, [1])

    def test_the_question_says_what_logout_does_and_does_not_do(self):
        for part in ("khoá đăng nhập", "tên đăng nhập", "máy này", "không đăng xuất khỏi CVAT", "phiên của thư mục ảnh"):
            self.assertIn(part, logout_text(2))

    def test_menu_has_the_logout_entry(self):
        labels = [self.app._menu.entrycget(i, "label") for i in range(self.app._menu.index("end") + 1)
                  if self.app._menu.type(i) == "command"]
        self.assertIn("Đăng xuất…", labels)

    # ---------- Cài đặt (F2) > Workspace > Nhớ đăng nhập CVAT (giờ) ----------
    def test_settings_window_has_the_remember_hours_and_defaults_to_eight(self):
        self.app.show_settings()
        self.app.root.update()
        self.assertEqual(self.app._remember_hours_var.get(), 8)
        self.assertIn("Nhớ đăng nhập CVAT (giờ)", " | ".join(G.texts(self.app._dialogs["settings"])))

    def test_changing_the_hours_is_saved_and_clamped(self):
        self.app.show_settings()
        self.app.root.update()
        self.app._remember_hours_var.set(12)
        self.app._apply_remember_hours()
        self.assertEqual(self.app.settings["workspace"]["remember_login_hours"], 12)
        self.assertEqual(json.loads(sc.settings_path().read_text(encoding="utf-8"))["workspace"]["remember_login_hours"], 12)
        self.app._remember_hours_var.set(5000)
        self.app._apply_remember_hours()
        self.assertEqual(self.app.settings["workspace"]["remember_login_hours"], cvatlogin.MAX_HOURS)
        self.app._remember_hours_var.set(-4)
        self.app._apply_remember_hours()
        self.assertEqual(self.app.settings["workspace"]["remember_login_hours"], 0)

    @win_only
    def test_zero_hours_forgets_the_remembered_login(self):
        self.remember()
        self.app.show_settings()
        self.app.root.update()
        self.app._remember_hours_var.set(0)
        self.app._apply_remember_hours()
        self.assertFalse(cvatlogin.login_path().exists())

    def test_a_non_number_in_the_box_changes_nothing(self):
        self.app.show_settings()
        self.app.root.update()
        before = self.app.settings["workspace"].get("remember_login_hours")
        self.app._remember_hours_spin.delete(0, "end")
        self.app._remember_hours_spin.insert(0, "abc")                       # người dùng gõ chữ vào ô số
        self.app._apply_remember_hours()
        self.assertEqual(self.app.settings["workspace"].get("remember_login_hours"), before)

    def test_close_still_asks_then_shuts_down(self):
        app, calls = self.app, []
        app.shutdown = lambda: calls.append("shutdown")
        app.confirm_close_busy = lambda: calls.append("busy") or True
        app.confirm_close = lambda: calls.append("unsaved") or True
        app.on_close()
        self.assertEqual(calls, ["busy", "unsaved", "shutdown"])
        app.confirm_close = lambda: False
        calls.clear()
        app.on_close()
        self.assertNotIn("shutdown", calls)


if __name__ == "__main__":
    unittest.main()
