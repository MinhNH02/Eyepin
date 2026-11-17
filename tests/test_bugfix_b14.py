"""B14 (buglist.md): Caps Lock làm hỏng phím tắt chữ.

Tk trên Windows báo Caps Lock bằng bit 0x2 (Lock) và đổi hoa/thường của keysym: Ctrl+Z khi Caps Lock bật tới ứng dụng là keysym `Z`
(state 0x6), không khớp binding `<Control-z>` (undo) mà khớp `<Control-Z>` (redo); Ctrl+S thành Ctrl+Shift+S (xuất file); `h` thành
`H` (ẩn mọi nhãn thay vì ẩn một mắt). Sau khi sửa: chữ hoa chỉ do Caps Lock (bit Lock) không được coi là Shift; Shift thật (bit 0x1)
vẫn đổi hành động (H = ẩn mọi nhãn). Bit NumLock (0x8, không phải Alt trên Windows) vẫn không ảnh hưởng (tests/test_keys_focus.py)."""
import os
import shutil
import sys
import tempfile
import tkinter as tk
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")      # không đụng cài đặt thật của người dùng

from eyepin import shortcuts as sc  # noqa: E402
import test_tracking as T  # noqa: E402

CTRL, LOCK, SHIFT, NUM = 0x4, 0x2, 0x1, 0x8


class Ev:
    """Sự kiện phím giả đủ cho `App._key_dispatch` (không cần focus thật)."""
    def __init__(self, keysym, state):
        self.keysym, self.state, self.widget = keysym, state, None


class EventToSeqCapsTests(unittest.TestCase):
    def test_caps_lock_letters_are_not_shift(self):
        # Caps Lock bật, không giữ Shift: keysym là chữ hoa nhưng người dùng bấm chữ thường
        self.assertEqual(sc.event_to_seq("H", LOCK), "h")
        self.assertEqual(sc.event_to_seq("Z", CTRL | LOCK), "<Control-z>")
        self.assertEqual(sc.event_to_seq("S", CTRL | LOCK), "<Control-s>")

    def test_caps_lock_with_real_shift_is_shift(self):
        # Caps Lock bật và giữ Shift: keysym là chữ thường nhưng người dùng bấm chữ hoa
        self.assertEqual(sc.event_to_seq("h", LOCK | SHIFT), "H")
        self.assertEqual(sc.event_to_seq("s", CTRL | LOCK | SHIFT), "<Control-S>")
        self.assertEqual(sc.event_to_seq("z", CTRL | LOCK | SHIFT), "<Control-Z>")

    def test_without_caps_lock_unchanged(self):
        self.assertEqual(sc.event_to_seq("h", 0), "h")
        self.assertEqual(sc.event_to_seq("H", SHIFT), "H")
        self.assertEqual(sc.event_to_seq("z", CTRL), "<Control-z>")
        self.assertEqual(sc.event_to_seq("Z", CTRL | SHIFT), "<Control-Z>")

    def test_numlock_and_caps_lock_together(self):
        self.assertEqual(sc.event_to_seq("Z", CTRL | LOCK | NUM), "<Control-z>")
        self.assertEqual(sc.event_to_seq("D", LOCK | NUM), "d")

    def test_caps_lock_leaves_non_letters_alone(self):
        self.assertEqual(sc.event_to_seq("Delete", LOCK), "<Delete>")
        self.assertEqual(sc.event_to_seq("Right", LOCK | SHIFT), "<Shift-Right>")
        self.assertEqual(sc.event_to_seq("period", LOCK), "<period>")
        self.assertEqual(sc.event_to_seq("1", CTRL | LOCK), "<Control-Key-1>")

    def test_caps_variant(self):
        self.assertEqual(sc.caps_variant("h"), "H")
        self.assertEqual(sc.caps_variant("L"), "l")
        self.assertEqual(sc.caps_variant("<Control-z>"), "<Control-Z>")
        self.assertEqual(sc.caps_variant("<Control-S>"), "<Control-s>")
        self.assertIsNone(sc.caps_variant("<Shift-Right>"))
        self.assertIsNone(sc.caps_variant("<period>"))
        self.assertIsNone(sc.caps_variant("<Delete>"))
        self.assertIsNone(sc.caps_variant("1"))


class CapsLockKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b14_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        from eyepin.gui import App
        app = self.app = App(self.root)
        app.ask_restore = lambda n: False
        app.load(self.dir, None)
        self.fired = []
        orig = app._actions

        def spied():
            # save/export mở hộp chọn file (chặn chương trình): chỉ ghi nhận, không chạy thật
            return {aid: (lambda fn=fn, aid=aid: (self.fired.append(aid), None if aid in ("save", "export") else fn()))
                    for aid, fn in orig().items()}
        app._actions = spied
        app._bind_keys()
        app.hover = None

    def press(self, keysym, state):
        self.fired.clear()
        res = self.app._key_dispatch(Ev(keysym, state))
        return list(self.fired), res

    def test_ctrl_z_with_caps_lock_is_undo(self):
        self.assertEqual(self.press("Z", CTRL | LOCK)[0], ["undo"])

    def test_ctrl_z_without_caps_lock_is_undo(self):
        self.assertEqual(self.press("z", CTRL)[0], ["undo"])

    def test_ctrl_shift_z_is_redo_with_or_without_caps_lock(self):
        self.assertEqual(self.press("Z", CTRL | SHIFT)[0], ["redo"])
        self.assertEqual(self.press("z", CTRL | SHIFT | LOCK)[0], ["redo"])

    def test_ctrl_s_saves_and_ctrl_shift_s_exports_under_caps_lock(self):
        self.assertEqual(self.press("S", CTRL | LOCK)[0], ["save"])
        self.assertEqual(self.press("s", CTRL | SHIFT | LOCK)[0], ["export"])
        self.assertEqual(self.press("S", CTRL | SHIFT)[0], ["export"])
        self.assertEqual(self.press("s", CTRL)[0], ["save"])

    def test_plain_letters_under_caps_lock(self):
        for ks, aid in (("Q", None), ("O", "outside"), ("K", "keyframe"), ("F", "frame_next"), ("D", "frame_prev")):
            fired, _ = self.press(ks, LOCK)
            if aid:
                self.assertEqual(fired, [aid], ks)

    def test_shift_letters_distinguished_from_caps_lock(self):
        # h = ẩn một mắt, H (Shift thật) = ẩn mọi nhãn; l / L tương tự; Caps Lock không đổi điều đó
        self.assertEqual(self.press("H", LOCK)[0], ["hide"])
        self.assertEqual(self.press("h", LOCK | SHIFT)[0], ["hide_all"])
        self.assertEqual(self.press("H", SHIFT)[0], ["hide_all"])
        self.assertEqual(self.press("h", 0)[0], ["hide"])
        self.assertEqual(self.press("L", LOCK)[0], ["lock"])
        self.assertEqual(self.press("l", LOCK | SHIFT)[0], ["lock_all"])
        self.assertEqual(self.press("L", SHIFT)[0], ["lock_all"])

    def test_numlock_does_not_break_letters(self):
        self.assertEqual(self.press("z", CTRL | NUM)[0], ["undo"])
        self.assertEqual(self.press("Z", CTRL | LOCK | NUM)[0], ["undo"])

    def test_unbound_letter_is_not_swallowed(self):
        fired, res = self.press("Y", LOCK)           # y không gán cho hành động nào
        self.assertEqual(fired, [])
        self.assertNotEqual(res, "break")

    def test_tk_bindings_exist_for_both_cases(self):
        # Tk chọn binding theo keysym thật: cả hai chữ hoa/thường phải có binding để Caps Lock không làm phím rơi vào khoảng trống
        r = self.root
        for seq in ("<Control-z>", "<Control-Z>", "<Control-s>", "<Control-S>", "h", "H", "l", "L", "q", "Q", "o", "O"):
            self.assertTrue(r.bind(seq), seq)

    def test_rebind_to_other_letter_works_under_caps_lock(self):
        app = self.app
        self.assertIsNone(app.rebind("outside", "j"))
        self.assertEqual(self.press("J", LOCK)[0], ["outside"])
        self.assertEqual(self.press("j", 0)[0], ["outside"])
        self.assertEqual(self.press("o", 0)[0], [])
        app.rebind("outside", None)
        self.assertEqual(self.press("O", LOCK)[0], ["outside"])

    def test_typing_in_frame_box_still_blocks_shortcuts(self):
        app = self.app
        app._typing = lambda: True
        self.assertEqual(self.press("Z", CTRL | LOCK)[0], [])


@unittest.skipUnless(os.environ.get("EYEPIN_REAL_FOCUS") == "1", "đặt EYEPIN_REAL_FOCUS=1 để chạy (mở cửa sổ, giành focus bàn phím)")
class RealTkKeyTests(CapsLockKeyTests):
    """Cùng các ca, nhưng đi qua binding thật của Tk (event_generate có bit Lock 0x2) thay vì gọi thẳng bộ phân phối."""

    def press(self, keysym, state):
        self.fired.clear()
        self.root.deiconify()
        self.root.update()
        self.root.focus_force()
        self.app.canvas.focus_force()
        self.root.update()
        if self.root.focus_get() is not self.app.canvas:
            self.skipTest("không giành được focus bàn phím")
        self.app.canvas.event_generate("<Key>", keysym=keysym, state=state)
        self.root.update()
        return list(self.fired), None

    def test_unbound_letter_is_not_swallowed(self):
        self.assertEqual(self.press("Y", LOCK)[0], [])

    def test_typing_in_frame_box_still_blocks_shortcuts(self):
        self.app._typing = lambda: True
        self.assertEqual(self.press("Z", CTRL | LOCK)[0], [])


if __name__ == "__main__":
    unittest.main()
