"""B08: hoàn tác (Ctrl+Z) và làm lại sau Del hoặc đổi label phải đưa ẩn riêng / khoá / Pinned về đúng mắt.

Trước khi sửa, các trạng thái này nằm ở App (theo chỉ số người + tên label), ngoài lịch sử hoàn tác của Session: Del bỏ chúng và Ctrl+Z
đưa dữ liệu mắt về nhưng không đưa trạng thái về; đổi label đổi chỗ trạng thái nhưng Ctrl+Z không đổi lại.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from test_final_fixes import FinalFixCase  # noqa: E402  (dựng App, một hoặc hai người, như test_final_fixes)


class UndoDeleteTests(FinalFixCase):
    def test_undo_delete_restores_hidden_and_pinned(self):
        app = self.make_app()
        app.hidden_objs.add((0, "mattrai"))
        app.pinned_eyes.add("mattrai")
        app.select_eye("mattrai", quiet=True)
        app.hover = None
        app.handlers["delete"]()
        self.assertNotIn(14, self.pins0(app))
        self.assertNotIn((0, "mattrai"), app.hidden_objs)              # xoá mắt: trạng thái của nó bị quên (đã chốt)
        self.assertNotIn("mattrai", app.pinned_eyes)
        app.handlers["undo"]()
        self.assertIn(14, self.pins0(app), app.notice)
        self.assertIn((0, "mattrai"), app.hidden_objs)                 # Ctrl+Z: mắt về cùng trạng thái ẩn riêng và Pinned
        self.assertIn("mattrai", app.pinned_eyes)
        self.assertNotIn((0, "matphai"), app.hidden_objs)
        app.handlers["redo"]()
        self.assertNotIn(14, self.pins0(app))
        self.assertNotIn((0, "mattrai"), app.hidden_objs)
        self.assertNotIn("mattrai", app.pinned_eyes)
        app.handlers["undo"]()
        self.assertEqual(app.hidden_objs, {(0, "mattrai")})
        self.assertEqual(set(app.pinned_eyes), {"mattrai"})

    def test_undo_shift_delete_restores_lock(self):
        app = self.make_app()
        app.locked.add("matphai")
        app.select_eye("matphai", quiet=True)
        app.hover = None
        app.delete_label(force=True)                                    # Shift+Del xoá cả mắt khoá
        self.assertNotIn(22, self.pins0(app))
        self.assertNotIn("matphai", app.locked)
        app.undo()
        self.assertIn(22, self.pins0(app))
        self.assertEqual(set(app.locked), {"matphai"})
        self.assertIn("[khoá]", app.tree.item("eye:matphai", "text"))  # thẻ cũng hiện lại khoá

    def test_undo_delete_of_person2_eye_restores_only_person2_state(self):
        app = self.two_people()
        app.hidden_objs.add((1, "matphai"))
        app.pinned_eyes.add("matphai")                                  # người 2 (bộ đang chọn)
        app.hover = None
        app.tree.selection_set("eye:matphai@1")
        app.delete_label()
        self.assertNotIn((1, "matphai"), app.hidden_objs)
        app.undo()
        self.assertEqual(app.hidden_objs, {(1, "matphai")})
        with app.s.layer_ctx(1):
            self.assertEqual(set(app.pinned_eyes), {"matphai"})
        with app.s.layer_ctx(0):
            self.assertEqual(set(app.pinned_eyes), set())

    def test_undo_after_person2_removed_brings_back_its_state(self):
        """Xoá cả hai mắt của người 2 (bộ rỗng tự bỏ) rồi hoàn tác hai lần: người 2 về với đủ khoá / ẩn riêng / Pinned."""
        app = self.two_people()
        app.locked.add("mattrai")
        app.pinned_eyes.add("matphai")
        app.hidden_objs.add((1, "matphai"))
        app.hover = None
        for iid in ("eye:mattrai@1", "eye:matphai@1"):
            app.tree.selection_set(iid)
            app.delete_label(force=True)
        self.assertEqual(len(app.s.layers), 1)
        app.undo()
        app.undo()
        self.assertEqual(len(app.s.layers), 2)
        self.assertEqual(app.hidden_objs, {(1, "matphai")})
        with app.s.layer_ctx(1):
            self.assertEqual((set(app.locked), set(app.pinned_eyes)), ({"mattrai"}, {"matphai"}))
        with app.s.layer_ctx(0):
            self.assertEqual((set(app.locked), set(app.pinned_eyes)), (set(), set()))


class UndoSwapTests(FinalFixCase):
    def test_undo_and_redo_label_swap_move_state_back_and_forth(self):
        app = self.two_people()
        app.hidden_objs.add((1, "mattrai"))                             # người 2: không bao giờ đổi
        app.tree.selection_set("eye:mattrai")
        self.assertEqual(app.s.cur, 0)
        app.hidden_objs.add((0, "mattrai"))
        app.pinned_eyes.add("matphai")
        before = self.pins0(app, 0)
        app.swap_labels()
        self.assertEqual(app.hidden_objs, {(0, "matphai"), (1, "mattrai")})
        with app.s.layer_ctx(0):
            self.assertEqual(set(app.pinned_eyes), {"mattrai"})
        app.undo()
        self.assertEqual(self.pins0(app, 0), before)                    # dữ liệu về như cũ
        self.assertEqual(app.hidden_objs, {(0, "mattrai"), (1, "mattrai")})   # trạng thái về theo dữ liệu
        with app.s.layer_ctx(0):
            self.assertEqual(set(app.pinned_eyes), {"matphai"})
        with app.s.layer_ctx(1):
            self.assertEqual(set(app.pinned_eyes), set())
        app.redo()
        self.assertEqual(self.pins0(app, 0)[22], before[14])
        self.assertEqual(app.hidden_objs, {(0, "matphai"), (1, "mattrai")})
        with app.s.layer_ctx(0):
            self.assertEqual(set(app.pinned_eyes), {"mattrai"})


class UndoKeepsLaterTogglesTests(FinalFixCase):
    def test_undo_of_an_edit_does_not_revert_later_hide_lock_pinned(self):
        """Ẩn / khoá / Pinned không phải bước hoàn tác: Ctrl+Z một lần sửa trước đó không được đổi lại chúng."""
        app = self.make_app()
        p = self.pins0(app)[14]
        app.s.move_point(0, 14, (p[0] + 2, p[1]))
        app.hidden_objs.add((0, "mattrai"))
        app.locked.add("matphai")
        app.pinned_eyes.add("matphai")
        app.undo()
        self.assertEqual(self.pins0(app)[14], p)                        # lần dời điểm đã hoàn tác
        self.assertEqual(app.hidden_objs, {(0, "mattrai")})
        self.assertEqual((set(app.locked), set(app.pinned_eyes)), ({"matphai"}, {"matphai"}))


if __name__ == "__main__":
    unittest.main()
