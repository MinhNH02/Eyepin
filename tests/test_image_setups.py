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

    def test_shortcuts_guide_lists_new_actions(self):
        from eyepin import shortcuts as sc
        self.assertEqual(sc.BY_ID["grid"].keys, ("g",))
        self.assertEqual(sc.BY_ID["image_setups"].keys, ("<Control-g>",))
        for aid in ("grid", "image_setups"):
            clash = [a.id for a in sc.ACTIONS if a.id != aid and set(a.keys) & set(sc.BY_ID[aid].keys)]
            self.assertEqual(clash, [], aid)


if __name__ == "__main__":
    unittest.main()
