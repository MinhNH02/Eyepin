"""Thanh bên phải kiểu CVAT lắp vào cửa sổ (Task 5, spec 4 và 7b): `App.tree` là `ObjectList`, nút trên thẻ tác động đúng đối tượng
của thẻ, tab theo thứ tự CVAT, tab Frame lân cận bật/tắt, icon CVAT trên thanh trên/trái (không chữ cố định), con trỏ ↔ thẻ."""
import os
import shutil
import sys
import tempfile
import threading
import tkinter as tk
import unittest
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")

import test_tracking as T  # noqa: E402
from eyepin import shortcuts as sc  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.icons import IconButton  # noqa: E402
from test_gui_cvat import CvatGuiCase  # noqa: E402   (phiên QC và việc nền dựng như test_gui_cvat)

ML, MR = EYES["mattrai"], EYES["matphai"]


class Ev:
    def __init__(self, x=0, y=0, widget=None):
        self.x, self.y, self.widget = x, y, widget
        self.x_root, self.y_root = x, y


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def count_widgets(w):
    return sum(1 + count_widgets(c) for c in w.winfo_children())


def icon_buttons(*roots):
    return [w for r in roots for w in walk(r) if isinstance(w, IconButton)]


class SidebarAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        cls.dir = tempfile.mkdtemp(prefix="eyepin_sidebar_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def new_home(self):
        os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, os.environ["EYEPIN_HOME"], True)

    def make_app(self, pin=True):
        from eyepin.gui import App, PIN_SEQ
        self.new_home()
        app = App(self.root)
        app.ask_restore = lambda n: False
        self.addCleanup(self.close_app, app)
        app.load(self.dir, None)
        if pin:
            truth = T.pins_at(0)
            app.go(0)
            app.start_pin()
            for _, pid in PIN_SEQ:
                app.on_press(Ev(*app.view.to_screen(truth[pid])))
            self.assertIn(0, app.s.pins, app.notice)
        return app

    def close_app(self, app):
        for job in (app._autosave_job, app._thumb_job, getattr(app, "_motion_job", None)):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass

    def two_people(self):
        """Người 1 ghim ở frame 0; người 2 (bộ mới) ghim ở frame 0, toạ độ dịch sang bên (như test_object_hide_lock)."""
        app = self.make_app()
        app.new_object()
        truth = T.pins_at(0)
        pts = [(x + 40, y + 60) for x, y in (truth[i] for spec in EYES.values() for i in spec.pins)]
        app.s.add_pin_free(0, pts)
        app.pinning, app.clicks = None, []
        app.refresh()
        self.assertEqual((len(app.s.layers), app.s.cur), (2, 1))
        return app

    def eye_center(self, app, label):
        pts = app._current_points()
        ids = EYES[label].ids
        return app.view.to_screen((sum(pts[i][0] for i in ids) / len(ids), sum(pts[i][1] for i in ids) / len(ids)))

    def tab_names(self, app):
        return [app.side.tab(t, "text") for t in app.side.tabs()]

    # ---------- tab ----------
    def test_tabs_in_cvat_order(self):
        app = self.make_app(pin=False)
        self.assertEqual(self.tab_names(app), ["Objects", "Labels", "Issues", "Frame lân cận"])
        self.assertEqual(app.side.select(), str(app.objects_tab))

    def test_neighbors_tab_toggle(self):
        app = self.make_app(pin=False)
        app.set_neighbors_tab(False)
        self.assertEqual(self.tab_names(app), ["Objects", "Labels", "Issues"])
        self.assertIs(app.settings["workspace"]["show_neighbors"], False)
        self.assertIs(sc.load_settings()["workspace"]["show_neighbors"], False)        # đã ghi ra settings.json
        app.set_neighbors_tab(True)
        self.assertEqual(self.tab_names(app), ["Objects", "Labels", "Issues", "Frame lân cận"])
        self.assertIs(sc.load_settings()["workspace"]["show_neighbors"], True)

    def test_neighbors_default_on_and_saved_off_is_respected_at_start(self):
        from eyepin.gui import App
        self.assertIs(sc.DEFAULT_SETTINGS["workspace"]["show_neighbors"], True)
        self.new_home()
        st = sc.load_settings()
        st["workspace"]["show_neighbors"] = False
        sc.save_settings(st)
        app = App(self.root)
        self.addCleanup(self.close_app, app)
        self.assertEqual(self.tab_names(app), ["Objects", "Labels", "Issues"])

    def test_neighbors_off_skips_thumbnails(self):
        from eyepin import gui
        app = self.make_app()
        calls = []
        real = gui.render_thumb
        with mock.patch.object(gui, "render_thumb", side_effect=lambda *a, **k: calls.append(1) or real(*a, **k)):
            app.set_neighbors_tab(False)
            app.refresh()
            app._thumbs_tick()
            self.assertEqual(calls, [])
            app.set_neighbors_tab(True)
            app.refresh()
            self.assertTrue(calls)
        self.assertNotEqual(str(app.t_prev.cget("image")) + str(app.t_next.cget("image")), "")

    def test_settings_workspace_has_neighbors_checkbox(self):
        app = self.make_app(pin=False)
        app.show_settings()
        app.root.update_idletasks()
        boxes = [w for w in walk(app._dialogs["settings"]) if w.winfo_class() == "TCheckbutton"
                 and str(w.cget("text")) == "Hiện tab Frame lân cận"]
        self.assertEqual(len(boxes), 1)
        boxes[0].invoke()
        self.assertEqual(len(app.side.tabs()), 3)
        self.assertIs(app.settings["workspace"]["show_neighbors"], False)
        boxes[0].invoke()
        self.assertEqual(self.tab_names(app)[-1], "Frame lân cận")
        app._dialogs["settings"].destroy()

    # ---------- thẻ đối tượng ----------
    def test_tree_is_an_object_list(self):
        from eyepin.gui_sidebar import ObjectList
        app = self.make_app()
        self.assertIsInstance(app.tree, ObjectList)
        self.assertEqual(app.tree.get_children(), ("eye:mattrai", "eye:matphai"))
        self.assertTrue(app.tree.item("eye:mattrai", "text").startswith("#1"))           # chữ của dòng giữ như cũ (test cũ đọc nó)

    def test_card_buttons_act_on_their_object(self):
        app = self.two_people()
        app.go(0)
        app.hover = self.eye_center(app, "mattrai")            # vị trí chuột cũ trên ảnh: nút trên thẻ không được theo nó
        with app.s.layer_ctx(0):
            before0 = dict(app.s.flags_at(0))
        app._on_object_action("occluded", "eye:matphai@1")
        with app.s.layer_ctx(1):
            got = {i for i, k in app.s.flags_at(0).items() if k == "occluded"}
        self.assertEqual(got, set(MR.ids))
        with app.s.layer_ctx(0):
            self.assertEqual(dict(app.s.flags_at(0)), before0)
        app.hover = self.eye_center(app, "mattrai")
        app._on_object_action("hidden", "eye:matphai@1")
        self.assertIn((1, "matphai"), app.hidden_objs)
        self.assertNotIn((0, "matphai"), app.hidden_objs)
        self.assertNotIn((1, "mattrai"), app.hidden_objs)
        # bấm thật vào nút Lock trên thẻ của người 1: chỉ khoá mắt đó của người 1
        app.tree.buttons("eye:mattrai")["lock"]._click(None)
        self.assertEqual(app.s.cur, 0)
        self.assertIn("mattrai", app.locked)
        app.s.select_layer(1)
        self.assertNotIn("mattrai", app.locked)

    def test_point_outside_button_flags_only_that_point(self):
        app = self.two_people()
        app.go(0)
        app.hover = self.eye_center(app, "mattrai")            # vị trí chuột cũ trên ảnh: nút của điểm không được theo nó
        with app.s.layer_ctx(0):
            before0 = dict(app.s.flags_at(0))
        with app.s.layer_ctx(1):
            before1 = dict(app.s.flags_at(0))
        app.tree.point_buttons("pt:17@1")["occluded"]._click(None)      # bấm thật vào nút Occluded của điểm 17 người 2
        self.assertEqual(app.tree.selection(), ("pt:17@1",))
        self.assertEqual(app.s.cur, 1)
        with app.s.layer_ctx(1):
            flags = dict(app.s.flags_at(0))
        self.assertEqual(flags.get(17), "occluded")
        self.assertEqual({i: k for i, k in flags.items() if i != 17}, {i: k for i, k in before1.items() if i != 17})
        with app.s.layer_ctx(0):
            self.assertEqual(dict(app.s.flags_at(0)), before0)         # người 1 không đổi
        self.assertEqual(app.tree.point_buttons("pt:17@1")["occluded"].name, "occluded")   # nút theo trạng thái mới
        self.assertEqual(app.tree.row_texts("pt:17@1")[2], "Occluded")
        app.tree.point_buttons("pt:17@1")["occluded"]._click(None)      # bấm lại: bỏ cờ
        with app.s.layer_ctx(1):
            self.assertNotEqual(app.s.flags_at(0).get(17), "occluded")
        app.tree.point_buttons("pt:23@1")["outside"]._click(None)       # Outside của một điểm mắt phải
        with app.s.layer_ctx(1):
            flags = dict(app.s.flags_at(0))
        self.assertEqual(flags.get(23), "outside")
        self.assertEqual([i for i, k in flags.items() if k == "outside"], [23])
        self.assertEqual(app.tree.point_buttons("pt:23@1")["outside"].name, "outside")
        # người 1, thao tác qua action (như nút) với iid không hậu tố
        app.hover = None
        app._on_object_action("outside", "pt:15")
        self.assertEqual(app.s.cur, 0)
        with app.s.layer_ctx(0):
            self.assertEqual([i for i, k in app.s.flags_at(0).items() if k == "outside"], [15])

    def test_card_navigation_buttons(self):
        app = self.make_app()
        app.s.toggle_pin_here(20)
        app.go(0)
        b = app.tree.buttons("eye:mattrai")
        self.assertFalse(b["prev"]._enabled)
        self.assertFalse(b["first"]._enabled)
        self.assertTrue(b["next"]._enabled and b["last"]._enabled)
        app.go(5)
        app._on_object_action("next", "eye:mattrai")
        self.assertEqual(app.f, 20)
        app._on_object_action("prev", "eye:mattrai")
        self.assertEqual(app.f, 0)
        app._on_object_action("last", "eye:mattrai")
        self.assertEqual(app.f, 20)
        app._on_object_action("first", "eye:mattrai")
        self.assertEqual(app.f, 0)

    def test_card_shows_object_state(self):
        app = self.make_app()
        app.s.toggle_pin_here(20)
        app.go(0)
        c = app.tree.item("eye:mattrai", "card")
        self.assertEqual((c["id"], c["label"], c["type"], c["status"]), (1, "mattrai", "SKELETON TRACK", "keyframe"))
        self.assertTrue(c["keyframe"])
        self.assertTrue(c["color"].startswith("#") and len(c["color"]) == 7)
        self.assertEqual(app.tree.buttons("eye:mattrai")["keyframe"].name, "star")
        app.go(10)
        c = app.tree.item("eye:mattrai", "card")
        self.assertEqual((c["keyframe"], c["status"], c["has_prev"], c["has_next"]), (False, "tool tính", True, True))
        self.assertEqual(app.tree.buttons("eye:mattrai")["keyframe"].name, "star_off")
        app.locked.add("mattrai")
        app.pinned_eyes.add("matphai")
        app.hidden_objs.add((0, "matphai"))
        app.refresh()
        self.assertEqual(app.tree.buttons("eye:mattrai")["lock"].name, "lock")
        self.assertEqual(app.tree.buttons("eye:matphai")["pinned"].name, "pinned")
        self.assertEqual(app.tree.buttons("eye:matphai")["hidden"].name, "eye_off")
        self.assertEqual(app.tree.buttons("eye:mattrai")["hidden"].name, "eye")

    def test_keyframe_star_on_card_toggles_only_that_eye(self):
        app = self.make_app()
        app.go(10)
        app.tree.buttons("eye:matphai")["keyframe"]._click(None)
        self.assertEqual(app.s.eye_keyframes("matphai"), [0, 10])
        self.assertEqual(app.s.eye_keyframes("mattrai"), [0])
        self.assertEqual(app.tree.set("eye:matphai", "sao"), "★")

    def test_label_change_returns_focus_to_canvas(self):
        app = self.make_app()
        before = {i: tuple(p) for i, p in app.s.pins[0].items()}
        calls = []
        app.canvas.focus_set = lambda: calls.append("canvas")
        app.tree.label_picker("eye:mattrai").set("matphai")
        app._on_object_action("label", "eye:mattrai")
        after = app.s.pins[0]
        for a, b in zip(ML.ids, MR.ids):
            self.assertEqual(tuple(after[b]), before[a])
            self.assertEqual(tuple(after[a]), before[b])
        self.assertIn("canvas", calls)
        self.assertEqual(app.tree.label_of("eye:mattrai"), "mattrai")              # ô label theo lại dữ liệu
        calls.clear()
        app.tree.label_picker("eye:mattrai").set("mattrai")                        # chọn lại đúng label cũ: không đổi gì
        app._on_object_action("label", "eye:mattrai")
        self.assertEqual({i: tuple(p) for i, p in app.s.pins[0].items()}, {i: tuple(p) for i, p in after.items()})
        self.assertIn("canvas", calls)

    def test_refresh_during_play_does_not_rebuild_cards(self):
        app = self.make_app()
        app.refresh()
        n = count_widgets(app.tree)
        card = app.tree.row_widget("eye:mattrai")
        self.assertIsNotNone(card)
        for _ in range(5):
            app.step(1)
        self.assertEqual(count_widgets(app.tree), n)
        self.assertIs(app.tree.row_widget("eye:mattrai"), card)

    def test_cards_and_left_star_follow_playback_and_pause(self):
        """Phát (Space) chỉ vẽ nhẹ mỗi frame: thẻ và nút ★ thanh trái vẫn phải theo frame đang xem (cập nhật tại chỗ), và đúng khi dừng."""
        app = self.make_app()
        app.go(0)
        b = app.tree.buttons("eye:mattrai")
        card = app.tree.row_widget("eye:mattrai")
        self.assertEqual((b["keyframe"].name, b["prev"]._enabled, app.kf_btn.name), ("star", False, "star"))
        app.toggle_play()
        self.assertTrue(app.playing)
        for _ in range(7):
            app._tick()                                                           # như bộ hẹn giờ khi phát
        self.assertEqual(app.f, 7)
        c = app.tree.item("eye:mattrai", "card")
        self.assertEqual((c["keyframe"], c["status"], c["has_prev"]), (False, "tool tính", True))
        self.assertEqual((b["keyframe"].name, b["prev"]._enabled, app.kf_btn.name), ("star_off", True, "star_off"))
        self.assertIs(app.tree.row_widget("eye:mattrai"), card)                    # cập nhật tại chỗ, không dựng lại thẻ
        app.toggle_play()                                                         # dừng
        self.assertFalse(app.playing)
        self.assertEqual(app.tree.set("eye:mattrai", "sao"), "☆")
        self.assertEqual(app.tree.card_texts("eye:mattrai")[2], "tool tính")
        b["prev"]._click(None)                                                    # nút keyframe trước trên thẻ bấm được
        self.assertEqual(app.f, 0)

    def test_play_to_the_end_leaves_cards_current(self):
        app = self.make_app()
        n = app.s.n_frames
        app.s.toggle_eye_key("mattrai", n - 3)                                    # keyframe ở frame bắt đầu phát
        app.go(n - 3)
        self.assertEqual((app.tree.item("eye:mattrai", "card")["keyframe"], app.kf_btn.name), (True, "star"))
        app.toggle_play()
        for _ in range(4):
            app._tick()                                                           # tick cuối: hết clip, tự dừng
        self.assertFalse(app.playing)
        self.assertEqual(app.f, n - 1)
        self.assertEqual(app.play_btn.name, "play")
        c = app.tree.item("eye:mattrai", "card")
        self.assertEqual((c["keyframe"], c["has_prev"], c["has_last"]), (False, True, True))
        self.assertEqual(app.kf_btn.name, "star_off")

    def test_left_star_follows_selection_change(self):
        app = self.make_app()
        app.s.toggle_eye_key("matphai", 10)                                       # frame 10: keyframe của riêng matphai
        app.go(10)
        self.assertEqual(app.kf_btn.name, "star")                                 # chưa chọn mắt: keyframe của cả job
        app.tree.selection_set("eye:mattrai")
        self.assertEqual(app.kf_btn.name, "star_off")
        app.select_eye("matphai")
        self.assertEqual(app.kf_btn.name, "star")
        app.select_eye("mattrai", quiet=True)
        self.assertEqual(app.kf_btn.name, "star_off")

    def test_selecting_a_card_of_another_person_switches_person_at_once(self):
        app = self.two_people()
        app.tree.selection_set("eye:mattrai")                    # không cần vòng sự kiện: on_select chạy đồng bộ
        self.assertEqual(app.s.cur, 0)
        app.tree.selection_set("eye:matphai@1")
        self.assertEqual(app.s.cur, 1)
        self.assertEqual(app._selected(), ("matphai", None))

    def test_menu_has_remove(self):
        app = self.make_app()
        labels = [app.obj_menu.entrycget(i, "label") for i in range(app.obj_menu.index("end") + 1)
                  if app.obj_menu.type(i) in ("command", "checkbutton")]
        self.assertTrue(any("Remove" in l for l in labels), labels)

    def test_menu_and_focus_actions_from_the_card(self):
        app = self.make_app()
        popped = []
        app.obj_menu.tk_popup = lambda x, y: popped.append((x, y))
        app.tree.menu_xy = (123, 45)
        app.tree.selection_set("eye:matphai")
        app._on_object_action("menu", "eye:matphai")
        self.assertEqual(popped, [(123, 45)])
        app.tree.selection_set("eye:mattrai")
        app.tree.buttons("eye:matphai")["more"]._click(None)                      # nút ⋮ trên thẻ: chọn thẻ đó rồi mở menu
        self.assertEqual(app.tree.selection(), ("eye:matphai",))
        self.assertEqual(len(popped), 2)
        app._on_object_action("focus", "eye:matphai")                             # nhấp đúp thẻ: phóng vào mắt
        self.assertIsNotNone(app.manual)
        self.assertIn("matphai", app.notice)

    def test_header_buttons_follow_state(self):
        app = self.make_app()
        hb = app.obj_head_btns
        self.assertEqual([hb[k].name for k in ("lock_all", "hide_all", "collapse", "add", "trash")],
                         ["unlock", "eye", "caret_down", "add", "trash"])
        hb["lock_all"]._click(None)
        self.assertEqual(app.locked, set(EYES))
        self.assertEqual(hb["lock_all"].name, "lock")
        hb["hide_all"]._click(None)
        self.assertEqual(app.look.eyes, {"mattrai": False, "matphai": False})
        self.assertEqual(hb["hide_all"].name, "eye_off")
        hb["collapse"]._click(None)
        self.assertTrue(all(app.tree.item(i, "open") for i in app.tree.get_children()))
        self.assertEqual(hb["collapse"].name, "caret_up")
        hb["collapse"]._click(None)
        self.assertFalse(any(app.tree.item(i, "open") for i in app.tree.get_children()))
        self.assertEqual(hb["collapse"].name, "caret_down")

    def test_card_tooltips_follow_rebound_keys(self):
        app = self.make_app(pin=False)
        self.assertEqual(app.tree.tip("occluded"), f"Occluded ({app.kl('occluded')})")
        self.assertIsNone(app.rebind("occluded", "<F7>"))
        self.assertEqual(app.tree.tip("occluded"), "Occluded (F7)")

    # ---------- con trỏ chuột ↔ thẻ ----------
    def test_hover_on_eye_activates_card(self):
        app = self.make_app()
        app.on_hover(Ev(*self.eye_center(app, "matphai")))
        self.assertEqual(app.tree.activated(), "eye:matphai")
        app.on_hover(Ev(*self.eye_center(app, "mattrai")))
        self.assertEqual(app.tree.activated(), "eye:mattrai")
        app.on_leave(None)
        self.assertIsNone(app.tree.activated())

    def test_pointer_on_card_draws_that_eye_bold(self):
        app = self.make_app()
        app.refresh()
        width = lambda: float(app.canvas.itemcget(app.canvas.find_withtag("outline:matphai")[0], "width"))
        self.assertEqual(width(), 1.0)
        app.tree.on_hover("eye:matphai")                                          # con trỏ vào thẻ #10
        app.refresh(light=True)
        self.assertGreater(width(), 1.0)
        self.assertEqual(float(app.canvas.itemcget(app.canvas.find_withtag("outline:mattrai")[0], "width")), 1.0)
        self.assertEqual(app.tree.activated(), "eye:matphai")
        app.tree.on_hover(None)
        app.refresh(light=True)
        self.assertEqual(width(), 1.0)
        self.assertIsNone(app.tree.activated())

    def test_pointer_on_card_does_not_scroll_the_list(self):
        app = self.make_app()
        with mock.patch.object(app.tree, "_scroll_to") as scroll:
            app.tree.on_hover("eye:matphai")                                      # cuộn lúc này sẽ kéo thẻ khác vào dưới con trỏ
            self.assertEqual(scroll.call_count, 0)
            app.tree.on_hover(None)
            app.on_hover(Ev(*self.eye_center(app, "matphai")))                    # con trỏ trên mắt trong ảnh: cuộn tới thẻ
            self.assertEqual(scroll.call_count, 1)

    def test_object_list_forgets_hover_of_a_destroyed_card(self):
        from eyepin.gui_sidebar import ObjectList
        got = []
        ol = ObjectList(self.root, on_action=lambda a, i: None, on_select=lambda: None, on_hover=got.append)
        self.addCleanup(ol.destroy)
        for label in EYES:
            ol.insert("", "end", iid=f"eye:{label}", text=label, card={"id": 1, "label": label})
        ol._hover("eye:matphai")                                                  # con trỏ đang ở trên thẻ #10
        ol.begin_update()
        ol.delete(*ol.get_children())
        ol.insert("", "end", iid="eye:mattrai", text="mattrai", card={"id": 1, "label": "mattrai"})
        ol.end_update()                                                           # thẻ #10 bị huỷ dưới con trỏ
        self.assertEqual(got, ["eye:matphai", None])
        self.assertIsNone(ol._hover_iid)
        ol._hover("eye:mattrai")
        ol.delete("eye:mattrai")
        self.assertEqual(got, ["eye:matphai", None, "eye:mattrai", None])

    # ---------- phím, ẩn, khoá ----------
    def test_l_key_follows_mouse(self):
        app = self.make_app()
        app.select_eye("mattrai", quiet=True)
        app.hover = self.eye_center(app, "matphai")
        app.handlers["lock"]()
        self.assertIn("matphai", app.locked)
        self.assertNotIn("mattrai", app.locked)
        app.hover = None                                                          # chuột không ở trên mắt nào: mắt đang chọn
        app.handlers["lock"]()
        self.assertIn("mattrai", app.locked)

    def test_stale_hidden_objs_pruned(self):
        app = self.two_people()
        app.hover = None
        app.hidden_objs.add((1, "mattrai"))
        app.pinned_eyes.add("mattrai")                                            # người 2 (bộ đang chọn)
        for iid in ("eye:mattrai@1", "eye:matphai@1"):
            app.tree.selection_set(iid)
            app.delete_label(force=True)
        self.assertEqual(len(app.s.layers), 1)                                    # bộ rỗng tự bỏ
        self.assertNotIn((1, "mattrai"), app.hidden_objs)
        app.new_object()                                                          # người mới lại là bộ 1: không được thừa hưởng
        truth = T.pins_at(0)
        app.s.add_pin_free(0, [(x + 40, y + 60) for x, y in (truth[i] for spec in EYES.values() for i in spec.pins)])
        app.pinning, app.clicks = None, []
        app.refresh()
        self.assertEqual(app.s.cur, 1)
        self.assertFalse(app._obj_hidden(1, "mattrai"))
        self.assertNotIn("mattrai", app.pinned_eyes)

    def test_render_thumb_skips_hidden_objects(self):
        from eyepin import gui
        from eyepin.render import Look, render_thumb
        app = self.make_app()
        plain = render_thumb(app.s, 0, app.view, (300, 140), look=Look()).astype(int)
        hid = render_thumb(app.s, 0, app.view, (300, 140), look=Look(), hidden=frozenset({(0, "mattrai")})).astype(int)
        by_label = render_thumb(app.s, 0, app.view, (300, 140), look=Look(eyes={"mattrai": False, "matphai": True})).astype(int)
        self.assertTrue(np.array_equal(hid, by_label))
        self.assertGreater(int(np.abs(plain - hid).sum()), 0)
        seen = []
        real = gui.render_thumb
        app.hidden_objs.add((0, "mattrai"))
        with mock.patch.object(gui, "render_thumb", side_effect=lambda *a, **k: seen.append(k.get("hidden")) or real(*a, **k)):
            app._update_thumbs()
        self.assertTrue(seen)
        self.assertTrue(all(h == frozenset({(0, "mattrai")}) for h in seen), seen)

    # ---------- thanh trên, thanh trái: icon CVAT, không chữ cố định ----------
    def app_bars(self, app):
        return [app._top_bar, app._name_row, app.tool_btns["cursor"].master, app.side]

    def test_no_captions_anywhere(self):
        app = self.make_app()
        app.refresh()
        btns = icon_buttons(app.root)
        self.assertGreater(len(btns), 40)
        for b in btns:
            self.assertIsNone(b.cap, b.name)
            for c in walk(b):
                if isinstance(c, tk.Label):
                    self.assertEqual(str(c.cget("text")), "", b.name)

    def test_every_icon_button_has_a_png(self):
        app = self.make_app()
        app.refresh()
        for b in icon_buttons(*self.app_bars(app)):
            self.assertEqual(b.glyph, "", f"nút {b.name} đang dùng chữ thay icon")
            self.assertNotEqual(str(b.icon.cget("image")), "", b.name)

    def test_zoom_icons_differ(self):
        app = self.make_app(pin=False)
        tools = app.tool_btns["cursor"].master
        by = {b.name: b for b in icon_buttons(tools)}
        zin, zout = by["zoom_in"], by["zoom_out"]
        self.assertNotEqual(str(zin.icon.cget("image")), str(zout.icon.cget("image")))
        self.assertEqual((zin.glyph, zout.glyph), ("", ""))

    def test_keyframe_jump_buttons_differ_from_frame_buttons(self):
        app = self.make_app(pin=False)
        for kf, fr in ((app.kf_prev_btn, app.frame_prev_btn), (app.kf_next_btn, app.frame_next_btn)):
            self.assertNotEqual(str(kf.icon.cget("image")), str(fr.icon.cget("image")))
            self.assertEqual(kf.glyph, "")

    def test_frame_nav_icons_follow_filter(self):
        app = self.make_app()
        self.assertEqual((app.frame_prev_btn.name, app.frame_next_btn.name), ("prev", "next"))
        app._filter_var.set("pinned"); app.set_filter()
        self.assertEqual((app.frame_prev_btn.name, app.frame_next_btn.name), ("prev_filtered", "next_filtered"))
        app._filter_var.set("all"); app.set_filter()
        self.assertEqual((app.frame_prev_btn.name, app.frame_next_btn.name), ("prev", "next"))

    def test_send_button_uses_cloud_upload_icon_and_greys_out(self):
        app = self.make_app(pin=False)
        self.assertEqual(app.cvat_send_btn.name, "upload")
        self.assertFalse(app.cvat_send_btn._enabled)                              # không mở job CVAT: nút Gửi mờ


class SidebarQcTests(CvatGuiCase):
    """Nút trên thẻ không sửa nhãn ở chế độ QC hay khi đang có việc nền (`_edit_blocked`)."""

    def test_card_edit_blocked_in_qc(self):
        self.serve(self.qc_job())
        app = self.make_app()
        s = self.open_job(app)
        app.go(0)
        self.assertTrue(s.qc)
        before = s.state()
        for action in ("keyframe", "outside", "occluded", "label"):
            app.notice = ""
            if action == "label":
                app.tree.label_picker("eye:mattrai").set("matphai")
            app._on_object_action(action, "eye:mattrai")
            self.assertIn("chế độ QC", app.notice, action)
            self.assertEqual(s.state(), before, action)
        app.notice = ""
        app.tree.buttons("eye:mattrai")["keyframe"]._click(None)                   # bấm thật vào ★ trên thẻ
        self.assertIn("chế độ QC", app.notice)
        self.assertEqual(s.state(), before)

    def test_point_buttons_blocked_in_qc(self):
        self.serve(self.qc_job())
        app = self.make_app()
        s = self.open_job(app)
        app.go(0)
        self.assertTrue(s.qc)
        before = s.state()
        for kind in ("outside", "occluded"):
            app.notice = ""
            app.tree.point_buttons("pt:17")[kind]._click(None)                     # bấm thật vào nút của điểm
            self.assertIn("chế độ QC", app.notice, kind)
            self.assertEqual(s.state(), before, kind)

    def test_card_edit_blocked_while_busy(self):
        self.serve()
        app = self.make_app()
        s = self.open_job(app)
        self.draw(app)
        app.go(3)
        gate = threading.Event()
        app._run_bg(lambda: gate.wait(10), lambda res, err: None, "Đang gửi thử…")
        before = s.state()
        for action in ("keyframe", "outside", "occluded"):
            app.notice = ""
            app._on_object_action(action, "eye:mattrai")
            self.assertIn("Đang gửi thử…", app.notice, action)
            self.assertEqual(s.state(), before, action)
        gate.set()
        self.wait(app)
        app._on_object_action("keyframe", "eye:mattrai")                           # xong việc nền: ★ trên thẻ lại hoạt động
        self.assertIn(3, s.eye_keyframes("mattrai"))


if __name__ == "__main__":
    unittest.main()
