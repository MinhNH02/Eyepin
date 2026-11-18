"""Giao diện cho mắt kiểu shape (design/2026-11-18-shape-design.md mục 6.2, 6.3): vẽ, nhớ kiểu, xoá, dán, và câu báo cho lệnh shape không có.
Ảnh giả của `test_tracking`. Bỏ qua nếu máy không mở được cửa sổ Tkinter."""
import os
import shutil
import sys
import tempfile
import tkinter as tk
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")      # không đụng cài đặt thật của người dùng

from eyepin.geometry import EYES  # noqa: E402
import test_tracking as T  # noqa: E402


def four(label: str, t: int) -> dict:
    truth = T.pins_at(t)
    return {i: truth[i] for i in EYES[label].pins}


class ShapeGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = tempfile.mkdtemp(prefix="eyepin_shape_gui_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def make_app(self):
        from eyepin.gui import App
        app = App(self.root)
        app.ask_restore = lambda n: False                  # test không bật hộp hỏi khôi phục
        os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, os.environ["EYEPIN_HOME"], True)
        app.load(self.dir, None)
        return app

    def draw(self, app, frame, label="mattrai", kind="shape"):
        """Vẽ một mắt ở `frame` đúng như người dùng: begin_draw, bản nháp 4 điểm, Apply."""
        app.go(frame)
        app.begin_draw(label, "points", kind=kind)
        app.draft = {"label": label, "four": four(label, frame)}
        app.apply_draft()

    @staticmethod
    def snap(s) -> dict:
        return {"pins": {f: dict(p) for f, p in s.pins.items()}, "flags": {f: dict(fl) for f, fl in s.flags.items()},
                "kind": dict(s.kind), "undo": len(s._undo)}

    def test_draw_shape_stays_on_one_frame(self):
        app = self.make_app()
        self.draw(app, 3)
        self.assertEqual(sorted(app.s.labels), [3])
        self.assertIn("shape mattrai", app.notice)
        self.assertIn("không bám", app.notice)

    def test_kind_is_remembered_and_locked(self):
        app = self.make_app()
        self.assertEqual(app.draw_kind_choice("mattrai"), ("track", False))
        self.draw(app, 3)
        self.assertEqual(app.draw_kind_choice("matphai"), ("shape", False))
        self.assertEqual(app.draw_kind_choice("mattrai"), ("shape", True))
        self.assertEqual(self.make_app().draw_kind_choice("matphai"), ("track", False))

    def test_delete_removes_only_this_frame(self):
        app = self.make_app()
        self.draw(app, 3)
        self.draw(app, 5)
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.delete_label()
        self.assertFalse(app.s.has_shape("mattrai", 3))
        self.assertTrue(app.s.has_shape("mattrai", 5))
        self.assertIn("shape mattrai", app.notice)
        self.assertIn("frame 3", app.notice)
        app.undo()
        self.assertTrue(app.s.has_shape("mattrai", 3))
        self.assertTrue(app.s.has_shape("mattrai", 5))

    def test_k_and_whole_eye_outside_show_a_message(self):
        app = self.make_app()
        self.draw(app, 3)
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        before = self.snap(app.s)
        for act in (app.toggle_pin_here, lambda: app.toggle_flag("outside"), app.end_label_here):
            app.notice = ""
            act()
            self.assertNotEqual(app.notice, "")
            self.assertEqual(self.snap(app.s), before)

    def test_flag_on_frame_without_shape_says_no_label(self):
        """Mắt shape đang chọn nhưng frame này không có shape của nó: cờ cả mắt và cờ một điểm không đổi gì, và thông báo nói đúng điều đó."""
        app = self.make_app()
        self.draw(app, 3)
        app.go(6)                                                  # frame không có shape của mattrai
        app.select_eye("mattrai", quiet=True)
        before = self.snap(app.s)
        app.notice = ""
        app.toggle_flag("occluded")                                # cả mắt
        self.assertIn("chưa có nhãn của mattrai", app.notice)
        self.assertNotIn("bỏ", app.notice)
        self.assertEqual(self.snap(app.s), before)
        app.tree.selection_set("pt:14")                            # một điểm (dòng điểm 14 trong DETAILS)
        self.assertEqual(app._selected(), ("mattrai", 14))
        app.notice = ""
        app.toggle_flag("occluded")
        self.assertIn("chưa có nhãn của mattrai", app.notice)
        self.assertNotIn("bỏ", app.notice)
        self.assertEqual(self.snap(app.s), before)

    def test_delete_on_frame_without_shape_shows_message(self):
        app = self.make_app()
        self.draw(app, 3)
        app.go(6)
        app.select_eye("mattrai", quiet=True)
        before = self.snap(app.s)
        app.notice = ""
        app.delete_label()
        self.assertIn("không có shape", app.notice)
        self.assertEqual(self.snap(app.s), before)

    def test_paste_shape_to_another_frame(self):
        app = self.make_app()
        self.draw(app, 3)
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.object_copy()
        app.go(8)
        app.paste_pins()
        self.assertTrue(app.s.has_shape("mattrai", 8))
        self.assertIn("thành shape mới", app.notice)

    def test_track_drawing_unchanged(self):
        app = self.make_app()
        self.draw(app, 3, kind="track")
        self.assertEqual(app.s.eye_kind("mattrai"), "track")
        self.assertTrue({3, 4, 5, T.N - 1} <= set(app.s.labels))
        self.assertEqual(app.notice, "Đã ghim mattrai ở frame 3 (track): tool bám mắt này sang các frame sau.")

    def test_draw_dialog_has_working_shape_radio_and_locks(self):
        app = self.make_app()
        self.draw(app, 3)
        app.go(3)                                                    # mattrai đã có shape ở frame này: bảng chọn sẵn matphai
        app.start_draw()
        d = app._dialogs["draw"]
        self.addCleanup(d.destroy)
        self.assertEqual(app._draw_kind_var.get(), "shape")          # matphai chưa có nhãn: theo kiểu vẽ gần nhất, không khoá
        radios = {w.cget("value"): w for w in d.winfo_children() if w.winfo_class() == "TRadiobutton"}
        self.assertNotIn("disabled", radios["shape"].state())
        self.assertNotIn("disabled", radios["track"].state())
        self.assertEqual(app._draw_kind_note.get(), "")
        app._draw_label_var.set(app._draw_label_values[0])           # đổi sang mattrai (đã là shape): khoá
        app._draw_label_changed()
        self.assertEqual(app._draw_kind_var.get(), "shape")
        self.assertIn("disabled", radios["track"].state())
        self.assertEqual(app._draw_kind_note.get(), "Mắt này đang là shape. Muốn vẽ kiểu khác: xoá nhãn của nó hoặc thêm người mới (+).")


if __name__ == "__main__":
    unittest.main()
