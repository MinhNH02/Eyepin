"""Danh sách đối tượng kiểu CVAT 2.75 (thanh bên phải, tab Objects): mỗi mắt một thẻ, nút nằm trên thẻ (spec 4.2).

Bố cục chép từ mã nguồn CVAT v2.75.0 (`object-item-basics.tsx`, `object-item-buttons.tsx`, `object-item-details.tsx`,
`object-item-element.tsx`, giấy phép MIT):

    ┃ #1  SKELETON TRACK · keyframe      [mattrai ▾]   ⋮      hàng 1: ID, loại (+ trạng thái chữ xám), ô label, nút menu
    ┃        ⏮      ◀      ▶      ⏭                           hàng 2: keyframe đầu / trước / kế / cuối (mờ khi không có)
    ┃   Outside  Lock  Occluded  Hidden  Keyframe  Pinned      hàng 3: đúng thứ tự CVAT, icon đổi theo trạng thái
    ┃ ▾ DETAILS                                               bấm để mở/đóng danh sách điểm
    ┃     điểm 14   ghim     Occluded  ⊘ ◎                     mỗi điểm một dòng; bấm dòng = chọn điểm; hai nút Outside / Occluded của điểm

Thẻ shape (`card["kind"] == "shape"`, chữ loại `SKELETON SHAPE`): không có hàng 2, hàng 3 chỉ còn Lock, Occluded, Hidden, Pinned như
nhánh shape của `object-item-buttons.tsx`; DETAILS giữ hai nút Outside / Occluded của từng điểm.

`ObjectList` có API giống `ttk.Treeview` (insert, delete, get_children, exists, item, set, selection*, identify_row, see) để mã
của App đang dùng `App.tree` chạy tiếp được. Dòng cấp 1 (iid `eye:<label>[@layer]`) là một thẻ; dòng cấp 2 (`pt:<id>[@layer]`) là
một dòng điểm trong DETAILS của thẻ đó; `values` của mọi dòng theo cột `(vai, sao, trang)`.

Cập nhật nhanh khi phát: giữa `begin_update()` và `end_update()`, `delete(*tất_cả)` rồi `insert(...)` với CÙNG dãy iid chỉ đổi
icon, chữ, màu của các widget đã có (không tạo widget mới); thẻ chỉ được tạo/huỷ cho iid mới/mất (đổi thứ tự thì xếp lại thẻ cũ).
Mỗi thuộc tính chỉ được gửi xuống Tk khi giá trị đổi.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import theme
from .geometry import EYES
from .icons import IconButton, Tooltip

COLUMNS = ("vai", "sao", "trang")
LABELS = tuple(EYES)                                        # ("mattrai", "matphai")
NAV = ("first", "prev", "next", "last")
SWITCHES = ("outside", "lock", "occluded", "hidden", "keyframe", "pinned")    # đúng thứ tự hàng 3 của CVAT
# icon khi trạng thái bật / tắt (CVAT: object-outside-icon/SelectOutlined, LockFilled/UnlockOutlined, TeamOutlined/UserOutlined,
# EyeInvisibleFilled/EyeOutlined, StarFilled/StarOutlined, PushpinFilled/PushpinOutlined)
SWITCH_ICONS = {"outside": ("outside", "inside"), "lock": ("lock", "unlock"), "occluded": ("occluded", "not_occluded"),
                "hidden": ("eye_off", "eye"), "keyframe": ("star", "star_off"), "pinned": ("pinned", "unpinned")}
# phím mặc định (CVAT) theo mã hành động của `shortcuts.py`; App truyền phím hiện hành qua `keys`
DEFAULT_KEYS = {"outside": "o", "lock": "l", "occluded": "q", "hide": "h", "keyframe": "k", "pinned": "p",
                "prev_keyframe": "e", "next_keyframe": "r"}
SHAPE_HIDDEN = NAV + ("outside", "keyframe")                 # thẻ shape (CVAT object-item-buttons.tsx): không có các nút này
CARD_DEFAULT = {"id": None, "label": "", "color": theme.MUTED, "type": "SKELETON TRACK", "status": "", "kind": "track",
                "outside": False, "lock": False, "occluded": False, "hidden": False, "keyframe": False, "pinned": False,
                "has_prev": False, "has_next": False, "has_first": False, "has_last": False,
                "label_hidden": False}      # label ẩn cho mọi đối tượng (tab Labels): nút Hidden của thẻ mờ, chữ khi trỏ chuột nói lý do

POINT_BTN_SIZE = 14                                             # nút Outside / Occluded của dòng điểm nhỏ hơn nút của thẻ (16)

CARD_BG = theme.WHITE
ROW_SEL_BG = theme.ORANGE_SOFT
_MISSING = object()


def _label_from_iid(iid: str) -> str:
    """`eye:matphai@1` → `matphai`."""
    return iid.partition(":")[2].partition("@")[0]


def _flat(items) -> tuple:
    """Như ttk.Treeview: nhận `f(a, b)` lẫn `f((a, b))`."""
    if len(items) == 1 and isinstance(items[0], (tuple, list)):
        items = items[0]
    return tuple(items)


class _Item:
    __slots__ = ("parent", "text", "values", "card", "open", "children")

    def __init__(self, parent, text, values, card, open_):
        self.parent, self.text, self.values, self.card, self.open = parent, text, values, card, open_
        self.children: list[str] = []


class _Cached:
    """Ghi nhớ giá trị đã đẩy xuống Tk để cập nhật tại chỗ chỉ gọi Tk khi giá trị đổi."""

    def _put(self, key, value, apply):
        if self._cache.get(key, _MISSING) != value:
            self._cache[key] = value
            apply(value)


class _PointRow(_Cached):
    """Một dòng điểm trong DETAILS: tên điểm, chữ nhỏ nguồn ("ghim" / "suy ra"), trạng thái ("Occluded" / "Outside" / "—")."""

    def __init__(self, card: "_Card", iid: str):
        self.iid, self._cache = iid, {}
        ol = card.ol
        f = self.frame = tk.Frame(card.det, bg=CARD_BG)
        self.name = tk.Label(f, bg=CARD_BG, fg=theme.INK, font=(theme.FONT, 9), anchor="w", width=9)
        self.src = tk.Label(f, bg=CARD_BG, fg=theme.MUTED, font=(theme.FONT, 8), anchor="w", width=7)
        self.state = tk.Label(f, bg=CARD_BG, fg=theme.INK, font=(theme.FONT, 9), anchor="e")
        self.name.pack(side="left", padx=(14, 4))
        self.src.pack(side="left")
        # nút Outside / Occluded riêng của điểm (CVAT: object-item-element); pack side=right nên Occluded gói trước = ngoài cùng bên phải
        self.btn: dict[str, IconButton] = {}
        for kind in ("occluded", "outside"):
            b = self.btn[kind] = ol._button(f, SWITCH_ICONS[kind][1], lambda _b, k=kind: ol._act(k, iid), iid,
                                            tip_name=f"pt_{kind}", size=POINT_BTN_SIZE)
            b.pack(side="right", padx=(0, 1))
        self.state.pack(side="right", padx=(4, 2))
        self.widgets = (f, self.name, self.src, self.state)
        for w in self.widgets:
            ol._bind_row(w, iid)

    def update(self, it: _Item, selected: bool, locked: bool = False):
        vals = tuple(it.values) + ("", "", "")
        state = str(vals[2])
        self._put("name", it.text, lambda v: self.name.configure(text=v))
        self._put("src", str(vals[0]), lambda v: self.src.configure(text=v))
        self._put("state", state, lambda v: self.state.configure(text=v))
        self._put("bg", ROW_SEL_BG if selected else CARD_BG, self._paint)
        for kind, on in (("outside", state == "Outside"), ("occluded", state == "Occluded")):
            b = self.btn[kind]
            want = SWITCH_ICONS[kind][0 if on else 1]
            if b.name != want:
                b.set_icon(want)
            want_on = not locked and state != "—"                   # thẻ khoá hoặc điểm không có ở frame này ("—"): mờ
            if b._enabled != want_on:
                b.set_enabled(want_on)

    def _paint(self, bg: str):
        for w in self.widgets:
            w.configure(bg=bg)
        for b in self.btn.values():
            b.base = bg
            b._paint(bg)

    def destroy(self):
        self.frame.destroy()


class _Card(_Cached):
    """Thẻ của một đối tượng (dòng cấp 1)."""

    def __init__(self, ol: "ObjectList", iid: str):
        self.ol, self.iid, self._cache = ol, iid, {}
        self.rows: dict[str, _PointRow] = {}
        self.order: list[str] = []
        f = self.frame = tk.Frame(ol.inner, bg=CARD_BG, highlightthickness=2, highlightbackground=theme.PAPER,
                                  highlightcolor=theme.PAPER, bd=0)
        self.bar = tk.Frame(f, width=6, bg=theme.MUTED)                 # vạch màu label bên trái (CVAT: border-left 6px)
        self.bar.pack(side="left", fill="y")
        body = self.body = tk.Frame(f, bg=CARD_BG)
        body.pack(side="left", fill="both", expand=True, padx=(6, 2), pady=(2, 0))
        plain = [f, self.bar, body]                                       # widget mà bấm vào = chọn thẻ

        # hàng 1 (object-item-basics): ID trên, loại (+ trạng thái) dưới | ô chọn label | nút ⋮
        r1 = tk.Frame(body, bg=CARD_BG)
        r1.pack(fill="x")
        r1.columnconfigure(0, weight=1)
        left = tk.Frame(r1, bg=CARD_BG)
        left.grid(row=0, column=0, sticky="w")
        self.id_lbl = tk.Label(left, bg=CARD_BG, fg=theme.INK, font=(theme.FONT, 10, "bold"), anchor="w")
        self.id_lbl.pack(anchor="w")
        typ = tk.Frame(left, bg=CARD_BG)
        typ.pack(anchor="w")
        self.type_lbl = tk.Label(typ, bg=CARD_BG, fg=theme.MUTED, font=(theme.FONT, 8), anchor="w", padx=0)
        self.status_lbl = tk.Label(typ, bg=CARD_BG, fg=theme.MUTED, font=(theme.FONT, 8), anchor="w", padx=0)
        self.type_lbl.pack(side="left")
        self.status_lbl.pack(side="left")
        self.cb = ttk.Combobox(r1, values=LABELS, state="readonly", width=8, style="Card.TCombobox", exportselection=False)
        self.cb.grid(row=0, column=1, padx=(4, 2))
        self.cb.bind("<<ComboboxSelected>>", lambda e: ol._on_label(iid))
        self.cb.bind("<MouseWheel>", ol._on_wheel)                      # chặn lớp TCombobox: con lăn không được đổi label
        self.cb.bind("<Button-3>", lambda e: ol._on_right(iid, e))
        Tooltip(self.cb, "Đổi label (mattrai / matphai)")
        self.btn: dict[str, IconButton] = {}
        self.btn["more"] = more = ol._button(r1, "more", lambda b: ol._menu_from_button(iid, b), iid)
        more.grid(row=0, column=2)
        plain += [r1, left, self.id_lbl, typ, self.type_lbl, self.status_lbl]

        # hàng 2 và 3 (object-item-buttons, track): canh giữa, các nút cách đều nhau (justify='space-around')
        rows = []
        for names in (NAV, SWITCHES):
            row = tk.Frame(body, bg=CARD_BG)
            row.pack(fill="x", padx=(0, 18))
            for col, name in enumerate(names):
                row.columnconfigure(col, weight=1, uniform="b")
                b = self.btn[name] = ol._button(row, name, lambda _b, a=name: ol._act(a, iid), iid)
                b.grid(row=0, column=col)
            plain.append(row)
            rows.append(row)
        self.nav_row, self.sw_row = rows

        # DETAILS (object-item-details): đầu mục bấm được + danh sách dòng điểm
        head = self.det_head = tk.Frame(body, bg=CARD_BG)
        self.btn["caret"] = caret = ol._button(head, "caret_down", lambda b: ol._toggle_open(iid), iid, tip_name="caret")
        caret.pack(side="left")
        self.det_lbl = tk.Label(head, text="DETAILS", bg=CARD_BG, fg=theme.MUTED, font=(theme.FONT, 8), cursor="hand2")
        self.det_lbl.pack(side="left")
        self.det_lbl.bind("<Button-1>", lambda e: ol._toggle_open(iid))
        self.det = tk.Frame(body, bg=CARD_BG)
        for w in [head] + plain:
            ol._bind_row(w, iid)
        ol._bind_common(self.det_lbl, iid)
        ol._bind_common(self.det, iid)
        f.bind("<Enter>", lambda e: ol._hover(iid), add="+")
        f.bind("<Leave>", lambda e: ol._unhover(iid, f), add="+")

    # ---- dòng điểm ----
    def sync_rows(self, children: list[str]):
        if children == self.order:
            return
        for pid in [p for p in self.rows if p not in children]:
            self.rows.pop(pid).destroy()
        for pid in children:
            if pid not in self.rows:
                self.rows[pid] = _PointRow(self, pid)
        if self.order != children[:len(self.order)]:                    # đổi thứ tự: xếp lại hết; chỉ thêm cuối: xếp phần mới
            for pid in children:
                self.rows[pid].frame.pack_forget()
            start = 0
        else:
            start = len(self.order)
        for pid in children[start:]:
            self.rows[pid].frame.pack(fill="x")
        self.order = list(children)

    # ---- cập nhật tại chỗ ----
    def update(self, it: _Item, owner_selected: bool, active: bool, sel: set):
        ol = self.ol
        c = ol._card_data(self.iid, it)
        self._put("color", c["color"], lambda v: self.bar.configure(bg=v))
        ident = f"#{c['id']}" if c["id"] is not None else ("" if it.card else it.text)
        self._put("id", ident, lambda v: self.id_lbl.configure(text=v))
        self._put("type", str(c["type"]), lambda v: self.type_lbl.configure(text=v))
        self._put("status", str(c["status"] or ""), lambda v: self.status_lbl.configure(text=f" · {v}" if v else ""))
        self._put("kind", c["kind"], self._show_kind)
        if self.cb.get() != c["label"]:
            self.cb.set(c["label"])
        locked = bool(c["lock"])
        self._put("cb_state", "disabled" if locked else "readonly", lambda v: self.cb.configure(state=v))
        for name in NAV:
            b, on = self.btn[name], bool(c[f"has_{name}"])
            if b._enabled != on:
                b.set_enabled(on)
        for name in SWITCHES:
            b = self.btn[name]
            want = SWITCH_ICONS[name][0 if c[name] else 1]
            if b.name != want:
                b.set_icon(want)
            on = name == "lock" or not locked                         # như CVAT: thẻ khoá thì chỉ còn nút Lock
            if name == "hidden" and c["label_hidden"]:
                on = False                                            # label đang ẩn cho mọi đối tượng: ẩn/hiện riêng mắt này không có tác dụng
            if b._enabled != on:
                b.set_enabled(on)
        self._put("has_rows", bool(self.order), self._show_head)
        self._put("open", bool(it.open), self._show_details)
        border = theme.ORANGE if active else (theme.INK if owner_selected else theme.PAPER)
        self._put("border", border, lambda v: self.frame.configure(highlightbackground=v, highlightcolor=v))
        items = ol._items
        for pid in self.order:
            self.rows[pid].update(items[pid], pid in sel, locked)

    def _show_kind(self, kind: str):
        """Bộ nút theo kiểu đối tượng (CVAT object-item-buttons.tsx): shape không có hàng điều hướng keyframe, Outside và Keyframe
        (Outside chỉ còn ở từng điểm trong DETAILS). `grid_remove` nhớ ô của nút nên đổi lại về track thì `grid()` trả đúng chỗ cũ."""
        shape = kind == "shape"
        for name in SHAPE_HIDDEN:
            if shape:
                self.btn[name].grid_remove()
            else:
                self.btn[name].grid()
            if name in SWITCHES:                                    # cột trống không giữ chỗ (uniform): bốn nút còn lại dàn đều cả hàng
                self.sw_row.columnconfigure(SWITCHES.index(name), weight=0 if shape else 1, uniform="" if shape else "b")
        if shape:
            self.nav_row.pack_forget()                              # hàng không còn nút nào: bỏ cả hàng, không để lại khoảng trống
        elif not self.nav_row.winfo_manager():
            self.nav_row.pack(fill="x", padx=(0, 18), before=self.sw_row)

    def _show_head(self, on: bool):
        """Đầu mục DETAILS chỉ hiện khi thẻ có dòng điểm (CVAT: chỉ hiện khi có chi tiết)."""
        if not on:
            self.det_head.pack_forget()
        elif self.det.winfo_manager():
            self.det_head.pack(fill="x", before=self.det)
        else:
            self.det_head.pack(fill="x")

    def _show_details(self, on: bool):
        self.btn["caret"].set_icon("caret_up" if on else "caret_down")
        if on:
            self.det.pack(fill="x", pady=(0, 3))
        else:
            self.det.pack_forget()

    def destroy(self):
        self.frame.destroy()


class ObjectList(ttk.Frame):
    """Danh sách thẻ đối tượng kiểu CVAT với API giống `ttk.Treeview`.

    on_action(action, iid): action ∈ {first, prev, next, last, outside, lock, occluded, hidden, keyframe, pinned, menu, label, focus, open}.
        "open": người dùng vừa mở/đóng DETAILS của thẻ `iid` (đã đổi xong; App cập nhật nút mở/thu tất cả).
        "outside" / "occluded" cũng đến từ hai nút nhỏ của dòng điểm (iid `pt:<id>[@layer]`); thẻ khoá thì hai nút đó mờ.
        "label" được gửi sau khi người dùng đổi ô label của thẻ (đọc giá trị mới bằng `label_of(iid)` ngay trong callback; sau
        callback ô label quay về giá trị của dữ liệu, App làm mới thì nó theo dữ liệu mới). "menu": chuột phải vào thẻ/dòng hoặc
        nút ⋮; dòng đó được chọn trước, toạ độ màn hình để mở menu ở `menu_xy`. "focus": nhấp đúp thẻ hoặc dòng điểm.
    on_select(): gọi mỗi khi lựa chọn THẬT SỰ đổi, dù do người bấm (thẻ, dòng điểm, chuột phải, nút ⋮, thu gọn DETAILS) hay do
        lệnh (`selection_set/add/remove/toggle`, `delete` dòng đang chọn, `item(iid, open=False)` khi đang chọn điểm của thẻ đó).
        Gọi lệnh mà lựa chọn không đổi thì không báo (ttk.Treeview của Tk 8.6 luôn sinh <<TreeviewSelect>>, và sinh muộn qua
        hàng đợi sự kiện; ở đây báo ngay, đồng bộ). Giữa `begin_update()`/`end_update()` không báo gì; `end_update()` báo đúng một
        lần nếu lựa chọn sau đợt cập nhật khác lúc bắt đầu.
    on_hover(iid | None) (tuỳ chọn): con trỏ vào một thẻ / rời khỏi thẻ (để App tô sáng mắt trên ảnh, spec 4.2).
    keys: phím hiện hành theo mã hành động của `shortcuts.py` ("outside", "lock", "occluded", "hide", "keyframe", "pinned",
        "prev_keyframe", "next_keyframe"); thiếu thì dùng phím CVAT. Đổi sau bằng `set_keys`.
    """

    def __init__(self, parent, on_action: Callable[[str, str], None], on_select: Callable[[], None],
                 keys: dict[str, str] | None = None, on_hover: Callable[[str | None], None] | None = None, **kw):
        super().__init__(parent, **kw)
        self.on_action, self.on_select, self.on_hover = on_action, on_select, on_hover
        self._keys: dict[str, str] = {}
        self.set_keys(keys or {})
        self._items: dict[str, _Item] = {}
        self._roots: list[str] = []
        self._sel: tuple[str, ...] = ()
        self._active: str | None = None
        self._open_mem: dict[str, bool] = {}                      # nhớ DETAILS mở/đóng theo iid, kể cả qua delete + insert
        self._cards: dict[str, _Card] = {}
        self._packed: list[str] = []
        self._batch = 0
        self._batch_sel: tuple[str, ...] = ()
        self._batch_sel_touched = False
        self._auto = 0
        self._hover_iid: str | None = None
        self.menu_xy: tuple[int, int] | None = None

        st = ttk.Style(self)                                      # ô label nền trắng như ô chọn của CVAT (clam để xám khi readonly)
        st.map("Card.TCombobox", fieldbackground=[("disabled", theme.PAPER), ("readonly", theme.WHITE)],
               selectbackground=[("readonly", theme.WHITE)], selectforeground=[("readonly", theme.INK)])
        self.canvas = tk.Canvas(self, bg=theme.PAPER, highlightthickness=0, bd=0, yscrollincrement=20)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=theme.PAPER)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=(0, 0, e.width, e.height)))
        self.canvas.bind("<Configure>", self._on_canvas_size)
        for w in (self.canvas, self.inner):
            w.bind("<MouseWheel>", self._on_wheel)

    # ================= API giống ttk.Treeview =================
    def insert(self, parent: str, index, iid: str | None = None, text: str = "", values: tuple = (),
               open: bool | None = None, card: dict | None = None, **_ignored) -> str:
        """Thêm dòng. `open=None` (mặc định) giữ trạng thái DETAILS đã nhớ của iid này (mới thì đóng). `card` chỉ dùng cho dòng cấp 1."""
        parent = parent or ""
        if iid is None:
            self._auto += 1
            iid = f"I{self._auto:03X}"
        if iid in self._items:
            raise tk.TclError(f"Item {iid} already exists")
        if parent and parent not in self._items:
            raise tk.TclError(f"Item {parent} not found")
        if parent and self._items[parent].parent:
            raise ValueError("ObjectList chỉ có hai mức: thẻ (eye:) và dòng điểm (pt:)")
        is_open = self._open_mem.get(iid, False) if open is None else bool(open)
        self._open_mem[iid] = is_open
        self._items[iid] = _Item(parent, str(text), tuple(values), dict(card) if card else None, is_open)
        siblings = self._items[parent].children if parent else self._roots
        if index == "end" or not isinstance(index, int) or index >= len(siblings):
            siblings.append(iid)
        else:
            siblings.insert(max(0, index), iid)
        self._sync()
        return iid

    def delete(self, *iids):
        """Xoá dòng và mọi dòng con của nó (như Treeview)."""
        iids = _flat(iids)
        for iid in iids:
            if iid not in self._items:
                raise tk.TclError(f"Item {iid} not found")
        before = self._sel
        for iid in iids:
            it = self._items.pop(iid, None)
            if it is None:                                         # đã xoá theo dòng cha ở trên
                continue
            for ch in it.children:
                self._items.pop(ch, None)
            if not it.parent:
                self._roots.remove(iid)
            elif it.parent in self._items:                         # dòng cha bị xoá trước trong cùng lệnh thì đã đi cùng
                self._items[it.parent].children.remove(iid)
        self._sel = tuple(i for i in self._sel if i in self._items)
        if not self._batch and self._active is not None and self._active not in self._items:
            self._active = None
        self._sync()
        self._changed(before)

    def get_children(self, parent: str | None = "") -> tuple[str, ...]:
        if not parent:
            return tuple(self._roots)
        return tuple(self._get(parent).children)

    def exists(self, iid: str) -> bool:
        return iid in self._items

    def parent(self, iid: str) -> str:
        return self._get(iid).parent

    def item(self, iid: str, option: str | None = None, **kw):
        """`item(iid, "text" | "values" | "open" | "card")`, `item(iid)` (dict), `item(iid, open=True, text=..., values=..., card=...)`."""
        it = self._get(iid)
        if kw:
            before = self._sel
            if "text" in kw:
                it.text = str(kw["text"])
            if "values" in kw:
                it.values = tuple(kw["values"])
            if "card" in kw:
                it.card = dict(kw["card"]) if kw["card"] else None
            if "open" in kw:
                self._set_open(iid, bool(kw["open"]))
            self._sync()
            self._changed(before)                                  # đóng DETAILS khi đang chọn điểm của thẻ: lựa chọn về cả mắt
            return None
        info = {"text": it.text, "image": "", "values": it.values, "open": bool(it.open), "tags": (),
                "card": self._card_data(iid, it)}
        if option is None:
            return info
        if option not in info:
            raise tk.TclError(f'unknown option "-{option}"')
        return info[option]

    def set(self, iid: str, column: str | None = None, value=None):
        """Giá trị cột (`"vai"`, `"sao"`, `"trang"` hoặc `"#1"`..`"#3"`) theo thứ tự `values`; có `value` thì ghi."""
        it = self._get(iid)
        vals = list(it.values) + [""] * (len(COLUMNS) - len(it.values))
        if column is None:
            return dict(zip(COLUMNS, vals))
        idx = int(column[1:]) - 1 if column.startswith("#") else COLUMNS.index(column)
        if value is None:
            return vals[idx]
        vals[idx] = value
        it.values = tuple(vals)
        self._sync()
        return None

    def selection(self) -> tuple[str, ...]:
        return self._sel

    def selection_set(self, *iids):
        self._select(self._check(_flat(iids)))

    def selection_add(self, *iids):
        add = self._check(_flat(iids))
        self._select(self._sel + tuple(i for i in add if i not in self._sel))

    def selection_remove(self, *iids):
        drop = set(self._check(_flat(iids)))
        self._select(tuple(i for i in self._sel if i not in drop))

    def selection_toggle(self, *iids):
        cur = list(self._sel)
        for i in self._check(_flat(iids)):
            if i in cur:
                cur.remove(i)
            else:
                cur.append(i)
        self._select(tuple(cur))

    def identify_row(self, y) -> str:
        """iid của dòng điểm hoặc thẻ nằm ở toạ độ y (tính từ mép trên của ObjectList); "" khi không trúng dòng nào."""
        if self._batch:
            return ""
        Y = self.winfo_rooty() + int(y)
        for iid in self._roots:
            card = self._cards.get(iid)
            if card is None or not card.frame.winfo_ismapped():
                continue
            fy = card.frame.winfo_rooty()
            if not fy <= Y < fy + card.frame.winfo_height():
                continue
            for pid in card.order:
                w = card.rows[pid].frame
                if w.winfo_ismapped() and w.winfo_rooty() <= Y < w.winfo_rooty() + w.winfo_height():
                    return pid
            return iid
        return ""

    def see(self, iid: str):
        """Như Treeview: mở DETAILS chứa dòng này rồi cuộn cho nó hiện ra."""
        it = self._get(iid)
        if it.parent and not self._items[it.parent].open:
            self.item(it.parent, open=True)
        self._scroll_to(iid)

    # ================= phần riêng của thẻ =================
    def begin_update(self):
        """Bắt đầu một đợt cập nhật: delete/insert chỉ đổi dữ liệu; widget được đồng bộ một lần ở `end_update`."""
        if self._batch == 0:
            self._batch_sel, self._batch_sel_touched = self._sel, False
        self._batch += 1

    def end_update(self):
        """Kết thúc đợt cập nhật: cùng dãy iid thì cập nhật tại chỗ; giữ lựa chọn (nếu trong đợt không chọn lại) và thẻ đang sáng."""
        if self._batch == 0:
            return
        self._batch -= 1
        if self._batch:
            return
        src = self._sel if self._batch_sel_touched else self._batch_sel
        self._sel = tuple(i for i in src if i in self._items)
        if self._active is not None and self._active not in self._items:
            self._active = None
        self._sync()
        self._changed(self._batch_sel)

    def activate(self, iid: str | None, scroll: bool = True):
        """Tô sáng thẻ (CVAT "activated": con trỏ đang ở trên mắt đó trong ảnh) và cuộn tới nếu bị khuất. None hoặc iid không có = thôi.
        `scroll=False` khi con trỏ đang ở trên chính thẻ đó trong danh sách: cuộn lúc ấy sẽ kéo thẻ khác vào dưới con trỏ."""
        iid = iid if iid in self._items else None
        if iid == self._active:
            return
        self._active = iid
        self._sync()
        if iid is not None and scroll and not self._batch:
            self._scroll_to(iid)

    def activated(self) -> str | None:
        return self._active

    def label_of(self, iid: str) -> str:
        """Label đang hiện trên ô chọn của thẻ (dòng điểm: của thẻ chứa nó)."""
        it = self._get(iid)
        top = it.parent or iid
        card = self._cards.get(top)
        return card.cb.get() if card is not None else self._card_data(top, self._items[top])["label"]

    def set_keys(self, keys: dict[str, str]):
        """Phím hiện hành để ghi trong chữ khi trỏ chuột ("hidden" được hiểu như "hide")."""
        keys = dict(keys)
        if "hidden" in keys and "hide" not in keys:
            keys["hide"] = keys["hidden"]
        self._keys = keys

    def tip(self, name: str) -> str:
        """Chữ khi trỏ chuột vào nút `name` của thẻ (tiếng Việt + phím hiện hành)."""
        k = lambda aid: self._keys.get(aid) or DEFAULT_KEYS[aid]
        return {
            "outside": f"Outside ({k('outside')})", "lock": f"Khoá/mở khoá ({k('lock')})",
            "occluded": f"Occluded ({k('occluded')})", "hidden": f"Ẩn/hiện ({k('hide')})",
            "keyframe": f"Keyframe ({k('keyframe')})", "pinned": f"Pinned ({k('pinned')})",
            "first": "Keyframe đầu", "prev": f"Keyframe trước ({k('prev_keyframe')})",
            "next": f"Keyframe kế ({k('next_keyframe')})", "last": "Keyframe cuối",
            "pt_outside": f"Outside cho điểm này ({k('outside')})", "pt_occluded": f"Occluded cho điểm này ({k('occluded')})",
            "more": "Menu của đối tượng (cũng bấm chuột phải vào thẻ)", "caret": "Mở/đóng chi tiết từng điểm (DETAILS)",
        }.get(name, name)

    def tip_for(self, name: str, iid: str) -> str:
        """Chữ khi trỏ chuột vào nút `name` của thẻ/dòng `iid`: như `tip`, trừ nút đang mờ vì một lý do cần nói ra."""
        it = self._items.get(iid)
        if name == "hidden" and it is not None and not it.parent:
            c = self._card_data(iid, it)
            why = []                                                  # nút Hidden mờ vì label ẩn (tab Labels) và/hoặc thẻ khoá: nói đúng lý do thật
            if c["label_hidden"]:
                why.append(f"label {c['label']} đang ẩn cho mọi đối tượng (tab Labels): hiện label ở đó trước")
            if c["lock"]:
                why.append(f"đối tượng đang khoá: mở khoá ({self._keys.get('lock') or DEFAULT_KEYS['lock']}) trước")
            if why:
                text = "; ".join(why)
                return text[0].upper() + text[1:]
        if name in ("pt_outside", "pt_occluded") and it is not None and it.parent:
            if self._card_data(it.parent, self._items[it.parent])["lock"]:
                return f"{self.tip(name)}: đối tượng đang khoá, mở khoá trước"
            if tuple(it.values)[2:3] == ("—",):
                return "Điểm này không có ở frame hiện tại"
        return self.tip(name)

    # ---- truy cập widget (cho App và test) ----
    def buttons(self, iid: str) -> dict[str, IconButton]:
        """Các nút của thẻ: first, prev, next, last, outside, lock, occluded, hidden, keyframe, pinned, more, caret."""
        return dict(self._card(iid).btn)

    def point_buttons(self, iid: str) -> dict[str, IconButton]:
        """Hai nút của dòng điểm `pt:<id>[@layer]`: outside, occluded."""
        it = self._get(iid)
        return dict(self._card(it.parent).rows[iid].btn)

    def label_picker(self, iid: str) -> ttk.Combobox:
        return self._card(iid).cb

    def row_widget(self, iid: str) -> tk.Frame | None:
        """Khung của thẻ (iid cấp 1) hoặc của dòng điểm; None khi chưa dựng."""
        it = self._items.get(iid)
        if it is None:
            return None
        if not it.parent:
            card = self._cards.get(iid)
            return card.frame if card else None
        card = self._cards.get(it.parent)
        row = card.rows.get(iid) if card else None
        return row.frame if row else None

    def card_texts(self, iid: str) -> tuple[str, str, str]:
        """(chữ ID, chữ loại, chữ trạng thái) đang hiện ở hàng 1 của thẻ."""
        c = self._card(iid)
        return c.id_lbl.cget("text"), c.type_lbl.cget("text"), c._cache.get("status", "")

    def row_texts(self, iid: str) -> tuple[str, str, str]:
        """(tên điểm, nguồn, trạng thái) đang hiện ở dòng điểm."""
        it = self._get(iid)
        row = self._card(it.parent).rows[iid]
        return row.name.cget("text"), row.src.cget("text"), row.state.cget("text")

    # ================= bên trong =================
    def _get(self, iid: str) -> _Item:
        it = self._items.get(iid)
        if it is None:
            raise tk.TclError(f"Item {iid} not found")
        return it

    def _card(self, iid: str) -> _Card:
        self._get(iid)
        card = self._cards.get(iid)
        if card is None:
            raise tk.TclError(f"Item {iid} chưa có thẻ (không phải dòng cấp 1, hoặc đang trong begin_update)")
        return card

    def _check(self, iids: tuple) -> tuple:
        for i in iids:
            self._get(i)
        return tuple(dict.fromkeys(iids))

    def _card_data(self, iid: str, it: _Item) -> dict:
        return {**CARD_DEFAULT, "label": _label_from_iid(iid), **(it.card or {})}

    def _select(self, new: tuple[str, ...]):
        before = self._sel
        self._sel = new
        if self._batch:
            self._batch_sel_touched = True
            return
        if new != before:
            self._sync()
        self._changed(before)

    def _changed(self, before: tuple):
        if not self._batch and self._sel != before and self.on_select:
            self.on_select()

    def _set_open(self, iid: str, on: bool):
        it = self._items[iid]
        it.open = on
        self._open_mem[iid] = on
        if not on and not it.parent and any(self._items[s].parent == iid for s in self._sel if s in self._items):
            # spec 7b.4: thu gọn DETAILS thì lựa chọn trở về cả mắt
            self._sel = tuple(dict.fromkeys(iid if self._items[s].parent == iid else s for s in self._sel))
            if self._batch:
                self._batch_sel_touched = True

    def _sync(self):
        """Đồng bộ widget theo dữ liệu: tạo/huỷ thẻ cho iid mới/mất, xếp lại khi đổi thứ tự, rồi cập nhật tại chỗ."""
        if self._batch:
            return
        items = self._items
        lost_hover = False
        for iid in [i for i in self._cards if i not in items or items[i].parent]:
            self._cards.pop(iid).destroy()
            if iid in self._packed:
                self._packed.remove(iid)
            if iid == self._hover_iid:                            # thẻ dưới con trỏ bị huỷ: Tk không gửi <Leave> cho nó nữa
                self._hover_iid, lost_hover = None, True
        for iid in self._roots:
            if iid not in self._cards:
                self._cards[iid] = _Card(self, iid)
        if self._packed != self._roots:
            # xếp theo thứ tự mới bằng `after=` (thẻ đang hiện chỉ dời chỗ, không bị gỡ rồi hiện lại)
            prev = None
            for iid in self._roots:
                fr = self._cards[iid].frame
                if prev is not None:
                    fr.pack(fill="x", padx=2, pady=(0, 4), after=prev)
                else:
                    first = self.inner.pack_slaves()
                    if first and first[0] is not fr:
                        fr.pack(fill="x", padx=2, pady=(0, 4), before=first[0])
                    else:
                        fr.pack(fill="x", padx=2, pady=(0, 4))
                prev = fr
            self._packed = list(self._roots)
        sel = set(self._sel)
        owners = {items[s].parent or s for s in self._sel}
        act = self._active
        act_owner = (items[act].parent or act) if act in items else None
        for iid in self._roots:
            card = self._cards[iid]
            card.sync_rows(items[iid].children)
            card.update(items[iid], iid in owners, iid == act_owner, sel)
        if lost_hover and self.on_hover:                          # báo sau cùng: App có thể gọi lại widget (activate) an toàn
            self.on_hover(None)

    def _scroll_to(self, iid: str):
        w = self.row_widget(iid)
        if w is None:
            return
        self.update_idletasks()
        view_h, total = self.canvas.winfo_height(), self.inner.winfo_height()
        if view_h <= 1 or total <= view_h or not w.winfo_ismapped():
            return
        top = w.winfo_rooty() - self.inner.winfo_rooty()
        y0 = self.canvas.canvasy(0)
        if top < y0:
            self.canvas.yview_moveto(top / total)
        elif top + w.winfo_height() > y0 + view_h:
            self.canvas.yview_moveto((top + w.winfo_height() - view_h) / total)

    def _on_canvas_size(self, e):
        if e.width > 1:
            self.canvas.itemconfigure(self._win, width=e.width)

    def _on_wheel(self, e):
        if self.inner.winfo_height() > self.canvas.winfo_height() and e.delta:
            self.canvas.yview_scroll(-3 if e.delta > 0 else 3, "units")
        return "break"

    # ---- nút và chuột ----
    def _button(self, parent, name: str, command, iid: str, tip_name: str | None = None, size: int = 16) -> IconButton:
        """Nút icon trên nền thẻ (trắng), gọn hơn nút thanh công cụ; chuột phải và con lăn như trên thẻ."""
        tip_name = tip_name or name
        b = IconButton(parent, name, command, tip=lambda: self.tip_for(tip_name, iid), kind="tool", size=size)
        b.base = CARD_BG
        b._paint(CARD_BG)
        b.icon.configure(pady=1)
        b.icon.pack_configure(padx=3 if size >= 16 else 1, pady=1)
        for w in (b, b.icon):
            self._bind_common(w, iid)
        return b

    def _bind_common(self, w, iid: str):
        w.bind("<Button-3>", lambda e: self._on_right(iid, e))
        w.bind("<MouseWheel>", self._on_wheel)

    def _bind_row(self, w, iid: str):
        """Bấm = chọn dòng; nhấp đúp = focus; chuột phải = chọn + menu; con lăn = cuộn danh sách."""
        w.bind("<Button-1>", lambda e: self._select((iid,)) if iid in self._items else None)
        w.bind("<Double-Button-1>", lambda e: self.on_action("focus", iid))
        self._bind_common(w, iid)

    def _act(self, action: str, iid: str):
        self.on_action(action, iid)

    def _on_right(self, iid: str, e):
        if iid not in self._items:
            return "break"
        self._select((iid,))
        self.menu_xy = (e.x_root, e.y_root)
        self.on_action("menu", iid)
        return "break"

    def _menu_from_button(self, iid: str, b: IconButton):
        self._select((iid,))
        self.menu_xy = (b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())
        self.on_action("menu", iid)

    def _on_label(self, iid: str):
        self.on_action("label", iid)
        if not self._batch:
            self._sync()                                          # ô label luôn theo dữ liệu (App từ chối thì quay lại)

    def _toggle_open(self, iid: str):
        """Mũi tên / chữ DETAILS của một thẻ: mở/đóng danh sách điểm, rồi báo App ("open") để nút mở/thu tất cả ở đầu danh sách theo kịp."""
        if iid not in self._items:
            return
        before = self._sel
        self._set_open(iid, not self._items[iid].open)
        self._sync()
        self._changed(before)
        self.on_action("open", iid)

    def _hover(self, iid: str):
        if self.on_hover and self._hover_iid != iid:
            self._hover_iid = iid
            self.on_hover(iid)

    def _unhover(self, iid: str, frame: tk.Misc):
        try:
            px, py = frame.winfo_pointerxy()
            x, y = frame.winfo_rootx(), frame.winfo_rooty()
            inside = x <= px < x + frame.winfo_width() and y <= py < y + frame.winfo_height()
        except tk.TclError:
            inside = False
        if self.on_hover and not inside and self._hover_iid == iid:
            self._hover_iid = None
            self.on_hover(None)
