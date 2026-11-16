"""Độ nhạy chuột (Cài đặt > Workspace): nhân quãng chuột kéo, tính từ chỗ bấm, cho kéo điểm, kéo cả mắt, xoay, vẽ khung và dời ảnh.
1,0 là như cũ; nhỏ hơn 1 là chậm hơn (đỡ nhạy), lớn hơn 1 là nhanh hơn."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import test_gui as _tg  # noqa: E402

Ev = _tg.Ev


class MouseSpeedTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins

    def pinned_app(self, speed=None):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        app.root.update()
        if speed is not None:
            app.settings["workspace"]["mouse_speed"] = speed
        return app

    def drag_point_by(self, app, dx_screen, pid=14):
        """Kéo điểm pid sang phải dx_screen pixel màn hình; trả về quãng điểm dời được (px ảnh gốc) và hệ số phóng k."""
        before = app.s.pins[0][pid]
        k = app.view.k
        sx, sy = app.view.to_screen(before)
        app.on_press(Ev(sx, sy))
        app.on_motion(Ev(sx + dx_screen, sy))
        app.on_release(Ev(sx + dx_screen, sy))
        return app.s.pins[0][pid][0] - before[0], k

    # ---------- giá trị cài đặt ----------
    def test_default_is_one_and_bad_values_fall_back(self):
        app = self.pinned_app()
        self.assertAlmostEqual(app.mouse_speed(), 1.0)
        app.settings["workspace"]["mouse_speed"] = "xấu"
        self.assertAlmostEqual(app.mouse_speed(), 1.0)
        app.settings["workspace"]["mouse_speed"] = None
        self.assertAlmostEqual(app.mouse_speed(), 1.0)

    def test_value_is_clamped_to_a_usable_range(self):
        app = self.pinned_app()
        app.settings["workspace"]["mouse_speed"] = 0.0
        self.assertAlmostEqual(app.mouse_speed(), 0.1)
        app.settings["workspace"]["mouse_speed"] = -2
        self.assertAlmostEqual(app.mouse_speed(), 0.1)
        app.settings["workspace"]["mouse_speed"] = 99
        self.assertAlmostEqual(app.mouse_speed(), 3.0)

    # ---------- kéo điểm ----------
    def test_speed_one_keeps_the_old_drag(self):
        app = self.pinned_app(1.0)
        moved, k = self.drag_point_by(app, 20)
        self.assertAlmostEqual(moved, 20 / k, delta=1.0)

    def test_slower_speed_moves_the_point_less(self):
        app = self.pinned_app(0.5)
        moved, k = self.drag_point_by(app, 20)
        self.assertAlmostEqual(moved, 10 / k, delta=1.0)

    def test_faster_speed_moves_the_point_more(self):
        app = self.pinned_app(2.0)
        moved, k = self.drag_point_by(app, 10)
        self.assertAlmostEqual(moved, 20 / k, delta=1.0)

    def test_point_does_not_jump_on_the_first_motion(self):
        """Mới bấm và nhúc nhích 1 pixel thì điểm gần như đứng yên dù độ nhạy thấp (tính từ chỗ bấm, không từ con trỏ thật)."""
        app = self.pinned_app(0.2)
        moved, k = self.drag_point_by(app, 1)
        self.assertLess(abs(moved), 1.0 / k + 0.5)

    def test_release_uses_the_same_scaling_as_motion(self):
        app = self.pinned_app(0.5)
        before = app.s.pins[0][14]
        k = app.view.k
        sx, sy = app.view.to_screen(before)
        app.on_press(Ev(sx, sy))
        app.on_motion(Ev(sx + 10, sy))
        app.on_motion(Ev(sx + 30, sy))
        app.on_release(Ev(sx + 30, sy))
        self.assertAlmostEqual(app.s.pins[0][14][0] - before[0], 15 / k, delta=1.0)

    def test_scaling_stops_after_release(self):
        app = self.pinned_app(0.5)
        self.drag_point_by(app, 20)
        self.assertIsNone(app._m0)
        app.on_motion(Ev(300, 200))                       # di chuột không bấm: không làm gì
        self.assertIsNone(app.drag)

    # ---------- kéo cả mắt ----------
    def test_drag_whole_eye_is_scaled(self):
        app = self.pinned_app(0.5)
        cx = sum(app.s.pins[0][i][0] for i in range(14, 22)) / 8
        cy = sum(app.s.pins[0][i][1] for i in range(14, 22)) / 8
        before = {i: app.s.pins[0][i] for i in range(14, 22)}
        k = app.view.k
        sx, sy = app.view.to_screen((cx, cy))
        app.on_press(Ev(sx, sy))
        app.on_motion(Ev(sx + 20, sy))
        app.on_release(Ev(sx + 20, sy))
        moved = [app.s.pins[0][i][0] - before[i][0] for i in before]
        self.assertTrue(all(abs(m - moved[0]) < 1e-6 for m in moved), "cả 8 điểm phải dời cùng một quãng")
        self.assertAlmostEqual(moved[0], 10 / k, delta=1.0)

    # ---------- dời ảnh ----------
    def pan_by(self, app, dx, button_move):
        app.fit()
        app.root.update()
        x0 = app.view.x0
        k = app.view.k
        button_move(app, dx)
        return (app.manual.x0 - x0) if app.manual else 0.0, k

    @staticmethod
    def right_drag(app, dx):
        app.on_pan_start(Ev(300, 200))
        app.on_pan(Ev(300 + dx, 200))

    def test_right_drag_pan_is_scaled(self):
        app = self.pinned_app(1.0)
        full, k = self.pan_by(app, 40, self.right_drag)
        app2 = self.pinned_app(0.5)
        half, _ = self.pan_by(app2, 40, self.right_drag)
        self.assertGreater(abs(full), 1e-6)
        self.assertAlmostEqual(half / full, 0.5, delta=0.05)

    def test_right_drag_pan_with_several_motions_is_scaled(self):
        app = self.pinned_app(0.5)
        app.fit()
        app.root.update()
        x0 = app.view.x0
        k = app.view.k
        app.on_pan_start(Ev(300, 200))
        for dx in (10, 20, 30, 40):
            app.on_pan(Ev(300 + dx, 200))
        self.assertAlmostEqual(abs(app.manual.x0 - x0), 20 / k, delta=0.5)

    # ---------- hộp Cài đặt ----------
    def test_settings_window_changes_the_speed(self):
        app = self.pinned_app()
        app.show_settings()
        app.root.update()
        self.assertTrue(hasattr(app, "_mouse_speed_var"))
        app._mouse_speed_var.set(0.4)
        app._apply_mouse_speed()
        self.assertAlmostEqual(app.settings["workspace"]["mouse_speed"], 0.4)
        self.assertAlmostEqual(app.mouse_speed(), 0.4)


if __name__ == "__main__":
    unittest.main()
