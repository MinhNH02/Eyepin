"""B11 (buglist.md): bấm một lần không kéo (hoặc dời dưới vài px) vẫn ghim frame và thêm một bước hoàn tác rỗng.

Trước khi sửa, `on_release` luôn gọi `Session.drag_point(s)` cho nhánh kéo điểm và kéo cả mắt, kể cả khi chuột không dời: frame có nhãn do tool
bám tự thành frame ghim (nhận nguyên nhãn) và có thêm một bước hoàn tác không đổi gì (kéo điểm còn đặt điểm vào đúng chỗ bấm, lệch khỏi tâm điểm).
Sau khi sửa: nhấn rồi thả không dời (dưới `DRAG_MIN_PX` trên màn hình), hoặc toạ độ không đổi, thì KHÔNG ghim, KHÔNG thêm bước hoàn tác, chỉ chọn như
cũ; kéo thật vẫn ghim như trước. `Session.drag_points` cũng không làm gì (không ghim, không hoàn tác) khi mọi toạ độ mới trùng toạ độ đang có.
Ảnh giả của `test_tracking` (không dùng dữ liệu công ty)."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
import test_gui as _tg  # noqa: E402

Ev = _tg.Ev
ML = EYES["mattrai"]
PIN = 3                       # frame ghim duy nhất; frame 4 có nhãn do tool bám


class ClickWithoutDragTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins

    def pinned_app(self, frame=PIN):
        app, seq = self.make_app()
        self.click_pins(app, seq, PIN)
        app.go(frame)
        app.root.update()
        app.select_eye("mattrai", quiet=True)
        app.refresh()
        self.assertIn(frame, app.s.labels)
        return app

    @staticmethod
    def state(app):
        s = app.s
        return copy.deepcopy(s._snapshot()), len(s._undo), len(s._redo)

    @staticmethod
    def point_xy(app):
        return app.view.to_screen(app.s.points_at(app.f)[ML.up])

    @staticmethod
    def eye_xy(app):
        pts = app.s.points_at(app.f)
        cx = sum(pts[i][0] for i in ML.ids) / len(ML.ids)
        cy = sum(pts[i][1] for i in ML.ids) / len(ML.ids)
        return app.view.to_screen((cx, cy))

    # ---------- bấm một lần, không kéo ----------
    def test_click_on_point_without_moving_does_not_pin(self):
        for frame in (PIN, PIN + 1):
            with self.subTest(frame=frame):
                app = self.pinned_app(frame)
                before = self.state(app)
                x, y = self.point_xy(app)
                x, y = x + 4, y + 3                       # bấm hơi lệch tâm điểm (trong vòng bắt điểm), thả đúng chỗ đó
                app.on_press(Ev(x, y))
                self.assertIsNotNone(app.drag)
                app.on_release(Ev(x, y))
                self.assertIsNone(app.drag)
                self.assertEqual(self.state(app), before, "không ghim, không thêm bước hoàn tác, điểm không nhảy theo chỗ bấm")
                self.assertEqual(app._selected()[0], "mattrai")

    def test_click_on_eye_body_without_moving_does_not_pin(self):
        for frame in (PIN, PIN + 1):
            with self.subTest(frame=frame):
                app = self.pinned_app(frame)
                before = self.state(app)
                x, y = self.eye_xy(app)
                app.on_press(Ev(x, y))
                self.assertIsNotNone(app.drag_eye)
                app.on_release(Ev(x, y))
                self.assertIsNone(app.drag_eye)
                self.assertEqual(self.state(app), before)

    def test_tiny_motion_below_threshold_does_not_pin(self):
        for kind in ("point", "eye"):
            with self.subTest(kind=kind):
                app = self.pinned_app(PIN + 1)
                before = self.state(app)
                x, y = self.point_xy(app) if kind == "point" else self.eye_xy(app)
                app.on_press(Ev(x, y))
                app.on_motion(Ev(x + 1, y))
                app._motion_draw()
                app.on_release(Ev(x + 1, y))
                self.assertEqual(self.state(app), before)
                self.assertIsNone(app.drag)
                self.assertIsNone(app.drag_eye)

    # ---------- kéo thật vẫn như cũ ----------
    def test_real_drag_still_pins_with_one_undo_step(self):
        for kind in ("point", "eye"):
            with self.subTest(kind=kind):
                app = self.pinned_app(PIN + 1)
                undo0 = len(app.s._undo)
                x, y = self.point_xy(app) if kind == "point" else self.eye_xy(app)
                p0 = app.s.points_at(PIN + 1)[ML.up]
                app.on_press(Ev(x, y))
                app.on_motion(Ev(x + 15, y + 6))
                app.on_release(Ev(x + 15, y + 6))
                self.assertIn(PIN + 1, app.s.pins)
                self.assertEqual(len(app.s._undo), undo0 + 1)
                self.assertGreater(app.s.pins[PIN + 1][ML.up][0], p0[0] + 1)

    # ---------- Session.drag_points ----------
    def test_session_drag_points_with_same_coordinates_is_noop(self):
        app = self.pinned_app(PIN + 1)
        s = app.s
        before = self.state(app)
        pts = dict(s.labels[PIN + 1].points)
        self.assertFalse(s.drag_points(PIN + 1, {ML.up: pts[ML.up]}))
        self.assertFalse(s.drag_points(PIN + 1, {i: pts[i] for i in ML.ids}))
        self.assertEqual(self.state(app), before)
        self.assertNotIn(PIN + 1, s.pins)
        # frame đã ghim, cùng toạ độ: cũng không thêm bước hoàn tác
        before = self.state(app)
        self.assertFalse(s.drag_points(PIN, {ML.up: s.pins[PIN][ML.up]}))
        self.assertEqual(self.state(app), before)

    def test_session_drag_points_with_different_coordinates_still_works(self):
        app = self.pinned_app(PIN + 1)
        s = app.s
        undo0 = len(s._undo)
        x, y = s.labels[PIN + 1].points[ML.up]
        self.assertTrue(s.drag_points(PIN + 1, {ML.up: (x + 3, y)}))
        self.assertIn(PIN + 1, s.pins)
        self.assertEqual(len(s._undo), undo0 + 1)


if __name__ == "__main__":
    unittest.main()
