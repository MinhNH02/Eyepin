"""B20 (buglist.md): chấm màu ở tab Labels (`gui_objects.py`) tính màu theo chỉ số 0/1 của label, trong khi ảnh và thẻ đối tượng tính theo
`obj_id - 1`; ở Color by Instance chấm của matphai (ID 10) khác màu matphai trên ảnh.

Chấm của label phải khớp màu mắt đó trên ảnh (cũng là vạch màu `card["color"]` của thẻ đối tượng của người đang chọn) ở Color by
Label / Instance / Group và với màu riêng đổi bằng Enter."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from eyepin.render import COLORS, GROUP_COLOR, INSTANCE_COLORS  # noqa: E402
import test_gui as _tg  # noqa: E402


def _hex(bgr):
    return "#%02x%02x%02x" % (bgr[2], bgr[1], bgr[0])


class LabelsTabDotTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins

    def pinned_app(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        app.go(10)
        app.root.update()
        return app

    @staticmethod
    def dot(app, label):
        canvas = app._label_btns[label][2]
        items = canvas.find_all()
        assert len(items) == 1, items
        return canvas.itemcget(items[0], "fill")

    def card(self, app, label):
        return app.tree.item(f"eye:{label}", "card")["color"]

    def test_ids_are_not_the_label_indexes(self):
        app = self.pinned_app()
        self.assertEqual([app.s.obj_ids[l] for l in EYES], [1, 10])                    # matphai là ID 10, không phải 2
        self.assertNotEqual(INSTANCE_COLORS[9 % len(INSTANCE_COLORS)], INSTANCE_COLORS[1 % len(INSTANCE_COLORS)])

    def test_label_mode_dot_is_label_color(self):
        app = self.pinned_app()
        for label in EYES:
            self.assertEqual(self.dot(app, label), _hex(COLORS[label]))

    def test_instance_mode_dot_matches_image_and_card(self):
        app = self.pinned_app()
        app.set_look(color_by="instance")
        for label in EYES:
            want = _hex(INSTANCE_COLORS[(app.s.obj_ids[label] - 1) % len(INSTANCE_COLORS)])
            self.assertEqual(self.card(app, label), want)
            self.assertEqual(self.dot(app, label), want, label)

    def test_group_mode_dot_matches_card(self):
        app = self.pinned_app()
        app.set_look(color_by="group")
        for label in EYES:
            self.assertEqual(self.dot(app, label), _hex(GROUP_COLOR))
            self.assertEqual(self.dot(app, label), self.card(app, label))

    def test_enter_color_dot_matches_card(self):
        app = self.pinned_app()
        app.tree.selection_set("eye:matphai")
        app.handlers["change_color"](None)                                             # phím Enter
        mine = _hex(app.look.colors["matphai"])
        self.assertEqual(self.dot(app, "matphai"), mine)
        self.assertEqual(self.dot(app, "mattrai"), _hex(COLORS["mattrai"]))            # mắt kia không đổi

    def test_dot_before_any_session_does_not_crash_and_uses_label_color(self):
        import shutil
        import tempfile
        from eyepin.gui import App
        os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, os.environ["EYEPIN_HOME"], True)
        app = App(self.root)
        self.assertEqual(self.dot(app, "mattrai"), _hex(COLORS["mattrai"]))
        self.assertEqual(self.dot(app, "matphai"), _hex(COLORS["matphai"]))


if __name__ == "__main__":
    unittest.main()
