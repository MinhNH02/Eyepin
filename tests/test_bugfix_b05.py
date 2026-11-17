"""B05 (buglist.md): đang giữ chuột kéo (tay cầm đổi kích thước, tay cầm xoay, một điểm, cả mắt) mà đổi frame bằng phím mũi tên.

Trước khi sửa, trạng thái kéo (`drag`, `drag_eye`, `drag_rot`, `drag_resize`) gắn với frame và nhãn lúc bấm nhưng không ai xoá nó khi frame đổi:
- tới frame chưa có nhãn của mắt đó: lần vẽ lại tính phần xem trước trên frame mới (`_resize_override`/`_rot_override` -> `None.items()`,
  `_eye_shift` -> `None[...]`), `go()` ném AttributeError/TypeError và mọi lần vẽ, kéo, thả sau đó ném lại: kẹt;
- tới frame có nhãn: thả chuột ghi phần kéo vào frame MỚI (ghim ngầm một frame người dùng không kéo).

Hành vi chọn sau khi sửa: HUỶ kéo (như CVAT), không thả: không ghim, không thêm bước hoàn tác, nhãn và khung nhìn như trước khi bấm, con trỏ
chuột không đổi; sự kiện kéo/thả chuột tới sau đó không làm gì. Cùng nguyên nhân và cùng cách xử lý: Space (phát) đổi frame giữa lúc kéo,
lệnh sửa nhãn bằng phím giữa lúc kéo (Ctrl+Z, Del, Ctrl+N đổi sang người mới), mở thư mục / job khác; kéo khung vẽ mắt dở cũng huỷ khi đổi frame.
Ảnh giả của `test_tracking` (không dùng dữ liệu công ty)."""
import copy
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from eyepin.render import resize_handles  # noqa: E402
import test_gui as _tg  # noqa: E402

Ev = _tg.Ev
ML = EYES["mattrai"]
PIN = 3            # frame ghim duy nhất: frame 2 chưa có nhãn (trước frame ghim đầu), frame 4 có nhãn do tool bám
KINDS = ("resize", "rotate", "point", "eye")


class DragCancelTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins

    # ---------- dựng và đo ----------
    def pinned_app(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, PIN)
        app.go(PIN)
        app.root.update()
        app.select_eye("mattrai", quiet=True)
        app.refresh()
        self.assertIsNone(app.manual, "trước khi bấm: khung nhìn tự động")
        self.assertIn(PIN + 1, app.s.labels)
        self.assertNotIn(PIN - 1, app.s.labels)
        return app

    @staticmethod
    def state(app):
        """Mọi thứ của Session mà một lần kéo có thể đổi: điểm ghim, cờ, ID của mọi người, và hai ngăn hoàn tác / làm lại."""
        s = app.s
        return copy.deepcopy(s._snapshot()), len(s._undo), len(s._redo)

    def start(self, app, kind):
        """Bấm và kéo một đoạn (chưa thả). Trả về chỗ chuột cho sự kiện kéo/thả tiếp theo."""
        pts = app.s.points_at(app.f)
        if kind == "resize":
            x, y = resize_handles(app.view, app._handle_for("mattrai")[3])["e"]
            app.on_press(Ev(x, y))
            self.assertIsNotNone(app.drag_resize)
        elif kind == "rotate":
            x, y = app.view.to_screen(app._handle_arg()[1])
            app.on_press(Ev(x, y))
            self.assertIsNotNone(app.drag_rot)
        elif kind == "point":
            x, y = app.view.to_screen(pts[ML.up])
            app.on_press(Ev(x, y))
            self.assertIsNotNone(app.drag)
        else:
            cx = sum(pts[i][0] for i in ML.ids) / len(ML.ids)
            cy = sum(pts[i][1] for i in ML.ids) / len(ML.ids)
            x, y = app.view.to_screen((cx, cy))
            app.on_press(Ev(x, y))
            self.assertIsNotNone(app.drag_eye)
        app.on_motion(Ev(x + 20, y + 8))
        app._motion_draw()
        return x + 30, y + 12

    def assert_clean(self, app, manual=None):
        for name in ("drag", "drag_eye", "drag_rot", "drag_resize", "draft_drag", "_box0", "_m0"):
            self.assertIsNone(getattr(app, name), f"{name} phải được xoá khi huỷ kéo")
        self.assertIs(app.manual, manual, "khung nhìn trở về như trước khi bấm")

    def finish_mouse(self, app, xy):
        """Sự kiện chuột vẫn tới sau khi đã huỷ (nút chuột còn đang giữ): không được ném lỗi."""
        app.on_motion(Ev(*xy))
        app._motion_draw()
        app.on_release(Ev(*xy))
        app.root.update()

    def assert_overlay_matches_session(self, app):
        """Phần vẽ trên ảnh không còn phần xem trước của lần kéo: điểm mattrai nằm đúng chỗ trong Session (hoặc không có, nếu frame chưa có nhãn)."""
        pts = app.s.points_at(app.f) or {}
        for i in ML.ids:
            items = app.canvas.find_withtag(f"pt:mattrai:{i}")
            if i not in pts:
                self.assertFalse(items, f"frame {app.f} không có nhãn mà vẫn vẽ điểm {i}")
                continue
            self.assertEqual(len(items), 1)
            x0, y0, x1, y1 = app.canvas.coords(items[0])
            want = app.view.to_screen(pts[i])
            self.assertLess(math.dist(((x0 + x1) / 2, (y0 + y1) / 2), want), 1.01, f"điểm {i}")

    # ---------- đổi frame bằng go() giữa lúc kéo: bốn loại kéo, tới frame chưa có nhãn và frame có nhãn ----------
    def test_go_during_any_drag_cancels_it(self):
        for kind in KINDS:
            for target in (PIN - 1, PIN + 1):
                with self.subTest(kind=kind, target=target):
                    app = self.pinned_app()
                    before = self.state(app)
                    cursor = app.canvas.cget("cursor")
                    nxt = self.start(app, kind)
                    app.go(target)                      # trước khi sửa: AttributeError/TypeError khi tới frame 2
                    self.assertEqual(app.f, target)
                    self.assert_clean(app)
                    self.assertIn("huỷ thao tác kéo dở", app.notice)
                    self.assertEqual(self.state(app), before)
                    self.assert_overlay_matches_session(app)
                    self.finish_mouse(app, nxt)          # trước khi sửa: thả chuột ở frame 4 ghim ngầm frame 4
                    self.assertEqual(self.state(app), before, "không ghim, không thêm bước hoàn tác")
                    self.assertEqual(app.canvas.cget("cursor"), cursor)
                    self.assert_overlay_matches_session(app)

    def test_arrow_keys_during_handle_drag(self):
        """Đúng như mô tả lỗi: giữ tay cầm rồi bấm → / ← (đường phím thật: `handlers` -> search -> step -> go)."""
        for kind, key, target in (("resize", "search_next", PIN + 1), ("rotate", "search_prev", PIN - 1),
                                  ("resize", "search_prev", PIN - 1), ("rotate", "search_next", PIN + 1)):
            with self.subTest(kind=kind, key=key):
                app = self.pinned_app()
                before = self.state(app)
                nxt = self.start(app, kind)
                app.handlers[key](None)
                self.assertEqual(app.f, target)
                self.assert_clean(app)
                self.finish_mouse(app, nxt)
                self.assertEqual(self.state(app), before)

    def test_new_drag_works_after_cancel(self):
        """Huỷ xong không kẹt: ở frame mới bấm kéo lại được và lần thả đó ghim đúng frame mới với một bước hoàn tác."""
        app = self.pinned_app()
        nxt = self.start(app, "resize")
        app.go(PIN + 1)
        self.finish_mouse(app, nxt)
        undo0 = len(app.s._undo)
        p0 = app.s.points_at(PIN + 1)[ML.up]
        x, y = app.view.to_screen(p0)
        app.on_press(Ev(x, y))
        self.assertEqual(app.drag[0], ML.up)
        app.on_motion(Ev(x + 10, y))
        app.on_release(Ev(x + 10, y))
        self.assertIn(PIN + 1, app.s.pins)
        self.assertEqual(len(app.s._undo), undo0 + 1)
        self.assertGreater(app.s.pins[PIN + 1][ML.up][0], p0[0] + 1)

    def test_go_to_same_frame_keeps_the_drag(self):
        """Đổi frame mới huỷ (như quy tắc bỏ mắt vẽ dở trong `go`): `go` tới chính frame đang xem không làm gì với lần kéo."""
        app = self.pinned_app()
        p0 = app.s.pins[PIN][ML.up]
        nxt = self.start(app, "point")
        app.go(PIN)
        self.assertIsNotNone(app.drag)
        app.on_release(Ev(*nxt))
        self.assertGreater(app.s.pins[PIN][ML.up][0], p0[0] + 1)

    # ---------- phát (Space) đang chạy ----------
    def test_playback_tick_during_drag_cancels_it(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                app = self.pinned_app()
                before = self.state(app)
                nxt = self.start(app, kind)
                app.toggle_play()
                try:
                    app._tick()                          # một nhịp phát: frame 3 -> 4
                    self.assertEqual(app.f, PIN + 1)
                    self.assert_clean(app)
                    self.finish_mouse(app, nxt)
                finally:
                    if app.playing:
                        app.toggle_play()
                self.assertEqual(self.state(app), before)

    # ---------- bản nháp vẽ mắt ----------
    def test_draft_point_drag_then_frame_change(self):
        app = self.pinned_app()
        app.begin_draw("mattrai", "box")
        x, y = 200, 150
        app.on_press(Ev(x, y)); app.on_motion(Ev(x + 60, y + 20)); app.on_release(Ev(x + 60, y + 20))
        self.assertIsNotNone(app.draft)
        before = self.state(app)
        sx, sy = app.view.to_screen(app.draft["four"][ML.up])
        app.on_press(Ev(sx, sy))
        self.assertEqual(app.draft_drag, ML.up)
        app.on_motion(Ev(sx + 5, sy - 5))
        app.go(PIN + 1)
        self.assertIsNone(app.draft)                      # mắt vẽ dở thuộc frame cũ: bỏ (quy tắc có từ trước)
        self.assert_clean(app)
        self.finish_mouse(app, (sx + 9, sy - 9))
        self.assertIsNone(app.draft)
        self.assertEqual(self.state(app), before)

    def test_box_drag_for_new_eye_is_cancelled_by_frame_change(self):
        """Đang kéo khung vẽ mắt (bảng Vẽ mắt > Kéo khung) mà đổi frame: bỏ khung kéo dở, vẫn ở chế độ kéo khung; kéo tiếp/thả không dựng lại
        mắt mẫu từ góc khung của frame cũ."""
        app = self.pinned_app()
        app.begin_draw("mattrai", "box")
        before = self.state(app)
        app.on_press(Ev(200, 150)); app.on_motion(Ev(260, 170)); app._motion_draw()
        self.assertIsNotNone(app.draft)
        app.go(PIN + 1)
        self.assert_clean(app)
        self.assertIsNone(app.draft)
        self.assertEqual(app.pinning, "drawbox")
        self.finish_mouse(app, (280, 175))
        self.assertIsNone(app.draft, "thả chuột sau khi đã huỷ không được tạo mắt mẫu")
        self.assertEqual(self.state(app), before)
        app.on_press(Ev(200, 150)); app.on_motion(Ev(260, 170)); app.on_release(Ev(260, 170))      # kéo lại ở frame mới vẫn được
        self.assertIsNotNone(app.draft)

    # ---------- lệnh sửa nhãn bằng phím giữa lúc kéo ----------
    def test_undo_during_drag_cancels_it(self):
        """Ctrl+Z giữa lúc kéo tay cầm: bỏ frame ghim duy nhất (mắt biến mất khỏi frame này). Trước khi sửa: AttributeError và kẹt."""
        app = self.pinned_app()
        nxt = self.start(app, "resize")
        app.handlers["undo"](None)
        self.assert_clean(app)
        self.assertNotIn(PIN, app.s.pins)
        after_undo = self.state(app)
        self.finish_mouse(app, nxt)
        self.assertEqual(self.state(app), after_undo, "thả chuột sau Ctrl+Z không ghim lại gì")

    def test_delete_eye_during_drag_cancels_it(self):
        """Del (xoá mắt dưới con trỏ) giữa lúc kéo cả mắt. Trước khi sửa: TypeError và kẹt."""
        app = self.pinned_app()
        nxt = self.start(app, "eye")
        app.handlers["delete"](None)
        self.assert_clean(app)
        self.assertFalse(any(i in pts for pts in app.s.pins.values() for i in ML.ids), "mattrai đã bị xoá")
        after_delete = self.state(app)
        self.finish_mouse(app, nxt)
        self.assertEqual(self.state(app), after_delete)

    def test_new_object_during_drag_cancels_it(self):
        """Ctrl+N (người mới, đổi `Session.cur`) giữa lúc kéo tay cầm xoay. Trước khi sửa: AttributeError và kẹt."""
        app = self.pinned_app()
        nxt = self.start(app, "rotate")
        app.handlers["new_object"](None)
        self.assertEqual(app.s.cur, 1)
        self.assert_clean(app)
        after_new = self.state(app)
        self.finish_mouse(app, nxt)
        self.assertEqual(self.state(app), after_new)
        app.cancel_pin()

    def test_tab_to_other_eye_during_drag_keeps_dragging_the_grabbed_eye(self):
        """Đổi mắt đang chọn (Tab) không đổi frame, người hay dữ liệu: lần kéo đi tiếp và thả chỉ sửa mắt đã nắm, ở frame đã nắm."""
        app = self.pinned_app()
        other = {i: app.s.points_at(PIN)[i] for i in EYES["matphai"].ids}
        nxt = self.start(app, "resize")
        app.handlers["next_object"](None)
        self.assertEqual(app._selected()[0], "matphai")
        self.assertIsNotNone(app.drag_resize)
        app.on_release(Ev(*nxt))
        self.assertIn(PIN, app.s.pins)
        self.assertEqual({i: app.s.pins[PIN][i] for i in other}, other)

    # ---------- mở thư mục / job khác ----------
    def test_open_other_folder_during_drag_cancels_it(self):
        app = self.pinned_app()
        nxt = self.start(app, "resize")
        app.load(self.dir, None)                          # cùng đường với mở job CVAT: `_show_session`
        self.assertEqual(app.f, 0)
        self.assertFalse(app.s.pins)
        self.assert_clean(app)
        self.finish_mouse(app, nxt)
        self.assertFalse(app.s.pins, "thả chuột không ghim gì vào phiên vừa mở")


if __name__ == "__main__":
    unittest.main()
