"""B09: xoá một người ở GIỮA (hoặc người đầu) không làm ẩn riêng / khoá / Pinned trượt sang người khác.

Trước khi sửa, trạng thái gắn theo CHỈ SỐ người: bỏ người 2 thì người 3 lên chỉ số 1 nhưng trạng thái của nó còn ở chỉ số 2 (rồi bị cắt),
còn trạng thái cũ ở chỉ số 1 thành của người 3.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from test_final_fixes import FinalFixCase  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
import test_tracking as T  # noqa: E402


class MultiPersonCase(FinalFixCase):
    def three_people(self):
        """Người 1 (chỉ số 0), người 2 (chỉ số 1, dịch (40, 60)), người 3 (chỉ số 2, dịch (-40, -50)), cùng ghim ở frame 0."""
        app = self.two_people()
        app.new_object()
        truth = T.pins_at(0)
        app.s.add_pin_free(0, [(x - 40, y - 50) for x, y in (truth[i] for spec in EYES.values() for i in spec.pins)])
        app.pinning, app.clicks = None, []
        app.refresh()
        self.assertEqual((len(app.s.layers), app.s.cur), (3, 2))
        return app

    @staticmethod
    def by_person(app):
        """Trạng thái của từng người, khoá theo ID mattrai của người đó (không theo chỉ số, vì chỉ số dịch khi xoá người)."""
        out = {}
        for i, L in enumerate(app.s.layers):
            with app.s.layer_ctx(i):
                out[L.obj_ids.get("mattrai")] = {"locked": set(app.locked), "pinned": set(app.pinned_eyes),
                                                 "hidden": {l for l in EYES if (i, l) in app.hidden_objs}}
        return out

    @staticmethod
    def delete_person(app, layer):
        app.hover = None
        for label in EYES:
            app.tree.selection_set(f"eye:{label}" + (f"@{layer}" if layer else ""))
            app.delete_label(force=True)


EMPTY = {"locked": set(), "pinned": set(), "hidden": set()}


class DeleteMiddlePersonTests(MultiPersonCase):
    def setup_state(self, app):
        ids = [L.obj_ids["mattrai"] for L in app.s.layers]
        with app.s.layer_ctx(1):                                        # người 2
            app.locked.add("mattrai")
            app.pinned_eyes.add("matphai")
        app.hidden_objs.add((1, "matphai"))
        with app.s.layer_ctx(2):                                        # người 3
            app.locked.add("matphai")
            app.pinned_eyes.add("mattrai")
        app.hidden_objs.add((2, "mattrai"))
        app.refresh()
        return ids

    def test_deleting_middle_person_keeps_person3_state(self):
        app = self.three_people()
        p1, p2, p3 = self.setup_state(app)
        self.delete_person(app, 1)
        self.assertEqual(len(app.s.layers), 2)
        self.assertEqual([L.obj_ids["mattrai"] for L in app.s.layers], [p1, p3])     # người 3 lên chỉ số 1
        self.assertEqual(self.by_person(app), {p1: EMPTY, p3: {"locked": {"matphai"}, "pinned": {"mattrai"}, "hidden": {"mattrai"}}})
        self.assertEqual(app.hidden_objs, {(1, "mattrai")})
        self.assertIn("[khoá]", app.tree.item("eye:matphai@1", "text"))              # thẻ của người 3 vẫn hiện khoá
        self.assertIn("[ẩn]", app.tree.item("eye:mattrai@1", "text"))
        self.assertNotIn("[khoá]", app.tree.item("eye:mattrai@1", "text"))

    def test_undo_middle_person_deletion_restores_everyone(self):
        app = self.three_people()
        p1, p2, p3 = self.setup_state(app)
        want = self.by_person(app)
        self.delete_person(app, 1)
        app.undo()
        app.undo()
        self.assertEqual([L.obj_ids.get("mattrai") for L in app.s.layers], [p1, p2, p3])
        self.assertEqual(self.by_person(app), want)
        self.assertEqual(app.hidden_objs, {(1, "matphai"), (2, "mattrai")})
        app.redo()
        app.redo()
        self.assertEqual(self.by_person(app), {p1: EMPTY, p3: want[p3]})

    def test_new_person_after_middle_deletion_starts_clean(self):
        app = self.three_people()
        p1, p2, p3 = self.setup_state(app)
        self.delete_person(app, 1)
        app.new_object()                                                 # người mới ở chỉ số 2 (chỉ số cũ của người 3)
        truth = T.pins_at(0)
        app.s.add_pin_free(0, [(x + 40, y + 60) for x, y in (truth[i] for spec in EYES.values() for i in spec.pins)])
        app.pinning, app.clicks = None, []
        app.refresh()
        self.assertEqual((len(app.s.layers), app.s.cur), (3, 2))
        new = app.s.layers[2].obj_ids["mattrai"]
        self.assertEqual(self.by_person(app)[new], EMPTY)
        self.assertEqual(self.by_person(app)[p3]["locked"], {"matphai"})


class DeleteFirstPersonTests(MultiPersonCase):
    def test_deleting_first_person_moves_person2_state_with_it(self):
        app = self.two_people()
        p1, p2 = (L.obj_ids["mattrai"] for L in app.s.layers)
        with app.s.layer_ctx(1):
            app.locked.add("matphai")
            app.pinned_eyes.add("mattrai")
        app.hidden_objs.add((1, "matphai"))
        with app.s.layer_ctx(0):
            app.pinned_eyes.add("matphai")                              # người 1: sẽ bị xoá
        self.delete_person(app, 0)
        self.assertEqual([L.obj_ids.get("mattrai") for L in app.s.layers], [p2])   # người 2 thành chỉ số 0
        self.assertEqual(self.by_person(app), {p2: {"locked": {"matphai"}, "pinned": {"mattrai"}, "hidden": {"matphai"}}})


if __name__ == "__main__":
    unittest.main()
