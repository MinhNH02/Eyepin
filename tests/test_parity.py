"""Các tính năng tái hiện từ CVAT (design/cvat-parity.md): panel Đối tượng, Labels, Issues, Appearance, Menu, thao tác frame."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import tkinter as tk  # noqa: E402

import numpy as np  # noqa: E402

from eyepin.geometry import EYES  # noqa: E402
from eyepin.headturn import Turn, TurnReport  # noqa: E402
from eyepin.render import TURN_BGR, TURN_UNSURE_BGR, Look, render_main, render_timeline  # noqa: E402
from eyepin.scan import Finding  # noqa: E402
import test_gui as _tg  # noqa: E402

Ev = _tg.Ev

ML, MR = EYES["mattrai"], EYES["matphai"]


class ParityTests(unittest.TestCase):
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

    def render(self, app, **kw):
        look = kw.pop("look", app.look)
        return render_main(app.s, 10, (960, 460), anchor=app.anchor, manual=app.view, look=look, **kw)[0].astype(int)

    # ---------- panel Đối tượng ----------
    def test_sort_by(self):
        app = self.pinned_app()
        order = lambda: [i.split(":")[1] for i in app.tree.get_children()]
        self.assertEqual(order(), ["mattrai", "matphai"])
        app.sort_var.set("ID - giảm dần"); app.refresh()
        self.assertEqual(order(), ["matphai", "mattrai"])
        app.sort_var.set("Tên label"); app.refresh()
        self.assertEqual(order(), ["matphai", "mattrai"])                 # theo chữ cái: matphai trước mattrai
        app.sort_var.set("Cập nhật gần nhất")
        app.s.touched = {"mattrai": 100.0, "matphai": 50.0}; app.refresh()
        self.assertEqual(order(), ["mattrai", "matphai"])
        app.s.touched = {"mattrai": 50.0, "matphai": 100.0}; app.refresh()
        self.assertEqual(order(), ["matphai", "mattrai"])
        self.assertEqual(app.items_var.get(), "Items: 2")
        self.assertTrue(app.tree.item("eye:mattrai", "text").startswith("#1"))      # ID không đổi theo thứ tự sắp xếp

    def test_lock_all_hide_all_collapse(self):
        app = self.pinned_app()
        app.toggle_lock_all()
        self.assertEqual(app.locked, set(EYES))
        app.toggle_lock_all()
        self.assertEqual(app.locked, set())
        app.hide_all_eyes()
        self.assertEqual(app.look.eyes, {"mattrai": False, "matphai": False})
        app.hide_all_eyes()
        self.assertEqual(app.look.eyes, {"mattrai": True, "matphai": True})
        app.tree.item("eye:mattrai", open=True)
        app.collapse_all()
        self.assertFalse(app.tree.item("eye:mattrai", "open"))
        app.collapse_all()
        self.assertTrue(app.tree.item("eye:mattrai", "open"))

    def test_swap_labels_and_undo(self):
        app = self.pinned_app()
        before = {i: tuple(p) for i, p in app.s.pins[0].items()}
        app.s.toggle_flag(0, 17, "occluded")
        app.swap_labels()
        after = app.s.pins[0]
        for a, b in zip(ML.ids, MR.ids):
            self.assertEqual(after[b], before[a])
            self.assertEqual(after[a], before[b])
        self.assertEqual(app.s.flags[0][25], "occluded")                 # cờ đi theo điểm: 17 -> 25
        self.assertTrue(app.s.undo())
        self.assertEqual(app.s.pins[0], before)
        self.assertEqual(app.s.flags[0][17], "occluded")

    def test_pinned_blocks_whole_eye_moves_and_rotation_but_not_single_points(self):
        app = self.pinned_app()
        app.tree.selection_set("eye:mattrai")
        self.assertIsNotNone(app._handle_arg())
        app.toggle_pinned()
        self.assertIn("mattrai", app.pinned_eyes)
        self.assertIsNone(app._handle_arg())                              # tay cầm xoay biến mất
        before = dict(app.s.pins[10]) if 10 in app.s.pins else dict(app.s.labels[10].points)
        app.rotate_eye(5)
        self.assertIn("Pinned", app.notice)
        self.assertNotIn(10, app.s.pins)                                  # không có gì thay đổi
        cx = sum(before[i][0] for i in (14, 18)) / 2
        cy = sum(before[i][1] for i in (14, 18)) / 2
        sx, sy = app.view.to_screen((cx, cy + 1))
        app.on_press(Ev(sx, sy)); app.on_motion(Ev(sx + 30, sy)); app.on_release(Ev(sx + 30, sy))
        self.assertNotIn(10, app.s.pins)                                  # kéo thân mắt bị từ chối
        px, py = app.view.to_screen(before[16])
        app.on_press(Ev(px, py)); app.on_motion(Ev(px + 20, py)); app.on_release(Ev(px + 20, py))
        self.assertIn(10, app.s.pins)                                     # kéo từng điểm vẫn được
        self.assertIn("[pinned]", app.tree.item("eye:mattrai", "text"))

    def test_make_a_copy_then_paste_replaces_only_that_eye(self):
        app = self.pinned_app()
        app.tree.selection_set("eye:mattrai")
        app.object_copy()
        self.assertEqual(set(app.clipboard), set(ML.ids))
        app.go(30)
        before_right = dict((app.s.pins.get(30) or app.s.labels[30].points))
        app.paste_pins()
        self.assertIn(30, app.s.pins)
        for i in MR.ids:
            self.assertEqual(app.s.points_at(30)[i], before_right[i])     # mắt kia giữ nguyên
        self.assertNotIn(30, app.s.eye_keyframes("matphai"))              # và không thành keyframe (B26)
        for i in ML.ids:
            self.assertEqual(app.s.pins[30][i], app.clipboard[i])

    def test_propagate_copies_labels_and_flags_in_one_undo_step(self):
        app = self.pinned_app()
        app.s.toggle_flag(0, 16, "outside")
        app.go(0)
        app.tree.selection_set("eye:mattrai")
        app.object_propagate(count=3)
        self.assertEqual(sorted(app.s.pins), [0, 1, 2, 3])
        for g in (1, 2, 3):
            self.assertEqual(app.s.pins[g], app.s.pins[0])
            self.assertEqual(app.s.flags[g], {16: "outside"})
        self.assertTrue(app.s.undo())
        self.assertEqual(sorted(app.s.pins), [0])
        self.assertEqual(app.s.propagate(app.s.n_frames - 1, 5), 0)         # đã ở frame cuối: không có frame nào để nhân
        from eyepin.session import Session
        with self.assertRaises(ValueError):
            Session(app.s.frames_dir).propagate(0, 2)                        # chưa có nhãn

    def test_propagate_directions_and_range_like_cvat_dialog(self):
        app = self.pinned_app()
        app.go(20)
        app.s.toggle_pin_here(20)
        app.tree.selection_set("eye:matphai")
        app.object_propagate(count=2, direction=-1)                       # sang trước
        self.assertEqual(sorted(g for g in app.s.pins if g != 0), [18, 19, 20])
        app.object_propagate(start=30, end=33)                            # theo khoảng frame
        self.assertEqual(sorted(g for g in app.s.pins if g >= 30), [30, 31, 32, 33])
        self.assertEqual(app.s.pins[33], app.s.pins[20])
        self.assertEqual(app.s.propagate(20, 5, -1, 25, 22), 4)           # khoảng đảo đầu cuối vẫn hiểu đúng, bỏ qua chính frame đang xem
        app.s.undo()
        # hộp thoại: bấm Yes với giá trị mặc định thì nhân tới hết job
        import threading
        def click_yes():
            d = app._propagate_dlg
            for w in d.winfo_children():
                if isinstance(w, tk.Frame) or w.winfo_class() == "TFrame":
                    for b in w.winfo_children():
                        if b.winfo_class() == "TButton" and b.cget("text") == "Yes":
                            b.invoke()
        app.root.after(300, click_yes)
        app.go(40)
        app.object_propagate()
        self.assertEqual(max(app.s.pins), app.s.n_frames - 1)

    def test_layers_remove_and_url(self):
        app = self.pinned_app()
        app.tree.selection_set("eye:mattrai")
        app.object_layer("front")
        self.assertEqual(app.look.top, "mattrai")
        app.object_layer("back")
        self.assertEqual(app.look.top, "matphai")
        app.object_layer("forward")
        self.assertEqual(app.look.top, "mattrai")
        app.object_layer("backward")
        self.assertEqual(app.look.top, "matphai")
        app.object_move_to_layer(1)
        self.assertEqual(app.look.top, "mattrai")
        app.object_move_to_layer(0)
        self.assertEqual(app.look.top, "matphai")
        app.object_url()
        clip = app.root.clipboard_get()
        self.assertTrue(clip.endswith("#frame=10#mattrai"), clip)
        app.s.toggle_pin_here(10)
        app.object_remove()
        self.assertNotIn(10, app.s.pins)
        app.object_remove()
        self.assertIn("không phải keyframe", app.notice)

    def test_change_color_cycles_per_eye(self):
        app = self.pinned_app()
        app.tree.selection_set("eye:matphai")
        a = self.render(app)
        app.handlers["change_color"](None)
        c1 = app.look.colors["matphai"]
        app.handlers["change_color"](None)
        self.assertNotEqual(c1, app.look.colors["matphai"])
        self.assertNotIn("mattrai", app.look.colors)
        self.assertGreater(int(np.abs(a - self.render(app)).sum()), 0)

    def test_context_menu_has_all_cvat_items(self):
        app = self.pinned_app()
        labels = [app.obj_menu.entrycget(i, "label") for i in range(app.obj_menu.index("end") + 1) if app.obj_menu.type(i) in ("command", "checkbutton")]
        for want in ("Tạo URL đối tượng", "Tạo bản sao", "Nhân sang N frame sau", "Đưa xuống nền", "Đưa lên trước", "Xuống một lớp",
                     "Lên một lớp", "Chuyển tới lớp", "Pinned", "Đổi label", "Bỏ keyframe", "Chạy hành động"):
            self.assertTrue(any(l.startswith(want) for l in labels), want)

    # ---------- Labels, Issues ----------
    def test_labels_tab_lock_and_hide_per_label(self):
        app = self.pinned_app()
        lk, ey, _ = app._label_btns["matphai"]
        lk._click(None)
        self.assertIn("matphai", app.locked)
        self.assertTrue(lk._active)
        ey._click(None)
        self.assertFalse(app.look.eyes["matphai"])
        self.assertTrue(ey._active)
        lk._click(None); ey._click(None)
        self.assertEqual((app.locked, app.look.eyes["matphai"]), (set(), True))

    def test_issues_tab_count_navigation_resolve_and_timeline(self):
        app = self.pinned_app()
        app.s.findings = [Finding("red", "crossing", "mattrai", 5, 6, (), "bắt chéo", None, [5, 6]),
                          Finding("yellow", "jump", "matphai", 20, 20, (), "nhảy", 20.0, [20]),
                          Finding("yellow", "ear_jump", "mattrai", 40, 40, (), "EAR", 0.2, [40])]
        app._fill_issues()
        self.assertEqual(app.issues_var.get(), "Items: 3")
        app.go(0)
        app.issue_step(1); self.assertEqual(app.f, 5)
        app.issue_step(1); self.assertEqual(app.f, 20)
        app.issue_step(-1); self.assertEqual(app.f, 5)
        app.issue_step(-1); self.assertIn("Không còn", app.notice)
        on = render_timeline(app.s, 0, 600)
        app.issue_toggle_show()
        off = render_timeline(app.s, 0, 600, show_issues=app.show_issues)
        self.assertFalse(app.show_issues)
        self.assertGreater(int(np.abs(on.astype(int) - off.astype(int)).sum()), 0)
        app.issue_table.selection_set("1")
        app.issue_resolve()
        self.assertEqual(app.issues_var.get(), "Items: 2")
        self.assertEqual([fd.frame for fd in app.s.findings], [5, 40])

    def two_turns(self):
        return [TurnReport("ok", 150.0, (Turn(20, 39, 30, 0.3, "mạnh", "mattrai", 2, 0, 0, 0),
                                         Turn(50, 55, 52, 0.15, "nhẹ", None, 0, 0, 0, 0)), 0, 3)]

    def test_timeline_shows_turn_band(self):
        app = self.pinned_app()
        app.s.turns = self.two_turns()
        img = render_timeline(app.s, 0, width=600)          # 60 frame, mỗi frame rộng 10 px
        col = lambda f: tuple(int(v) for v in img[3, f * 10 + 5])
        self.assertEqual(col(25), TURN_BGR)
        self.assertEqual(col(52), TURN_UNSURE_BGR)
        self.assertEqual(col(45), (235, 235, 235))
        app.s.turns = []
        img = render_timeline(app.s, 0, width=600)
        self.assertTrue((img[3, 100:] == 235).all())

    def test_issues_tab_lists_turns_first(self):
        app = self.pinned_app()
        app.s.turns = self.two_turns()
        app.s.findings = [Finding("yellow", "jump", "matphai", 30, 30, (), "nhảy", 20.0, [30])]
        app._fill_issues()
        self.assertEqual(app.issues_var.get(), "Items: 3")
        self.assertEqual(self.row(app, 0), ("#1", "20–39", "Quay đầu mạnh, co 30%"))
        self.assertIn("Mức: Xanh lá", app.issue_info[0])      # quay đầu: thông tin, xanh lá
        self.assertIn("Mức: Vàng", app.issue_info[2])
        self.assertEqual(app.items, [20, 50, 30])
        app.go(0)
        seen = []
        for _ in range(3):
            app.issue_step(1)
            seen.append(app.f)
        self.assertEqual(seen, [20, 30, 50])
        app.issue_table.selection_set("0")
        app.issue_resolve()
        self.assertEqual((len(app.s.turns[0].turns), len(app.s.findings)), (2, 1))
        self.assertIn("tính lại từ điểm ghim", app.notice)
        app.issue_table.selection_set("2")
        app.issue_resolve()
        self.assertEqual(app.s.findings, [])
        app.s.turns = []
        app._fill_issues()
        self.assertEqual(app.issues_var.get(), "Items: 0")

    def test_issues_text_follows_every_field_of_a_turn_not_only_its_bounds(self):
        app = self.pinned_app()
        app.s.turns = self.two_turns()
        app.refresh()
        self.assertNotIn("7 frame không chắc", app.issue_info[0])
        t = app.s.turns[0].turns[0]
        app.s.turns = [TurnReport("ok", 150.0, (Turn(t.first, t.last, t.peak, 0.33, "mạnh", "matphai", t.confirmed, 7, 0, 0),) + app.s.turns[0].turns[1:], 0, 3)]
        app.refresh()                                       # cùng ranh giới, cùng số ghim xác nhận, nhưng chữ đã đổi
        self.assertIn("7 frame không chắc", app.issue_info[0])      # chi tiết (bấm vào dòng mới thấy)
        self.assertIn("co 33%", self.row(app, 0)[2])                # dòng ngắn

    def row(self, app, i):
        """Giá trị ba cột (#, Frame, Vấn đề) của dòng thứ i trong bảng Issues."""
        return tuple(app.issue_table.item(app.issue_table.get_children()[i], "values"))

    def test_issue_table_columns_can_be_resized_and_fit_the_panel(self):
        app = self.pinned_app()
        tab = app.issue_table
        cols = ("#0", "n", "frame", "desc")
        for c in cols:
            self.assertLessEqual(tab.column(c, "minwidth"), 40, c)        # kéo mép cột để thu hẹp được, không bị kẹt ở độ rộng ban đầu
        self.assertLessEqual(sum(int(tab.column(c, "width")) for c in cols), 350)   # mặc định vừa panel (~380 px): cột Mức không bị đẩy ra ngoài
        self.assertTrue(all(tab.column(c, "stretch") in (0, False) for c in ("#0", "n", "frame")))
        self.assertTrue(app.issue_xbar.winfo_exists())                    # kéo rộng hơn panel thì cuộn ngang

    def test_issue_table_has_separate_columns_and_only_the_dot_is_colored(self):
        app = self.pinned_app()
        app.s.findings = [Finding("red", "crossing", "mattrai", 5, 6, (14, 16, 18), "đường viền bắt chéo", None, [5, 6]),
                          Finding("yellow", "ear_closed", "matphai", 20, 20, (), "mắt gần nhắm (EAR 0.05)", 0.05, [20])]
        app._fill_issues()
        tab = app.issue_table
        self.assertEqual(tuple(tab["columns"]), ("n", "frame", "desc"))     # không có cột chữ "Mức": chấm màu thay cho nó
        self.assertEqual([tab.heading(c, "text") for c in ("n", "frame", "desc")], ["#", "Frame", "Vấn đề"])
        self.assertEqual(self.row(app, 0), ("#1", "5–6", "Đường viền bắt chéo"))
        self.assertEqual(self.row(app, 1), ("#2", "20", "Mắt gần nhắm"))
        ids = tab.get_children()
        self.assertNotEqual(tab.item(ids[0], "image"), tab.item(ids[1], "image"))     # chấm đỏ khác chấm vàng
        self.assertEqual(tab.item(ids[0], "tags"), "")                                  # không tô cả dòng
        tab.selection_set(ids[0])
        app.on_issue_select(None)
        text = app.issue_detail.cget("text")
        for part in ("#1 · Mức: Đỏ", "Frame 5–6 (2 frame)", "mattrai", "đường viền bắt chéo", "Điểm liên quan: 14, 16, 18", "Cách xử lý"):
            self.assertIn(part, text)
        app.s.findings = []
        app._fill_issues()
        self.assertEqual(tab.item(tab.get_children()[0], "values")[2], "Không có frame nào cần chú ý.")
        self.assertEqual(app.issues_var.get(), "Items: 0")

    def test_new_turns_raise_a_banner_that_says_which_frames_to_fix(self):
        app = self.pinned_app()
        self.assertFalse(app.turn_bar.winfo_manager())
        app.s.turns = self.two_turns()
        app.refresh()
        self.assertEqual(app.turn_bar.winfo_manager(), "place")              # vừa phát hiện: báo ngay, không chờ người dùng mở tab Issues
        text = app.turn_text.get()
        for part in ("frame 20–39", "frame 50–55", "chỉnh tay"):
            self.assertIn(part, text)
        app.turn_jump()                                                       # nút "Tới đoạn quay đầu"
        self.assertEqual(app.f, 20)
        app.dismiss_turns()                                                   # nút Đóng
        self.assertFalse(app.turn_bar.winfo_manager())
        app.refresh()
        self.assertFalse(app.turn_bar.winfo_manager())                        # không đổi gì thì không báo lại
        app.s.turns = [TurnReport("ok", 150.0, self.two_turns()[0].turns + (Turn(57, 59, 58, 0.2, "vừa", None, 0, 0, 0, 0),), 0, 3)]
        app.refresh()
        self.assertEqual(app.turn_bar.winfo_manager(), "place")              # có đoạn mới thì báo lại
        self.assertIn("frame 57–59", app.turn_text.get())

    def test_status_says_when_the_current_frame_is_inside_a_turn(self):
        app = self.pinned_app()
        app.s.turns = self.two_turns()
        app.go(25)
        self.assertIn("QUAY ĐẦU #1 (frame 20–39)", app.status.get())
        app.go(45)
        self.assertNotIn("QUAY ĐẦU", app.status.get())

    def test_refresh_shows_turns_in_issues_when_they_change(self):
        app = self.pinned_app()
        self.assertEqual(app.issues_var.get(), "Items: 0")
        app.s.turns = self.two_turns()
        app.refresh(light=True)
        self.assertEqual(app.issues_var.get(), "Items: 0")          # vẽ nhẹ (kéo, di chuột) không dựng lại danh sách
        app.refresh()
        self.assertEqual(app.issues_var.get(), "Items: 2")
        self.assertEqual(len(app.issue_table.get_children()), 2)
        app.s.turns = []
        app.refresh()
        self.assertEqual(app.issues_var.get(), "Items: 0")

    # ---------- Appearance ----------
    def test_appearance_color_by_selected_opacity_outline_and_text(self):
        app = self.pinned_app()
        base = self.render(app)
        diff = lambda **kw: int(np.abs(base - self.render(app, look=Look(eyes={"mattrai": True, "matphai": True}, **kw))).sum())
        self.assertGreater(diff(color_by="instance"), 0)
        self.assertGreater(diff(color_by="group"), 0)
        self.assertEqual(Look().color_of("mattrai", 0), Look(color_by="label").color_of("mattrai", 5))      # label: không phụ thuộc ID
        self.assertNotEqual(Look(color_by="instance").color_of("mattrai", 0), Look(color_by="instance").color_of("matphai", 1))
        self.assertGreater(diff(outlined=True), 0)
        self.assertNotEqual(diff(outlined=True, outline_color=(0, 0, 255)), diff(outlined=True))      # đổi màu viền đổi ảnh
        self.assertGreater(diff(text_always=True), 0)
        self.assertNotEqual(diff(text_always=True, font_size=2.0), diff(text_always=True))
        sel = lambda **kw: render_main(app.s, 10, (960, 460), anchor=app.anchor, manual=app.view,
                                       look=Look(eyes={"mattrai": True, "matphai": True}, **kw), selected="mattrai")[0].astype(int)
        self.assertGreater(int(np.abs(sel() - sel(selected_opacity=0.3)).sum()), 0)
        app.set_look(color_by="instance", outlined=True)
        self.assertEqual((app._color_by_var.get(), app.look.color_by), ("label", "instance"))   # biến radio chỉ đổi khi người dùng bấm

    def test_appearance_settings_persist(self):
        from eyepin import shortcuts as sc
        app = self.pinned_app()
        app.set_look(color_by="instance", outlined=True, selected_opacity=0.5)
        app.settings["display"] = {k: getattr(app.look, k) for k in ("color_by", "outlined", "selected_opacity")}
        self.assertEqual(sc.load_settings()["display"], {})                # chưa lưu ra file cho tới khi đóng
        st = sc.DEFAULT_SETTINGS
        for k in ("rotate_all", "show_deleted"):
            self.assertIn(k, st["player"])
        for k in ("text_always", "text_content", "font_size", "focus_padding", "zoom_step"):
            self.assertIn(k, st["workspace"])

    # ---------- Menu ----------
    def test_remove_annotations_confirmation_and_undo(self):
        app = self.pinned_app()
        app.s.toggle_pin_here(10)
        app.remove_annotations(confirmed=False)
        self.assertEqual(sorted(app.s.pins), [0, 10])
        app.remove_annotations(confirmed=True)
        self.assertEqual(app.s.pins, {})
        self.assertEqual(app.s.labels, {})
        self.assertTrue(app.s.undo())
        self.assertEqual(sorted(app.s.pins), [0, 10])
        app.s.clear_all(); app.notice = ""
        app.remove_annotations(confirmed=True)
        self.assertIn("Chưa có nhãn", app.notice)

    def test_run_actions_dialog_and_each_action(self):
        app = self.pinned_app()
        app.show_run_actions()
        app.root.update()
        self.assertTrue(app._dialogs["actions"].winfo_exists())
        app._dialogs["actions"].destroy()
        app.s.toggle_pin_here(20)
        app.s.toggle_pin_here(30)
        app.go(10)
        app.run_action("clear_after")
        self.assertEqual(sorted(app.s.pins), [0])
        app.run_action("scan")
        self.assertEqual(app.issues_var.get(), f"Items: {len(app.s.findings)}")
        app.run_action("swap")
        app.run_action("lock_all")
        self.assertEqual(app.locked, set(EYES))
        self.assertEqual({a for _, a in app.ACTIONS}, {"scan", "propagate", "clear_after", "swap", "lock_all", "remove_all"})

    def test_finish_job_saves_then_exports(self):
        app = self.pinned_app()
        exported = []
        app.export = lambda: exported.append(True)
        app.finish_job(export=False)
        self.assertEqual(exported, [])
        self.assertTrue(os.path.exists(app.state_path()))
        app.finish_job(export=True)
        self.assertEqual(exported, [True])

    # ---------- frame ----------
    def test_name_row_copy_search_delete_and_show_deleted(self):
        app = self.pinned_app()
        self.assertEqual(app.name_var.get(), app.s.names[10])
        app.copy_frame_name()
        self.assertEqual(app.root.clipboard_get(), app.s.names[10])
        app.copy_frame_path()
        self.assertEqual(app.root.clipboard_get(), os.path.join(app.s.frames_dir, app.s.names[10]))
        app.search_frame_by_name("f020")
        self.assertEqual(app.f, 20)
        app.search_frame_by_name("khong-co")
        self.assertIn("Không có frame", app.notice)
        app.go(5)
        app.toggle_delete_frame()
        self.assertIn(5, app.s.deleted)
        self.assertIn("đã xoá", app.name_var.get())
        app.go(4)
        app.step(1)
        self.assertEqual(app.f, 6)                                       # nhảy qua frame đã xoá
        app.step(-1)
        self.assertEqual(app.f, 4)
        app.settings["player"]["show_deleted"] = True
        app.step(1)
        self.assertEqual(app.f, 5)
        app.go(5); app.toggle_delete_frame()
        self.assertNotIn(5, app.s.deleted)
        # lưu và mở lại phiên giữ danh sách frame xoá
        app.s.delete_frame(7)
        self.assertEqual(self.reload(app).deleted, {7})

    def reload(self, app):
        from eyepin.session import Session
        s2 = Session(app.s.frames_dir)
        s2.load_state(app.s.state())
        return s2

    def test_rotate_all_off_keeps_per_frame_rotation(self):
        app = self.pinned_app()
        app.rotate(1)
        app.go(11)
        self.assertEqual(app.rot, 1)                                     # mặc định: xoay tất cả ảnh
        app.settings["player"]["rotate_all"] = False
        app.rot = 0
        app.go(12)
        app.rotate(2)
        self.assertEqual(app.rot, 2)
        app.go(13)
        self.assertEqual(app.rot, 0)
        app.go(12)
        self.assertEqual(app.rot, 2)

    def test_focus_object_zooms_to_the_eye_with_padding(self):
        app = self.pinned_app()
        app.settings["workspace"]["focus_padding"] = 80
        app.tree.selection_set("eye:matphai")
        app.focus_object()
        self.assertIsNotNone(app.manual)
        pts = app._eye_points("matphai")
        x0, y0, x1, y1 = app._bbox(pts)
        w, h = app.render_size
        for x, y in ((x0, y0), (x1, y1)):
            sx, sy = app.manual.to_screen((x, y))
            self.assertTrue(79 <= sx <= w - 79 and 79 <= sy <= h - 79, (sx, sy))
        app.settings["workspace"]["focus_padding"] = 10
        app.focus_object()
        self.assertGreater(app.manual.k, app.view.k * 0.99)

    # ---------- đổi kích thước mắt bằng 8 tay cầm của khung chọn (như CVAT) ----------
    def _select(self, app, label):
        app.select_eye(label, quiet=True)
        app.refresh()

    def _drag_handle(self, app, label, name, dx, dy):
        from eyepin.render import resize_handles
        hx, hy = resize_handles(app.view, app._handle_for(label)[3])[name]
        app.on_press(Ev(hx, hy))
        self.assertIsNotNone(app.drag_resize, f"bấm tay cầm {name} phải bắt đầu đổi kích thước")
        app.on_motion(Ev(hx + dx, hy + dy))
        app._motion_draw()
        app.on_release(Ev(hx + dx, hy + dy))

    def test_selected_eye_shows_eight_resize_handles(self):
        app = self.pinned_app()
        self._select(app, "mattrai")
        for name in ("nw", "n", "ne", "e", "se", "s", "sw", "w"):
            self.assertTrue(app.canvas.find_withtag(f"resize:{name}"), name)
        app.locked.add("mattrai")                            # mắt khoá: không có tay cầm
        app.refresh()
        self.assertFalse(app.canvas.find_withtag("resize:e"))
        app.locked.discard("mattrai")

    def test_dragging_the_right_edge_widens_the_eye_to_the_right_only(self):
        app = self.pinned_app()
        self._select(app, "mattrai")
        sp, other = EYES["mattrai"], EYES["matphai"]
        before = dict(app.s.points_at(10))
        view0 = (app.view.x0, app.view.y0, app.view.k)
        self._drag_handle(app, "mattrai", "e", 30, 0)
        after, k = app.s.pins[10], app.view.k
        self.assertAlmostEqual(after[sp.last][0], before[sp.last][0] + 30 / k, delta=0.02)     # khoé phải ra thêm 30 px màn hình
        self.assertAlmostEqual(after[sp.first][0], before[sp.first][0], delta=1e-6)           # cạnh trái đứng yên
        for i in sp.ids:
            self.assertAlmostEqual(after[i][1], before[i][1], delta=1e-6)                      # chiều cao không đổi
        for i in other.ids:
            self.assertEqual(app.s.points_at(10)[i], before[i])                                # mắt kia không đổi
        self.assertNotIn(10, app.s.eye_keyframes("matphai"))                                   # và không thành keyframe (B26)
        self.assertEqual((app.view.x0, app.view.y0, app.view.k), view0)                        # ảnh không dời
        self.assertTrue(app.s.undo())
        self.assertNotIn(10, app.s.pins)

    def test_dragging_a_corner_scales_both_ways_from_the_opposite_corner(self):
        app = self.pinned_app()
        self._select(app, "matphai")
        sp = EYES["matphai"]
        before = {i: app.s.points_at(10)[i] for i in sp.ids}
        top, bottom = min(p[1] for p in before.values()), max(p[1] for p in before.values())
        left, right = min(p[0] for p in before.values()), max(p[0] for p in before.values())
        self._drag_handle(app, "matphai", "se", 20, 10)
        after, k = {i: app.s.pins[10][i] for i in sp.ids}, app.view.k
        self.assertAlmostEqual(min(p[0] for p in after.values()), left, delta=1e-6)
        self.assertAlmostEqual(min(p[1] for p in after.values()), top, delta=1e-6)
        self.assertAlmostEqual(max(p[0] for p in after.values()), right + 20 / k, delta=0.02)
        self.assertAlmostEqual(max(p[1] for p in after.values()), bottom + 10 / k, delta=0.02)

    def test_pressing_an_eye_corner_still_drags_the_point_not_the_box(self):
        app = self.pinned_app()
        self._select(app, "mattrai")
        sx, sy = app.view.to_screen(app.s.points_at(10)[EYES["mattrai"].first])
        app.on_press(Ev(sx, sy))
        self.assertIsNone(app.drag_resize)
        self.assertEqual(app.drag[0], EYES["mattrai"].first)
        app.on_release(Ev(sx, sy))

    def test_labels_are_vector_items_that_follow_the_points(self):
        """Nhãn vẽ bằng đối tượng vector của Canvas (như CVAT vẽ SVG): mỗi điểm ghim là một vòng tròn đúng chỗ, ở mọi hướng xoay ảnh."""
        app = self.pinned_app()
        pts = app.s.points_at(10)
        for rot in (0, 1, 2, 3):
            app.rot = rot
            app.manual = None
            app.refresh()
            self.assertEqual(app.canvas.itemcget(app._patch_item, "state"), "hidden")
            for label, spec in EYES.items():
                for pid in spec.pins:
                    items = app.canvas.find_withtag(f"pt:{label}:{pid}")
                    self.assertTrue(items, f"rot={rot}: thiếu điểm {pid}")
                    x0, y0, x1, y1 = app.canvas.coords(items[0])
                    back = app._unrot(Ev((x0 + x1) / 2, (y0 + y1) / 2))
                    want = app.view.to_screen(pts[pid])
                    self.assertLess(abs(back.x - want[0]) + abs(back.y - want[1]), 1.5, f"rot={rot}, điểm {pid}")
        app.rot = 0
        app.refresh()

    def test_dragging_a_point_moves_its_vector_item_without_new_images(self):
        app = self.pinned_app()
        app.refresh()
        base_obj, main = app._base_rot, app._main
        sx, sy = app.view.to_screen(app.s.points_at(10)[16])
        app.on_press(Ev(sx, sy))
        app.on_motion(Ev(sx + 15, sy + 4))
        app._motion_draw()
        x0, y0, x1, y1 = app.canvas.coords(app.canvas.find_withtag("pt:mattrai:16")[0])
        self.assertLess(abs((x0 + x1) / 2 - (sx + 15)) + abs((y0 + y1) / 2 - (sy + 4)), 1.5)
        self.assertIs(app._base_rot, base_obj)                # không dựng lại ảnh nền
        self.assertIs(app._main, main)
        self.assertEqual(app.canvas.itemcget(app._patch_item, "state"), "hidden")
        app.on_release(Ev(sx + 15, sy + 4))

    def test_label_opacity_falls_back_to_the_blended_raster_overlay(self):
        app = self.pinned_app()
        app.look.opacity = 0.5                                # Canvas của Tk không có độ trong suốt: dùng lại cách vẽ ảnh để trộn đúng màu
        app.refresh()
        self.assertEqual(app.canvas.itemcget(app._patch_item, "state"), "normal")
        self.assertEqual(app.canvas.find_withtag("ov"), ())
        app.look.opacity = 1.0
        app.refresh()
        self.assertTrue(app.canvas.find_withtag("ov"))
        self.assertEqual(app.canvas.itemcget(app._patch_item, "state"), "hidden")

    def test_patch_rendering_equals_full_render_and_is_small(self):
        """Đường vẽ ảnh (dùng khi nhãn có độ mờ < 100%): ảnh nền + mảnh thay đổi ghép lại phải bằng đúng ảnh vẽ đầy đủ, và mảnh nhỏ hơn cả khung nhiều."""
        app = self.pinned_app()
        app.look.opacity = 0.9
        self.addCleanup(setattr, app.look, "opacity", 1.0)
        app.tree.selection_set("eye:mattrai")
        for rot in (0, 1, 3):
            app.rot = rot
            app.manual = None
            app.refresh()
            app.refresh(light=True)
            full, _ = render_main(app.s, app.f, app.render_size, anchor=app.anchor, manual=app.manual, look=app.look,
                                  handle=app._handle_arg(), selected=app._selected()[0], show_ids=app.show_ids)
            if rot:
                full = np.ascontiguousarray(np.rot90(full, -rot))
            x, y = (int(v) for v in app.canvas.coords(app._patch_item))
            comp = app._base_rot.copy()
            w, h = app._patch.width(), app._patch.height()
            comp[y:y + h, x:x + w] = full[y:y + h, x:x + w]
            self.assertTrue(np.array_equal(comp, full), f"rot={rot}: mảnh không phủ hết phần khác ảnh nền")
            self.assertLess(w * h, 0.5 * full.shape[0] * full.shape[1])
        app.rot = 0
        # kéo điểm không dựng lại ảnh nền
        app.refresh()
        key = app._base_key
        base_obj = app._base_rot
        app.on_press(Ev(*app.view.to_screen(app.s.labels[10].points[16] if 10 not in app.s.pins else app.s.pins[10][16])))
        app.on_motion(Ev(*[v + 15 for v in app.view.to_screen(app.s.labels[10].points[16] if 10 not in app.s.pins else app.s.pins[10][16])]))
        app.root.update()
        self.assertEqual(app._base_key, key)
        self.assertIs(app._base_rot, base_obj)
        app.on_release(Ev(0, 0))

    def test_delete_label_undo_lock_force_and_export(self):
        import tempfile
        from eyepin import cvatxml
        app = self.pinned_app()
        app.s.toggle_pin_here(30)
        app.tree.selection_set("eye:matphai")
        before = {f: dict(p) for f, p in app.s.pins.items()}
        # bị khoá: Delete từ chối, Shift+Delete xoá
        app.locked.add("matphai")
        app.handlers["delete"](None)
        self.assertIn("khoá", app.notice)
        self.assertEqual(app.s.pins, before)
        app.handlers["delete_force"](None)
        self.assertIn("Đã xoá matphai", app.notice)
        for f, pts in app.s.pins.items():
            self.assertEqual(set(pts), set(ML.ids))                              # chỉ còn mắt trái ở mọi frame ghim
        self.assertEqual(app.s.missing_eyes(), ["matphai"])
        self.assertTrue(all(set(r.points) == set(ML.ids) for r in app.s.labels.values()))
        self.assertIn("không có nhãn", app.tree.item("eye:matphai", "text"))
        self.assertEqual(app.tree.set("eye:matphai", "trang"), "đã xoá")
        # xuất file: chỉ có track mắt trái
        out = os.path.join(tempfile.mkdtemp(), "o.xml")
        info = app.s.export(out)
        self.assertEqual(info["tracks"], ["mattrai"])
        ann = cvatxml.parse(out)
        self.assertEqual((len(ann.tracks["mattrai"]), len(ann.tracks["matphai"])), (1, 0))
        # xoá lần nữa: báo không còn gì để xoá; hoàn tác trả lại đúng như cũ
        app.locked.clear()
        app.handlers["delete"](None)
        self.assertIn("chưa có nhãn nào", app.notice)
        self.assertTrue(app.s.undo())
        self.assertEqual(app.s.pins, before)
        self.assertEqual(app.s.missing_eyes(), [])

    def test_repin_one_eye_after_delete_and_track_starts_there(self):
        import tempfile
        from eyepin import cvatxml
        import test_tracking as T
        app = self.pinned_app()
        app.go(20)
        app.tree.selection_set("eye:matphai")
        app.delete_label()
        app.start_pin("full")
        self.assertEqual(app.pinning, "one")                                      # chỉ cần 4 điểm cho mắt đã xoá
        truth = T.pins_at(20)
        for pid in MR.pins:
            sx, sy = app.view.to_screen(truth[pid])
            app.on_press(Ev(sx, sy))
        self.assertIsNone(app.pinning)
        self.assertEqual(app.s.missing_eyes(), [])
        self.assertEqual(sorted(f for f in app.s.pins if set(MR.ids) <= set(app.s.pins[f])), [20])
        self.assertTrue(set(ML.ids) <= set(app.s.pins[20]))                       # mắt trái giữ nguyên ở frame 20
        for i in MR.pins:
            self.assertLess(math.dist(app.s.pins[20][i], truth[i]), 1.5)
        out = os.path.join(tempfile.mkdtemp(), "o.xml")
        app.s.export(out)
        ann = cvatxml.parse(out)
        self.assertEqual(min(ann.tracks["matphai"][0].keys), 20)                  # track mắt phải bắt đầu từ frame ghim lại
        self.assertEqual(min(ann.tracks["mattrai"][0].keys), 0)
        # chọn mắt theo vị trí khi cả hai mắt đều có: sửa lại mắt gần nhất
        label = app.s.add_pin_one(25, [truth[i] for i in MR.pins])
        self.assertEqual(label, "matphai")

    def test_end_label_marks_outside_from_this_frame(self):
        app = self.pinned_app()
        app.tree.selection_set("eye:mattrai")
        app.end_label_here()
        self.assertIn(10, app.s.pins)
        self.assertEqual({i: k for i, k in app.s.flags[10].items()}, {i: "outside" for i in ML.ids})
        self.assertEqual(app.s.flags_at(40), {i: "outside" for i in ML.ids})        # cờ chép sang các frame sau
        self.assertEqual(app.s.flags_at(5), {})                                      # trước đó không đổi
        self.assertTrue(app.s.undo())
        self.assertNotIn(10, app.s.pins)

    def test_object_ids_like_cvat(self):
        """Mỗi mắt là một đối tượng có ID thật: đánh khi ghim, lưu trong phiên và file xuất, ID đã xoá không dùng lại."""
        import tempfile
        from eyepin import cvatxml
        from eyepin.session import Session
        import test_tracking as T
        app = self.pinned_app()
        self.assertEqual(app.s.obj_ids, {"mattrai": 1, "matphai": 10})                # như CVAT: skeleton 1 chiếm ID 1 và 8 điểm con (2-9), skeleton 2 là 10
        self.assertTrue(app.tree.item("eye:mattrai", "text").startswith("#1 "))
        self.assertTrue(app.tree.item("eye:matphai", "text").startswith("#10"))
        app.tree.selection_set("eye:matphai")
        self.assertTrue(app._handle_arg()[3].endswith("#10"))
        # xuất: track mang đúng ID
        out = os.path.join(tempfile.mkdtemp(), "o.xml")
        app.s.export(out)
        ann = cvatxml.parse(out)
        self.assertEqual((ann.tracks["mattrai"][0].attrs["id"], ann.tracks["matphai"][0].attrs["id"]), ("1", "10"))
        # lưu và mở lại phiên giữ ID
        s2 = Session(app.s.frames_dir)
        s2.load_state(app.s.state())
        self.assertEqual((s2.obj_ids, s2.next_id), (app.s.obj_ids, app.s.next_id))
        # xoá rồi ghim lại: ID mới (19), không dùng lại 10; hoàn tác trả lại 10
        app.s.delete_eye("matphai")
        self.assertEqual(app.s.obj_ids, {"mattrai": 1})
        truth = T.pins_at(0)
        app.s.add_pin_one(0, [truth[i] for i in MR.pins])
        self.assertEqual(app.s.obj_ids["matphai"], 19)
        self.assertTrue(app.s.undo())
        self.assertEqual(app.s.obj_ids, {"mattrai": 1})
        self.assertTrue(app.s.undo())
        self.assertEqual(app.s.obj_ids, {"mattrai": 1, "matphai": 10})
        # mở file nhãn có sẵn ID: dùng đúng ID đó, ID mới đánh tiếp sau ID lớn nhất
        s3 = Session(app.s.frames_dir, out)
        self.assertEqual((s3.obj_ids, s3.next_id), ({"mattrai": 1, "matphai": 10}, 11))

    def test_per_eye_keyframes_navigation_and_star(self):
        app = self.pinned_app()
        app.s.toggle_eye_key("mattrai", 20)
        app.s.toggle_eye_key("matphai", 35)
        self.assertEqual(app.s.eye_keyframes("mattrai"), [0, 20])
        self.assertEqual(app.s.eye_keyframes("matphai"), [0, 35])
        app.tree.selection_set("eye:mattrai")
        app.go(0)
        app.jump_pin(1)
        self.assertEqual(app.f, 20)                                               # nhảy theo keyframe của mắt đang chọn
        app.jump_pin(1)
        self.assertIn("Không còn", app.notice)
        app.tree.selection_set("eye:matphai")
        app.go(0)
        app.jump_pin(1)
        self.assertEqual(app.f, 35)
        app.last_keyframe(); self.assertEqual(app.f, 35)
        app.first_keyframe(); self.assertEqual(app.f, 0)
        # ngôi sao theo từng mắt
        app.go(20)
        app.refresh()
        self.assertEqual((app.tree.set("eye:mattrai", "sao"), app.tree.set("eye:matphai", "sao")), ("★", "☆"))
        # phím K với mắt đang chọn chỉ đổi keyframe của mắt đó
        app.tree.selection_set("eye:matphai")
        app.handlers["keyframe"](None)
        self.assertEqual(app.s.eye_keyframes("matphai"), [0, 20, 35])
        self.assertEqual(app.s.eye_keyframes("mattrai"), [0, 20])
        app.handlers["keyframe"](None)
        self.assertEqual(app.s.eye_keyframes("matphai"), [0, 35])
        # mỗi mắt bám độc lập: bỏ keyframe 20 của mattrai không làm đổi nhãn mắt phải
        right_before = {f: dict((i, p) for i, p in r.points.items() if i in MR.ids) for f, r in app.s.labels.items()}
        app.s.toggle_eye_key("mattrai", 20)
        right_after = {f: dict((i, p) for i, p in r.points.items() if i in MR.ids) for f, r in app.s.labels.items()}
        self.assertEqual(right_before, right_after)
        # xuất: keyframe riêng từng mắt, cả hai track đủ đến hết job
        import tempfile
        from eyepin import cvatxml
        out = os.path.join(tempfile.mkdtemp(), "o.xml")
        app.s.export(out)
        ann = cvatxml.parse(out)
        self.assertIn(35, ann.tracks["matphai"][0].keys)

    def two_people(self):
        """Hai người trong cùng job: người thứ nhất ghim ở frame 0, người thứ hai (bộ mới) ghim ở frame 0 với toạ độ dịch sang bên."""
        import test_tracking as T
        app = self.pinned_app()
        app.new_object()
        self.assertEqual(app.pinning, "full")
        truth = T.pins_at(0)
        pts = [(x + 40, y + 60) for x, y in (truth[i] for spec in EYES.values() for i in spec.pins)]
        app.s.add_pin_free(0, pts)
        app.pinning, app.clicks = None, []
        app.refresh()
        return app

    def test_multiple_objects_per_label_with_cvat_style_ids(self):
        app = self.two_people()
        s = app.s
        self.assertEqual(len(s.layers), 2)
        self.assertEqual(s.layers[0].obj_ids, {"mattrai": 1, "matphai": 10})
        self.assertEqual(s.layers[1].obj_ids, {"mattrai": 19, "matphai": 28})            # như CVAT: 1, 10, 19, 28
        self.assertEqual([(i, l, n) for i, l, n in s.objects()], [(0, "mattrai", 1), (0, "matphai", 10), (1, "mattrai", 19), (1, "matphai", 28)])
        self.assertEqual(s.cur, 1)
        texts = [app.tree.item(i, "text") for i in app.tree.get_children()]
        self.assertEqual([t.split()[0] for t in texts], ["#1", "#10", "#19", "#28"])
        self.assertEqual(app.items_var.get(), "Items: 4")
        self.assertIn("eye:mattrai@1", app.tree.get_children())
        # hai bộ độc lập: xoay mắt của người 2 không đổi người 1
        before0 = {f: dict(r.points) for f, r in s.layers[0].labels.items()}
        app.tree.selection_set("eye:mattrai@1")
        app.rotate_eye(8)
        self.assertEqual({f: dict(r.points) for f, r in s.layers[0].labels.items()}, before0)
        # chọn dòng của người 1 thì chuyển sang bộ đó; thao tác sau đó tác động lên đối tượng vừa chọn
        app.tree.selection_set("eye:matphai")
        app.root.update()                                                  # chuyển bộ đối tượng qua sự kiện chọn dòng như khi dùng thật
        self.assertEqual(s.cur, 0)
        self.assertEqual(app._selected(), ("matphai", None))
        # khoá riêng từng người
        app.locked.add("matphai")
        self.assertIn("matphai", app.locked)
        app.tree.selection_set("eye:matphai@1")
        app.root.update()
        self.assertEqual(s.cur, 1)
        self.assertNotIn("matphai", app.locked)
        # bấm vào mắt của người khác trên khung ảnh thì chuyển sang người đó
        app.go(0)
        app.tree.selection_set("eye:mattrai")
        app.root.update()
        self.assertEqual(s.cur, 0)
        target = s.layers[1].labels[0].points[16]
        app.on_press(Ev(*app.view.to_screen(target)))
        app.on_release(Ev(0, 0))
        self.assertEqual(s.cur, 1)

    def test_two_people_render_export_and_persist(self):
        import tempfile
        from eyepin import cvatxml
        from eyepin.session import Session
        app = self.two_people()
        s = app.s
        one = Session(s.frames_dir)
        # vẽ: ảnh có hai người khác ảnh chỉ có một người
        full = self.render(app)
        saved = s.layers
        s.layers, s.cur = saved[:1], 0
        only0 = self.render(app)
        s.layers, s.cur = saved, 1
        self.assertGreater(int(np.abs(full - only0).sum()), 0)
        # xuất: bốn track, hai track mỗi label, ID giữ nguyên trong file
        out = os.path.join(tempfile.mkdtemp(), "o.xml")
        info = s.export(out)
        self.assertEqual(info["tracks"], ["matphai", "matphai", "mattrai", "mattrai"])
        ann = cvatxml.parse(out)
        self.assertEqual(sorted(t.attrs["id"] for l in EYES for t in ann.tracks[l]), ["1", "10", "19", "28"])
        self.assertEqual((len(ann.tracks["mattrai"]), len(ann.tracks["matphai"])), (2, 2))
        # lưu và mở lại phiên giữ cả hai người và ID
        one.load_state(s.state())
        self.assertEqual([L.obj_ids for L in one.layers], [L.obj_ids for L in s.layers])
        self.assertEqual((one.cur, one.next_id), (s.cur, s.next_id))
        self.assertEqual(sorted(one.layers[1].pins), sorted(s.layers[1].pins))
        # phiên cũ (bản 1, một bộ đối tượng) vẫn mở được
        old = s.state()
        old.update(version=1, **{k: old["layers"][0][k] for k in ("pins", "flags", "estimates")}, ids=old["layers"][0]["ids"])
        old.pop("layers")
        legacy = Session(s.frames_dir)
        legacy.load_state(old)
        self.assertEqual(len(legacy.layers), 1)
        self.assertEqual(legacy.obj_ids, {"mattrai": 1, "matphai": 10})

    def test_undo_removes_a_new_object_and_delete_drops_empty_layer(self):
        app = self.two_people()
        s = app.s
        app.tree.selection_set("eye:mattrai@1")
        app.delete_label(force=True)
        self.assertEqual(len(s.layers), 2)                                  # còn matphai của người 2
        app.tree.selection_set("eye:matphai@1")
        app.delete_label(force=True)
        self.assertEqual(len(s.layers), 1)                                  # bộ rỗng tự bỏ
        self.assertEqual(s.cur, 0)
        self.assertEqual(s.objects(), [(0, "mattrai", 1), (0, "matphai", 10)])
        self.assertTrue(s.undo())
        self.assertTrue(s.undo())
        self.assertEqual([n for _, _, n in s.objects()], [1, 10, 19, 28])
        self.assertTrue(s.undo())                                           # hoàn tác việc ghim người 2
        self.assertEqual([n for _, _, n in s.objects()], [1, 10])

    def test_sort_by_works_across_objects_and_remove_annotations_resets_layers(self):
        app = self.two_people()
        app.sort_var.set("ID - giảm dần")
        app.refresh()
        self.assertEqual([i.split("@")[0] for i in app.tree.get_children()][:2], ["eye:matphai", "eye:mattrai"])
        self.assertEqual(app.tree.item(app.tree.get_children()[0], "text").split()[0], "#28")
        app.remove_annotations(confirmed=True)
        self.assertEqual(len(app.s.layers), 1)
        self.assertEqual(app.s.cur, 0)

    def test_zoom_step_setting(self):
        app = self.pinned_app()
        self.assertAlmostEqual(app.zoom_step(), 1.25)
        app.settings["workspace"]["zoom_step"] = 1.5
        app.fit()
        k0 = app.view.k
        app.handlers["zoom_in"](None)
        self.assertAlmostEqual(app.manual.k / k0, 1.5, places=3)
        app.settings["workspace"]["zoom_step"] = "xấu"
        self.assertAlmostEqual(app.zoom_step(), 1.25)

    def test_settings_window_has_the_new_options(self):
        app = self.pinned_app()
        app.show_settings()
        app.root.update()
        texts = []

        def walk(w):
            for c in w.winfo_children():
                try:
                    texts.append(c.cget("text"))
                except Exception:
                    pass
                walk(c)
        walk(app._dialogs["settings"])
        joined = " | ".join(str(t) for t in texts)
        for want in ("Xoay tất cả ảnh", "Hiện frame đã xoá", "Luôn hiện chữ cạnh mắt", "Cỡ chữ", "Đệm khi phóng vào mắt", "Hệ số zoom"):
            self.assertIn(want, joined)

    def test_menu_and_header_entries_exist(self):
        app = self.pinned_app()
        self.assertTrue(hasattr(app, "name_var"))
        for aid in ("run_actions", "remove_annotations", "finish_job", "pinned", "propagate", "change_color", "delete_frame", "search_frame"):
            self.assertIn(aid, app.handlers)


if __name__ == "__main__":
    unittest.main()


class SegmentCacheTests(unittest.TestCase):
    """Sửa một frame ghim chỉ tính lại đúng đoạn của nó; kết quả giống hệt tính lại từ đầu."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import tempfile
        import cv2
        import test_tracking as T
        cls.dir = tempfile.mkdtemp(prefix="eyepin_seg_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))
        cls._rm = shutil.rmtree

    @classmethod
    def tearDownClass(cls):
        cls._rm(cls.dir, ignore_errors=True)

    def test_unchanged_segments_are_reused_and_results_are_identical(self):
        import random
        import test_tracking as T
        from eyepin.session import Session
        s = Session(self.dir)
        for f in (0, 20, 40):
            clicks = [T.pins_at(f)[i] for spec in EYES.values() for i in spec.pins]
            random.Random(f).shuffle(clicks)
            s.add_pin_free(f, clicks)
        seg_before = dict(s._segments)
        self.assertEqual(len(seg_before), 6)                                          # 3 keyframe x 2 mắt, mỗi mắt tính riêng
        s.drag_points(20, {16: (s.pins[20][16][0] + 3, s.pins[20][16][1])})            # sửa frame ghim ở giữa
        reused = [k for k in s._segments if k in seg_before and s._segments[k] is seg_before[k]]
        self.assertEqual(sorted(k[0] for k in reused), [0, 0, 20, 40, 40])             # mắt phải ở frame 20 không đổi nên cũng dùng lại
        cached = {f: dict(r.points) for f, r in s.labels.items()}
        s._segments = {}
        s.recompute()                                                                  # tính lại từ đầu
        self.assertEqual({f: dict(r.points) for f, r in s.labels.items()}, cached)
        arrival = {f: dict(r.points) for f, r in s.arrival.items()}
        self.assertEqual(sorted(arrival), [20, 40])
