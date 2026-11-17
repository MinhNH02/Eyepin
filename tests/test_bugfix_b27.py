"""B27 (buglist.md, hồi quy do B11): ngưỡng "chỉ bấm, không kéo" (`DRAG_MIN_PX` = 3 px) bị tính SAU khi nhân độ nhạy chuột.

Trước khi sửa, `App.on_release` đo quãng dời bằng sự kiện đã qua `_scaled` (nhân độ nhạy, tính từ chỗ bấm). Độ nhạy 0,25 kéo con trỏ 10 px màn hình
thành 2,5 px < 3 nên bị coi là chỉ bấm: lần chỉnh tinh (thứ độ nhạy thấp sinh ra để làm) bị bỏ, điểm nhảy về chỗ cũ, không ghim, không hoàn tác.
Sau khi sửa: quãng dời đo trên toạ độ con trỏ THẬT (pixel canvas giữa lúc nhấn và lúc thả, chưa nhân độ nhạy, chưa quy ra toạ độ ảnh): dưới
`DRAG_MIN_PX` px màn hình mới coi là chỉ bấm; từ ngưỡng đó trở lên thì ghim và dời theo độ nhạy như cũ. Ảnh giả của `test_tracking`."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from eyepin.gui import DRAG_MIN_PX  # noqa: E402
import test_gui as _tg  # noqa: E402

Ev = _tg.Ev
ML = EYES["mattrai"]


class ClickThresholdUsesRealCursorTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins

    def pinned_app(self, speed=1.0):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        app.root.update()
        app.settings["workspace"]["mouse_speed"] = speed
        return app

    @staticmethod
    def point_xy(app, pid=14):
        return app.view.to_screen(app.s.pins[0][pid])

    @staticmethod
    def eye_xy(app):
        pts = app.s.pins[0]
        cx = sum(pts[i][0] for i in ML.ids) / len(ML.ids)
        cy = sum(pts[i][1] for i in ML.ids) / len(ML.ids)
        return app.view.to_screen((cx, cy))

    def drag(self, app, kind, dx, steps=1):
        """Nhấn tại điểm 14 (kind="point") hoặc thân mắt (kind="eye"), kéo sang phải dx px màn hình, thả. Trả (quãng dời px ảnh, số bước hoàn tác thêm)."""
        x, y = self.point_xy(app) if kind == "point" else self.eye_xy(app)
        before = app.s.pins[0][14]
        undo0 = len(app.s._undo)
        app.on_press(Ev(x, y))
        for i in range(1, steps + 1):
            app.on_motion(Ev(x + dx * i / steps, y))
        app._motion_draw()
        app.on_release(Ev(x + dx, y))
        after = app.s.pins[0][14]
        return math.dist(before, after), len(app.s._undo) - undo0

    # ---------- độ nhạy thấp: lần chỉnh tinh phải ghim ----------
    def test_low_speed_real_drag_is_pinned(self):
        for kind in ("point", "eye"):
            with self.subTest(kind=kind):
                app = self.pinned_app(0.25)
                k = app.view.k
                moved, undo = self.drag(app, kind, 10)               # 10 px con trỏ -> 2,5 px sau độ nhạy, dưới ngưỡng 3 nếu đo sai chỗ
                self.assertEqual(undo, 1, "kéo thật phải thêm đúng một bước hoàn tác")
                self.assertAlmostEqual(moved, 2.5 / k, delta=0.6 / k + 0.3)
                self.assertGreater(moved, 0.5 / k)

    def test_low_speed_drag_with_many_motions_is_pinned(self):
        app = self.pinned_app(0.25)
        k = app.view.k
        moved, undo = self.drag(app, "point", 10, steps=5)
        self.assertEqual(undo, 1)
        self.assertAlmostEqual(moved, 2.5 / k, delta=0.6 / k + 0.3)

    def test_slowest_speed_with_threshold_sized_cursor_drag_is_pinned(self):
        app = self.pinned_app(0.1)
        moved, undo = self.drag(app, "point", DRAG_MIN_PX + 1)
        self.assertEqual(undo, 1)
        self.assertGreater(moved, 0)

    # ---------- dưới ngưỡng trên con trỏ thật: vẫn chỉ bấm ----------
    def test_click_in_place_does_not_pin_at_any_speed(self):
        for speed in (0.1, 0.25, 1.0, 3.0):
            for kind in ("point", "eye"):
                with self.subTest(speed=speed, kind=kind):
                    app = self.pinned_app(speed)
                    moved, undo = self.drag(app, kind, 0)
                    self.assertEqual(undo, 0)
                    self.assertEqual(moved, 0)

    def test_cursor_move_below_threshold_is_click_even_when_speed_amplifies_it(self):
        app = self.pinned_app(3.0)
        moved, undo = self.drag(app, "point", DRAG_MIN_PX - 1)       # 2 px con trỏ nhân 3 = 6 px, nhưng người dùng chưa thật sự kéo
        self.assertEqual((moved, undo), (0, 0))

    def test_speed_one_threshold_on_real_cursor(self):
        for kind in ("point", "eye"):
            with self.subTest(kind=kind):
                app = self.pinned_app(1.0)
                moved, undo = self.drag(app, kind, DRAG_MIN_PX - 1)
                self.assertEqual((moved, undo), (0, 0), "dưới ngưỡng: chỉ chọn")
                moved, undo = self.drag(app, kind, DRAG_MIN_PX + 1)
                self.assertEqual(undo, 1, "từ ngưỡng trở lên: ghim như cũ")
                self.assertGreater(moved, 0)

    def test_zoomed_view_threshold_is_in_screen_pixels_not_image_pixels(self):
        """Phóng to thì 1 px màn hình là một phần nhỏ px ảnh; ngưỡng vẫn là 3 px MÀN HÌNH."""
        app = self.pinned_app(1.0)
        app.zoom(2.0, (app.view.to_screen(app.s.pins[0][14])))
        app.root.update()
        k = app.view.k
        self.assertGreater(k, 3.0)
        moved, undo = self.drag(app, "point", DRAG_MIN_PX - 1)
        self.assertEqual((moved, undo), (0, 0))
        moved, undo = self.drag(app, "point", DRAG_MIN_PX + 1)
        self.assertEqual(undo, 1)
        self.assertAlmostEqual(moved, (DRAG_MIN_PX + 1) / k, delta=1.0 / k + 0.3)

    def test_zoomed_view_and_low_speed_fine_adjustment_is_pinned(self):
        app = self.pinned_app(0.25)
        app.zoom(2.0, (app.view.to_screen(app.s.pins[0][14])))
        app.root.update()
        k = app.view.k
        moved, undo = self.drag(app, "point", 10)
        self.assertEqual(undo, 1)
        self.assertAlmostEqual(moved, 2.5 / k, delta=0.6 / k + 0.2)

    # ---------- xoay ảnh: khoảng cách không đổi khi đổi về toạ độ chưa xoay ----------
    def test_low_speed_drag_on_rotated_image_is_pinned(self):
        app = self.pinned_app(0.25)
        app.rot = 1
        app.manual = None
        app.refresh()
        w0, h0 = app.render_size
        px, py = app.view.to_screen(app.s.pins[0][14])
        u, v = h0 - py, px                                           # chiều xuôi: chưa xoay -> đã xoay (rot = 1), như test_gui
        undo0 = len(app.s._undo)
        before = app.s.pins[0][14]
        app.on_press(Ev(u, v))
        self.assertIsNotNone(app.drag)
        app.on_motion(Ev(u, v + 10))
        app._motion_draw()
        app.on_release(Ev(u, v + 10))
        self.assertEqual(len(app.s._undo), undo0 + 1)
        self.assertGreater(math.dist(before, app.s.pins[0][14]), 0.5 / app.view.k)
        app.rot = 0


if __name__ == "__main__":
    unittest.main()
