"""Hidden và Lock theo từng đối tượng (spec 7b.3): Hidden trên thẻ đối tượng và phím h chỉ ẩn MỘT mắt của MỘT người (như CVAT);
nút Hidden ở tab Labels và phím H vẫn ẩn theo label cho mọi người; nút Lock ở tab Labels khoá label ở mọi người."""
import os
import shutil
import sys
import tempfile
import tkinter as tk
import unittest

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")

import test_tracking as T  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.render import Look, render_main  # noqa: E402


class Ev:
    def __init__(self, x=0, y=0, widget=None):
        self.x, self.y, self.widget = x, y, widget


class ObjectHideLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = tempfile.mkdtemp(prefix="eyepin_hidelock_")
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

    def two_people(self):
        """Người 1 ghim ở frame 0; người 2 (bộ mới) ghim ở frame 0 với toạ độ dịch sang bên."""
        app = self.make_app()
        app.new_object()
        truth = T.pins_at(0)
        pts = [(x + 40, y + 60) for x, y in (truth[i] for spec in EYES.values() for i in spec.pins)]
        app.s.add_pin_free(0, pts)
        app.pinning, app.clicks = None, []
        app.refresh()
        self.assertEqual((len(app.s.layers), app.s.cur), (2, 1))
        return app

    def render(self, app, *, hidden=frozenset(), eyes=None):
        look = Look(eyes=eyes) if eyes is not None else Look()
        return render_main(app.s, 0, (960, 460), anchor=app.anchor, manual=app.view, look=look, hidden=hidden)[0].astype(int)

    # --- vẽ ---
    def test_hidden_object_draws_like_hidden_label_with_one_person(self):
        app = self.make_app()
        shown = self.render(app)
        by_object = self.render(app, hidden=frozenset({(0, "mattrai")}))
        by_label = self.render(app, eyes={"mattrai": False, "matphai": True})
        self.assertTrue(np.array_equal(by_object, by_label))
        self.assertGreater(int(np.abs(shown - by_object).sum()), 0)

    def test_hiding_person2_eye_keeps_person1_eye(self):
        app = self.two_people()
        shown = self.render(app)
        hide2 = self.render(app, hidden=frozenset({(1, "mattrai")}))
        hide1 = self.render(app, hidden=frozenset({(0, "mattrai")}))
        self.assertGreater(int(np.abs(shown - hide2).sum()), 0)
        self.assertGreater(int(np.abs(hide2 - hide1).sum()), 0)

    def test_gui_passes_hidden_objects_to_the_canvas_painter(self):
        app = self.make_app()
        app.select_eye("mattrai", quiet=True)
        app.refresh()
        n_shown = len(app.canvas.find_withtag("pt:mattrai:14"))
        self.assertGreater(n_shown, 0)
        app.handlers["hide"]()
        self.assertEqual(len(app.canvas.find_withtag("pt:mattrai:14")), 0)
        self.assertGreater(len(app.canvas.find_withtag("pt:matphai:22")), 0)

    # --- phím h và thẻ đối tượng ---
    def test_h_key_hides_only_selected_object(self):
        app = self.make_app()
        app.hover = None
        app.select_eye("mattrai", quiet=True)
        app.handlers["hide"]()
        self.assertIn((0, "mattrai"), app.hidden_objs)
        self.assertTrue(app.look.eyes["mattrai"])
        self.assertTrue(app._obj_hidden(0, "mattrai"))
        self.assertFalse(app._obj_hidden(0, "matphai"))
        app.handlers["hide"]()                                           # bấm lần nữa: hiện lại
        self.assertNotIn((0, "mattrai"), app.hidden_objs)

    def test_h_key_acts_on_the_person_of_the_selected_object(self):
        app = self.two_people()
        app.hover = None
        app.tree.selection_set("eye:mattrai@1")
        app.handlers["hide"]()
        self.assertEqual(app.hidden_objs, {(1, "mattrai")})
        app.tree.selection_set("eye:mattrai")
        self.root.update()
        app.handlers["hide"]()
        self.assertEqual(app.hidden_objs, {(0, "mattrai"), (1, "mattrai")})

    def test_h_key_prefers_eye_under_mouse(self):
        app = self.make_app()
        app.select_eye("mattrai", quiet=True)
        pts = app._current_points()
        ids = EYES["matphai"].ids
        app.hover = app.view.to_screen((sum(pts[i][0] for i in ids) / len(ids), sum(pts[i][1] for i in ids) / len(ids)))
        app.handlers["hide"]()
        self.assertEqual(app.hidden_objs, {(0, "matphai")})

    def test_h_key_without_target_only_shows_a_notice(self):
        app = self.make_app()
        app.hover = None
        app.tree.selection_remove(app.tree.selection())
        app.handlers["hide"]()
        self.assertEqual(app.hidden_objs, set())
        self.assertIn("Chọn", app.notice)

    def test_hide_all_and_labels_tab_hidden_still_use_label_visibility(self):
        app = self.two_people()
        app._toggle_label_visible("mattrai")
        self.assertFalse(app.look.eyes["mattrai"])
        self.assertEqual(app.hidden_objs, set())
        self.assertTrue(app._obj_hidden(0, "mattrai") and app._obj_hidden(1, "mattrai"))
        self.assertFalse(app._obj_hidden(1, "matphai"))
        app.hide_all_eyes()
        self.assertTrue(app._obj_hidden(1, "matphai"))
        self.assertEqual(app.hidden_objs, set())

    def test_tree_row_marks_hidden_object(self):
        app = self.two_people()
        app.hidden_objs.add((1, "mattrai"))
        app.refresh_objects()
        self.assertIn("[ẩn]", app.tree.item("eye:mattrai@1", "text"))
        self.assertNotIn("[ẩn]", app.tree.item("eye:mattrai", "text"))

    # --- tab Labels: khoá mọi người ---
    def test_labels_tab_lock_locks_every_person(self):
        app = self.two_people()
        app._toggle_label_lock("mattrai")
        for layer in (0, 1):
            app.s.select_layer(layer)
            self.assertIn("mattrai", app.locked, layer)
            self.assertNotIn("matphai", app.locked, layer)
        app._toggle_label_lock("mattrai")                                # bấm lần nữa: mở khoá mọi người
        for layer in (0, 1):
            app.s.select_layer(layer)
            self.assertNotIn("mattrai", app.locked, layer)

    def test_layerset_set_all(self):
        from eyepin.gui_objects import LayerSet
        cur = [0]
        ls = LayerSet(lambda: cur[0])
        ls.set_all("x", True, 3)
        for i in range(3):
            cur[0] = i
            self.assertIn("x", ls)
        ls.set_all("x", False, 3)
        for i in range(3):
            cur[0] = i
            self.assertNotIn("x", ls)

    def test_card_lock_and_l_key_stay_per_person(self):
        app = self.two_people()
        app.hover = None
        app.tree.selection_set("eye:mattrai@1")
        app.handlers["lock"]()
        self.assertIn("mattrai", app.locked)                             # người 2 (bộ đang chọn)
        app.s.select_layer(0)
        self.assertNotIn("mattrai", app.locked)

    # --- kéo ---
    def test_hidden_object_cannot_be_dragged(self):
        app = self.make_app()
        app.go(0)
        app.hidden_objs.add((0, "mattrai"))
        app.refresh()
        before = {i: tuple(p) for i, p in app.s.pins[0].items()}
        sx, sy = app.view.to_screen(before[14])
        app.on_press(Ev(sx, sy)); app.on_motion(Ev(sx + 25, sy)); app.on_release(Ev(sx + 25, sy))
        self.assertEqual({i: tuple(p) for i, p in app.s.pins[0].items()}, before)
        app.hidden_objs.discard((0, "mattrai"))                          # đối chứng: hiện lại thì kéo được
        app.on_press(Ev(sx, sy)); app.on_motion(Ev(sx + 25, sy)); app.on_release(Ev(sx + 25, sy))
        self.assertNotEqual({i: tuple(p) for i, p in app.s.pins[0].items()}, before)

    def test_hidden_object_has_no_rotate_handle(self):
        app = self.make_app()
        app.select_eye("mattrai", quiet=True)
        self.assertIsNotNone(app._handle_arg())
        app.hidden_objs.add((0, "mattrai"))
        self.assertIsNone(app._handle_arg())


if __name__ == "__main__":
    unittest.main()
