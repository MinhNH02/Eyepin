"""B12 (buglist.md): `Session.clear_all` và Remove annotations đếm/ghi hoàn tác sai khi bộ đang chọn trống mà bộ khác có ghim.

Tái hiện trước khi sửa: người 1 có ghim, "+" thêm người 2 (bộ mới, trống, đang chọn). `clear_all` đếm `len(self.pins)` = 0 của bộ đang chọn,
không ghi hoàn tác, nhưng vẫn xoá ghim của người 1 và bỏ bộ thứ hai: Ctrl+Z không khôi phục được. Remove annotations báo "Chưa có nhãn nào để xoá"
mà không xoá gì (dù bộ khác có ghim).

Sau khi sửa: số trả về / số báo = tổng frame ghim của MỌI người; hoàn tác khôi phục đúng (cả số người)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
import test_gui as _tg  # noqa: E402
import test_parity as _tp  # noqa: E402
import test_tracking as T  # noqa: E402


class ClearAllScopeTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins
    pinned_app = _tp.ParityTests.pinned_app

    def one_person_plus_empty(self):
        """Người 1 có ghim ở frame 0 và 10; bộ thứ hai trống và đang được chọn."""
        app = self.pinned_app()
        app.s.toggle_pin_here(10)
        app.s.add_layer()
        self.assertEqual((len(app.s.layers), app.s.cur, app.s.pins), (2, 1, {}))
        return app

    def test_session_clear_all_counts_and_undoes_other_layers(self):
        app = self.one_person_plus_empty()
        s = app.s
        n = s.clear_all()
        self.assertEqual(n, 2)                                   # đếm ghim của người 1, không phải của bộ trống đang chọn
        self.assertEqual((len(s.layers), s.pins), (1, {}))
        self.assertTrue(s.undo())                                # hoàn tác phải trả lại ghim của người 1 và bộ trống
        self.assertEqual(len(s.layers), 2)
        self.assertEqual(sorted(s.layers[0].pins), [0, 10])

    def test_remove_annotations_reports_other_layers(self):
        app = self.one_person_plus_empty()
        app.notice = ""
        app.remove_annotations(confirmed=True)
        self.assertNotIn("Chưa có nhãn", app.notice)
        self.assertIn("2 frame ghim", app.notice)
        self.assertEqual(sorted(app.s.layers[0].pins), [])
        self.assertTrue(app.s.undo())
        self.assertEqual(sorted(app.s.layers[0].pins), [0, 10])

    def test_counts_all_people_when_current_has_pins(self):
        app = self.pinned_app()                                  # người 1: frame 0
        app.s.add_layer()
        truth = T.pins_at(0)
        pts = [(x + 40, y + 60) for x, y in (truth[i] for spec in EYES.values() for i in spec.pins)]
        app.s.add_pin_free(0, pts)                               # người 2: frame 0
        self.assertEqual(app.s.clear_all(), 2)                   # hai người, mỗi người một frame ghim

    def test_nothing_to_remove_stays_quiet(self):
        app, seq = self.make_app()
        app.notice = ""
        app.remove_annotations(confirmed=True)
        self.assertIn("Chưa có nhãn", app.notice)
        n_undo = len(app.s._undo)
        self.assertEqual(app.s.clear_all(), 0)
        self.assertEqual(len(app.s._undo), n_undo)               # không có gì để xoá thì không ghi bước hoàn tác


if __name__ == "__main__":
    unittest.main()
