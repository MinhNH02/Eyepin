"""Kiểm luồng thao tác của cửa sổ bằng cách giả lập chuột. Bỏ qua nếu máy không mở được cửa sổ Tkinter."""
import math
import os
import shutil
import sys
import tempfile
import tkinter as tk
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")      # không đụng cài đặt thật của người dùng

from eyepin.geometry import EYES  # noqa: E402
import test_tracking as T  # noqa: E402


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = tempfile.mkdtemp(prefix="eyepin_gui_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def make_app(self):
        from eyepin.gui import App, PIN_SEQ
        app = App(self.root)
        app.ask_restore = lambda n: False                  # test không bật hộp hỏi khôi phục
        os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, os.environ["EYEPIN_HOME"], True)
        app.load(self.dir, None)
        return app, PIN_SEQ

    def click_pins(self, app, seq, frame):
        truth = T.pins_at(frame)
        app.go(frame)
        app.start_pin()
        # khung nhìn chưa có nhãn nên là toàn khung: đổi toạ độ frame -> màn hình qua View hiện tại
        for _, pid in seq:
            sx, sy = app.view.to_screen(truth[pid])
            app.on_press(Ev(sx, sy))

    def test_eight_clicks_create_a_pin(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        self.assertIn(0, app.s.pins)
        self.assertFalse(app.pinning)
        worst = max(math.dist(app.s.pins[0][i], T.pins_at(0)[i]) for i in seq_ids(seq))
        self.assertLess(worst, 1.5)      # sai số do làm tròn pixel màn hình
        self.assertIn(10, app.s.labels)  # đã bám về phía sau

    def test_first_eye_is_drawn_after_four_clicks_without_waiting_for_eight(self):
        import numpy as np
        from eyepin.render import render_main
        app, seq = self.make_app()
        truth = T.pins_at(0)
        app.go(0)
        app.start_pin()
        ids = [pid for _, pid in seq]
        base, _ = render_main(app.s, 0, (960, 460), anchor=app.anchor, manual=app.view)
        for k, pid in enumerate(ids[:3], 1):
            sx, sy = app.view.to_screen(truth[pid])
            app.on_press(Ev(sx, sy))
            self.assertIsNone(app._preview_pts())                     # mới 1..3 điểm: chưa đủ một mắt
        sx, sy = app.view.to_screen(truth[ids[3]])
        app.on_press(Ev(sx, sy))
        pv = app._preview_pts()
        self.assertIsNotNone(pv)
        self.assertEqual(len(pv), 8)                                  # 4 điểm bấm + 4 điểm tool suy ra
        for i in ids[:4]:
            self.assertLess(math.dist(pv[i if i in pv else i], truth[i]), 2.0)
        shown, _ = render_main(app.s, 0, (960, 460), anchor=app.anchor, manual=app.view, preview=pv)
        self.assertGreater(int(np.abs(base.astype(int) - shown.astype(int)).sum()), 0)
        self.assertIn("Đã vẽ mắt đầu", app.status.get() if False else (app.refresh() or app.status.get()))
        for pid in ids[4:]:
            sx, sy = app.view.to_screen(truth[pid])
            app.on_press(Ev(sx, sy))
        self.assertIn(0, app.s.pins)                                  # đủ 8 điểm thì ghim như cũ
        self.assertIsNone(app._preview_pts())

    def test_interleaved_clicks_still_work_without_a_preview(self):
        app, seq = self.make_app()
        truth = T.pins_at(0)
        app.go(0)
        app.start_pin()
        ids = [pid for _, pid in seq]
        mixed = [ids[0], ids[4], ids[1], ids[5], ids[2], ids[6], ids[3], ids[7]]   # xen kẽ hai mắt
        for pid in mixed[:4]:
            sx, sy = app.view.to_screen(truth[pid])
            app.on_press(Ev(sx, sy))
        self.assertIsNone(app._preview_pts())
        for pid in mixed[4:]:
            sx, sy = app.view.to_screen(truth[pid])
            app.on_press(Ev(sx, sy))
        self.assertIn(0, app.s.pins)

    def test_escape_cancels_a_partial_pin(self):
        app, seq = self.make_app()
        app.go(0)
        app.start_pin()
        app.on_press(Ev(100, 100))
        app.cancel_pin()
        self.assertEqual((bool(app.pinning), app.clicks, app.s.pins), (False, [], {}))

    def test_drag_moves_a_point_on_a_pinned_frame(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        before = app.s.pins[0][14]
        sx, sy = app.view.to_screen(before)
        app.on_press(Ev(sx, sy))
        app.on_motion(Ev(sx + 20, sy))
        app.on_release(Ev(sx + 20, sy))
        self.assertGreater(app.s.pins[0][14][0], before[0] + 1)

    def test_wheel_zooms_around_the_cursor_and_fit_resets(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        k0 = app.view.k
        cx, cy = 480, 230
        p_before = app.view.to_frame(cx, cy)
        app.on_wheel(type("E", (), {"x": cx, "y": cy, "delta": 120})())
        self.assertGreater(app.view.k, k0 * 1.1)
        p_after = app.view.to_frame(cx, cy)
        self.assertAlmostEqual(p_before[0], p_after[0], places=4)
        app.go(1)                                   # đổi frame không làm mất mức phóng
        self.assertAlmostEqual(app.view.k, app.manual.k)
        app.on_wheel(type("E", (), {"x": cx, "y": cy, "delta": -120})())
        self.assertLess(app.view.k, app.manual.k * 1.01)
        app.fit()
        self.assertIsNone(app.manual)

    def test_right_drag_pans(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        p = app.view.to_frame(300, 200)
        app.on_pan_start(Ev(300, 200))
        app.on_pan(Ev(340, 190))
        sx, sy = app.view.to_screen(p)
        self.assertAlmostEqual(sx, 340, delta=1)
        self.assertAlmostEqual(sy, 190, delta=1)

    def test_left_drag_on_empty_space_pans_but_does_not_move_points(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        pins_before = dict(app.s.pins[0])
        far = (20, 20)                              # chỗ trống, xa mọi điểm
        p = app.view.to_frame(*far)
        app.on_press(Ev(*far))
        app.on_motion(Ev(far[0] + 50, far[1] + 30))
        app.on_release(Ev(far[0] + 50, far[1] + 30))
        sx, sy = app.view.to_screen(p)
        self.assertAlmostEqual(sx, far[0] + 50, delta=1)
        self.assertAlmostEqual(sy, far[1] + 30, delta=1)
        self.assertEqual(app.s.pins[0], pins_before)
        self.assertIsNotNone(app.manual)

    def test_middle_drag_pans_too(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        p = app.view.to_frame(400, 300)
        app.on_pan_start(Ev(400, 300))
        app.on_pan(Ev(380, 330))
        sx, sy = app.view.to_screen(p)
        self.assertAlmostEqual(sx, 380, delta=1)
        self.assertAlmostEqual(sy, 330, delta=1)

    def test_clicks_while_pinning_do_not_pan(self):
        app, seq = self.make_app()
        app.go(0)
        app.start_pin()
        app.on_press(Ev(300, 200))
        app.on_motion(Ev(340, 230))
        app.on_release(Ev(340, 230))
        self.assertIsNone(app.manual)
        self.assertEqual(len(app.clicks), 1)

    def test_unordered_clicks_and_ctrl_z(self):
        import random
        app, seq = self.make_app()
        truth = T.pins_at(0)
        app.go(0)
        app.start_pin()
        pts = [truth[pid] for _, pid in seq]
        random.Random(3).shuffle(pts)                 # bấm lung tung thứ tự
        for p in pts[:5]:
            app.on_press(Ev(*app.view.to_screen(p)))
        app.undo()                                    # Ctrl+Z khi đang ghim dở: bỏ điểm vừa bấm
        self.assertEqual(len(app.clicks), 4)
        for p in pts[4:]:
            app.on_press(Ev(*app.view.to_screen(p)))
        self.assertIn(0, app.s.pins)
        self.assertLess(math.dist(app.s.pins[0][16], truth[16]), 1.5)
        app.undo()                                    # Ctrl+Z sau khi ghim xong: bỏ cả frame ghim
        self.assertNotIn(0, app.s.pins)
        app.redo()
        self.assertIn(0, app.s.pins)

    def test_bad_clicks_show_a_message_and_restart_the_pin(self):
        app, seq = self.make_app()
        app.go(0)
        app.start_pin()
        for k in range(8):
            app.on_press(Ev(300 + k, 200))            # 8 điểm gần như trùng nhau
        self.assertEqual(app.s.pins, {})
        self.assertTrue(app.pinning)
        self.assertEqual(app.clicks, [])
        self.assertIn("Không ghim được", app.notice)

    def test_frame_entry_buttons_and_play(self):
        app, seq = self.make_app()
        app.entry_var.set("25")
        app.on_entry(None)
        self.assertEqual(app.f, 25)
        app.step(-10)
        self.assertEqual(app.f, 15)
        app.step("last")
        self.assertEqual(app.f, T.N - 1)
        app.step(1)                                         # không vượt quá frame cuối
        self.assertEqual(app.f, T.N - 1)
        app.step("first")
        self.assertEqual((app.f, app.entry_var.get()), (0, "0"))
        app.entry_var.set("abc")
        app.on_entry(None)
        self.assertEqual(app.f, 0)
        self.assertIn("không hợp lệ", app.notice)
        app.entry_var.set("9999")
        app.on_entry(None)
        self.assertEqual(app.f, T.N - 1)                   # số quá lớn được kẹp lại

    def test_global_arrow_keys_are_ignored_while_typing_in_the_frame_box(self):
        app, seq = self.make_app()
        app.go(5)
        real = self.root.focus_get
        try:
            self.root.focus_get = lambda: app.entry               # giả lập: con trỏ đang ở ô số frame
            self.assertTrue(app._typing())
            app.handlers["search_next"](None)
            self.assertEqual(app.f, 5)                          # mũi tên chỉ di chuyển con trỏ trong ô, không đổi frame
            self.root.focus_get = lambda: app.canvas
            self.assertFalse(app._typing())
            app.handlers["search_next"](None)
            self.assertEqual(app.f, 6)
            app.handlers["frame_prev"](None)
            self.assertEqual(app.f, 5)                          # D = frame trước, F = frame sau (như CVAT)
            app.handlers["frame_next"](None)
            self.assertEqual(app.f, 6)
            app.handlers["jump_fwd"](None)
            self.assertEqual(app.f, 16)
            app.handlers["first"](None)
            self.assertEqual(app.f, 0)
            app.handlers["last"](None)
            self.assertEqual(app.f, T.N - 1)
        finally:
            self.root.focus_get = real

    def test_up_down_in_the_entry_change_frame_and_stop_the_event(self):
        app, seq = self.make_app()
        app.go(5)
        self.assertEqual(app.on_entry_up(None), "break")
        self.assertEqual(app.f, 6)
        app.on_entry_down(None)
        app.on_entry_down(None)
        self.assertEqual(app.f, 4)

    def test_play_advances_and_stops_at_the_last_frame(self):
        app, seq = self.make_app()
        app.go(T.N - 3)
        app.toggle_play()
        self.assertTrue(app.playing)
        for _ in range(5):
            app._tick()
        self.assertFalse(app.playing)
        self.assertEqual(app.f, T.N - 1)

    def test_jump_between_pins_and_pin_here(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        self.click_pins(app, seq, 30)
        app.go(10)
        app.jump_pin(1)
        self.assertEqual(app.f, 30)
        app.jump_pin(-1)
        self.assertEqual(app.f, 0)
        app.jump_pin(-1)
        self.assertEqual(app.f, 0)
        self.assertIn("Không còn", app.notice)
        app.go(45)
        app.toggle_pin_here()
        self.assertIn(45, app.s.pins)
        app.toggle_pin_here()
        self.assertNotIn(45, app.s.pins)

    def test_q_and_o_toggle_flags_on_the_hovered_point(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        sx, sy = app.view.to_screen(app.s.pins[0][16])
        app.on_hover(Ev(sx + 2, sy + 1))
        app.toggle_flag("occluded")
        self.assertEqual(app.s.flags[0][16], "occluded")
        app.toggle_flag("outside")
        self.assertEqual(app.s.flags[0][16], "outside")
        app.toggle_flag("outside")
        self.assertNotIn(16, app.s.flags[0])
        app.on_hover(Ev(5, 5))                              # xa mọi điểm
        app.toggle_flag("occluded")
        self.assertIn("lại gần", app.notice)
        app.go(5)                                           # frame tool tính: như CVAT, Q biến frame này thành keyframe của riêng mắt đó
        sx, sy = app.view.to_screen(app.s.points_at(5)[16])
        app.on_hover(Ev(sx, sy))
        app.toggle_flag("occluded")
        self.assertEqual(app.s.flags_at(5).get(16), "occluded")
        self.assertEqual((5 in app.s.eye_keyframes("mattrai"), 5 in app.s.eye_keyframes("matphai")), (True, False))
        self.assertIn("keyframe", app.notice)

    def test_panel_button_uses_the_selection_not_a_stale_mouse_position(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        sx, sy = app.view.to_screen(app.s.pins[0][16])
        app.on_hover(Ev(sx, sy))
        app.on_leave(Ev(0, 0))                              # chuột rời ảnh sang panel
        app.tree.selection_set("eye:matphai")
        app.root.update()
        app.toggle_flag("occluded")                         # nút Occluded ở panel: cả mắt đang chọn, như cờ của đối tượng trong CVAT
        self.assertEqual({i for i, k in app.s.flags_at(0).items() if k == "occluded"}, set(EYES["matphai"].ids))
        self.assertIn("matphai", app.notice)

    def test_hidden_corner_pin_with_seven_clicks(self):
        import random
        app, seq = self.make_app()
        truth = T.pins_at(0)
        app.go(0)
        app.start_pin("hidden")
        pts = [truth[i] for i in EYES["mattrai"].pins if i != 18] + [truth[i] for i in EYES["matphai"].pins]
        random.Random(4).shuffle(pts)
        for p in pts:
            app.on_press(Ev(*app.view.to_screen(p)))
        self.assertIn(0, app.s.pins)
        self.assertEqual({i for i, k in app.s.flags[0].items() if k == "occluded"}, {17, 18, 19})
        self.assertIn("Khoé 18", app.notice)
        self.assertLess(math.dist(app.s.pins[0][18], truth[18]), 2.0)
        app.undo()
        self.assertNotIn(0, app.s.pins)

    def test_drag_point_and_whole_eye_on_a_tracked_frame(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(5)
        self.assertNotIn(5, app.s.pins)
        pts = app.s.labels[5].points
        sx, sy = app.view.to_screen(pts[17])            # điểm suy ra, không phải điểm ghim
        app.on_press(Ev(sx, sy)); app.on_motion(Ev(sx + 30, sy)); app.on_release(Ev(sx + 30, sy))
        self.assertIn(5, app.s.pins)
        self.assertGreater(app.s.pins[5][17][0], pts[17][0] + 3)
        app.go(9)
        before = dict(app.s.labels[9].points)
        cx = sum(app.view.to_screen(before[i])[0] for i in (14, 18)) / 2
        cy = sum(app.view.to_screen(before[i])[1] for i in (14, 18)) / 2
        app.on_press(Ev(cx, cy + 1)); app.on_motion(Ev(cx + 30, cy + 1)); app.on_release(Ev(cx + 30, cy + 1))
        self.assertIn(9, app.s.pins)
        self.assertGreater(app.s.pins[9][14][0], before[14][0] + 3)
        self.assertTrue(app.s.undo())
        self.assertNotIn(9, app.s.pins)

    def test_layers_and_marker_size(self):
        import numpy as np
        from eyepin.render import Look, render_main
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        def img(**kw):
            return render_main(app.s, 0, (960, 460), anchor=app.anchor, manual=app.view, look=Look(eyes={"mattrai": True, "matphai": True}, **kw))[0].astype(int)
        full = img()
        for kw in ({"image": False}, {"points": False}, {"outline": False}, {"size": 2.0}, {"opacity": 0.4}):
            self.assertGreater(int(np.abs(full - img(**kw)).sum()), 0, kw)
        left_off = render_main(app.s, 0, (960, 460), anchor=app.anchor, manual=app.view, look=Look(eyes={"mattrai": False, "matphai": True}))[0].astype(int)
        self.assertGreater(int(np.abs(full - left_off).sum()), 0)
        app.handlers["marker_up"](None)
        self.assertGreater(app.look.size, 1.0)
        app._layer_vars["mattrai"].set(False); app.set_layer("mattrai")
        self.assertFalse(app.look.eyes["mattrai"])
        app.handlers["toggle_ids"](None)
        self.assertFalse(app.look.ids)

    def test_image_adjust_and_layer_order(self):
        import numpy as np
        from eyepin.render import Look
        app, seq = self.make_app()
        a = np.full((4, 4, 3), 100, np.uint8)
        self.assertGreater(int(Look(brightness=150).adjust(a).mean()), 100)        # thang của CVAT: 100 là gốc
        self.assertEqual(int(Look(contrast=200.0).adjust(a).mean()), 72)
        c = np.zeros((2, 2, 3), np.uint8); c[..., 2] = 200
        self.assertEqual(int(Look(saturation=0).adjust(c)[0, 0].std()), 0)
        self.assertIs(Look().adjust(a), a)                                          # mặc định: không chép ảnh
        self.assertEqual(Look(top="mattrai").order(), ["matphai", "mattrai"])
        app.handlers["swap_top"](None)
        self.assertEqual(app.look.top, "mattrai")
        app.set_look(brightness=140.0, gamma=2.0)
        app.reset_adjust()
        self.assertEqual(app.look.brightness, 100.0)
        self.assertEqual(app.look.gamma, 1.0)

    def test_old_display_scale_is_reset(self):
        """settings.json cũ lưu độ sáng theo thang cộng (−100..100): không được hiểu thành 30% (ảnh tối đen)."""
        app, seq = self.make_app()
        app.settings["workspace"]["remember_display"] = True
        app.settings["display"] = {"brightness": 30}
        app._apply_settings_to_look()
        self.assertEqual(app.look.brightness, 100.0)
        self.assertIn("thang của CVAT", app.notice)
        self.assertEqual(app.settings["display"]["color_scale"], "cvat")

    def test_filter_search_and_objects_panel(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.s.toggle_pin_here(10)
        app.s.toggle_pin_here(20)
        app.go(0)
        app.handlers["search_next"](None)
        self.assertEqual(app.f, 1)                                  # chưa lọc: đi từng frame
        app._filter_var.set("pinned"); app.set_filter()
        app.go(0)
        app.handlers["search_next"](None)
        self.assertEqual(app.f, 10)
        app.handlers["search_next"](None)
        self.assertEqual(app.f, 20)
        app.handlers["search_prev"](None)
        self.assertEqual(app.f, 10)
        app.go(20); app.handlers["search_next"](None)
        self.assertEqual(app.f, 20)
        self.assertIn("Không còn", app.notice)
        # panel Đối tượng: hai mắt, mỗi mắt 8 điểm
        self.assertEqual(set(app.tree.get_children()), {"eye:mattrai", "eye:matphai"})
        self.assertEqual(len(app.tree.get_children("eye:mattrai")), 8)
        # khoá một mắt thì không kéo được điểm của nó
        app.go(10)
        app.tree.selection_set("eye:mattrai")
        app.handlers["lock"](None)
        self.assertIn("mattrai", app.locked)
        before = dict(app.s.pins[10])
        sx, sy = app.view.to_screen(before[16])
        app.on_press(Ev(sx, sy)); app.on_motion(Ev(sx + 30, sy)); app.on_release(Ev(sx + 30, sy))
        self.assertEqual(app.s.pins[10], before)
        app.handlers["lock"](None)
        self.assertNotIn("mattrai", app.locked)
        # chọn điểm trong panel rồi bấm Q (chuột không ở gần điểm nào)
        app.hover = None
        app.tree.selection_set("pt:17")
        app.handlers["occluded"](None)
        self.assertEqual(app.s.flags[10][17], "occluded")
        # ẩn mắt qua panel
        app.tree.selection_set("eye:matphai")
        app.toggle_eye_hidden()
        self.assertFalse(app.look.eyes["matphai"])

    def test_keymap_is_cvat_like_and_rebindable(self):
        from eyepin import shortcuts as sc
        app, seq = self.make_app()
        self.assertEqual(set(app.handlers), set(sc.BY_ID))
        self.assertEqual(sc.conflicts(app.bind_map), {})
        self.assertEqual(app.bind_map["frame_next"], ("f",))
        self.assertEqual(app.bind_map["next_keyframe"], ("r",))
        self.click_pins(app, seq, 0)
        app.s.toggle_pin_here(30)
        app.go(5)
        app.handlers["step_fwd"](None)
        self.assertEqual(app.f, 15)                                   # V = nhảy theo bước (mặc định 10)
        app.handlers["next_keyframe"](None)
        self.assertEqual(app.f, 30)
        app.handlers["prev_keyframe"](None)
        self.assertEqual(app.f, 0)
        # gán lại phím: trùng thì từ chối; hợp lệ thì có hiệu lực và lưu ra file
        self.assertIn("đang dùng", app.rebind("draw_full", "f"))
        self.assertIsNone(app.rebind("draw_full", "m"))
        self.assertEqual(app.bind_map["draw_full"], ("m",))
        import json
        saved = json.load(open(sc.settings_path(), encoding="utf-8"))
        self.assertEqual(saved["shortcuts"]["draw_full"], ["m"])
        self.assertIsNone(app.rebind("draw_full", None))
        self.assertEqual(app.bind_map["draw_full"], ())                  # phím N nay mở bảng vẽ từng mắt; ghim 8 điểm không còn phím mặc định
        self.assertEqual(app.bind_map["draw_eye"], ("n",))

    def test_event_to_seq_and_pretty(self):
        from eyepin import shortcuts as sc
        self.assertEqual(sc.event_to_seq("n", 0), "n")
        self.assertEqual(sc.event_to_seq("N", 1), "N")
        self.assertEqual(sc.event_to_seq("s", 4), "<Control-s>")
        self.assertEqual(sc.event_to_seq("Right", 1), "<Shift-Right>")
        self.assertEqual(sc.event_to_seq("1", 4), "<Control-Key-1>")
        self.assertIsNone(sc.event_to_seq("Shift_L", 1))
        self.assertEqual(sc.pretty("<Control-z>"), "Ctrl+Z")
        self.assertEqual(sc.pretty("N"), "Shift+N")
        self.assertEqual(sc.pretty("<Control-Z>"), "Ctrl+Shift+Z")
        self.assertEqual(sc.pretty("<Control-Key-1>"), "Ctrl+1")

    def test_settings_roundtrip_and_guide(self):
        import tempfile as tf
        from pathlib import Path
        from eyepin import shortcuts as sc
        d = Path(tf.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        st = sc.load_settings(d / "none.json")
        self.assertEqual(st["player"]["step"], 10)
        st["player"]["step"] = 25
        sc.save_settings(st, d / "s.json")
        self.assertEqual(sc.load_settings(d / "s.json")["player"]["step"], 25)
        (d / "bad.json").write_text("{khong phai json", encoding="utf-8")
        self.assertEqual(sc.load_settings(d / "bad.json")["player"]["step"], 10)
        md = sc.guide_markdown()
        for a in sc.ACTIONS:
            self.assertIn(a.label, md)

    def test_copy_paste_tab_and_label_keys(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        app.handlers["copy"](None)
        self.assertIsNotNone(app.clipboard)
        app.go(40)
        self.assertNotIn(40, app.s.pins)
        app.handlers["paste"](None)
        self.assertIn(40, app.s.pins)
        self.assertEqual(app.s.pins[40], {i: tuple(p) for i, p in app.clipboard.items()})
        app.handlers["next_object"](None)
        self.assertEqual(app._selected()[0], "mattrai")
        app.handlers["next_object"](None)
        self.assertEqual(app._selected()[0], "matphai")
        app.handlers["label_mattrai"](None)
        self.assertEqual(app._selected()[0], "mattrai")
        app.handlers["hide"](None)
        self.assertFalse(app.look.eyes["mattrai"])
        app.handlers["lock_all"](None)
        self.assertEqual(app.locked, {"mattrai", "matphai"})

    def test_settings_window_and_guide_window_open(self):
        app, seq = self.make_app()
        app.root.update()
        app.handlers["settings"](None)
        app.handlers["shortcuts"](None)
        app.root.update()
        self.assertTrue(app._dialogs["settings"].winfo_exists())
        self.assertTrue(app._dialogs["shortcuts"].winfo_exists())
        app.settings["player"]["fit_on_frame"] = True
        app.manual = app.view
        app.go(3)
        self.assertIsNone(app.manual)

    def test_ctrl_s_saves_the_session_and_it_restores(self):
        from eyepin import shortcuts as sc
        from eyepin.gui import App
        app, seq = self.make_app()
        self.assertEqual(app.bind_map["save"], ("<Control-s>",))
        self.assertEqual(app.bind_map["export"], ("<Control-S>",))
        self.click_pins(app, seq, 0)
        app.s.toggle_pin_here(10)
        app.s.toggle_flag(10, 17, "occluded")
        self.assertTrue(app.s.dirty)
        app.refresh()
        self.assertTrue(app.root.title().endswith("*"))
        app.handlers["save"](None)
        self.assertFalse(app.s.dirty)
        self.assertIn("Đã lưu", app.notice)
        self.assertTrue(os.path.exists(app.state_path()))
        # mở lại cùng thư mục ảnh: khôi phục đủ frame ghim và cờ
        app2 = App(self.root)
        app2.ask_restore = lambda n: True
        app2.load(self.dir, None)
        self.assertEqual(sorted(app2.s.pins), [0, 10])
        self.assertEqual(app2.s.flags[10][17], "occluded")
        self.assertEqual(sorted(app2.s.labels), sorted(app.s.labels))
        self.assertFalse(app2.s.dirty)
        # từ chối khôi phục thì bắt đầu trống
        app3 = App(self.root)
        app3.ask_restore = lambda n: False
        app3.load(self.dir, None)
        self.assertEqual(app3.s.pins, {})

    def test_pins_mode_never_touches_the_saved_session(self):
        from eyepin.gui import App
        app, seq = self.make_app()
        self.assertFalse(app.scratch)
        self.click_pins(app, seq, 0)
        app.save_work()
        path = app.state_path()
        with open(path, "rb") as fh:
            before = fh.read()
        pins = {str(f): {str(i): list(p) for i, p in T.pins_at(f).items()} for f in (0, 20, 40)}

        def no_restore(n):
            raise AssertionError("mở bằng --pins không được hỏi khôi phục")
        app2 = App(self.root)
        app2.ask_restore = no_restore
        app2.load(self.dir, None, pins=pins)
        self.assertTrue(app2.scratch)
        self.assertEqual(sorted(app2.s.pins), [0, 20, 40])
        app2.s.dirty = True                                  # có thay đổi chưa lưu: tự lưu và Ctrl+S đều phải bị chặn
        app2.save_work()
        self.assertIn("--pins", app2.notice)
        notice = app2.notice
        app2.save_work(auto=True)
        app2._autosave_tick()
        self.assertEqual(app2.notice, notice)
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(), before)

    def test_open_xml_in_pins_mode_keeps_the_pins_and_scratch(self):
        from unittest import mock
        from eyepin.gui import App
        app, seq = self.make_app()
        pins = {str(f): {str(i): list(p) for i, p in T.pins_at(f).items()} for f in (0, 20, 40)}
        app2 = App(self.root)
        app2.ask_restore = lambda n: False
        app2.load(self.dir, None, pins=pins)
        xml = os.path.join(self.dir, "e_scratch.xml")
        app2.s.export(xml)
        with mock.patch("eyepin.gui.filedialog.askopenfilename", return_value=xml):
            app2.open_xml()
        self.assertTrue(app2.scratch)
        self.assertEqual(sorted(app2.s.pins), [0, 20, 40])

    # ---------- vẽ từng mắt kiểu CVAT: chọn label, bấm 4 điểm hoặc kéo khung, chỉnh, Apply ----------
    def _click(self, app, p):
        sx, sy = app.view.to_screen(p)
        app.on_press(Ev(sx, sy))
        app.on_release(Ev(sx, sy))

    def test_draw_one_eye_by_four_clicks_then_apply(self):
        app, _ = self.make_app()
        truth = T.pins_at(0)
        app.begin_draw("mattrai", "points")
        for pid in EYES["mattrai"].pins:
            self._click(app, truth[pid])
        self.assertIsNotNone(app.draft)                     # vẽ xong là bản nháp màu cam để chỉnh, chưa ghim
        self.assertEqual(app.draft["label"], "mattrai")
        self.assertNotIn(0, app.s.pins)
        self.assertEqual(len(app._preview_pts()), 8)
        self.assertTrue(app.draft_bar.winfo_ismapped() or app.draft_bar.winfo_manager())
        app.apply_draft()
        self.assertIsNone(app.draft)
        self.assertEqual(app.s.eyes_in_pin(0), ["mattrai"])                     # chỉ mắt đã chọn, mắt kia không bị đụng
        worst = max(math.dist(app.s.pins[0][i], truth[i]) for i in EYES["mattrai"].pins)
        self.assertLess(worst, 1.5)
        self.assertIn(10, app.s.labels)                     # mắt vừa vẽ được bám sang các frame sau như track
        self.assertFalse(app.draft_bar.winfo_manager())

    def test_draw_by_dragging_a_box_then_adjusting_a_point_then_apply(self):
        app, _ = self.make_app()
        sp = EYES["matphai"]
        truth = T.pins_at(0)
        x0, x1 = truth[sp.first][0], truth[sp.last][0]
        y0, y1 = truth[sp.up][1] - 1, truth[sp.lo][1] + 1
        app.begin_draw("matphai", "box")
        a, b = app.view.to_screen((x0, y0)), app.view.to_screen((x1, y1))
        app.on_press(Ev(*a))
        app.on_motion(Ev((a[0] + b[0]) // 2, (a[1] + b[1]) // 2))
        self.assertIsNotNone(app.draft)                     # mắt mẫu hiện ngay trong lúc kéo
        app.on_motion(Ev(*b))
        app.on_release(Ev(*b))
        four = app.draft["four"]
        self.assertAlmostEqual(four[sp.first][0], x0, delta=1.0)
        self.assertAlmostEqual(four[sp.last][0], x1, delta=1.0)
        self.assertLess(four[sp.up][1], four[sp.lo][1])
        up = four[sp.up]
        target = (up[0] + 2, up[1] - 2)
        s0, s1 = app.view.to_screen(up), app.view.to_screen(target)
        app.on_press(Ev(*s0))                               # kéo điểm giữa mí trên của bản nháp
        app.on_motion(Ev(*s1))
        app.on_release(Ev(*s1))
        self.assertLess(math.dist(app.draft["four"][sp.up], target), 1.0)
        app.apply_draft()
        self.assertEqual(app.s.eyes_in_pin(0), ["matphai"])
        self.assertLess(math.dist(app.s.pins[0][sp.up], target), 1.0)

    def test_drawing_one_eye_does_not_keyframe_the_other(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)                        # cả hai mắt ở frame 0
        app.go(10)
        truth = T.pins_at(10)
        app.begin_draw("mattrai", "points")
        for pid in EYES["mattrai"].pins:
            self._click(app, truth[pid])
        app.apply_draft()
        self.assertEqual(app.s.eye_keyframes("mattrai"), [0, 10])
        self.assertEqual(app.s.eye_keyframes("matphai"), [0])                 # như CVAT: vẽ mắt này không tạo keyframe cho mắt kia

    def test_cancel_and_invalid_draft(self):
        app, _ = self.make_app()
        truth = T.pins_at(0)
        app.begin_draw("mattrai", "points")
        for pid in EYES["mattrai"].pins:
            self._click(app, truth[pid])
        sp = EYES["mattrai"]
        far = (truth[sp.last][0] + 30, truth[sp.up][1])      # kéo giữa mí trên ra ngoài khoé: không còn giống một mắt
        app.on_press(Ev(*app.view.to_screen(app.draft["four"][sp.up])))
        app.on_motion(Ev(*app.view.to_screen(far)))
        app.on_release(Ev(*app.view.to_screen(far)))
        app.apply_draft()
        self.assertIsNotNone(app.draft)                     # không hợp lệ: giữ bản nháp để sửa tiếp, nói rõ lý do
        self.assertIn("Không ghim được", app.notice)
        self.assertNotIn(0, app.s.pins)
        app.cancel_pin()                                    # Esc / Huỷ
        self.assertIsNone(app.draft)
        self.assertIsNone(app.pinning)
        self.assertNotIn(0, app.s.pins)

    def test_draw_dialog_and_key(self):
        app, _ = self.make_app()
        app.handlers["draw_eye"](None)                      # phím N
        d = app._dialogs["draw"]
        self.assertTrue(d.winfo_exists())
        self.assertEqual(app._draw_label_var.get().split()[0], "mattrai")       # frame chưa có mắt nào: mặc định mắt trái
        self.assertEqual(app._draw_kind_var.get(), "track")
        shape = [w for w in self._walk(d) if w.winfo_class() == "TRadiobutton" and "Shape" in str(w.cget("text"))]
        self.assertTrue(shape and "disabled" in shape[0].state())
        app._draw_label_var.set(app._draw_label_values[1])
        box_btn = [w for w in self._walk(d) if w.winfo_class() == "TButton" and "Kéo khung" in str(w.cget("text"))][0]
        box_btn.invoke()
        self.assertEqual((app.pinning, app.draw_label), ("drawbox", "matphai"))
        self.assertFalse(d.winfo_exists())

    def test_editing_a_label_never_moves_the_view(self):
        """Như CVAT: xoay hay sửa nhãn trên một frame không được dời/phóng ảnh; sang frame khác hoặc bấm Vừa khung thì mới canh lại."""
        from eyepin.render import make_view
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(10)
        app.select_eye("mattrai", quiet=True)
        self.assertIsNone(app.manual)
        v = lambda: (app.view.x0, app.view.y0, app.view.k)
        before = v()
        for _ in range(4):
            app.rotate_eye(5)
        self.assertEqual(v(), before)
        app.go(11)                                          # frame khác: vẫn tự canh theo nhãn như trước
        fresh = make_view(app.s, 11, app.render_size, app.anchor, None)
        self.assertEqual(v(), (fresh.x0, fresh.y0, fresh.k))
        app.go(10)
        app.fit()                                           # Vừa khung: canh lại theo nhãn đã xoay
        fresh = make_view(app.s, 10, app.render_size, app.anchor, None)
        self.assertEqual(v(), (fresh.x0, fresh.y0, fresh.k))

    def test_first_pin_on_an_empty_frame_still_zooms_to_the_eyes(self):
        from eyepin.render import make_view
        app, seq = self.make_app()
        empty = (app.view.x0, app.view.y0, app.view.k)
        self.click_pins(app, seq, 0)
        fresh = make_view(app.s, 0, app.render_size, app.anchor, None)
        self.assertEqual((app.view.x0, app.view.y0, app.view.k), (fresh.x0, fresh.y0, fresh.k))
        self.assertNotEqual((fresh.x0, fresh.y0, fresh.k), empty)

    def test_hidden_corner_mode_draws_an_eye_before_all_seven_clicks(self):
        app, seq = self.make_app()
        truth = T.pins_at(0)

        def click(pid):
            sx, sy = app.view.to_screen(truth[pid])
            app.on_press(Ev(sx, sy))
        app.start_pin("hidden")
        for pid in EYES["mattrai"].pins:                    # 4 điểm của mắt thấy đủ trước
            click(pid)
        self.assertIsNotNone(app._preview_pts())
        self.assertIn("Đã vẽ", app.status.get())
        app.start_pin("hidden")
        sp = EYES["matphai"]
        for pid in (sp.first, sp.up, sp.lo):                # 3 điểm của mắt bị che khoé trước
            click(pid)
        pre = app._preview_pts()
        self.assertIsNotNone(pre)
        self.assertEqual(len(pre), 8)
        for pid in EYES["mattrai"].pins:                    # đủ 7 điểm thì vẫn ghim như cũ
            click(pid)
        self.assertIn(0, app.s.pins)
        self.assertIsNone(app.pinning)

    def test_info_box_computes_the_accuracy_report_on_demand(self):
        app, seq = self.make_app()
        self.assertIn("Chưa có mẫu nào", app.accuracy_report())          # chưa ghim: nói rõ thay vì in số
        pins = {str(f): {str(i): list(p) for i, p in T.pins_at(f).items()} for f in (0, 20, 40)}
        app.s.load_pins(pins)
        text = app.accuracy_report()
        for part in ("đường thẳng CVAT", "bám tiến (tool)", "2 mẫu", "đo tại frame ghim bị giấu"):
            self.assertIn(part, text)
        app.show_info()
        d = app._dialogs["info"]
        buttons = [w for w in self._walk(d) if w.winfo_class() == "TButton" and "chính xác" in str(w.cget("text"))]
        self.assertTrue(buttons, "hộp Thông tin cần có nút tính độ chính xác")
        self.assertFalse([w for w in self._walk(d) if w.winfo_class() == "Text"])       # chưa bấm thì chưa tính
        buttons[0].invoke()
        texts = [w for w in self._walk(d) if w.winfo_class() == "Text"]
        self.assertTrue(texts and "bám tiến (tool)" in texts[0].get("1.0", "end"))
        d.destroy()

    @staticmethod
    def _walk(w):
        yield w
        for c in w.winfo_children():
            yield from GuiTests._walk(c)

    def test_autosave_only_when_dirty_and_session_must_match_frames(self):
        app, seq = self.make_app()
        app.save_work(auto=True)
        self.assertFalse(os.path.exists(app.state_path()))           # chưa thay đổi gì: không ghi
        self.click_pins(app, seq, 0)
        app._autosave_tick()
        self.assertTrue(os.path.exists(app.state_path()))
        self.assertIn("Tự lưu", app.notice)
        app.settings["workspace"]["autosave"] = False
        app.s.toggle_pin_here(5)
        app._autosave_tick()
        self.assertTrue(app.s.dirty)                                  # tắt tự lưu thì không ghi
        with self.assertRaises(ValueError):
            app.s.load_state({"version": 1, "frames": 7, "pins": {}})

    def test_icon_toolbar_filter_info_and_fullscreen(self):
        from eyepin.icons import IconButton
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.root.update()
        self.assertIsInstance(app.filter_btn, IconButton)
        app._filter_var.set("pinned"); app.set_filter()
        self.assertTrue(app.filter_btn._active)                     # đang lọc thì nút Lọc được tô
        app._filter_var.set("all"); app.set_filter()
        self.assertFalse(app.filter_btn._active)
        app.handlers["hide_all"](None)
        self.assertTrue(app.eye_btn._active)
        app.handlers["hide_all"](None)
        self.assertFalse(app.eye_btn._active)
        app.handlers["info"](None)
        app.root.update()
        texts = [w.cget("text") for w in app._dialogs["info"].winfo_children() if w.winfo_class() == "TLabel"]
        self.assertIn("Frame ghim", texts)
        self.assertIn("Thống kê (mỗi mắt)", texts)
        self.assertTrue(any(t.startswith("Manually 1 · Interpolated") for t in
                            [w.cget("text") for w in app._dialogs["info"].winfo_children() if w.winfo_class() == "TLabel"]))
        self.assertTrue(any("1" in t for t in texts))
        app.handlers["fullscreen"](None)
        self.assertTrue(app.root.attributes("-fullscreen"))
        app.handlers["cancel"](None)                                 # Esc thoát toàn màn hình khi không đang ghim dở
        self.assertFalse(app.root.attributes("-fullscreen"))
        app.handlers["play"](None)
        self.assertEqual(app.play_btn.glyph, app.play_btn.glyph)
        app.handlers["play"](None)

    def test_rotate_image_keeps_mouse_hits_correct_and_hand_tool_pans(self):
        import numpy as np
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        for r in (1, 2, 3, 0):
            app.rot = 0
            app.rotate(r if r else 0)
            app.rot = r
            app.manual = None
            app.refresh()
            w0, h0 = app.render_size
            px, py = app.view.to_screen(app.s.pins[0][16])
            u, v = {0: (px, py), 1: (h0 - py, px), 2: (w0 - px, h0 - py), 3: (py, w0 - px)}[r]      # chiều xuôi: chưa xoay -> đã xoay
            app.drag = None
            app.on_press(Ev(u, v))
            self.assertIsNotNone(app.drag, f"rot={r}")
            self.assertEqual(app.drag[0], 16)
            app.on_release(Ev(u, v))
        # ảnh hiển thị thật sự bị xoay: kích thước ảnh trên canvas đổi chỗ rộng, cao khi xoay 90 độ
        app.rot = 1
        app.refresh()
        self.assertEqual(app._main.width(), app.main_size[0])
        self.assertEqual(app.render_size, (app.main_size[1], app.main_size[0]))
        app.rot = 0
        # công cụ Dời ảnh: kéo chuột là dời ảnh, không động tới nhãn
        app.set_tool("hand")
        before = dict(app.s.pins[0])
        sx, sy = app.view.to_screen(before[16])
        app.on_press(Ev(sx, sy)); app.on_motion(Ev(sx + 25, sy + 10)); app.on_release(Ev(sx + 25, sy + 10))
        self.assertEqual(app.s.pins[0], before)
        self.assertIsNotNone(app.manual)
        app.set_tool("cursor")
        self.assertTrue(app.tool_btns["cursor"]._active)
        self.assertFalse(app.tool_btns["hand"]._active)

    def test_rotate_a_label_by_handle_and_keys_and_star_toggles_keyframe(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.s.toggle_pin_here(10)
        app.go(10)
        app.root.update()
        # chưa chọn mắt nào: không có tay cầm, phím xoay báo cần chọn
        self.assertIsNone(app._handle_arg())
        app.handlers["eye_rot_cw"](None)
        self.assertIn("Chọn một mắt", app.notice)
        app.tree.selection_set("eye:mattrai")
        self.assertIsNotNone(app._handle_arg())
        before = dict(app.s.pins[10])
        xs = [before[i][0] for i in range(14, 22)]
        ys = [before[i][1] for i in range(14, 22)]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2           # CVAT xoay quanh tâm khung bao thẳng
        app.handlers["eye_rot_cw5"](None)                                    # phím: xoay 5 độ
        after = app.s.pins[10]
        for i in range(14, 22):
            self.assertAlmostEqual(math.dist(after[i], (cx, cy)), math.dist(before[i], (cx, cy)), places=6)     # giữ nguyên khoảng cách tới tâm
        self.assertGreater(max(math.dist(after[i], before[i]) for i in range(14, 22)), 0.5)
        self.assertEqual({i: after[i] for i in range(22, 30)}, {i: before[i] for i in range(22, 30)})           # mắt kia không đổi
        app.handlers["eye_rot_ccw5"](None)
        for i in range(14, 22):
            self.assertLess(math.dist(app.s.pins[10][i], before[i]), 0.05)      # tâm khung đổi chút sau khi xoay nên không về đúng tuyệt đối
        # kéo tay cầm một góc 90 độ
        app.refresh()
        a, h, c, box = app._handle_for("mattrai")
        self.assertAlmostEqual(h[0], c[0])                                   # tay cầm ở giữa, phía trên khung
        self.assertLess(h[1], box[1])
        self.assertIn("MATTRAI #1", app._handle_arg()[3])
        hs = app.view.to_screen(h)
        cs = app.view.to_screen(c)
        vx, vy = hs[0] - cs[0], hs[1] - cs[1]
        tx, ty = cs[0] - vy, cs[1] + vx                                      # quay vectơ tâm->tay cầm 90 độ theo chiều kim đồng hồ
        app.on_press(Ev(*hs)); app.on_motion(Ev(tx, ty)); app.on_release(Ev(tx, ty))
        moved = app.s.pins[10]
        self.assertGreater(max(math.dist(moved[i], before[i]) for i in range(14, 22)), 3)
        for i in range(14, 22):
            self.assertAlmostEqual(math.dist(moved[i], (cx, cy)), math.dist(before[i], (cx, cy)), delta=0.3)
        self.assertTrue(app.s.undo())                                        # một bước hoàn tác
        # ngôi sao trong panel: bấm vào cột ★ thì ghim / bỏ ghim frame
        app.go(10)
        self.assertEqual(app.tree.set("eye:mattrai", "sao"), "★")
        app.go(5)
        self.assertEqual(app.tree.set("eye:mattrai", "sao"), "☆")
        self.assertEqual(app.tree.set("eye:mattrai", "vai"), "skeleton track")
        self.assertTrue(app.tree.item("eye:mattrai", "text").startswith("#1"))

    def test_keyframe_navigation_buttons_of_the_object_panel(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 3)
        app.s.toggle_pin_here(20)
        app.s.toggle_pin_here(40)
        app.go(25)
        app.first_keyframe()
        self.assertEqual(app.f, 3)
        app.last_keyframe()
        self.assertEqual(app.f, 40)
        app.jump_pin(-1)
        self.assertEqual(app.f, 20)

    def test_h_hides_and_shows_labels(self):
        import numpy as np
        from eyepin.render import render_main
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(0)
        shown, _ = render_main(app.s, 0, (960, 460), anchor=app.anchor, manual=app.view)
        app.handlers["hide_all"](None)
        self.assertTrue(app.hide_labels)
        hidden, _ = render_main(app.s, 0, (960, 460), anchor=app.anchor, manual=app.view, hide_labels=True)
        self.assertGreater(int(np.abs(shown.astype(int) - hidden.astype(int)).sum()), 0)       # có nhãn thì ảnh khác
        raw = app.s.bgr(0)
        self.assertEqual(hidden.shape[2], 3)
        # khi ẩn: không kéo được điểm, không đánh cờ được
        before = dict(app.s.pins[0])
        sx, sy = app.view.to_screen(before[16])
        app.on_press(Ev(sx, sy))
        app.on_motion(Ev(sx + 30, sy))
        app.on_release(Ev(sx + 30, sy))
        self.assertEqual(app.s.pins[0], before)
        app.on_hover(Ev(sx, sy))
        app.toggle_flag("occluded")
        self.assertNotIn(0, app.s.flags)
        self.assertIn("đang ẩn", app.notice)
        app.handlers["hide_all"](None)
        self.assertFalse(app.hide_labels)

    def test_scan_fills_the_list_and_export_works(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.scan()
        self.assertGreaterEqual(app.listbox.size(), 1)
        out = os.path.join(self.dir, "e.xml")
        self.assertEqual(app.s.export(out)["path"], out)


def seq_ids(seq):
    return [pid for _, pid in seq]


if __name__ == "__main__":
    unittest.main()
