"""B06 (buglist.md, TASKS.md mục 8 "known issue a"): ô số frame giữ focus bàn phím làm phím tắt toàn cục bị nuốt.

Phím tắt gắn trên cửa sổ chính (thẻ ".") và `App._typing()` coi "focus đang ở ô số frame" là "đang gõ", nên mọi phím tắt (Del, Ctrl+Z,
q/o/h/l...) bị bỏ qua cho tới khi focus rời ô. Đã tái hiện bằng phím thật (event_generate trên cửa sổ hiện, focus thật):
- ↑/↓ trong ô đổi frame nhưng focus ở lại ô (và ô vẫn ghi số frame cũ): Del, Ctrl+Z, i... sau đó không chạy;
- Enter nhảy frame và trả focus về ảnh, nhưng cùng phím Enter đó chạy tiếp phím tắt Enter của cửa sổ (đổi màu mắt đang chọn);
- Esc trong ô không làm gì: chữ gõ dở còn nguyên, focus ở lại ô, phím tắt vẫn bị nuốt;
- Tab trong ô chuyển focus sang panel phải (ttk.Notebook): ←/→ đổi tab panel thay vì đổi frame.

Hành vi sau khi sửa: Enter, ↑/↓, Esc, Tab (Shift+Tab) đều rời ô: ô về số frame hiện tại, focus về ảnh, và phím đó không chạy tiếp
phím tắt cùng phím của cửa sổ ("break"). Gõ chữ trong ô (và trong các ô nhập của hộp phụ: F2, Tìm frame, Vẽ mắt...) vẫn không chạy
phím tắt toàn cục. Ảnh giả của `test_tracking` (không dùng dữ liệu công ty).

Test phím thật (lớp `RealKeyTests`) mở cửa sổ và giành focus nên chỉ chạy khi đặt EYEPIN_REAL_FOCUS=1."""
import os
import re
import shutil
import sys
import tempfile
import tkinter as tk
import unittest
from tkinter import ttk

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")      # không đụng cài đặt thật của người dùng

from eyepin import shortcuts as sc  # noqa: E402
import test_tracking as T  # noqa: E402


def make_dir():
    d = tempfile.mkdtemp(prefix="eyepin_b06_")
    for t in range(T.N):
        cv2.imwrite(os.path.join(d, f"f{t:03d}.png"), T.render(t))
    return d


def new_app(root, frames_dir):
    from eyepin.gui import App
    app = App(root)
    app.ask_restore = lambda n: False
    app.load(frames_dir, None)
    return app


def press(widget, seq, keysym):
    """Chạy đúng binding của RIÊNG ô (thẻ widget, chạy trước lớp TEntry, cửa sổ "." và "all") như Tk chạy khi có phím `seq`.
    Trả chuỗi Tk nhận lại: "break" = Tk dừng, không chạy binding của các thẻ sau (phím tắt của cửa sổ, chuyển focus của Tab)."""
    script = widget.bind(seq)
    if not script:
        return None
    cmd = re.search(r"\[(\S+) %#", script).group(1)
    args = ("0", "??", "0", "??", "??", "0", "0", "??", "0", "0", "", "0", keysym, "0", str(widget), "2", "0", "0", "0")
    return widget.tk.call(cmd, *args)


class EntryKeyTests(unittest.TestCase):
    """Không cần focus thật: gọi binding của ô, đo focus bằng cách thay `canvas.focus_set`."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = make_dir()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        self.errors = []
        self.root.report_callback_exception = lambda *a: self.errors.append(a)   # lỗi trong binding không bị nuốt
        self.addCleanup(lambda: self.assertEqual(self.errors, []))
        self.app = new_app(self.root, self.dir)
        self.calls = []
        self.app.canvas.focus_set = lambda: self.calls.append("canvas")

    def type_in(self, text):
        self.app.entry_var.set(text)                     # chữ đang gõ dở trong ô, chưa Enter

    # (1) ↑/↓
    def test_up_down_step_then_give_keys_back(self):
        app = self.app
        app.go(3)
        self.assertEqual(press(app.entry, "<Up>", "Up"), "break")
        self.assertEqual(app.f, 4)
        self.assertEqual(self.calls, ["canvas"], "↑ trong ô: focus phải về ảnh để Del, Ctrl+Z... chạy lại")
        self.assertEqual(app.entry_var.get(), "4", "ô phải ghi frame mới")
        self.assertEqual(press(app.entry, "<Down>", "Down"), "break")
        self.assertEqual(app.f, 3)
        self.assertEqual(self.calls, ["canvas", "canvas"])
        self.assertEqual(app.entry_var.get(), "3")

    # (2) Enter
    def test_enter_jumps_gives_keys_back_and_stops_the_enter_shortcut(self):
        app = self.app
        self.type_in("5")
        self.assertEqual(press(app.entry, "<Return>", "Return"), "break",
                         "Enter nhảy frame không được chạy tiếp phím tắt Enter của cửa sổ (đổi màu mắt)")
        self.assertEqual(app.f, 5)
        self.assertEqual(self.calls, ["canvas"])
        self.assertEqual(app.entry_var.get(), "5")

    def test_enter_out_of_range_shows_the_frame_actually_opened(self):
        app = self.app
        self.type_in("999")
        self.assertEqual(press(app.entry, "<Return>", "Return"), "break")
        self.assertEqual(app.f, T.N - 1)
        self.assertEqual(app.entry_var.get(), str(T.N - 1))
        self.assertEqual(self.calls, ["canvas"])

    def test_enter_invalid_number_restores_box(self):
        app = self.app
        app.go(2)
        self.type_in("abc")
        self.assertEqual(press(app.entry, "<Return>", "Return"), "break")
        self.assertEqual(app.f, 2)
        self.assertEqual(app.entry_var.get(), "2")
        self.assertEqual(self.calls, ["canvas"])

    # (3) Esc
    def test_escape_cancels_typing_and_gives_keys_back(self):
        app = self.app
        app.go(2)
        self.type_in("12")
        self.assertEqual(press(app.entry, "<Escape>", "Escape"), "break",
                         "Esc trong ô chỉ rời ô, không chạy tiếp Esc của cửa sổ (huỷ / thoát toàn màn hình)")
        self.assertEqual(app.f, 2, "Esc không nhảy frame")
        self.assertEqual(app.entry_var.get(), "2", "chữ gõ dở bị bỏ, ô về số frame hiện tại")
        self.assertEqual(self.calls, ["canvas"])

    # (4) Tab, Shift+Tab
    def test_tab_leaves_box_to_the_image(self):
        app = self.app
        app.go(2)
        for seq, keysym in (("<Tab>", "Tab"), ("<ISO_Left_Tab>", "ISO_Left_Tab")):
            self.calls.clear()
            self.type_in("7")
            self.assertEqual(press(app.entry, seq, keysym), "break", f"{seq}: không để Tk chuyển focus sang panel phải")
            self.assertEqual(self.calls, ["canvas"], seq)
            self.assertEqual(app.entry_var.get(), "2", seq)
            self.assertEqual(app.f, 2, seq)

    def test_tab_on_image_never_enters_the_box(self):
        # Tab trên ảnh là "chọn đối tượng kế" và trả "break": Tk không chuyển focus vào ô số frame bằng Tab
        app = self.app
        self.assertIn("<Tab>", app.bind_map["next_object"])
        self.assertEqual(app.handlers["next_object"](), "break")

    # (5) gõ chữ trong ô nhập: phím tắt toàn cục không chạy
    def test_typing_in_frame_box_runs_no_shortcut(self):
        app = self.app
        self.root.focus_get = lambda: app.entry               # giả "focus đang ở ô" (cửa sổ ẩn không nhận focus thật)
        self.addCleanup(lambda: delattr(self.root, "focus_get"))
        before = (dict(app.look.eyes), set(app.locked), app.show_ids)
        for aid in ("hide", "lock", "toggle_ids", "delete", "undo", "occluded", "outside"):
            self.assertIsNone(app.handlers[aid](), aid)
        self.assertEqual((dict(app.look.eyes), set(app.locked), app.show_ids), before)

    def test_dialog_fields_are_outside_the_shortcut_tag(self):
        # phím tắt gắn trên thẻ "." của cửa sổ chính, không gắn bind_all: ô nhập của hộp phụ (Toplevel riêng) không mang thẻ "."
        app = self.app
        for aid in ("hide", "delete", "undo", "lock", "occluded"):
            for seq in app.bind_map[aid]:
                self.assertTrue(self.root.bind(seq), seq)
                self.assertEqual(self.root.bind_all(seq), "", seq)
        app.show_settings()
        app.start_draw()
        query = tk.Toplevel(self.root)                    # như simpledialog.askstring của "Tìm frame theo tên"
        self.addCleanup(query.destroy)
        ttk.Entry(query).pack()
        boxes = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, (tk.Entry, ttk.Entry, tk.Spinbox, tk.Text)):
                    boxes.append(c)
                walk(c)
        for d in (app._dialogs["settings"], app._dialogs["draw"], query):
            walk(d)
        self.assertGreaterEqual(len(boxes), 3)
        for b in boxes:
            self.assertNotIn(".", b.bindtags(), b)
        for name in ("settings", "draw"):
            app._dialogs[name].destroy()


@unittest.skipUnless(os.environ.get("EYEPIN_REAL_FOCUS") == "1", "đặt EYEPIN_REAL_FOCUS=1 để chạy (mở cửa sổ, giành focus bàn phím)")
class RealKeyTests(unittest.TestCase):
    """Phím thật qua đủ chuỗi bindtags của Tk (ô -> TEntry -> cửa sổ -> all): cần cửa sổ hiện và giữ focus."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.dir = make_dir()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def setUp(self):
        app = self.app = new_app(self.root, self.dir)
        self.fired = []
        orig = app._actions

        def spied():
            return {aid: (lambda fn=fn, aid=aid: (self.fired.append(aid), fn())) for aid, fn in orig().items()}
        app._actions = spied
        app._bind_keys()
        app.hover = None
        self.root.deiconify()
        self.root.update()
        self.root.focus_force()
        app.entry.focus_force()
        self.root.update()
        if self.root.focus_get() is not app.entry:
            self.skipTest("không giành được focus bàn phím")

    def key(self, seq):
        w = self.root.focus_get() or self.root
        w.event_generate(seq)
        self.root.update()

    def into_box(self):
        self.app.entry.focus_force()
        self.root.update()
        self.assertIs(self.root.focus_get(), self.app.entry)

    def test_keys_work_after_each_way_of_leaving_the_box(self):
        app = self.app
        for leave in ("<KeyPress-Up>", "<KeyPress-Down>", "<KeyPress-Return>", "<KeyPress-Escape>", "<KeyPress-Tab>"):
            self.into_box()
            self.fired.clear()
            self.key(leave)
            self.assertIs(self.root.focus_get(), app.canvas, leave)
            self.assertEqual(self.fired, [], f"{leave} không được chạy phím tắt cùng phím")
            self.assertEqual(app.entry_var.get(), str(app.f), leave)
            self.key("<KeyPress-i>")
            self.key("<Control-z>")
            self.assertEqual(self.fired, ["toggle_ids", "undo"], leave)

    def test_typing_letters_in_box_runs_no_shortcut(self):
        self.into_box()
        self.app.entry_var.set("")
        self.fired.clear()
        for k in ("<KeyPress-h>", "<KeyPress-l>", "<KeyPress-q>", "<KeyPress-o>"):
            self.key(k)
        self.assertEqual(self.fired, [])
        self.assertEqual(self.app.entry_var.get(), "hlqo")
        self.key("<KeyPress-Escape>")


if __name__ == "__main__":
    unittest.main()
