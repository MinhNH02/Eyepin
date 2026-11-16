"""Hộp hỏi khi đóng tool mà còn thay đổi chưa lưu: Có = lưu rồi thoát, Không = thoát bỏ thay đổi, Huỷ = ở lại."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import test_gui as _tg  # noqa: E402

T = _tg.T


class CloseConfirmTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins

    def dirty_app(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        self.assertTrue(app.s.dirty)
        return app

    def close(self, app, answer):
        """Gọi on_close với câu trả lời `answer` cho hộp hỏi; trả về (hộp hỏi có hiện không, cửa sổ có bị huỷ không)."""
        with mock.patch("tkinter.messagebox.askyesnocancel", return_value=answer) as ask, \
                mock.patch("tkinter.messagebox.showerror") as err, \
                mock.patch.object(app.root, "destroy") as destroy:
            app.on_close()
        return ask, err, destroy

    def test_no_prompt_when_nothing_is_unsaved(self):
        app, _ = self.make_app()
        self.assertFalse(app.s.dirty)
        ask, _, destroy = self.close(app, None)
        ask.assert_not_called()
        destroy.assert_called_once()

    def test_no_prompt_without_a_session(self):
        from eyepin.gui import App
        app = App(self.root)
        self.assertIsNone(app.s)
        ask, _, destroy = self.close(app, None)
        ask.assert_not_called()
        destroy.assert_called_once()

    def test_prompt_shows_when_there_are_unsaved_changes(self):
        app = self.dirty_app()
        ask, _, _ = self.close(app, None)
        ask.assert_called_once()

    def test_cancel_keeps_the_window_and_the_work(self):
        app = self.dirty_app()
        ask, _, destroy = self.close(app, None)
        destroy.assert_not_called()
        self.assertTrue(app.s.dirty)
        self.assertFalse(os.path.exists(app.state_path()))   # Huỷ cũng không được lén lưu

    def test_yes_saves_then_closes(self):
        app = self.dirty_app()
        _, _, destroy = self.close(app, True)
        destroy.assert_called_once()
        self.assertFalse(app.s.dirty)
        self.assertTrue(os.path.exists(app.state_path()))

    def test_no_closes_without_saving(self):
        app = self.dirty_app()
        _, _, destroy = self.close(app, False)
        destroy.assert_called_once()
        self.assertFalse(os.path.exists(app.state_path()))

    def test_failed_save_does_not_close(self):
        app = self.dirty_app()
        with mock.patch.object(app.s, "save_state", side_effect=OSError("đĩa đầy")):
            ask, err, destroy = self.close(app, True)
        destroy.assert_not_called()
        err.assert_called_once()
        self.assertTrue(app.s.dirty)

    def test_pins_mode_asks_before_discarding_and_never_writes(self):
        from eyepin.gui import App
        app, _ = self.make_app()
        pins = {str(f): {str(i): list(p) for i, p in T.pins_at(f).items()} for f in (0, 20, 40)}
        app2 = App(self.root)
        app2.load(self.dir, None, pins=pins)
        self.assertTrue(app2.scratch)
        app2.s.dirty = True
        with mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask, \
                mock.patch("tkinter.messagebox.askyesnocancel") as three, \
                mock.patch.object(app2.root, "destroy") as destroy:
            app2.on_close()
        ask.assert_called_once()
        three.assert_not_called()                            # không có nút "lưu" vì không có file phiên
        destroy.assert_not_called()
        with mock.patch("tkinter.messagebox.askyesno", return_value=True), mock.patch.object(app2.root, "destroy") as destroy:
            app2.on_close()
        destroy.assert_called_once()
        self.assertFalse(os.path.exists(app2.state_path()))


if __name__ == "__main__":
    unittest.main()
