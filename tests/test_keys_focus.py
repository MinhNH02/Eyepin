"""Phím tắt bị "mất": ô số frame giữ focus, Del theo con trỏ chuột như CVAT, NumLock khi gán phím, dòng nhắc sau khi xoá mắt."""
import os
import shutil
import sys
import tempfile
import tkinter as tk
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")

from eyepin import shortcuts as sc  # noqa: E402
import test_tracking as T  # noqa: E402


class Ev:
    def __init__(self, x=0, y=0, widget=None):
        self.x, self.y, self.widget = x, y, widget


class EventToSeqTests(unittest.TestCase):
    def test_numlock_is_not_alt_when_rebinding(self):
        # Tk trên Windows báo NumLock bằng bit 0x8; Alt là 0x20000
        self.assertEqual(sc.event_to_seq("d", 0x8), "d")
        self.assertEqual(sc.event_to_seq("z", 0x8 | 0x4), "<Control-z>")
        self.assertEqual(sc.event_to_seq("Delete", 0x8), "<Delete>")
        self.assertEqual(sc.event_to_seq("d", 0x20000), "<Alt-d>")


class KeyFocusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = tempfile.mkdtemp(prefix="eyepin_keys_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def make_app(self):
        from eyepin.gui import App, PIN_SEQ
        app = App(self.root)
        app.ask_restore = lambda n: False
        os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, os.environ["EYEPIN_HOME"], True)
        app.load(self.dir, None)
        truth = T.pins_at(0)
        app.go(0)
        app.start_pin()
        for _, pid in PIN_SEQ:
            app.on_press(Ev(*app.view.to_screen(truth[pid])))
        return app

    def eye_center(self, app, label):
        from eyepin.geometry import EYES
        pts = app._current_points()
        ids = EYES[label].ids
        return app.view.to_screen((sum(pts[i][0] for i in ids) / len(ids), sum(pts[i][1] for i in ids) / len(ids)))

    # --- ô số frame ---
    def spy_focus(self, app):
        calls = []
        app.canvas.focus_set = lambda: calls.append("canvas")
        return calls

    def test_click_outside_frame_entry_gives_keys_back(self):
        # bấm ô số frame rồi bấm nút / dải thời gian (không lấy focus): phím tắt phải chạy lại
        app = self.make_app()
        calls = self.spy_focus(app)
        app.entry_var.set("f0")                           # chữ đã lọt vào ô
        for w in (app.canvas, app._top_bar, app.tree):
            calls.clear()
            app._click_focus(Ev(widget=w), focused=app.entry)
            self.assertEqual(calls, ["canvas"], w)
        self.assertEqual(app.entry_var.get(), str(app.f))  # ô trở về số frame hiện tại

    def test_click_inside_frame_entry_keeps_typing(self):
        app = self.make_app()
        calls = self.spy_focus(app)
        app._click_focus(Ev(widget=app.entry), focused=app.entry)
        self.assertEqual(calls, [])

    def test_click_when_focus_elsewhere_changes_nothing(self):
        app = self.make_app()
        calls = self.spy_focus(app)
        app._click_focus(Ev(widget=app.canvas), focused=app.tree)
        app._click_focus(Ev(widget=app.canvas), focused=None)
        self.assertEqual(calls, [])

    def test_click_handler_is_installed_for_every_widget(self):
        app = self.make_app()
        self.assertIn("_click_focus", self.root.bind_all("<ButtonPress>"))

    # --- Del theo con trỏ ---
    def test_delete_removes_eye_under_mouse_without_panel_selection(self):
        app = self.make_app()
        app.tree.selection_remove(app.tree.selection())
        app.hover = self.eye_center(app, "matphai")
        app.handlers["delete"]()
        self.assertNotIn(22, app.s.pins.get(0, {}))
        self.assertIn(14, app.s.pins.get(0, {}))
        app.handlers["undo"]()
        self.assertIn(22, app.s.pins.get(0, {}))

    def test_eye_under_mouse_wins_over_panel_selection(self):
        app = self.make_app()
        app.select_eye("mattrai", quiet=True)
        app.hover = self.eye_center(app, "matphai")
        app.handlers["delete"]()
        self.assertNotIn(22, app.s.pins.get(0, {}))
        self.assertIn(14, app.s.pins.get(0, {}))

    def test_delete_uses_panel_selection_when_mouse_not_on_eye(self):
        app = self.make_app()
        app.select_eye("mattrai", quiet=True)
        app.hover = None
        app.handlers["delete"]()
        self.assertNotIn(14, app.s.pins.get(0, {}))

    def test_delete_hint_names_the_draw_key(self):
        app = self.make_app()
        app.select_eye("mattrai", quiet=True)
        app.hover = None
        app.handlers["delete"]()
        self.assertIn(f"Bấm {app.kl('draw_eye')} ", app.notice)
        self.assertNotIn("Bấm — ", app.notice)


if __name__ == "__main__":
    unittest.main()
