"""B13 (buglist.md): hẹn giờ `after` còn sót khi đóng cửa sổ.

`App._schedule_autosave` (mỗi 2 phút), `_thumbs_tick`, `_tick` của phát, `_motion_draw` (after_idle) và tooltip đều hẹn bằng `after`.
`Tk.destroy` xoá lệnh Python tương ứng nhưng hẹn giờ vẫn nằm trong trình thông dịch Tcl; khi vòng lặp sự kiện của cửa sổ khác chạy
(cùng luồng) thì hẹn giờ đó nổ: "invalid command name ..._autosave_tick". Sau khi sửa: mọi đường huỷ cửa sổ chính (on_close/shutdown,
root.destroy() trực tiếp như `--selftest`) huỷ MỌI hẹn giờ còn chờ."""
import os
import shutil
import sys
import tempfile
import tkinter as tk
import unittest

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")      # không đụng cài đặt thật của người dùng

import test_tracking as T  # noqa: E402


def pending(tk_app):
    return tk_app.splitlist(tk_app.call("after", "info"))


class AfterCancelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            tk.Tk().destroy()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b13_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def make(self, load=True):
        from eyepin.gui import App
        root = tk.Tk()
        root.withdraw()

        def close():
            try:
                root.destroy()
            except tk.TclError:                    # đã đóng trong test
                pass
        self.addCleanup(close)
        app = App(root)
        app.ask_restore = lambda n: False
        if load:
            app.load(self.dir, None)
        return root, app

    def test_autosave_is_pending_at_start_and_cancelled_on_shutdown(self):
        root, app = self.make(load=False)
        interp = root.tk
        self.assertTrue(pending(interp), "autosave phải đang hẹn giờ")
        app.shutdown()
        self.assertEqual(pending(interp), ())

    def test_every_pending_timer_cancelled_on_shutdown(self):
        root, app = self.make()
        interp = root.tk
        app.toggle_play()                          # _tick
        app._schedule_thumbs()                     # _thumbs_tick
        app._motion_refresh()                      # after_idle
        self.assertGreaterEqual(len(pending(interp)), 4)
        app.shutdown()
        self.assertEqual(pending(interp), ())

    def test_plain_root_destroy_also_cancels_everything(self):
        # `run(selftest)` và các test đóng bằng root.destroy() thẳng, không qua shutdown()
        root, app = self.make()
        interp = root.tk
        app.toggle_play()
        app._schedule_thumbs()
        root.destroy()
        self.assertEqual(pending(interp), ())

    def test_on_close_cancels_everything(self):
        root, app = self.make()
        interp = root.tk
        app.toggle_play()
        app.s.dirty = False
        app.on_close()
        self.assertEqual(pending(interp), ())


if __name__ == "__main__":
    unittest.main()
