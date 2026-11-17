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

    # ---- cài đặt lưu trên đĩa: thang cũ, khoá mới ----
    def old_home(self, display):
        """EYEPIN_HOME tạm có settings.json chứa `display`, đặt TRƯỚC khi tạo App (đường khởi động thật)."""
        import json
        import shutil
        import tempfile
        from eyepin import shortcuts as sc
        home = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, home, True)
        prev = os.environ.get("EYEPIN_HOME")
        os.environ["EYEPIN_HOME"] = home
        self.addCleanup(lambda: os.environ.__setitem__("EYEPIN_HOME", prev) if prev else os.environ.pop("EYEPIN_HOME", None))
        path = sc.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"display": display, "workspace": {"remember_display": True}}), encoding="utf-8")
        return path

    def test_startup_with_old_scale_settings_notifies_and_does_not_write(self):
        from eyepin.gui import App
        path = self.old_home({"brightness": 30, "contrast": 1.2})
        before = path.read_bytes()
        app = App(self.root)
        self.assertEqual((app.look.brightness, app.look.contrast), (100.0, 100.0))
        self.assertEqual(path.read_bytes(), before)              # khởi động không ghi file cài đặt
        app.load(self.dir, None)                                 # mở thư mục như dòng lệnh `gui <thư mục>`
        app.root.update()
        self.assertIn("thang của CVAT", app.status.get())

    def test_old_scale_notice_survives_opening_a_folder(self):
        """Mở thư mục ngay sau khi khởi động (khôi phục phiên, --pins) ghi đè `notice`: thông báo đổi thang vẫn phải hiện một lần."""
        from eyepin.gui import App
        T = _tg.T
        self.old_home({"brightness": 30})
        app = App(self.root)
        pins = {str(f): {str(i): list(p) for i, p in T.pins_at(f).items()} for f in (0, 20)}
        app.load(self.dir, None, pins=pins)
        app.root.update()
        self.assertIn("thang của CVAT", app.status.get())
        app.go(1)                                                # thông báo giữ tới khi có thông báo mới (như mọi thông báo), không ghép lặp
        self.assertEqual(app.status.get().count("thang của CVAT"), 1)
        self.assertEqual(app._pending_notice, "")

    def test_startup_with_old_default_values_is_silent(self):
        from eyepin.gui import App
        self.old_home({"brightness": 0.0, "contrast": 1.0, "saturation": 1.0})
        app = App(self.root)
        app.load(self.dir, None)
        app.root.update()
        self.assertNotIn("thang của CVAT", app.status.get())    # không mất gì người dùng đã chỉnh: không báo

    def test_new_scale_is_saved_under_new_keys_and_read_back(self):
        """Bản EyePin cũ đọc `brightness` theo thang cộng: thang % phải lưu dưới khoá khác để bản cũ không biến ảnh thành đen trắng."""
        import json
        from unittest import mock
        from eyepin.gui import App
        path = self.old_home({"brightness_pct": 140.0})
        app = App(self.root)
        self.assertEqual(app.look.brightness, 140.0)
        app.look.contrast = 150.0
        with mock.patch.object(app.root, "destroy"):
            app.on_close()
        saved = json.loads(path.read_text(encoding="utf-8"))["display"]
        self.assertEqual((saved["brightness_pct"], saved["contrast_pct"], saved["saturation_pct"]), (140.0, 150.0, 100.0))
        self.assertFalse({"brightness", "contrast", "saturation"} & set(saved))

    def test_shortcuts_guide_lists_new_actions(self):
        from eyepin import shortcuts as sc
        self.assertEqual(sc.BY_ID["grid"].keys, ("g",))
        self.assertEqual(sc.BY_ID["image_setups"].keys, ("<Control-g>",))
        for aid in ("grid", "image_setups"):
            clash = [a.id for a in sc.ACTIONS if a.id != aid and set(a.keys) & set(sc.BY_ID[aid].keys)]
            self.assertEqual(clash, [], aid)


if __name__ == "__main__":
    unittest.main()
