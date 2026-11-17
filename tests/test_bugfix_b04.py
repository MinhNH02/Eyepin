"""B04 (buglist.md): bảng màu điểm (`render.POINT_PALETTE`, mỗi vị trí điểm một màu) ghi đè cách tô "Color by Instance/Group" và màu riêng
đổi bằng Enter (`look.colors`): trước khi sửa, ở mọi chế độ 8 điểm vẫn mang 8 màu của bảng, chỉ đường viền mắt (1 px) đổi màu.

Quy tắc sau khi sửa (`render._draw_eye`): bảng màu điểm chỉ dùng khi tô theo nhãn (Color by Label, mặc định) và mắt chưa có màu riêng (Enter);
Instance / Group / màu riêng thì điểm cùng màu mắt (= màu đường viền = màu vạch trên thẻ ở panel phải). Mặc định giữ nguyên như trước.

Kiểm cả hai đường vẽ: `render.CvPainter` (ảnh numpy, không cần cửa sổ) và `gui.CanvasPainter` (đối tượng Canvas trong cửa sổ).
Ảnh giả của `test_tracking` (không dùng dữ liệu công ty)."""
import os
import shutil
import sys
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES, derive, four_in_box  # noqa: E402
from eyepin.render import (COLORS, GROUP_COLOR, INSTANCE_COLORS, PIN_IDS, POINT_PALETTE, CvPainter, Look, View,  # noqa: E402
                           _draw_eye, render_main)
from eyepin.session import Session  # noqa: E402
import test_gui as _tg  # noqa: E402
import test_tracking as T  # noqa: E402

ML, MR = EYES["mattrai"], EYES["matphai"]
VIEW = View(0, 0, 3.0, 960, 460)
PALETTE = {spec.ids[pos]: POINT_PALETTE[pos] for spec in EYES.values() for pos in range(len(spec.ids))}   # màu bảng của từng điểm


def eye_pts(label):
    spec = EYES[label]
    box = (100, 100, 160, 120) if label == "mattrai" else (200, 100, 260, 120)
    return derive(spec, four_in_box(spec, box))


class Rec:
    """Bút vẽ ghi lại màu: điểm (có tag pt:<mắt>:<id>) và đường viền mắt (tag outline:<mắt>)."""

    def __init__(self):
        self.points, self.outline = {}, {}

    def poly(self, pts, color, width, tag=None):
        if tag:
            self.outline[tag.split(":")[1]] = tuple(color)

    def line(self, *a, **k):
        pass

    def circle(self, c, r, color, width=1, tag=None):
        if tag:
            self.points[int(tag.split(":")[2])] = tuple(color)

    def dashed_circle(self, *a, **k):
        pass

    def text(self, *a, **k):
        pass


def draw(look, label="mattrai", index=0):
    rec = Rec()
    _draw_eye(rec, VIEW, eye_pts(label), label, pinned=True, ids=False, scale=1.0, look=look, index=index, tagged=True)
    return rec


class RuleTests(unittest.TestCase):
    """Quy tắc màu điểm trong `_draw_eye` (bút vẽ ghi lại, không cần cửa sổ)."""

    def test_label_mode_keeps_point_palette(self):
        for label in EYES:
            rec = draw(Look(), label)
            self.assertEqual(rec.points, {i: PALETTE[i] for i in EYES[label].ids})     # như trước khi sửa
            self.assertEqual(rec.outline[label], COLORS[label])

    def test_instance_mode_points_take_instance_color(self):
        for label, index in (("mattrai", 0), ("matphai", 9)):                          # ID 1 và 10 như CVAT
            rec = draw(Look(color_by="instance"), label, index)
            want = INSTANCE_COLORS[index % len(INSTANCE_COLORS)]
            self.assertEqual(set(rec.points.values()), {want})                          # trước khi sửa: 8 màu của bảng
            self.assertEqual(rec.outline[label], want)

    def test_group_mode_points_take_group_color(self):
        rec = draw(Look(color_by="group"), "matphai", 9)
        self.assertEqual(set(rec.points.values()), {GROUP_COLOR})
        self.assertEqual(rec.outline["matphai"], GROUP_COLOR)

    def test_custom_color_from_enter_overrides_palette_only_for_that_eye(self):
        mine = INSTANCE_COLORS[2]
        look = Look(colors={"mattrai": mine})                                          # Enter đổi màu mattrai, vẫn Color by Label
        self.assertEqual(set(draw(look, "mattrai").points.values()), {mine})
        self.assertEqual(draw(look, "matphai", 9).points, {i: PALETTE[i] for i in MR.ids})   # mắt kia giữ bảng màu điểm
        for color_by in ("instance", "group"):                                          # màu riêng thắng mọi cách tô
            self.assertEqual(set(draw(Look(color_by=color_by, colors={"mattrai": mine}), "mattrai").points.values()), {mine})

    def test_point_colors_off_still_uses_eye_color(self):
        rec = draw(Look(point_colors=False), "mattrai")
        self.assertEqual(set(rec.points.values()), {COLORS["mattrai"]})


class CvPainterTests(unittest.TestCase):
    """Đường vẽ ảnh numpy (`render_main` -> `draw_overlay` -> `CvPainter`): đọc màu pixel ở tâm điểm ghim."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b04_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))
        cls.s = Session(cls.dir)
        truth = T.pins_at(0)
        for label, spec in EYES.items():
            cls.s.add_pin(0, label, {i: truth[i] for i in spec.pins})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def centers(self, look):
        s = self.s
        img, view = render_main(s, 0, (960, 460), look=look, ids=s.obj_ids)
        pts = s.points_at(0)
        return {i: tuple(int(v) for v in img[view.to_screen(pts[i])[1], view.to_screen(pts[i])[0]])
                for spec in EYES.values() for i in spec.pins}

    def test_label_mode_keeps_point_palette(self):
        self.assertEqual(self.centers(Look()), {i: PALETTE[i] for i in PIN_IDS})

    def test_instance_mode(self):
        got = self.centers(Look(color_by="instance"))
        for label, spec in EYES.items():
            want = INSTANCE_COLORS[(self.s.obj_ids[label] - 1) % len(INSTANCE_COLORS)]
            self.assertEqual({got[i] for i in spec.pins}, {want}, label)

    def test_group_mode(self):
        self.assertEqual(set(self.centers(Look(color_by="group")).values()), {GROUP_COLOR})

    def test_custom_color(self):
        mine = INSTANCE_COLORS[4]
        got = self.centers(Look(colors={"matphai": mine}))
        self.assertEqual({got[i] for i in MR.pins}, {mine})
        self.assertEqual({i: got[i] for i in ML.pins}, {i: PALETTE[i] for i in ML.pins})

    def test_cv_painter_directly(self):
        img = np.zeros((460, 960, 3), np.uint8)
        pts = eye_pts("mattrai")
        _draw_eye(CvPainter(img), VIEW, pts, "mattrai", pinned=True, ids=False, scale=1.0, look=Look(color_by="instance"), index=0)
        for i in ML.pins:
            x, y = VIEW.to_screen(pts[i])
            self.assertEqual(tuple(int(v) for v in img[y, x]), INSTANCE_COLORS[0])


def _hex(bgr):
    return "#%02x%02x%02x" % (bgr[2], bgr[1], bgr[0])


class CanvasPainterTests(unittest.TestCase):
    """Đường vẽ trong cửa sổ (`gui.CanvasPainter`, nhãn đặc 100%): màu của đối tượng Canvas `pt:<mắt>:<id>`, và khớp với màu vạch của thẻ
    trong panel phải (`card["color"]`) ở Instance / Group / Enter."""
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
    def canvas_colors(app, label):
        """{id điểm: màu} của điểm trên Canvas: điểm ghim tô đặc (fill), điểm suy ra là vòng (outline)."""
        out = {}
        for i in EYES[label].ids:
            items = app.canvas.find_withtag(f"pt:{label}:{i}")
            assert len(items) == 1, (label, i, items)
            out[i] = app.canvas.itemcget(items[0], "fill" if i in PIN_IDS else "outline")
        return out

    def card_color(self, app, label):
        return app.tree.item(f"eye:{label}", "card")["color"]

    def test_label_mode_keeps_point_palette(self):
        app = self.pinned_app()
        self.assertGreaterEqual(app.look.opacity, 0.999)                               # đường CanvasPainter
        for label in EYES:
            self.assertEqual(self.canvas_colors(app, label), {i: _hex(PALETTE[i]) for i in EYES[label].ids})
            self.assertEqual(self.card_color(app, label), _hex(COLORS[label]))         # thẻ: màu nhãn như trước

    def test_instance_and_group_points_match_card(self):
        app = self.pinned_app()
        for color_by in ("instance", "group"):
            with self.subTest(color_by=color_by):
                app.set_look(color_by=color_by)
                for label in EYES:
                    card = self.card_color(app, label)
                    want = GROUP_COLOR if color_by == "group" else INSTANCE_COLORS[(app.s.obj_ids[label] - 1) % len(INSTANCE_COLORS)]
                    self.assertEqual(card, _hex(want))
                    self.assertEqual(set(self.canvas_colors(app, label).values()), {card})   # trước khi sửa: 8 màu của bảng
        app.set_look(color_by="label")
        self.assertEqual(self.canvas_colors(app, "mattrai"), {i: _hex(PALETTE[i]) for i in ML.ids})

    def test_enter_changes_point_color_of_selected_eye(self):
        app = self.pinned_app()
        app.tree.selection_set("eye:matphai")
        app.handlers["change_color"](None)                                             # phím Enter
        mine = app.look.colors["matphai"]
        self.assertEqual(self.card_color(app, "matphai"), _hex(mine))
        self.assertEqual(set(self.canvas_colors(app, "matphai").values()), {_hex(mine)})
        self.assertEqual(self.canvas_colors(app, "mattrai"), {i: _hex(PALETTE[i]) for i in ML.ids})   # mắt kia không đổi


if __name__ == "__main__":
    unittest.main()
