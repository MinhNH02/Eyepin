"""Đợt sửa sau final review của thanh bên kiểu CVAT (.superpowers/sdd/cvat-sidebar/progress.md, "Final review").

I1  phím theo con trỏ (Del, h, l, q/o) và phím xoay `, . < >` không tác động mắt/điểm đang ẩn.
I2  Hidden / Lock / Pinned đi theo mắt khi đổi label (ô label trên thẻ, menu ⋮) và bị quên khi xoá mắt.
I3  "+" / Ctrl+N khi đang chọn thẻ của người 1: 8 điểm bấm vào người MỚI, người 1 không đổi.
M1  `L` và nút khoá tất cả khoá / mở khoá MỌI người.
M2  nút Hidden của thẻ mờ khi label đang ẩn ở tab Labels.
M3  bật lại tab Frame lân cận không để lỗi CVAT lọt ra.
M4  rê chuột vào/ra thẻ không vẽ lại ảnh thu nhỏ và dải thời gian.
M5  mở DETAILS của một thẻ cập nhật nút mở/thu ở đầu danh sách.
M6  chỉ một chuỗi `_tick` khi phát; dừng / đóng cửa sổ thì huỷ hẹn giờ.
M8  bấm chỗ trống không chọn người khác qua mắt đang ẩn của người đó.
"""
import os
import re
import shutil
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")

import test_tracking as T  # noqa: E402
from eyepin.cvatapi import CvatError  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402

ML, MR = EYES["mattrai"], EYES["matphai"]


class Ev:
    def __init__(self, x=0, y=0, widget=None):
        self.x, self.y, self.widget = x, y, widget
        self.x_root, self.y_root = x, y


class FinalFixCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = tempfile.mkdtemp(prefix="eyepin_finalfix_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def make_app(self, pin=True):
        from eyepin.gui import App, PIN_SEQ
        os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, os.environ["EYEPIN_HOME"], True)
        app = App(self.root)
        app.ask_restore = lambda n: False
        self.addCleanup(self.close_app, app)
        app.load(self.dir, None)
        if pin:
            truth = T.pins_at(0)
            app.go(0)
            app.start_pin()
            for _, pid in PIN_SEQ:
                app.on_press(Ev(*app.view.to_screen(truth[pid])))
            self.assertIn(0, app.s.pins, app.notice)
        return app

    def close_app(self, app):
        for name in ("_autosave_job", "_thumb_job", "_motion_job", "_play_job"):
            job = getattr(app, name, None)
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass

    @staticmethod
    def shifted():
        """8 điểm ghim của người 2: người 1 dịch (40, 60) px (như test_object_hide_lock)."""
        truth = T.pins_at(0)
        return [(x + 40, y + 60) for x, y in (truth[i] for spec in EYES.values() for i in spec.pins)]

    def two_people(self):
        app = self.make_app()
        app.new_object()
        app.s.add_pin_free(0, self.shifted())
        app.pinning, app.clicks = None, []
        app.refresh()
        self.assertEqual((len(app.s.layers), app.s.cur), (2, 1))
        return app

    @staticmethod
    def center(app, label, layer=None):
        """Tâm mắt `label` (của người `layer`, mặc định người đang chọn) trên màn hình."""
        s = app.s
        pts = s.layers[layer].labels[app.f].points if layer is not None else app._current_points()
        ids = EYES[label].ids
        return app.view.to_screen((sum(pts[i][0] for i in ids) / len(ids), sum(pts[i][1] for i in ids) / len(ids)))

    @staticmethod
    def pins0(app, layer=None):
        s = app.s
        pins = s.layers[layer].pins if layer is not None else s.pins
        return {i: tuple(p) for i, p in pins.get(0, {}).items()}

    def pending_ticks(self) -> int:
        """Số hẹn giờ `after` của `App._tick` đang chờ trong cửa sổ gốc (tên lệnh Tk là `<số>_tick`)."""
        tk_ = self.root.tk
        n = 0
        for i in tk_.splitlist(tk_.call("after", "info")):
            try:
                script = str(tk_.splitlist(tk_.call("after", "info", i))[0])
            except tk.TclError:
                continue
            n += bool(re.fullmatch(r"\d+_tick", script))
        return n


class PointerKeysSkipHiddenTests(FinalFixCase):
    """I1: Del / h / l / q / o theo con trỏ chỉ nhắm mắt/điểm đang HIỆN; không có thì dùng thẻ đang chọn."""

    def test_del_after_h_deletes_selected_eye_not_the_hidden_one_under_pointer(self):
        app = self.make_app()
        app.select_eye("matphai", quiet=True)
        app.hover = self.center(app, "mattrai")
        app.handlers["hide"]()                                           # mattrai đang hiện dưới con trỏ: h ẩn nó (và chọn thẻ của nó, B01)
        self.assertEqual(app.hidden_objs, {(0, "mattrai")})
        app.select_eye("matphai", quiet=True)                            # người dùng chọn lại thẻ matphai
        app.handlers["delete"]()                                         # con trỏ vẫn ở đó, trên mắt đã ẩn
        pins = self.pins0(app)
        self.assertIn(14, pins, app.notice)                              # mắt ẩn không bị xoá
        self.assertNotIn(22, pins, app.notice)                           # xoá mắt đang chọn
        self.assertIn("matphai", app.notice)

    def test_h_over_hidden_eye_acts_on_the_selected_card(self):
        app = self.make_app()
        app.select_eye("matphai", quiet=True)
        app.hover = self.center(app, "mattrai")
        app.handlers["hide"]()                                           # ẩn mattrai và chọn thẻ của nó (B01)
        app.select_eye("matphai", quiet=True)                            # người dùng chọn lại thẻ matphai
        app.handlers["hide"]()                                           # con trỏ trên mắt đã ẩn: tác động thẻ đang chọn
        self.assertEqual(app.hidden_objs, {(0, "mattrai"), (0, "matphai")})
        app.select_eye("mattrai", quiet=True)                            # hiện lại mắt ẩn: qua thẻ của nó
        app.handlers["hide"]()
        self.assertEqual(app.hidden_objs, {(0, "matphai")})

    def test_l_skips_hidden_eye_under_pointer(self):
        app = self.make_app()
        app.select_eye("matphai", quiet=True)
        app.hidden_objs.add((0, "mattrai"))
        app.hover = self.center(app, "mattrai")
        app.handlers["lock"]()
        self.assertIn("matphai", app.locked)
        self.assertNotIn("mattrai", app.locked)

    def test_q_near_hidden_point_does_not_flag_it(self):
        app = self.make_app()
        app.hidden_objs.add((0, "mattrai"))
        app.tree.selection_remove(*app.tree.selection())
        app.hover = app.view.to_screen(app._current_points()[14])
        before = dict(app.s.flags_at(0))
        app.handlers["occluded"]()                                       # không điểm hiện nào gần, không chọn gì: chỉ nhắc
        self.assertEqual(dict(app.s.flags_at(0)), before)
        app.select_eye("matphai", quiet=True)
        app.hover = app.view.to_screen(app._current_points()[14])
        app.handlers["occluded"]()                                       # rơi về thẻ đang chọn: cả matphai
        flags = app.s.flags_at(0)
        self.assertNotEqual(flags.get(14), "occluded")
        self.assertTrue(all(flags.get(i) == "occluded" for i in MR.ids), flags)

    def test_label_level_hidden_eye_is_skipped_by_del(self):
        app = self.make_app()
        app.select_eye("matphai", quiet=True)
        app._toggle_label_visible("mattrai")                             # ẩn label mattrai ở tab Labels
        app.hover = self.center(app, "mattrai")
        app.handlers["delete"]()
        pins = self.pins0(app)
        self.assertIn(14, pins)
        self.assertNotIn(22, pins)

    def test_keys_with_all_labels_hidden_use_the_selection(self):
        app = self.make_app()
        app.select_eye("matphai", quiet=True)
        app.toggle_labels()                                              # H: ẩn mọi nhãn
        self.assertTrue(app.hide_labels)
        app.hover = self.center(app, "mattrai")
        app.handlers["lock"]()
        self.assertEqual(set(app.locked), {"matphai"})
        app.handlers["delete_force"]()
        pins = self.pins0(app)
        self.assertIn(14, pins)
        self.assertNotIn(22, pins)

    def test_rotate_keys_refuse_a_hidden_eye(self):
        app = self.make_app()
        app.select_eye("mattrai", quiet=True)
        app.hover = None
        before = self.pins0(app)
        app.hidden_objs.add((0, "mattrai"))
        for aid in ("eye_rot_cw", "eye_rot_ccw5"):
            app.handlers[aid]()
            self.assertEqual(self.pins0(app), before, aid)
            self.assertIn("ẩn", app.notice, aid)
        app.hidden_objs.clear()
        app.toggle_labels()                                              # H: ẩn mọi nhãn
        app.handlers["eye_rot_cw"]()
        self.assertEqual(self.pins0(app), before)
        app.toggle_labels()
        app.handlers["eye_rot_cw"]()                                     # đối chứng: hiện thì xoay được
        self.assertNotEqual(self.pins0(app), before)


class StateFollowsEyeTests(FinalFixCase):
    """I2: Hidden / Lock / Pinned gắn với mắt, không với tên label."""

    def test_label_swap_refused_when_an_eye_is_locked(self):
        app = self.make_app()
        app.locked.add("mattrai")
        before = self.pins0(app)
        app.tree.label_picker("eye:matphai").set("mattrai")             # ô label của thẻ KHÔNG khoá
        app._on_object_action("label", "eye:matphai")
        self.assertEqual(self.pins0(app), before)
        self.assertIn("khoá", app.notice)
        app.swap_labels()                                                # menu ⋮ "Đổi label" cũng bị chặn
        self.assertEqual(self.pins0(app), before)
        self.assertEqual(set(app.locked), {"mattrai"})

    def test_label_swap_moves_hidden_and_pinned_with_the_eye(self):
        app = self.two_people()
        app.hidden_objs.add((1, "mattrai"))                              # người 2: không được đổi
        app.tree.selection_set("eye:mattrai")
        self.assertEqual(app.s.cur, 0)
        app.hidden_objs.add((0, "mattrai"))
        app.pinned_eyes.add("matphai")
        before = self.pins0(app, 0)
        app.tree.label_picker("eye:mattrai").set("matphai")
        app._on_object_action("label", "eye:mattrai")
        after = self.pins0(app, 0)
        self.assertEqual(after[22], before[14])                          # dữ liệu đã đổi chỗ
        self.assertEqual(app.hidden_objs, {(0, "matphai"), (1, "mattrai")})
        with app.s.layer_ctx(0):
            self.assertEqual(set(app.pinned_eyes), {"mattrai"})
        with app.s.layer_ctx(1):
            self.assertEqual(set(app.pinned_eyes), set())

    def test_delete_forgets_hidden_and_pinned_state(self):
        app = self.make_app()
        app.hidden_objs.add((0, "mattrai"))
        app.pinned_eyes.add("mattrai")
        app.select_eye("mattrai", quiet=True)
        app.hover = None
        app.handlers["delete"]()
        self.assertNotIn(14, self.pins0(app))
        self.assertNotIn((0, "mattrai"), app.hidden_objs)
        self.assertNotIn("mattrai", app.pinned_eyes)
        self.assertFalse(app._obj_hidden(0, "mattrai"))                  # vẽ lại mắt này thì nó hiện

    def test_deleting_last_eye_of_person2_keeps_person1_lock(self):
        app = self.two_people()
        with app.s.layer_ctx(0):
            app.locked.add("matphai")
        app.hover = None
        for iid in ("eye:mattrai@1", "eye:matphai@1"):
            app.tree.selection_set(iid)
            app.delete_label(force=True)
        self.assertEqual((len(app.s.layers), app.s.cur), (1, 0))         # bộ rỗng tự bỏ
        self.assertIn("matphai", app.locked)                             # khoá của người 1 còn nguyên


class NewObjectTests(FinalFixCase):
    def test_new_object_with_person1_selected_pins_the_new_person(self):
        """I3: "+" khi đang chọn thẻ người 1: 8 điểm vào người mới, người 1 không đổi."""
        app = self.make_app()
        app.select_eye("mattrai", quiet=True)
        before = self.pins0(app)
        app.new_object()
        for p in self.shifted():
            app.on_press(Ev(*app.view.to_screen(p)))
            app.on_release(Ev(*app.view.to_screen(p)))
        self.assertEqual(len(app.s.layers), 2, app.notice)
        self.assertEqual(self.pins0(app, 0), before)
        self.assertEqual(set(self.pins0(app, 1)), set(ML.ids) | set(MR.ids), app.notice)       # người mới có đủ hai mắt
        self.assertEqual(app.s.cur, 1)


class LockAllTests(FinalFixCase):
    def lock_state(self, app):
        out = {}
        for layer in range(len(app.s.layers)):
            with app.s.layer_ctx(layer):
                out[layer] = set(app.locked)
        return out

    def test_lock_all_key_and_header_lock_every_person(self):
        """M1: `L` / nút khoá tất cả tác động mọi người; icon khoá chỉ đặc khi mọi mắt của mọi người đều khoá."""
        app = self.two_people()
        hb = app.obj_head_btns["lock_all"]
        app.handlers["lock_all"]()
        self.assertEqual(self.lock_state(app), {0: set(EYES), 1: set(EYES)})
        self.assertEqual(hb.name, "lock")
        app.locked.discard("matphai")                                    # mở khoá một mắt của người 2
        app.refresh()
        self.assertEqual(hb.name, "unlock")
        hb._click(None)                                                  # chưa khoá hết: khoá hết
        self.assertEqual(self.lock_state(app), {0: set(EYES), 1: set(EYES)})
        hb._click(None)                                                  # đã khoá hết: mở khoá hết
        self.assertEqual(self.lock_state(app), {0: set(), 1: set()})
        self.assertEqual(hb.name, "unlock")

    def test_lock_all_header_icon_ignores_a_person_fully_locked_alone(self):
        app = self.two_people()
        app.locked.update(EYES)                                          # chỉ người 2 khoá hết
        app.refresh()
        self.assertEqual(app.obj_head_btns["lock_all"].name, "unlock")


class CardHiddenWhileLabelHiddenTests(FinalFixCase):
    def test_card_hidden_button_disabled_while_label_hidden(self):
        """M2: label ẩn ở tab Labels: nút Hidden của thẻ mờ (chữ khi trỏ chuột giải thích), bấm không đổi trạng thái riêng."""
        app = self.make_app()
        b = lambda label: app.tree.buttons(f"eye:{label}")["hidden"]
        self.assertTrue(b("mattrai")._enabled)
        app._toggle_label_visible("mattrai")
        self.assertFalse(app.look.eyes["mattrai"])
        self.assertFalse(b("mattrai")._enabled)
        self.assertTrue(b("matphai")._enabled)
        self.assertIn("tab Labels", app.tree.tip_for("hidden", "eye:mattrai"))
        self.assertEqual(app.tree.tip_for("hidden", "eye:matphai"), app.tree.tip("hidden"))
        app._on_object_action("hidden", "eye:mattrai")                   # gọi thẳng (như phím h trên thẻ đang chọn)
        self.assertEqual(app.hidden_objs, set())
        self.assertIn("tab Labels", app.notice)
        app._toggle_label_visible("mattrai")                             # hiện label lại: nút bật lại, mắt hiện
        self.assertTrue(b("mattrai")._enabled)
        self.assertFalse(app._obj_hidden(0, "mattrai"))


class NeighborsTabTests(FinalFixCase):
    def test_turning_neighbors_tab_on_does_not_raise_cvat_errors(self):
        """M3: bật tab Frame lân cận khi đọc frame lỗi: không ném CvatError ra Tk, lỗi thành thông báo khi ảnh nhỏ được vẽ."""
        from eyepin import gui
        app = self.make_app()
        app.set_neighbors_tab(False)
        with mock.patch.object(gui, "render_thumb", side_effect=CvatError("Mất kết nối CVAT (thử)")):
            app.set_neighbors_tab(True)                                  # trước đây: CvatError lọt ra
            job = app._thumb_job
            self.assertIsNotNone(job)
            self.root.after_cancel(job)                                  # chạy nhịp đó ngay tại đây thay vì đợi 150 ms
            app._thumbs_tick()
        self.assertIn("Mất kết nối CVAT (thử)", app.notice)


class CardHoverRedrawTests(FinalFixCase):
    def test_card_hover_redraw_skips_thumbnails_and_timeline(self):
        """M4: con trỏ vào/ra thẻ chỉ vẽ lại phần nhãn (mắt đậm), không tính lại ảnh thu nhỏ và dải thời gian."""
        app = self.make_app()
        app.refresh()
        self.root.update_idletasks()
        with mock.patch.object(app, "_schedule_thumbs") as sched, mock.patch.object(app, "_update_timeline") as tl:
            app._on_card_hover("eye:matphai")
            self.root.update_idletasks()
            outline = app.canvas.find_withtag("outline:matphai")
            self.assertGreater(float(app.canvas.itemcget(outline[0], "width")), 1.0)    # vẫn vẽ mắt đậm
            app._on_card_hover(None)
            self.root.update_idletasks()
            self.assertEqual((sched.call_count, tl.call_count), (0, 0))
            app._motion_refresh()                                        # đối chứng: kéo chuột vẫn hẹn vẽ ảnh nhỏ
            self.root.update_idletasks()
            self.assertEqual(sched.call_count, 1)


class HeaderCaretTests(FinalFixCase):
    def test_opening_one_card_details_updates_header_caret(self):
        """M5: mở DETAILS của một thẻ: nút mở/thu tất cả ở đầu danh sách đổi theo."""
        app = self.make_app()
        hb = app.obj_head_btns["collapse"]
        self.assertEqual(hb.name, "caret_down")
        app.tree.buttons("eye:mattrai")["caret"]._click(None)
        self.assertTrue(app.tree.item("eye:mattrai", "open"))
        self.assertEqual(hb.name, "caret_up")
        app.tree.buttons("eye:mattrai")["caret"]._click(None)
        self.assertEqual(hb.name, "caret_down")


class PlayTimerTests(FinalFixCase):
    def test_space_pressed_quickly_keeps_one_tick_chain(self):
        """M6: Space bật/tắt nhanh chỉ để lại một chuỗi `_tick`; dừng thì không còn hẹn giờ nào."""
        app = self.make_app()
        base = self.pending_ticks()
        app.handlers["play"]()
        app.handlers["play"]()
        app.handlers["play"]()                                           # bật - tắt - bật thật nhanh
        self.assertTrue(app.playing)
        self.assertEqual(self.pending_ticks() - base, 1)
        app._tick()                                                      # một nhịp (như hẹn giờ chạy): vẫn một chuỗi
        self.assertEqual(self.pending_ticks() - base, 1)
        app.handlers["play"]()                                           # dừng
        self.assertEqual(self.pending_ticks() - base, 0)

    def test_play_to_the_end_leaves_no_timer(self):
        app = self.make_app()
        base = self.pending_ticks()
        app.go(app.s.n_frames - 3)
        app.toggle_play()
        for _ in range(4):
            app._tick()
        self.assertFalse(app.playing)
        self.assertEqual(self.pending_ticks() - base, 0)

    def test_close_cancels_the_play_timer(self):
        app = self.make_app()
        base = self.pending_ticks()
        app.toggle_play()
        self.assertEqual(self.pending_ticks() - base, 1)
        app.confirm_close = lambda: True
        with mock.patch.object(app.root, "destroy"):
            app.on_close()
        self.assertEqual(self.pending_ticks() - base, 0)


class PickLayerTests(FinalFixCase):
    def test_click_on_hidden_eye_of_another_person_does_not_switch(self):
        """M8: bấm chỗ (trống) có mắt ẩn của người khác: không chuyển người, không báo "Mắt này đang ẩn"."""
        app = self.two_people()
        app.go(0)
        app.tree.selection_set("eye:mattrai")
        self.assertEqual(app.s.cur, 0)
        app.hidden_objs.add((1, "mattrai"))                              # ẩn riêng mắt trái của người 2
        app._toggle_label_visible("matphai")                             # ẩn label matphai (mọi người)
        for label in ("mattrai", "matphai"):
            xy = self.center(app, label, layer=1)
            self.assertIsNone(app._eye_at(xy), label)                    # chỗ bấm không có mắt nào của người 1
            app.notice = ""
            app.on_press(Ev(*xy))
            app.on_release(Ev(*xy))
            self.assertEqual(app.s.cur, 0, label)
            self.assertNotIn("đang ẩn", app.notice, label)
        app.hidden_objs.clear()                                          # đối chứng: mắt hiện thì bấm vào nó chuyển người
        xy = self.center(app, "mattrai", layer=1)
        app.on_press(Ev(*xy))
        app.on_release(Ev(*xy))
        self.assertEqual(app.s.cur, 1)


if __name__ == "__main__":
    unittest.main()
