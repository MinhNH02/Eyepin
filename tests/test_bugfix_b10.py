"""B10: nút "khoá tất cả" ở đầu danh sách (và phím L) đúng sau khi xoá mắt đang khoá của người thứ 2 trở đi.

Trước khi sửa, "đã khoá hết" xét cả mắt đã xoá (không còn thẻ) của người thứ 2 trở đi, nên icon báo chưa khoá dù mọi thẻ đều khoá,
L lần đầu chỉ "khoá" mắt không tồn tại; và mắt vẽ lại sau đó nhận luôn khoá ấy.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from test_bugfix_b09 import MultiPersonCase  # noqa: E402
import test_tracking as T  # noqa: E402


class LockAllHeaderTests(MultiPersonCase):
    def lock_state(self, app):
        out = {}
        for layer in range(len(app.s.layers)):
            with app.s.layer_ctx(layer):
                out[layer] = set(app.locked)
        return out

    def test_header_stays_locked_after_deleting_a_locked_eye_of_person2(self):
        app = self.two_people()
        hb = app.obj_head_btns["lock_all"]
        app.handlers["lock_all"]()
        self.assertEqual(hb.name, "lock")
        app.hover = None
        app.tree.selection_set("eye:mattrai@1")
        app.delete_label(force=True)                                    # Shift+Del mắt khoá của người 2
        self.assertFalse(app.tree.exists("eye:mattrai@1"))
        self.assertEqual(hb.name, "lock", "mọi thẻ còn lại đều khoá")
        self.assertTrue(app._all_locked())
        app.handlers["lock_all"]()                                       # một lần L: mở khoá hết (không phải hai lần)
        self.assertEqual(self.lock_state(app), {0: set(), 1: set()})
        self.assertEqual(hb.name, "unlock")

    def test_header_after_deleting_the_middle_person(self):
        app = self.three_people()
        hb = app.obj_head_btns["lock_all"]
        app.handlers["lock_all"]()
        self.delete_person(app, 1)
        self.assertEqual(len(app.s.layers), 2)
        self.assertEqual(self.lock_state(app), {0: set(EYES), 1: set(EYES)})
        self.assertEqual(hb.name, "lock")

    def test_lock_all_does_not_lock_a_deleted_eye(self):
        """L chỉ khoá đối tượng đang có (như CVAT): vẽ lại mắt đã xoá của người 2 thì mắt mới không khoá và icon về "chưa khoá hết"."""
        app = self.two_people()
        hb = app.obj_head_btns["lock_all"]
        app.hover = None
        app.tree.selection_set("eye:mattrai@1")
        app.delete_label()
        app.handlers["lock_all"]()
        self.assertEqual(hb.name, "lock")
        truth = T.pins_at(0)
        with app.s.layer_ctx(1):
            app.s.pin_eye(0, "mattrai", {i: (truth[i][0] + 40, truth[i][1] + 60) for i in EYES["mattrai"].pins})
        app.refresh()
        self.assertTrue(app.tree.exists("eye:mattrai@1"))
        self.assertEqual(self.lock_state(app), {0: set(EYES), 1: {"matphai"}})
        self.assertEqual(hb.name, "unlock")


if __name__ == "__main__":
    unittest.main()
