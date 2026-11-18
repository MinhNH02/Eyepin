"""Giao diện cho mắt kiểu shape (design/2026-11-18-shape-design.md mục 6.2, 6.3): vẽ, nhớ kiểu, xoá, dán, và câu báo cho lệnh shape không có.
Ảnh giả của `test_tracking`. Bỏ qua nếu máy không mở được cửa sổ Tkinter."""
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


def four(label: str, t: int) -> dict:
    truth = T.pins_at(t)
    return {i: truth[i] for i in EYES[label].pins}


class ShapeGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = tempfile.mkdtemp(prefix="eyepin_shape_gui_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def make_app(self):
        from eyepin.gui import App
        app = App(self.root)
        app.ask_restore = lambda n: False                  # test không bật hộp hỏi khôi phục
        os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, os.environ["EYEPIN_HOME"], True)
        app.load(self.dir, None)
        return app

    def draw(self, app, frame, label="mattrai", kind="shape"):
        """Vẽ một mắt ở `frame` đúng như người dùng: begin_draw, bản nháp 4 điểm, Apply."""
        app.go(frame)
        app.begin_draw(label, "points", kind=kind)
        app.pinning, app.clicks = None, []                 # như `_press_draw` sau 4 cú bấm: hết chế độ bấm điểm, còn bản nháp
        app.draft = {"label": label, "four": four(label, frame)}
        app.apply_draft()

    @staticmethod
    def snap(s) -> dict:
        return {"pins": {f: dict(p) for f, p in s.pins.items()}, "flags": {f: dict(fl) for f, fl in s.flags.items()},
                "kind": dict(s.kind), "undo": len(s._undo)}

    def test_draw_shape_stays_on_one_frame(self):
        app = self.make_app()
        self.draw(app, 3)
        self.assertEqual(sorted(app.s.labels), [3])
        self.assertIn("shape mattrai", app.notice)
        self.assertIn("không bám", app.notice)

    def test_kind_is_remembered_and_locked(self):
        app = self.make_app()
        self.assertEqual(app.draw_kind_choice("mattrai"), ("track", False))
        self.draw(app, 3)
        self.assertEqual(app.draw_kind_choice("matphai"), ("shape", False))
        self.assertEqual(app.draw_kind_choice("mattrai"), ("shape", True))
        self.assertEqual(self.make_app().draw_kind_choice("matphai"), ("track", False))

    def test_delete_removes_only_this_frame(self):
        app = self.make_app()
        self.draw(app, 3)
        self.draw(app, 5)
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.delete_label()
        self.assertFalse(app.s.has_shape("mattrai", 3))
        self.assertTrue(app.s.has_shape("mattrai", 5))
        self.assertIn("shape mattrai", app.notice)
        self.assertIn("frame 3", app.notice)
        app.undo()
        self.assertTrue(app.s.has_shape("mattrai", 3))
        self.assertTrue(app.s.has_shape("mattrai", 5))

    def test_k_and_whole_eye_outside_show_a_message(self):
        app = self.make_app()
        self.draw(app, 3)
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        before = self.snap(app.s)
        for act in (app.toggle_pin_here, lambda: app.toggle_flag("outside"), app.end_label_here):
            app.notice = ""
            act()
            self.assertNotEqual(app.notice, "")
            self.assertEqual(self.snap(app.s), before)

    def leave_shape_frame(self, app, frame=6):
        """Chọn mattrai (shape ở frame 3) rồi sang `frame` không có shape của nó: từ Task 8 thẻ của nó biến mất nên lựa chọn bị bỏ."""
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.go(frame)
        self.assertFalse(app.tree.exists("eye:mattrai"))
        self.assertEqual(app.tree.selection(), ())

    def test_flag_on_frame_without_shape_says_no_label(self):
        """Mắt shape đang chọn nhưng frame này không có shape của nó: cờ cả mắt và cờ một điểm không đổi gì, và thông báo nói đúng điều đó.
        Từ Task 8 panel không còn thẻ nào để chọn mắt đó ở frame này, nên lựa chọn được giả lập (`_selected`) để giữ chốt chặn phòng thủ."""
        app = self.make_app()
        self.draw(app, 3)
        self.leave_shape_frame(app)                                # frame không có shape của mattrai
        before = self.snap(app.s)
        app._selected = lambda: ("mattrai", None)                  # cả mắt
        app.notice = ""
        app.toggle_flag("occluded")
        self.assertIn("chưa có nhãn của mattrai", app.notice)
        self.assertNotIn("bỏ", app.notice)
        self.assertEqual(self.snap(app.s), before)
        app._selected = lambda: ("mattrai", 14)                    # một điểm (dòng điểm 14 trong DETAILS)
        app.notice = ""
        app.toggle_flag("occluded")
        self.assertIn("chưa có nhãn của mattrai", app.notice)
        self.assertNotIn("bỏ", app.notice)
        self.assertEqual(self.snap(app.s), before)

    def test_delete_on_frame_without_shape_shows_message(self):
        app = self.make_app()
        self.draw(app, 3)
        self.leave_shape_frame(app)
        before = self.snap(app.s)
        app.notice = ""
        app.delete_label()                                         # không còn gì đang chọn: chỉ nhắc chọn, không đổi gì
        self.assertIn("Chọn một mắt", app.notice)
        self.assertEqual(self.snap(app.s), before)
        app._selected = lambda: ("mattrai", None)                  # chốt chặn phòng thủ: lỗi của session hiện ra, không đổi gì
        app.notice = ""
        app.delete_label()
        self.assertIn("không có shape", app.notice)
        self.assertEqual(self.snap(app.s), before)

    # ---------- Task 8: thẻ SKELETON SHAPE, dòng trạng thái ----------
    def cards(self, app) -> dict:
        return {i: app.tree.item(i, "card") for i in app.tree.get_children()}

    def test_card_only_on_frames_with_a_shape(self):
        app = self.make_app()
        self.draw(app, 3)
        app.go(3)
        c = self.cards(app)
        mine = [i for i in c if i.startswith("eye:mattrai")]
        self.assertEqual(len(mine), 1)
        self.assertEqual(c[mine[0]]["type"], "SKELETON SHAPE")
        self.assertEqual(c[mine[0]]["kind"], "shape")
        self.assertEqual(c[mine[0]]["id"], 1)
        self.assertEqual(c[mine[0]]["status"], "")
        self.assertEqual(app.items_var.get(), f"Items: {len(c)}")
        app.go(4)
        c = self.cards(app)
        self.assertFalse(any(i.startswith("eye:mattrai") for i in c))
        self.assertEqual(app.items_var.get(), f"Items: {len(c)}")

    def test_card_id_follows_the_frame(self):
        app = self.make_app()
        self.draw(app, 3)
        self.draw(app, 5)
        app.go(5)
        card = app.tree.item("eye:mattrai", "card")
        self.assertEqual(card["id"], 10)
        for k in ("keyframe", "has_first", "has_last", "has_prev", "has_next", "outside"):
            self.assertIs(card[k], False, k)
        self.assertEqual(app.tree.card_texts("eye:mattrai")[:2], ("#10", "SKELETON SHAPE"))
        app.select_eye("mattrai", quiet=True)
        self.assertIn("#10", app._handle_arg()[3])                 # chữ cạnh khung chọn trên ảnh: ID của shape ở frame này
        app.go(3)
        self.assertEqual(app.tree.item("eye:mattrai", "card")["id"], 1)

    def test_drawn_id_is_the_shape_id(self):
        """Chữ cạnh mắt trên ảnh (luôn hiện chữ) mang ID của shape ở frame này, không phải số thứ tự label."""
        app = self.make_app()
        self.draw(app, 3)
        self.draw(app, 5)
        app.look.text_always = True
        app.go(5)
        app.refresh()
        texts = [app.canvas.itemcget(i, "text") for i in app.canvas.find_withtag("ov") if app.canvas.type(i) == "text"]
        self.assertTrue(any(t.startswith("#10 MATTRAI") for t in texts), texts)

    def test_status_text_says_shape(self):
        from eyepin.render import status_text
        app = self.make_app()
        self.draw(app, 3)
        text = status_text(app.s, 3)
        self.assertIn("SHAPE", text)
        self.assertNotIn("FRAME GHIM", text)
        self.draw(app, 3, label="matphai", kind="track")          # có một mắt track ghim ở frame này: vẫn là frame ghim
        self.assertIn("FRAME GHIM", status_text(app.s, 3))

    def test_track_cards_unchanged(self):
        app = self.make_app()
        self.draw(app, 3, kind="track")
        app.go(3)
        card = app.tree.item("eye:mattrai", "card")
        self.assertEqual((card["kind"], card["type"], card["status"], card["keyframe"]), ("track", "SKELETON TRACK", "keyframe", True))
        self.root.update_idletasks()
        b = app.tree.buttons("eye:mattrai")
        names = ("first", "prev", "next", "last", "outside", "lock", "occluded", "hidden", "keyframe", "pinned")
        self.assertEqual([n for n in names if b[n].winfo_manager()], list(names))
        self.assertIn("FRAME GHIM", app.status.get())
        self.assertEqual(set(app.tree.get_children()), {"eye:mattrai", "eye:matphai"})

    def test_shape_selected_from_panel_and_dragged_on_its_frame(self):
        """Mắt shape chọn từ panel ở frame có shape: kéo một điểm chỉ sửa shape ở frame đó."""
        from test_gui import Ev
        app = self.make_app()
        self.draw(app, 3)
        self.draw(app, 5)
        app.go(3)
        app.tree.selection_set("eye:mattrai")
        self.assertEqual(app._selected(), ("mattrai", None))
        other = dict(app.s.pins[5])
        before = app.s.pins[3][14]
        sx, sy = app.view.to_screen(before)
        app.hover = (sx, sy)
        self.assertEqual(app._eye_at((sx, sy), visible_only=True), "mattrai")
        self.assertEqual(app._nearest_pin_point((sx, sy), visible_only=True), 14)
        app.on_press(Ev(sx, sy))
        app.on_motion(Ev(sx + 20, sy))
        app.on_release(Ev(sx + 20, sy))
        self.assertGreater(app.s.pins[3][14][0], before[0] + 1)
        self.assertEqual(app.s.pins[5], other)
        self.assertEqual(sorted(app.s.pins), [3, 5])
        app.tree.selection_set("pt:14")                            # dòng điểm của thẻ shape chọn được
        self.assertEqual(app._selected(), ("mattrai", 14))

    def test_shape_only_info_and_keyframe_jump(self):
        """Người chỉ có shape: hộp Thông tin không có dòng "Keyframe khi xuất" rỗng; nhảy keyframe với mắt shape đang chọn nói rõ lý do."""
        app = self.make_app()
        self.draw(app, 3)
        self.assertNotIn("Keyframe khi xuất", [k for k, _ in app._stat_rows()])
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.jump_pin(1)
        self.assertEqual(app.f, 3)
        self.assertIn("shape không có keyframe", app.notice)

    def mixed(self):
        """matphai track + mattrai shape ở frame 3 (cùng một người)."""
        app = self.make_app()
        self.draw(app, 3, label="matphai", kind="track")
        self.draw(app, 3)
        app.go(3)
        return app

    def test_remove_keyframe_menu_on_track_keeps_other_eyes_shape(self):
        """Menu "Bỏ keyframe ở frame này" với mắt TRACK ở frame có shape của mắt kia: chỉ bỏ keyframe của mắt track đó (như K),
        shape và ID của nó còn nguyên; một bước hoàn tác."""
        app = self.mixed()
        sid = app.s.object_id("mattrai", 3)
        undo = len(app.s._undo)
        app.select_eye("matphai", quiet=True)
        app.object_remove()
        self.assertTrue(app.s.has_shape("mattrai", 3))
        self.assertEqual(app.s.object_id("mattrai", 3), sid)
        self.assertEqual(app.s.eye_keyframes("matphai"), [])
        self.assertEqual(len(app.s._undo), undo + 1)
        self.assertIn("matphai", app.notice)
        app.undo()
        self.assertEqual(app.s.eye_keyframes("matphai"), [3])
        self.assertEqual(app.s.object_id("mattrai", 3), sid)

    def test_remove_whole_pin_refuses_when_a_shape_is_here(self):
        """Lệnh bỏ cả frame ghim (`App.remove_pin`) ở frame có shape: không đổi gì, báo lý do."""
        app = self.mixed()
        before = self.snap(app.s)
        app.notice = ""
        app.remove_pin()
        self.assertEqual(self.snap(app.s), before)
        self.assertIn("shape", app.notice)

    def test_remove_keyframe_menu_refuses_locked_shape(self):
        app = self.make_app()
        self.draw(app, 3)
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.toggle_lock()
        before = self.snap(app.s)
        app.object_remove()
        self.assertEqual(self.snap(app.s), before)
        self.assertIn("khoá", app.notice)

    def test_remove_keyframe_menu_on_shape_keeps_other_eye(self):
        """Menu "Bỏ keyframe ở frame này" với mắt shape: chỉ xoá shape đó ở frame này (như Del), mắt track kia giữ keyframe."""
        app = self.make_app()
        self.draw(app, 3, label="matphai", kind="track")
        self.draw(app, 3)
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.object_remove()
        self.assertFalse(app.s.has_shape("mattrai", 3))
        self.assertEqual(app.s.eye_keyframes("matphai"), [3])
        self.assertIn("shape mattrai", app.notice)

    def test_paste_shape_to_another_frame(self):
        app = self.make_app()
        self.draw(app, 3)
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.object_copy()
        app.go(8)
        app.paste_pins()
        self.assertTrue(app.s.has_shape("mattrai", 8))
        self.assertIn("thành shape mới", app.notice)

    def test_propagate_from_app_keeps_other_eyes_shapes(self):
        """C1 qua `App.object_propagate`: shape mattrai ở 3 nhân sang 4, 5; shape matphai ở 4, 5 còn nguyên; câu báo nói là shape mới."""
        app = self.make_app()
        self.draw(app, 3)
        self.draw(app, 4, label="matphai")
        self.draw(app, 5, label="matphai")
        rid = dict(app.s.shape_ids["matphai"])
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.object_propagate(count=2)
        self.assertEqual(app.s.shape_ids["matphai"], rid)
        for f in (4, 5):
            self.assertTrue(app.s.has_shape("matphai", f))
            self.assertTrue(app.s.has_shape("mattrai", f))
        self.assertIn("shape mới", app.notice)
        self.assertNotIn("frame ghim", app.notice)

    def test_propagate_track_notice_unchanged(self):
        app = self.make_app()
        self.draw(app, 3, kind="track")
        self.draw(app, 3, label="matphai", kind="track")
        app.go(3)
        app.select_eye("mattrai", quiet=True)
        app.object_propagate(count=2)
        self.assertEqual(app.notice, "Đã nhân nhãn sang 2 frame (các frame sau); mỗi frame thành frame ghim.")

    def test_clear_after_keeps_shapes(self):
        """I2: "Xoá mọi keyframe sau frame này" ở người có cả track lẫn shape: chỉ bỏ keyframe của mắt track; shape còn nguyên, câu báo nói đúng."""
        app = self.make_app()
        self.draw(app, 0, label="matphai", kind="track")
        self.draw(app, 6, label="matphai", kind="track")
        self.draw(app, 5)
        self.draw(app, 8)
        ids = dict(app.s.shape_ids["mattrai"])
        app.go(4)
        undo = len(app.s._undo)
        app.run_action("clear_after")
        self.assertEqual(app.s.eye_keyframes("matphai"), [0])
        self.assertEqual(app.s.shape_ids["mattrai"], ids)
        self.assertTrue(app.s.has_shape("mattrai", 5) and app.s.has_shape("mattrai", 8))
        self.assertEqual(app.notice, "Đã xoá 1 keyframe sau frame 4; giữ nguyên 2 shape.")
        self.assertEqual(len(app.s._undo), undo + 1)
        app.undo()
        self.assertEqual(app.s.eye_keyframes("matphai"), [0, 6])

    def test_clear_after_track_only_unchanged(self):
        app = self.make_app()
        for f in (0, 6, 9):
            self.draw(app, f, kind="track")
        app.go(4)
        app.run_action("clear_after")
        self.assertEqual(sorted(app.s.pins), [0])
        self.assertEqual(app.notice, "Đã xoá 2 keyframe sau frame 4.")

    def test_track_drawing_unchanged(self):
        app = self.make_app()
        self.draw(app, 3, kind="track")
        self.assertEqual(app.s.eye_kind("mattrai"), "track")
        self.assertTrue({3, 4, 5, T.N - 1} <= set(app.s.labels))
        self.assertEqual(app.notice, "Đã ghim mattrai ở frame 3 (track): tool bám mắt này sang các frame sau.")

    def test_draw_dialog_has_working_shape_radio_and_locks(self):
        app = self.make_app()
        self.draw(app, 3)
        app.go(3)                                                    # mattrai đã có shape ở frame này: bảng chọn sẵn matphai
        app.start_draw()
        d = app._dialogs["draw"]
        self.addCleanup(d.destroy)
        self.assertEqual(app._draw_kind_var.get(), "shape")          # matphai chưa có nhãn: theo kiểu vẽ gần nhất, không khoá
        radios = {w.cget("value"): w for w in d.winfo_children() if w.winfo_class() == "TRadiobutton"}
        self.assertNotIn("disabled", radios["shape"].state())
        self.assertNotIn("disabled", radios["track"].state())
        self.assertEqual(app._draw_kind_note.get(), "")
        app._draw_label_var.set(app._draw_label_values[0])           # đổi sang mattrai (đã là shape): khoá
        app._draw_label_changed()
        self.assertEqual(app._draw_kind_var.get(), "shape")
        self.assertIn("disabled", radios["track"].state())
        self.assertEqual(app._draw_kind_note.get(), "Mắt này đang là shape. Muốn vẽ kiểu khác: xoá nhãn của nó hoặc thêm người mới (+).")


if __name__ == "__main__":
    unittest.main()
