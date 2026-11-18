"""Widget `ObjectList` (thanh bên phải kiểu CVAT, spec 4.2): thẻ đối tượng với API giống `ttk.Treeview`, chạy một mình không cần App."""
import os
import sys
import time
import tkinter as tk
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import theme  # noqa: E402
from eyepin.icons import IconButton  # noqa: E402

try:
    from eyepin.gui_sidebar import ObjectList  # noqa: E402
except ImportError:                                  # bước RED: module chưa có thì từng test báo lỗi rõ ràng
    ObjectList = None

POINTS = {"mattrai": range(14, 22), "matphai": range(22, 30)}
PINS = {14, 16, 18, 20, 22, 24, 26, 28}
GROUPS = ["outside|inside", "lock|unlock", "occluded|not_occluded", "eye|eye_off", "star|star_off", "pinned|unpinned"]


def card(label, **kw):
    c = {"id": 1 if label == "mattrai" else 10, "label": label, "color": "#3E7BFA" if label == "mattrai" else "#2BB673",
         "type": "SKELETON TRACK", "status": "keyframe", "outside": False, "lock": False, "occluded": False, "hidden": False,
         "keyframe": True, "pinned": False, "has_prev": True, "has_next": True, "has_first": True, "has_last": True}
    c.update(kw)
    return c


def fill(ol, layer=0, cards=None, labels=("mattrai", "matphai"), open_=None):
    """Chèn thẻ như `App.refresh_objects`: mỗi mắt một dòng `eye:` và 8 dòng `pt:`."""
    suf = f"@{layer}" if layer else ""
    for label in labels:
        eid = f"eye:{label}{suf}"
        c = (cards or {}).get(label) or card(label)
        kw = {} if open_ is None else {"open": open_}
        ol.insert("", "end", iid=eid, text=f"#{c['id']}  {label}", values=("skeleton track", "★", "keyframe"), card=c, **kw)
        for pid in POINTS[label]:
            ol.insert(eid, "end", iid=f"pt:{pid}{suf}", text=f"điểm {pid}",
                      values=("ghim" if pid in PINS else "suy ra", "★", "Occluded" if pid == 17 else ""))


def count_widgets(w):
    return sum(1 + count_widgets(c) for c in w.winfo_children())


def icon_buttons(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, IconButton):
            out.append(c)
        out.extend(icon_buttons(c))
    return out


class ObjectListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError:
            raise unittest.SkipTest("không có màn hình để mở cửa sổ Tkinter")
        cls.root.withdraw()
        theme.apply(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.assertIsNotNone(ObjectList, "chưa có eyepin.gui_sidebar.ObjectList")
        self.actions, self.selects = [], []
        self.ol = ObjectList(self.root, on_action=lambda a, i: self.actions.append((a, i)),
                             on_select=lambda: self.selects.append(self.ol.selection()),
                             keys={"occluded": "q", "outside": "o", "lock": "l", "hide": "h", "keyframe": "k", "pinned": "p",
                                   "prev_keyframe": "e", "next_keyframe": "r"})
        self.ol.pack(fill="both", expand=True)

    def tearDown(self):
        self.ol.destroy()

    # ---------- 7 test của brief ----------
    def test_treeview_like_api(self):
        ol = self.ol
        fill(ol)
        self.assertEqual(ol.get_children(), ("eye:mattrai", "eye:matphai"))
        self.assertEqual(len(ol.get_children("eye:mattrai")), 8)
        self.assertEqual(ol.get_children("eye:mattrai")[0], "pt:14")
        self.assertEqual(ol.item("eye:mattrai", "text"), "#1  mattrai")
        self.assertEqual(ol.set("eye:mattrai", "sao"), "★")
        self.assertEqual(ol.set("eye:mattrai", "trang"), "keyframe")
        self.assertEqual(ol.set("eye:mattrai", "vai"), "skeleton track")
        self.assertEqual(ol.item("pt:17", "values"), ("suy ra", "★", "Occluded"))
        self.assertEqual(ol.set("pt:17", "trang"), "Occluded")
        self.assertEqual(ol.item("eye:mattrai")["text"], "#1  mattrai")
        ol.selection_set("pt:17")
        self.assertEqual(ol.selection(), ("pt:17",))
        ol.selection_remove(*ol.selection())
        self.assertEqual(ol.selection(), ())
        ol.selection_set("eye:matphai")
        ol.selection_remove(ol.selection())                       # như test cũ: truyền nguyên tuple một đối số
        self.assertEqual(ol.selection(), ())
        self.assertIs(ol.exists("eye:x"), False)
        self.assertIs(ol.exists("pt:22"), True)
        with self.assertRaises(tk.TclError):
            ol.item("eye:x", "text")
        with self.assertRaises(tk.TclError):
            ol.insert("", "end", iid="eye:mattrai")
        ol.delete("eye:matphai")                                  # xoá dòng cha thì xoá cả dòng con, như Treeview
        self.assertEqual(ol.get_children(), ("eye:mattrai",))
        self.assertFalse(ol.exists("pt:22"))
        ol.delete(*ol.get_children())
        self.assertEqual(ol.get_children(), ())

    def test_open_details(self):
        ol = self.ol
        fill(ol)
        rows = [ol.row_widget(i) for i in ol.get_children("eye:mattrai")]
        self.assertIs(ol.item("eye:mattrai", "open"), False)
        ol.item("eye:mattrai", open=True)
        self.root.update_idletasks()
        self.assertIs(ol.item("eye:mattrai", "open"), True)
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(r.winfo_ismapped() for r in rows))
        self.assertFalse(any(ol.row_widget(i).winfo_ismapped() for i in ol.get_children("eye:matphai")))
        ol.item("eye:mattrai", open=False)
        self.root.update_idletasks()
        self.assertIs(ol.item("eye:mattrai", "open"), False)
        self.assertFalse(any(r.winfo_ismapped() for r in rows))

    def test_buttons_send_action_with_iid(self):
        ol = self.ol
        fill(ol, layer=1)
        b = ol.buttons("eye:matphai@1")
        order = ["outside", "lock", "occluded", "hidden", "keyframe", "pinned", "first", "prev", "next", "last"]
        for name in order:
            b[name]._click(None)
        self.assertEqual(self.actions, [(name, "eye:matphai@1") for name in order])
        self.actions.clear()
        ol.item("eye:matphai@1", card=card("matphai", has_prev=False))
        b["prev"]._click(None)
        self.assertEqual(self.actions, [])
        b["next"]._click(None)
        self.assertEqual(self.actions, [("next", "eye:matphai@1")])

    def test_button_icons_follow_state(self):
        ol = self.ol
        fill(ol)
        pairs = {"outside": ("outside", "inside"), "lock": ("lock", "unlock"), "occluded": ("occluded", "not_occluded"),
                 "hidden": ("eye_off", "eye"), "keyframe": ("star", "star_off"), "pinned": ("pinned", "unpinned")}
        for key, (on, off) in pairs.items():
            with self.subTest(key=key):
                ol.item("eye:mattrai", card=card("mattrai", **{key: True}))
                self.assertEqual(ol.buttons("eye:mattrai")[key].name, on)
                ol.item("eye:mattrai", card=card("mattrai", **{key: False}))
                self.assertEqual(ol.buttons("eye:mattrai")[key].name, off)

    def test_same_iids_update_in_place(self):
        ol = self.ol
        fill(ol)
        self.root.update_idletasks()
        n = count_widgets(ol)
        lock_btn = ol.buttons("eye:mattrai")["lock"]
        self.assertEqual(lock_btn.name, "unlock")
        ol.begin_update()
        ol.delete(*ol.get_children())
        fill(ol, cards={"mattrai": card("mattrai", lock=True, status="tool tính")})
        ol.end_update()
        self.root.update_idletasks()
        self.assertEqual(count_widgets(ol), n)                    # không tạo widget mới
        self.assertIs(ol.buttons("eye:mattrai")["lock"], lock_btn)   # đúng widget cũ
        self.assertEqual(lock_btn.name, "lock")                   # nhưng icon đã theo thẻ mới
        # thêm iid mới (người thứ hai) → dựng thêm thẻ
        ol.begin_update()
        ol.delete(*ol.get_children())
        fill(ol)
        fill(ol, layer=1)
        ol.end_update()
        self.root.update_idletasks()
        self.assertEqual(ol.get_children(), ("eye:mattrai", "eye:matphai", "eye:mattrai@1", "eye:matphai@1"))
        self.assertGreater(count_widgets(ol), n)
        self.assertIsNotNone(ol.buttons("eye:matphai@1"))

    def test_reorder_moves_cards_without_rebuilding(self):
        ol = self.ol
        fill(ol)
        self.root.update_idletasks()
        n = count_widgets(ol)
        frames = {i: ol.row_widget(i) for i in ol.get_children()}
        ol.begin_update()                                         # Sort by đổi: cùng iid, khác thứ tự
        ol.delete(*ol.get_children())
        fill(ol, labels=("matphai", "mattrai"))
        ol.end_update()
        self.root.update_idletasks()
        self.assertEqual(ol.get_children(), ("eye:matphai", "eye:mattrai"))
        self.assertEqual(count_widgets(ol), n)
        self.assertEqual({i: ol.row_widget(i) for i in ol.get_children()}, frames)
        self.assertLess(frames["eye:matphai"].winfo_y(), frames["eye:mattrai"].winfo_y())
        ol.insert("", 0, iid="eye:mattrai@1", card=card("mattrai", id=19))   # chèn theo chỉ số như Treeview
        self.root.update_idletasks()
        self.assertEqual(ol.get_children()[0], "eye:mattrai@1")
        self.assertLess(ol.row_widget("eye:mattrai@1").winfo_y(), frames["eye:matphai"].winfo_y())

    def test_order_of_buttons_matches_cvat(self):
        ol = self.ol
        fill(ol)
        self.root.update_idletasks()
        b = ol.buttons("eye:mattrai")
        row3 = [b[k] for k in ("outside", "lock", "occluded", "hidden", "keyframe", "pinned")]
        for btn, group in zip(row3, GROUPS):
            self.assertIn(btn.name, group.split("|"))
        # thứ tự trên màn hình (trái → phải) cũng đúng CVAT, và cùng một hàng
        xs = [w.winfo_x() for w in row3]
        self.assertEqual(xs, sorted(xs))
        self.assertEqual(len({w.winfo_parent() for w in row3}), 1)
        nav = [b[k] for k in ("first", "prev", "next", "last")]
        self.assertEqual([w.name for w in nav], ["first", "prev", "next", "last"])
        nx = [w.winfo_x() for w in nav]
        self.assertEqual(nx, sorted(nx))

    def test_shape_card_buttons(self):
        """Thẻ SKELETON SHAPE (CVAT object-item-buttons.tsx, nhánh shape): chỉ Lock, Occluded, Hidden, Pinned; không có bốn nút điều hướng
        keyframe, Outside, Keyframe. Cùng iid đổi về track thì hiện lại đủ 10 nút."""
        ol = self.ol
        names = ("first", "prev", "next", "last", "outside", "lock", "occluded", "hidden", "keyframe", "pinned")
        shape = card("mattrai", kind="shape", type="SKELETON SHAPE", status="", keyframe=False, has_prev=False, has_next=False,
                     has_first=False, has_last=False)
        fill(ol, cards={"mattrai": shape})
        self.root.update_idletasks()
        b = ol.buttons("eye:mattrai")
        shown = [n for n in names if b[n].winfo_manager()]
        self.assertEqual(sorted(shown, key=lambda n: b[n].winfo_x()), ["lock", "occluded", "hidden", "pinned"])
        self.assertEqual(shown, ["lock", "occluded", "hidden", "pinned"])
        gaps = {b[q].winfo_x() - b[p].winfo_x() for p, q in zip(shown, shown[1:])}
        self.assertLessEqual(max(gaps) - min(gaps), 1)                  # bốn nút dàn đều, ô của nút đã ẩn không giữ chỗ
        for n in ("first", "prev", "next", "last", "outside", "keyframe"):
            self.assertEqual(b[n].winfo_manager(), "", n)
        self.assertEqual(ol.card_texts("eye:mattrai")[1], "SKELETON SHAPE")
        ol.item("eye:mattrai", card=card("mattrai"))                  # cùng iid về track (vd. hoàn tác): đủ nút như test_order_of_buttons_matches_cvat
        self.root.update_idletasks()
        self.assertEqual([n for n in names if b[n].winfo_manager()], list(names))
        row3 = [b[k] for k in ("outside", "lock", "occluded", "hidden", "keyframe", "pinned")]
        xs = [w.winfo_x() for w in row3]
        self.assertEqual(xs, sorted(xs))
        nx = [b[k].winfo_x() for k in ("first", "prev", "next", "last")]
        self.assertEqual(nx, sorted(nx))
        other = ol.buttons("eye:matphai")                                    # thẻ track chưa từng đổi kiểu: cùng vị trí nút
        self.assertEqual(xs, [other[k].winfo_x() for k in ("outside", "lock", "occluded", "hidden", "keyframe", "pinned")])
        self.assertEqual(nx, [other[k].winfo_x() for k in ("first", "prev", "next", "last")])
        self.assertLess(b["first"].winfo_rooty(), b["lock"].winfo_rooty())     # hàng điều hướng lại nằm trên hàng nút
        self.assertEqual(ol.card_texts("eye:mattrai")[1], "SKELETON TRACK")

    def test_activate_highlights(self):
        ol = self.ol
        fill(ol)
        self.assertIsNone(ol.activated())
        before = ol.row_widget("eye:matphai").cget("highlightbackground")
        ol.activate("eye:matphai")
        self.assertEqual(ol.activated(), "eye:matphai")
        self.assertNotEqual(ol.row_widget("eye:matphai").cget("highlightbackground"), before)
        ol.activate(None)
        self.assertIsNone(ol.activated())
        self.assertEqual(ol.row_widget("eye:matphai").cget("highlightbackground"), before)
        ol.activate("eye:khong_co")                               # iid không có: không sáng gì, không lỗi
        self.assertIsNone(ol.activated())

    def test_no_static_text_on_buttons(self):
        ol = self.ol
        fill(ol)
        ol.item("eye:mattrai", open=True)
        btns = icon_buttons(ol)
        self.assertGreaterEqual(len(btns), 2 * 12)
        for b in btns:
            self.assertIsNone(b.cap)

    # ---------- thêm: chọn, chuột, label, gộp cập nhật ----------
    def test_click_selects_and_notifies_only_on_change(self):
        ol = self.ol
        fill(ol)
        ol.item("eye:mattrai", open=True)
        self.root.update_idletasks()                              # Tk bỏ qua sự kiện chuột của widget chưa hiện
        ol.row_widget("eye:matphai").event_generate("<Button-1>")
        self.assertEqual(ol.selection(), ("eye:matphai",))
        self.assertEqual(self.selects, [("eye:matphai",)])
        ol.row_widget("eye:matphai").event_generate("<Button-1>")     # bấm lại thẻ đang chọn: không đổi, không báo
        self.assertEqual(len(self.selects), 1)
        ol.row_widget("pt:17").event_generate("<Button-1>")
        self.assertEqual(ol.selection(), ("pt:17",))
        self.assertEqual(len(self.selects), 2)
        ol.selection_set("pt:17")                                    # gọi lệnh mà lựa chọn không đổi: không báo
        self.assertEqual(len(self.selects), 2)
        ol.selection_set("eye:mattrai")                              # đổi bằng lệnh: báo (như <<TreeviewSelect>>)
        self.assertEqual(self.selects[-1], ("eye:mattrai",))
        ol.selection_remove("eye:matphai")                           # bỏ một dòng không chọn: không đổi
        self.assertEqual(len(self.selects), 3)

    def test_right_click_and_double_click(self):
        ol = self.ol
        fill(ol)
        self.root.update_idletasks()
        ol.row_widget("eye:matphai").event_generate("<Button-3>", x=4, y=4)
        self.assertEqual(ol.selection(), ("eye:matphai",))
        self.assertEqual(self.actions, [("menu", "eye:matphai")])
        self.assertIsNotNone(ol.menu_xy)
        self.actions.clear()
        w = ol.row_widget("eye:mattrai")                          # nhấp đúp = hai lần nhấn gần nhau
        w.event_generate("<ButtonPress-1>", time=1000, x=3, y=3)
        w.event_generate("<ButtonRelease-1>", time=1010, x=3, y=3)
        w.event_generate("<ButtonPress-1>", time=1100, x=3, y=3)
        self.assertEqual(ol.selection(), ("eye:mattrai",))
        self.assertEqual(self.actions, [("focus", "eye:mattrai")])
        self.actions.clear()
        ol.buttons("eye:mattrai")["more"]._click(None)              # nút ⋮: chọn thẻ đó rồi mở menu
        self.assertEqual(ol.selection(), ("eye:mattrai",))
        self.assertEqual(self.actions, [("menu", "eye:mattrai")])

    def test_label_picker_sends_label_action(self):
        ol = self.ol
        fill(ol)
        seen = []
        ol.on_action = lambda a, i: seen.append((a, i, ol.label_of(i)))
        self.assertEqual(ol.label_of("eye:mattrai"), "mattrai")
        cb = ol.label_picker("eye:mattrai")
        self.assertEqual(tuple(cb.cget("values")), ("mattrai", "matphai"))
        cb.set("matphai")
        cb.event_generate("<<ComboboxSelected>>")
        self.assertEqual(seen, [("label", "eye:mattrai", "matphai")])   # trong callback đọc được label mới
        self.assertEqual(ol.label_of("eye:mattrai"), "mattrai")          # App không đổi dữ liệu: ô label quay về label cũ
        cb.set("matphai")
        cb.event_generate("<<ComboboxSelected>>")
        ol.item("eye:mattrai", card=card("matphai"))                      # App đổi dữ liệu: ô label theo
        self.assertEqual(ol.label_of("eye:mattrai"), "matphai")

    def test_batch_keeps_selection_and_open_and_is_silent(self):
        ol = self.ol
        fill(ol)
        ol.item("eye:mattrai", open=True)
        ol.selection_set("pt:17")
        ol.activate("eye:matphai")
        self.selects.clear()
        ol.begin_update()
        ol.delete(*ol.get_children())
        fill(ol)                                                  # không truyền open: giữ DETAILS đang mở
        ol.end_update()
        self.assertEqual(ol.selection(), ("pt:17",))
        self.assertIs(ol.item("eye:mattrai", "open"), True)
        self.assertEqual(ol.activated(), "eye:matphai")
        self.assertEqual(self.selects, [])
        # dựng lại mà dòng đang chọn biến mất: lựa chọn rỗng và báo một lần
        ol.begin_update()
        ol.delete(*ol.get_children())
        fill(ol, labels=("matphai",))
        ol.end_update()
        self.assertEqual(ol.selection(), ())
        self.assertEqual(self.selects, [()])
        self.assertEqual(ol.activated(), "eye:matphai")             # thẻ đang sáng vẫn còn thì vẫn sáng
        ol.begin_update()
        ol.delete(*ol.get_children())
        fill(ol, labels=("mattrai",))
        ol.end_update()
        self.assertIsNone(ol.activated())                         # thẻ đang sáng mất thì thôi sáng
        self.assertEqual(self.selects, [()])                      # lựa chọn vẫn rỗng: không báo thêm

    def test_collapse_by_caret_moves_point_selection_to_eye(self):
        ol = self.ol
        fill(ol)
        caret = ol.buttons("eye:mattrai")["caret"]
        caret._click(None)
        self.assertIs(ol.item("eye:mattrai", "open"), True)
        self.assertEqual(caret.name, "caret_up")
        ol.selection_set("pt:15")
        caret._click(None)                                        # spec 7b.4: thu gọn DETAILS → lựa chọn về cả mắt
        self.assertIs(ol.item("eye:mattrai", "open"), False)
        self.assertEqual(caret.name, "caret_down")
        self.assertEqual(ol.selection(), ("eye:mattrai",))
        self.assertEqual(self.selects[-1], ("eye:mattrai",))
        # thu gọn bằng lệnh (nút "thu gọn tất cả" của App gọi item(open=False)) cũng vậy, và báo on_select
        ol.item("eye:matphai", open=True)
        ol.selection_set("pt:23")
        n = len(self.selects)
        ol.item("eye:matphai", open=False)
        self.assertEqual(ol.selection(), ("eye:matphai",))
        self.assertEqual(len(self.selects), n + 1)
        ol.item("eye:matphai", open=False)                       # đã đóng: không đổi gì, không báo
        self.assertEqual(len(self.selects), n + 1)

    def test_disabled_nav_and_locked_switches(self):
        ol = self.ol
        fill(ol, cards={"mattrai": card("mattrai", has_first=False, has_prev=False, has_next=True, has_last=False, lock=True)})
        b = ol.buttons("eye:mattrai")
        self.assertEqual([b[k]._enabled for k in ("first", "prev", "next", "last")], [False, False, True, False])
        # như CVAT: thẻ khoá thì chỉ nút Lock còn bấm được, ô label cũng khoá
        self.assertTrue(b["lock"]._enabled)
        self.assertFalse(any(b[k]._enabled for k in ("outside", "occluded", "hidden", "keyframe", "pinned")))
        self.assertEqual(str(ol.label_picker("eye:mattrai").cget("state")), "disabled")
        ol.item("eye:mattrai", card=card("mattrai"))
        self.assertTrue(all(b[k]._enabled for k in ("outside", "occluded", "hidden", "keyframe", "pinned")))

    def test_tooltips_use_current_keys(self):
        ol = self.ol
        self.assertEqual(ol.tip("outside"), "Outside (o)")
        self.assertEqual(ol.tip("lock"), "Khoá/mở khoá (l)")
        self.assertEqual(ol.tip("occluded"), "Occluded (q)")
        self.assertEqual(ol.tip("hidden"), "Ẩn/hiện (h)")
        self.assertEqual(ol.tip("keyframe"), "Keyframe (k)")
        self.assertEqual(ol.tip("pinned"), "Pinned (p)")
        self.assertEqual(ol.tip("prev"), "Keyframe trước (e)")
        ol.set_keys({"occluded": "/"})
        self.assertEqual(ol.tip("occluded"), "Occluded (/)")
        self.assertEqual(ol.tip("lock"), "Khoá/mở khoá (l)")       # phím không truyền thì dùng mặc định CVAT

    def test_card_text_and_point_rows(self):
        ol = self.ol
        fill(ol, cards={"matphai": card("matphai", id=None, status="đã xoá")})
        self.assertEqual(ol.card_texts("eye:mattrai"), ("#1", "SKELETON TRACK", "keyframe"))
        self.assertEqual(ol.card_texts("eye:matphai"), ("", "SKELETON TRACK", "đã xoá"))
        self.assertEqual(ol.row_texts("pt:17"), ("điểm 17", "suy ra", "Occluded"))
        self.assertEqual(ol.row_texts("pt:14"), ("điểm 14", "ghim", ""))
        ol.item("pt:14", values=("ghim", "★", "Outside"))
        self.assertEqual(ol.row_texts("pt:14"), ("điểm 14", "ghim", "Outside"))

    def test_identify_row(self):
        ol = self.ol
        fill(ol)
        ol.item("eye:matphai", open=True)
        self.root.update_idletasks()
        for iid in ("eye:mattrai", "eye:matphai", "pt:25"):
            w = ol.row_widget(iid)
            y = w.winfo_rooty() - ol.winfo_rooty() + (4 if iid.startswith("eye:") else w.winfo_height() // 2)   # thẻ: hàng 1
            self.assertEqual(ol.identify_row(y), iid)
        self.assertEqual(ol.identify_row(10 ** 5), "")

    def test_mouse_wheel_scrolls_list(self):
        ol = self.ol
        for layer in range(3):
            fill(ol, layer=layer, open_=True)
        self.root.update_idletasks()
        ol.canvas.configure(height=200)
        self.root.update_idletasks()
        self.assertEqual(ol.canvas.yview()[0], 0.0)
        ol.row_widget("pt:15").event_generate("<MouseWheel>", delta=-120)
        self.assertGreater(ol.canvas.yview()[0], 0.0)
        top = ol.canvas.yview()[0]
        ol.label_picker("eye:mattrai").event_generate("<MouseWheel>", delta=120)   # con lăn trên ô label: cuộn danh sách, không đổi label
        self.assertLess(ol.canvas.yview()[0], top)
        self.assertEqual(ol.label_of("eye:mattrai"), "mattrai")
        self.assertEqual(self.actions, [])

    # ---------- Task 5b: nút Outside / Occluded cho từng điểm trong DETAILS ----------
    def test_point_row_has_outside_and_occluded_buttons(self):
        ol = self.ol
        fill(ol, layer=1, open_=True)
        self.root.update_idletasks()
        pb = ol.point_buttons("pt:17@1")
        self.assertEqual(set(pb), {"outside", "occluded"})
        self.assertEqual((pb["outside"].name, pb["occluded"].name), ("inside", "occluded"))   # điểm 17 đang Occluded, không Outside
        self.assertEqual(ol.point_buttons("pt:14@1")["occluded"].name, "not_occluded")
        pb["outside"]._click(None)
        pb["occluded"]._click(None)
        self.assertEqual(self.actions, [("outside", "pt:17@1"), ("occluded", "pt:17@1")])
        self.assertEqual(ol.selection(), ())                       # bấm nút không tự chọn dòng (App chọn khi xử lý)
        # nằm cùng hàng, sau chữ trạng thái, đúng thứ tự Outside rồi Occluded
        row = ol.row_widget("pt:17@1")
        self.assertEqual({pb["outside"].winfo_parent(), pb["occluded"].winfo_parent()}, {str(row)})
        state = next(w for w in row.winfo_children() if w.winfo_class() == "Label" and w.cget("text") == "Occluded")
        self.assertGreater(pb["outside"].winfo_x(), state.winfo_x())
        self.assertGreater(pb["occluded"].winfo_x(), pb["outside"].winfo_x())
        self.assertLessEqual(pb["outside"].size, 16)
        # chữ khi trỏ chuột: tiếng Việt + phím hiện hành
        self.assertEqual(ol.tip("pt_outside"), "Outside cho điểm này (o)")
        self.assertEqual(ol.tip("pt_occluded"), "Occluded cho điểm này (q)")
        ol.set_keys({"occluded": "/"})
        self.assertEqual(ol.tip("pt_occluded"), "Occluded cho điểm này (/)")
        # bấm vào chính dòng điểm vẫn là chọn điểm
        row.event_generate("<Button-1>")
        self.assertEqual(ol.selection(), ("pt:17@1",))

    def test_point_buttons_follow_state_in_place(self):
        ol = self.ol
        fill(ol)
        self.root.update_idletasks()
        n = count_widgets(ol)
        pb = ol.point_buttons("pt:15")
        self.assertEqual((pb["outside"].name, pb["occluded"].name), ("inside", "not_occluded"))
        ol.item("pt:15", values=("ghim", "★", "Outside"))
        self.assertEqual((pb["outside"].name, pb["occluded"].name), ("outside", "not_occluded"))
        ol.begin_update()                                          # đợt cập nhật khi phát: cùng dãy iid
        ol.delete(*ol.get_children())
        fill(ol)
        ol.item("pt:15", values=("ghim", "★", "Occluded"))
        ol.end_update()
        self.root.update_idletasks()
        self.assertEqual(count_widgets(ol), n)
        self.assertIs(ol.point_buttons("pt:15")["outside"], pb["outside"])                   # đúng widget cũ
        self.assertEqual((pb["outside"].name, pb["occluded"].name), ("inside", "occluded"))
        ol.begin_update()
        ol.delete(*ol.get_children())
        fill(ol)                                                   # điểm 15 về "" (không cờ), điểm 17 vẫn Occluded
        ol.end_update()
        self.assertEqual((pb["outside"].name, pb["occluded"].name), ("inside", "not_occluded"))
        self.assertEqual(ol.point_buttons("pt:17")["occluded"].name, "occluded")
        ol.item("pt:16", values=("suy ra", "★", "—"))              # "—" = chưa có điểm: không cờ nào
        self.assertEqual((ol.point_buttons("pt:16")["outside"].name, ol.point_buttons("pt:16")["occluded"].name),
                         ("inside", "not_occluded"))

    def test_point_buttons_dim_when_card_locked(self):
        ol = self.ol
        fill(ol, cards={"mattrai": card("mattrai", lock=True)})
        for pid in POINTS["mattrai"]:
            self.assertFalse(any(b._enabled for b in ol.point_buttons(f"pt:{pid}").values()), pid)
        pb = ol.point_buttons("pt:17")
        pb["outside"]._click(None)
        pb["occluded"]._click(None)
        self.assertEqual(self.actions, [])                         # mờ thì không bấm được
        self.assertTrue(all(b._enabled for b in ol.point_buttons("pt:22").values()))     # thẻ kia không khoá
        ol.item("eye:mattrai", card=card("mattrai"))
        self.assertTrue(all(b._enabled for b in pb.values()))
        pb["occluded"]._click(None)
        self.assertEqual(self.actions, [("occluded", "pt:17")])

    def test_in_place_update_is_fast(self):
        ol = self.ol
        for layer in range(2):
            fill(ol, layer=layer)
        self.root.update_idletasks()
        t0 = time.perf_counter()
        for k in range(50):
            ol.begin_update()
            ol.delete(*ol.get_children())
            for layer in range(2):
                fill(ol, layer=layer, cards={"mattrai": card("mattrai", keyframe=bool(k % 2), status=f"s{k % 3}")})
            ol.end_update()
        per = (time.perf_counter() - t0) / 50
        self.assertLess(per, 0.025, f"{per * 1000:.1f} ms mỗi lần cập nhật 4 thẻ")


if __name__ == "__main__":
    unittest.main()
