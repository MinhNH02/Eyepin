"""Hộp Image setups (như CVAT): lưới, độ sáng, tương phản, bão hoà, gamma; phím g (lưới) và Ctrl+G (mở hộp)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import test_gui as _tg  # noqa: E402

Ev = _tg.Ev


class ImageSetupsTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins

    def pinned_app(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        app.root.update()
        return app

    def test_g_toggles_grid_and_redraws_the_base(self):
        app = self.pinned_app()
        before = app._base_raw.copy()
        app.handlers["grid"](None)
        app.root.update()
        self.assertTrue(app.look.grid)
        self.assertFalse(np.array_equal(before, app._base_raw))
        app.handlers["grid"](None)
        self.assertFalse(app.look.grid)

    def test_apply_setup_clamps(self):
        app = self.pinned_app()
        app._apply_setup("grid_size", 0)
        self.assertEqual(app.look.grid_size, 1)
        app._apply_setup("gamma", 5)
        self.assertAlmostEqual(app.look.gamma, 2.6)
        app._apply_setup("brightness", 150)
        self.assertEqual(app.look.brightness, 150.0)
        app._apply_setup("grid_color", "Không có")
        self.assertEqual(app.look.grid_color, "White")

    def test_reset_color_keeps_grid(self):
        app = self.pinned_app()
        app._apply_setup("grid", True)
        app._apply_setup("brightness", 150)
        app._apply_setup("gamma", 2.0)
        app.reset_adjust()
        self.assertEqual((app.look.brightness, app.look.contrast, app.look.saturation, app.look.gamma), (100.0, 100.0, 100.0, 1.0))
        self.assertTrue(app.look.grid)
        self.assertEqual(app._setup_vars["brightness"].get(), 100.0)

    def test_box_opens_and_vars_follow_look(self):
        app = self.pinned_app()
        app.show_image_setups()
        app.root.update()
        self.assertEqual(app._setup_vars["grid_size"].get(), app.look.grid_size)
        app.toggle_grid()
        self.assertEqual(bool(app._setup_vars["grid"].get()), app.look.grid)
        self.assertIn("Lưới", app.notice)

    def test_hover_readout_under_rotation(self):
        """Ảnh đang xoay 90°: chữ đo là toạ độ ảnh, không phải toạ độ màn hình."""
        import re
        app = self.pinned_app()
        app.rotate(1)
        app.root.update()
        ux, uy = app.view.to_screen(app.s.points_at(app.f)[16])
        w0, h0 = app.render_size
        app.on_hover(Ev(h0 - uy, ux))                            # ngược với App._unrot khi xoay 1 lần
        text = app.measure_var.get()
        m = re.search(r"tới điểm 16: (\d+),(\d) px", text)
        self.assertIsNotNone(m, text)
        # to_screen làm tròn tới nửa pixel màn hình mỗi trục: sai tới √2·0,5/k pixel ảnh, cộng 0,05 cho chữ số lẻ đã làm tròn
        self.assertLessEqual(float(f"{m.group(1)}.{m.group(2)}"), 0.71 / app.view.k + 0.05)

    def test_readout_follows_a_drag_with_coordinates_only(self):
        app = self.pinned_app()
        sx, sy = app.view.to_screen(app.s.pins[0][14])
        app.on_press(Ev(sx, sy))
        app.on_motion(Ev(sx + 20, sy))
        text = app.measure_var.get()
        app.on_release(Ev(sx + 20, sy))
        x = float(text.split("·")[0].split()[1].replace(",", "."))
        self.assertAlmostEqual(x, app.view.to_frame(sx + 20, sy)[0], delta=0.01)
        self.assertNotIn("tới điểm", text)

    def test_hover_readout_without_labels(self):
        app, _ = self.make_app()
        app.go(5)
        app.root.update()
        app.on_hover(Ev(10, 10))
        self.assertNotIn("tới điểm", app.measure_var.get())

    def test_guides_drawn_only_when_on_and_eye_selected(self):
        from eyepin.render import Look, render_main
        app = self.pinned_app()
        size = (480, 320)

        def img(**kw):
            return render_main(app.s, 0, size, look=Look(axis_guide=kw.pop("guide")), **kw)[0]

        off = img(guide=False, selected="mattrai")
        self.assertFalse(np.array_equal(off, img(guide=True, selected="mattrai")))
        self.assertTrue(np.array_equal(img(guide=False, selected=None), img(guide=True, selected=None)))

    def test_shortcuts_guide_lists_new_actions(self):
        from eyepin import shortcuts as sc
        self.assertEqual(sc.BY_ID["grid"].keys, ("g",))
        self.assertEqual(sc.BY_ID["image_setups"].keys, ("<Control-g>",))
        for aid in ("grid", "image_setups"):
            clash = [a.id for a in sc.ACTIONS if a.id != aid and set(a.keys) & set(sc.BY_ID[aid].keys)]
            self.assertEqual(clash, [], aid)


if __name__ == "__main__":
    unittest.main()
