"""B01 (buglist.md): phím h ẩn mắt ĐANG HIỆN dưới con trỏ rồi báo "bấm h lần nữa để hiện"; bấm h lần nữa (con trỏ không ở trên mắt
hiện nào, kể cả khi vẫn nằm trên chỗ mắt vừa ẩn) phải HIỆN LẠI đúng mắt đó, kể cả khi nó là mắt của người thứ hai.
Cách sửa: h ẩn mắt dưới con trỏ thì chọn luôn thẻ của mắt đó (`select_eye(label, quiet=True)`), nên lần h kế tiếp rơi về đúng thẻ ấy.
h khi con trỏ không ở trên mắt nào vẫn dùng thẻ đang chọn như cũ."""
import os
import shutil
import sys
import tempfile
import tkinter as tk
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")

import test_tracking as T  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402


class Ev:
    def __init__(self, x=0, y=0, widget=None):
        self.x, self.y, self.widget = x, y, widget
        self.x_root, self.y_root = x, y


class HKeyShowsTheEyeItHidTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b01_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    # --- dựng App giả như tests/test_final_fixes.py ---
    def make_app(self):
        from eyepin.gui import App, PIN_SEQ
        os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, os.environ["EYEPIN_HOME"], True)
        app = App(self.root)
        app.ask_restore = lambda n: False
        self.addCleanup(self.close_app, app)
        app.load(self.dir, None)
        truth = T.pins_at(0)
        app.go(0)
        app.start_pin()
        for _, pid in PIN_SEQ:
            app.on_press(Ev(*app.view.to_screen(truth[pid])))
        self.assertIn(0, app.s.pins, app.notice)
        return app

    def close_app(self, app):
        for name in ("_autosave_job", "_thumb_job", "_motion_job", "_play_job"):
            job = getattr(app, name, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass

    def two_people(self):
        """Người 1 ghim ở frame 0; người 2 ghim ở frame 0 với toạ độ người 1 dịch (40, 60) px; người 2 đang được chọn."""
        app = self.make_app()
        app.new_object()
        truth = T.pins_at(0)
        app.s.add_pin_free(0, [(x + 40, y + 60) for x, y in (truth[i] for spec in EYES.values() for i in spec.pins)])
        app.pinning, app.clicks = None, []
        app.refresh()
        self.assertEqual((len(app.s.layers), app.s.cur), (2, 1))
        return app

    @staticmethod
    def center(app, label, layer=None):
        """Tâm mắt `label` (của người `layer`, mặc định người đang chọn) trên màn hình."""
        pts = app.s.layers[layer].labels[app.f].points if layer is not None else app._current_points()
        ids = EYES[label].ids
        return app.view.to_screen((sum(pts[i][0] for i in ids) / len(ids), sum(pts[i][1] for i in ids) / len(ids)))

    @staticmethod
    def empty_spot(app):
        """Một chỗ trên ảnh xa mọi mắt (góc trên trái của frame)."""
        return app.view.to_screen((5.0, 5.0))

    def press_h(self, app):
        app.handlers["hide"]()

    # --- một người ---
    def test_h_twice_with_pointer_still_on_the_hidden_eye_shows_it_again(self):
        app = self.make_app()
        app.select_eye("matphai", quiet=True)                            # thẻ đang chọn là mắt KHÁC mắt dưới con trỏ
        app.hover = self.center(app, "mattrai")
        self.press_h(app)
        self.assertEqual(app.hidden_objs, {(0, "mattrai")})
        self.assertEqual(app.tree.selection(), ("eye:mattrai",))         # thẻ của mắt vừa ẩn được chọn
        self.assertIn("Đã ẩn mattrai", app.notice)
        self.assertIn(f"bấm {app.kl('hide')} lần nữa để hiện", app.notice)
        self.assertIsNone(app._eye_under_pointer())                      # con trỏ vẫn ở đó nhưng mắt đã ẩn: không còn "dưới con trỏ"
        self.press_h(app)                                                # làm đúng lời thông báo
        self.assertEqual(app.hidden_objs, set(), app.notice)             # mattrai hiện lại, matphai không bị ẩn
        self.assertIn("Đã hiện mattrai", app.notice)

    def test_h_again_with_pointer_on_empty_spot_or_off_the_image_shows_the_same_eye(self):
        for where in ("empty", "off"):
            with self.subTest(where=where):
                app = self.make_app()
                app.select_eye("mattrai", quiet=True)
                app.hover = self.center(app, "matphai")
                self.press_h(app)
                self.assertEqual(app.hidden_objs, {(0, "matphai")})
                app.hover = self.empty_spot(app) if where == "empty" else None
                self.assertIsNone(app._eye_under_pointer())
                self.press_h(app)
                self.assertEqual(app.hidden_objs, set(), app.notice)
                self.assertEqual(app.tree.selection(), ("eye:matphai",))

    def test_card_hidden_button_after_h_targets_the_same_eye(self):
        app = self.make_app()
        app.select_eye("matphai", quiet=True)
        app.hover = self.center(app, "mattrai")
        self.press_h(app)
        sel = app.tree.selection()[0]
        app._on_object_action("hidden", sel)                             # nút Hidden trên thẻ đang chọn
        self.assertEqual(sel, "eye:mattrai")
        self.assertEqual(app.hidden_objs, set(), app.notice)

    # --- nhiều người ---
    def test_two_people_h_twice_over_person2_eye_shows_it_again(self):
        app = self.two_people()
        app.tree.selection_set("eye:matphai@1")                          # người 2 đang chọn, thẻ matphai của người 2
        self.root.update()
        self.assertEqual(app.s.cur, 1)
        app.hover = self.center(app, "mattrai", layer=1)
        self.press_h(app)
        self.assertEqual(app.hidden_objs, {(1, "mattrai")})
        self.assertEqual(app.s.cur, 1)                                   # không đổi người
        self.assertEqual(app.tree.selection(), ("eye:mattrai@1",))       # đúng thẻ của người 2
        self.assertIn(f"bấm {app.kl('hide')} lần nữa để hiện", app.notice)
        self.press_h(app)
        self.assertEqual(app.hidden_objs, set(), app.notice)
        self.assertEqual(app.s.cur, 1)
        self.assertIn("Đã hiện mattrai", app.notice)

    def test_two_people_h_twice_over_person1_eye_leaves_person2_alone(self):
        app = self.two_people()
        app.tree.selection_set("eye:matphai")                            # thẻ của người 1: chuyển sang người 1
        self.root.update()
        self.assertEqual(app.s.cur, 0)
        app.hidden_objs.add((1, "mattrai"))                              # một mắt của người 2 đang ẩn sẵn
        app.hover = self.center(app, "mattrai", layer=0)
        self.press_h(app)
        self.assertEqual(app.hidden_objs, {(0, "mattrai"), (1, "mattrai")})
        self.assertEqual((app.s.cur, app.tree.selection()), (0, ("eye:mattrai",)))
        app.hover = self.empty_spot(app)
        self.press_h(app)
        self.assertEqual(app.hidden_objs, {(1, "mattrai")}, app.notice)  # chỉ mắt vừa ẩn của người 1 hiện lại
        self.assertEqual(app.s.cur, 0)

    # --- con trỏ không ở trên mắt nào: như cũ ---
    def test_h_without_eye_under_pointer_uses_the_selected_card(self):
        for where in ("empty", "off"):
            with self.subTest(where=where):
                app = self.make_app()
                app.select_eye("matphai", quiet=True)
                app.hover = self.empty_spot(app) if where == "empty" else None
                self.press_h(app)
                self.assertEqual(app.hidden_objs, {(0, "matphai")})
                self.assertEqual(app.tree.selection(), ("eye:matphai",))
                self.press_h(app)
                self.assertEqual(app.hidden_objs, set())

    def test_h_with_a_point_row_selected_keeps_the_point_selection(self):
        app = self.make_app()
        app.tree.selection_set("pt:14")                                  # dòng điểm 14 (mattrai) trong DETAILS
        self.root.update()
        app.hover = None
        self.press_h(app)
        self.assertEqual(app.hidden_objs, {(0, "mattrai")})
        self.assertEqual(app.tree.selection(), ("pt:14",))               # không bị đổi sang thẻ mắt
        self.press_h(app)
        self.assertEqual(app.hidden_objs, set())


if __name__ == "__main__":
    unittest.main()
