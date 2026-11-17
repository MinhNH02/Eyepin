"""B15 (buglist.md): (a) chữ khi trỏ chuột vào nút Hidden mờ của thẻ chỉ nhắc tab Labels, dù nút cũng mờ khi thẻ KHOÁ;
(b) nút Outside/Occluded của từng điểm trong DETAILS vẫn bật khi điểm không có ở frame hiện tại (trạng thái "—").

Tái hiện trước khi sửa: (a) thẻ khoá -> `tip_for("hidden", ...)` = tip mặc định "Ẩn/hiện (h)", không nói vì sao nút mờ; thẻ vừa khoá vừa label ẩn chỉ nhắc tab Labels;
(b) dòng điểm "—" có `_enabled` True.
Sau khi sửa: tip nêu đúng lý do thật (label ẩn -> hiện label ở tab Labels trước; thẻ khoá -> mở khoá trước); nút điểm "—" mờ (bấm không gửi gì)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import test_object_list as TO  # noqa: E402
import test_final_fixes as TF  # noqa: E402
from test_object_list import card, fill  # noqa: E402


class ListBase(unittest.TestCase):
    """Chỉ mượn cách dựng ObjectList của test_object_list (không kế thừa để khỏi chạy lại cả bộ test đó)."""
    setUpClass = classmethod(TO.ObjectListTest.setUpClass.__func__)
    tearDownClass = classmethod(TO.ObjectListTest.tearDownClass.__func__)
    setUp = TO.ObjectListTest.setUp
    tearDown = TO.ObjectListTest.tearDown


class HiddenTooltipTests(ListBase):
    def tip(self, **kw):
        fill(self.ol, cards={"mattrai": card("mattrai", **kw)})
        return self.ol.tip_for("hidden", "eye:mattrai")

    def test_locked_card_tip_says_unlock(self):
        t = self.tip(lock=True)
        self.assertIn("khoá", t)
        self.assertIn("mở khoá", t)
        self.assertNotIn("tab Labels", t)
        self.assertFalse(self.ol.buttons("eye:mattrai")["hidden"]._enabled)

    def test_label_hidden_tip_names_labels_tab(self):
        t = self.tip(label_hidden=True)
        self.assertIn("tab Labels", t)
        self.assertNotIn("mở khoá", t)

    def test_both_reasons_are_both_named(self):
        t = self.tip(lock=True, label_hidden=True)
        self.assertIn("tab Labels", t)
        self.assertIn("mở khoá", t)

    def test_enabled_card_keeps_plain_tip(self):
        self.assertEqual(self.tip(), self.ol.tip("hidden"))
        self.assertTrue(self.ol.buttons("eye:mattrai")["hidden"]._enabled)


class PointButtonsAbsentPointTests(ListBase):
    def test_point_without_data_here_is_dimmed(self):
        ol = self.ol
        fill(ol)
        ol.item("pt:16", values=("ghim", "★", "—"))                 # điểm không có ở frame hiện tại
        pb = ol.point_buttons("pt:16")
        self.assertFalse(any(b._enabled for b in pb.values()))
        pb["outside"]._click(None)
        pb["occluded"]._click(None)
        self.assertEqual(self.actions, [])
        ol.item("pt:16", values=("ghim", "★", ""))                  # điểm có lại: bật lại
        self.assertTrue(all(b._enabled for b in pb.values()))
        ol.item("pt:16", values=("ghim", "★", "Outside"))           # có cờ thì vẫn bật (để bỏ cờ)
        self.assertTrue(all(b._enabled for b in pb.values()))

    def test_absent_point_tip_explains(self):
        ol = self.ol
        fill(ol)
        ol.item("pt:16", values=("ghim", "★", "—"))
        self.assertIn("không có", ol.tip_for("pt_outside", "pt:16"))
        self.assertIn("không có", ol.tip_for("pt_occluded", "pt:16"))
        self.assertEqual(ol.tip_for("pt_outside", "pt:14"), ol.tip("pt_outside"))


class AppHiddenAndPointTests(TF.FinalFixCase):
    def test_app_deleted_eye_rows_dimmed_other_eye_enabled(self):
        app = self.make_app()
        app.s.delete_eye("mattrai")
        app.refresh()
        gone = [app.tree.point_buttons(f"pt:{i}") for i in range(14, 22)]
        self.assertTrue(gone and not any(b._enabled for pb in gone for b in pb.values()))
        keep = app.tree.point_buttons("pt:22")
        self.assertTrue(all(b._enabled for b in keep.values()))

    def test_app_locked_card_tip(self):
        app = self.make_app()
        app.locked.add("mattrai")
        app.refresh()
        self.assertIn("mở khoá", app.tree.tip_for("hidden", "eye:mattrai"))


if __name__ == "__main__":
    unittest.main()
