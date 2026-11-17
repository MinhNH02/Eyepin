"""B21 (buglist.md, sót sau B05): ba kẽ hở còn lại của việc huỷ lần kéo dở (`App._cancel_drag`).

(a) Esc giữa lúc kéo không huỷ kéo (`cancel_pin` chỉ huỷ chế độ ghim / bản nháp).
(b) Bấm l, L, h, H, p giữa lúc kéo không huỷ kéo: thả chuột vẫn sửa được mắt vừa bị khoá / ẩn / Pinned. Các lệnh đổi khoá, ẩn, Pinned gọi
    `_cancel_drag` như `edit_command` làm.
(c) Khi phát (Space), `_tick` không bỏ bản nháp vẽ mắt (draft, draft_drag, _box0) như `go()` làm khi đổi frame: bản nháp đi theo sang frame khác.
Ảnh giả của `test_tracking` (không dùng dữ liệu công ty). Mô phỏng chuột như `test_bugfix_b05`."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import test_bugfix_b05 as _b05  # noqa: E402
import test_gui as _tg  # noqa: E402

Ev = _tg.Ev
PIN = _b05.PIN
KINDS = _b05.KINDS


class DragLeftoverTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins
    pinned_app = _b05.DragCancelTests.pinned_app
    state = staticmethod(_b05.DragCancelTests.state)
    start = _b05.DragCancelTests.start
    assert_clean = _b05.DragCancelTests.assert_clean
    finish_mouse = _b05.DragCancelTests.finish_mouse

    # ---------- (a) Esc ----------
    def test_escape_during_any_drag_cancels_it(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                app = self.pinned_app()
                before = self.state(app)
                nxt = self.start(app, kind)
                app.handlers["cancel"](None)
                self.assert_clean(app)
                self.assertEqual(app.f, PIN)
                self.assertEqual(self.state(app), before)
                self.finish_mouse(app, nxt)
                self.assertEqual(self.state(app), before, "thả chuột sau Esc không ghi gì")

    def test_escape_without_drag_still_cancels_pinning(self):
        app = self.pinned_app()
        app.start_pin("full")
        self.assertEqual(app.pinning, "full")
        app.handlers["cancel"](None)
        self.assertIsNone(app.pinning)

    # ---------- (b) khoá / ẩn / Pinned giữa lúc kéo ----------
    def test_lock_hide_pinned_keys_during_drag_cancel_it(self):
        for kind in KINDS:
            for key in ("lock", "lock_all", "hide", "hide_all", "pinned"):
                with self.subTest(kind=kind, key=key):
                    app = self.pinned_app()
                    before = self.state(app)
                    nxt = self.start(app, kind)
                    app.handlers[key](None)
                    self.assert_clean(app)
                    self.finish_mouse(app, nxt)
                    self.assertEqual(self.state(app), before, "thả chuột sau khi khoá / ẩn / Pinned không được sửa mắt")

    def test_lock_hide_pinned_still_work_without_drag(self):
        app = self.pinned_app()
        app.handlers["lock"](None)
        self.assertIn("mattrai", app.locked)
        app.handlers["lock"](None)
        app.handlers["hide"](None)
        self.assertIn((app.s.cur, "mattrai"), app.hidden_objs)
        app.handlers["hide"](None)
        app.handlers["pinned"](None)
        self.assertIn("mattrai", app.pinned_eyes)
        app.handlers["hide_all"](None)
        self.assertTrue(app.hide_labels)

    # ---------- (c) nhịp phát giữa lúc có bản nháp ----------
    def test_playback_tick_drops_draft_like_go(self):
        app = self.pinned_app()
        app.begin_draw("mattrai", "box")
        app.on_press(Ev(200, 150)); app.on_motion(Ev(260, 170)); app.on_release(Ev(260, 170))
        self.assertIsNotNone(app.draft)
        sx, sy = app.view.to_screen(app.draft["four"][14])
        app.on_press(Ev(sx, sy))
        self.assertIsNotNone(app.draft_drag)
        app.toggle_play()
        try:
            app._tick()
            self.assertEqual(app.f, PIN + 1)
            self.assertIsNone(app.draft)
            self.assertIsNone(app.draft_drag)
            self.assertIsNone(app._box0)
        finally:
            if app.playing:
                app.toggle_play()

    def test_playback_tick_drops_box_in_progress(self):
        app = self.pinned_app()
        app.begin_draw("mattrai", "box")
        app.on_press(Ev(200, 150)); app.on_motion(Ev(260, 170)); app._motion_draw()
        self.assertIsNotNone(app.draft)
        app.toggle_play()
        try:
            app._tick()
            self.assertIsNone(app.draft)
            self.assertIsNone(app._box0)
        finally:
            if app.playing:
                app.toggle_play()


if __name__ == "__main__":
    unittest.main()
