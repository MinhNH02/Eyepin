"""Panel Đối tượng, tab Labels và tab Issues của EyePin (phần mở rộng của `App`, tách khỏi gui.py cho gọn).

Mô phỏng thẻ đối tượng của CVAT 2.75 (đã khảo sát trên CVAT local, xem design/cvat-parity.md): Sort by, khoá tất cả / ẩn tất cả,
menu ⋮ (Make a copy, Propagate, đổi lớp, Remove, Create object URL, Run annotation action), Pinned, đổi label, đổi màu (Enter),
tab Labels (khoá và ẩn theo label), tab Issues (đếm, trước/sau, ẩn, đã xử lý).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import NamedTuple

from . import gaps, theme
from .cvatapi import CvatError
from .geometry import EYES
from .gui_cvat import edit_command
from .icons import IconButton
from .render import INSTANCE_COLORS
from .scan import HINT, SHORT
from .session import QC_MSG, SHAPE_ONLY_MSG


class IssueEntry(NamedTuple):
    """Một dòng của tab Issues: `kind` ("turn" | "finding" | "gap" | "auto" | "cvat") và `payload` (dữ liệu của dòng, xem `ObjectsMixin._issue_entries`),
    khoảng frame (`first` None: dòng không có frame để nhảy tới), chữ ngắn, mức ("red" | "yellow" | "green") và chi tiết."""
    kind: str
    payload: object
    first: int | None
    last: int | None
    short: str
    level: str
    detail: str


def _pair_key(i: int, x):
    return (i, x)


def _labels_of(d: dict) -> set:
    """Các label có thể có trong một tập: mọi nhãn mắt và các label từng thêm. Không lấy label từ khoá đã lưu vì đổi label (`swap_eyes`)
    chuyển mã của mắt sang label kia."""
    return set(EYES) | set(d.values())


class LayerSet:
    """Tập nhãn mắt riêng cho từng bộ đối tượng (người): `label in s` chỉ nói về bộ đang chọn, nên khoá hay Pinned của người này không
    ảnh hưởng người kia. Dùng như `set` thông thường trên bộ đang chọn.
    Mỗi mắt được lưu theo khoá `key(người, label)` (mặc định chính cặp đó). App dùng mã ổn định của mắt (`App._eye_key`, tức
    `Layer.eye_uid` của Session): xoá người giữa không làm trạng thái trượt sang người khác, Ctrl+Z / Ctrl+Y sau Del hay đổi label đưa
    trạng thái về đúng mắt (B08, B09). Mắt đã mất không cần dọn: mã của nó không bao giờ được cấp lại."""

    def __init__(self, cur, key=None):
        self._cur, self._key, self._d = cur, key or _pair_key, {}         # _d: khoá lưu -> label lúc thêm (chỉ để biết label ngoài EYES)

    def _s(self) -> set:
        i = self._cur()
        return {x for x in _labels_of(self._d) if self.has(i, x)}

    def __contains__(self, x):
        return self.has(self._cur(), x)

    def __iter__(self):
        return iter(sorted(self._s()))

    def __len__(self):
        return len(self._s())

    def __bool__(self):
        return bool(self._s())

    def __eq__(self, other):
        return self._s() == set(other)

    def has(self, i: int, x) -> bool:
        """`x` có trong tập của người `i` (không cần chọn người đó)."""
        return self._key(i, x) in self._d

    def put(self, i: int, x, on: bool):
        """Thêm (`on`) hoặc bỏ `x` cho người `i`."""
        if on:
            self._d[self._key(i, x)] = x
        else:
            self._d.pop(self._key(i, x), None)

    def add(self, x):
        self.put(self._cur(), x, True)

    def discard(self, x):
        self.put(self._cur(), x, False)

    def clear(self):
        for x in self._s():
            self.discard(x)

    def update(self, xs):
        for x in xs:
            self.add(x)

    def set_all(self, x, on: bool, layers: int):
        """Thêm (`on`) hoặc bỏ `x` ở mọi bộ đối tượng 0..layers-1 (nút Lock ở tab Labels khoá label cho mọi người)."""
        for i in range(layers):
            self.put(i, x, on)

    def all_have(self, x, layers: int) -> bool:
        return layers > 0 and all(self.has(i, x) for i in range(layers))


class ObjectSet:
    """Tập các mắt dạng cặp (chỉ số người, label), dùng như `set` (App.hidden_objs: ẩn riêng từng mắt). Lưu theo khoá `key(người, label)`
    như `LayerSet`, nên cặp trả ra luôn theo chỉ số người HIỆN TẠI của mắt; duyệt tập chỉ gồm mắt của `count()` người đang có."""

    def __init__(self, key, count):
        self._key, self._count, self._d = key, count, {}                # _d: khoá lưu -> label lúc thêm (chỉ để biết label ngoài EYES)

    def _pairs(self) -> set:
        labels = _labels_of(self._d)
        return {(i, x) for i in range(self._count()) for x in labels if self._key(i, x) in self._d}

    def __contains__(self, p):
        return self._key(*p) in self._d

    def __iter__(self):
        return iter(sorted(self._pairs()))

    def __len__(self):
        return len(self._pairs())

    def __bool__(self):
        return bool(self._pairs())

    def __eq__(self, other):
        try:
            return self._pairs() == set(other)
        except TypeError:
            return NotImplemented

    __hash__ = None

    def __repr__(self):
        return f"ObjectSet({sorted(self._pairs())})"

    def add(self, p):
        self._d[self._key(*p)] = p[1]

    def discard(self, p):
        self._d.pop(self._key(*p), None)

    def clear(self):
        self._d.clear()


SORTS = ("ID - tăng dần", "ID - giảm dần", "Tên label", "Cập nhật gần nhất")


class ObjectsMixin:
    # ---------- khởi dựng ----------
    def _objects_extras(self, obj_tab):
        """Đầu danh sách đối tượng (CVAT objects-list-header, spec 4.1) và menu ⋮. Gọi trước khi tạo `self.tree` để nằm trên danh sách thẻ.
        Hàng 1: `Items: N` · Sort by. Hàng 2: khoá tất cả (LockFilled/UnlockOutlined), ẩn tất cả (EyeInvisibleFilled/EyeOutlined),
        mở/thu tất cả DETAILS (CaretUpFilled/CaretDownOutlined), rồi hai nút của EyePin: đối tượng mới (+) và xoá mắt.
        Các nút từng nằm dưới bảng (keyframe, khoá, ẩn, Occluded, Outside, Pinned, ⋮) nay ở trên từng thẻ."""
        head = ttk.Frame(obj_tab)
        head.pack(fill="x", pady=(2, 2))
        r1 = ttk.Frame(head)
        r1.pack(fill="x")
        self.items_var = tk.StringVar(value="Items: 0")
        ttk.Label(r1, textvariable=self.items_var).pack(side="left", padx=(2, 0))
        self.sort_var = tk.StringVar(value=SORTS[0])
        cb = ttk.Combobox(r1, textvariable=self.sort_var, values=SORTS, state="readonly", width=17)
        cb.pack(side="right", padx=(0, 2))
        ttk.Label(r1, text="Sort by", style="Muted.TLabel").pack(side="right", padx=(0, 4))
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh(light=False))
        r2 = ttk.Frame(head)
        r2.pack(fill="x", pady=(2, 0))
        self.obj_head_btns = {}
        for key, name, cmd, tip in (("lock_all", "unlock", self.toggle_lock_all, f"Khoá / mở khoá mọi đối tượng ({self.kl('lock_all')})"),
                                    ("hide_all", "eye", self.hide_all_eyes, "Ẩn / hiện tất cả"),
                                    ("collapse", "caret_down", self.collapse_all, "Mở / thu gọn DETAILS của mọi đối tượng"),
                                    ("add", "add", self.new_object, f"Đối tượng mới (người mới), ID mới ({self.kl('new_object')})"),
                                    ("trash", "trash", self.delete_label, f"Xoá mắt đang chọn ({self.kl('delete')}); Ctrl+Z hoàn tác")):
            b = self.obj_head_btns[key] = IconButton(r2, name, lambda b, c=cmd: c(), tip=tip, kind="tool")
            b.pack(side="left", padx=(12 if key == "add" else 1, 1))
        self.pinned_eyes = LayerSet(lambda: self.s.cur if self.s else 0, self._eye_key)
        self._build_obj_menu()

    def _sync_object_header(self):
        """Icon của ba nút "tất cả" theo trạng thái hiện tại (như CVAT: icon đặc khi đang bật)."""
        hb = getattr(self, "obj_head_btns", None)
        if not hb:
            return
        kids = self.tree.get_children()
        want = {"lock_all": "lock" if self._all_locked() else "unlock",                    # mọi mắt của mọi người
                "hide_all": "eye_off" if not any(self.look.eyes.values()) else "eye",
                "collapse": "caret_up" if any(self.tree.item(i, "open") for i in kids) else "caret_down"}
        for key, name in want.items():
            if hb[key].name != name:
                hb[key].set_icon(name)

    def _build_obj_menu(self):
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label="Tạo URL đối tượng", command=self.object_url)
        m.add_command(label="Tạo bản sao (Make a copy)", command=self.object_copy)
        m.add_command(label=f"Nhân sang N frame sau (Propagate, {self.kl('propagate')})…", command=self.object_propagate)
        m.add_separator()
        m.add_command(label="Đưa xuống nền (To background)", command=lambda: self.object_layer("back"))
        m.add_command(label="Đưa lên trước (To foreground)", command=lambda: self.object_layer("front"))
        m.add_command(label="Xuống một lớp (To one layer backward)", command=lambda: self.object_layer("backward"))
        m.add_command(label="Lên một lớp (To one layer forward)", command=lambda: self.object_layer("forward"))
        m.add_command(label="Chuyển tới lớp… (Move to layer)", command=self.object_move_to_layer)
        m.add_separator()
        self._pinned_var = tk.BooleanVar(value=False)
        m.add_checkbutton(label=f"Pinned ({self.kl('pinned')})", variable=self._pinned_var, command=self.toggle_pinned)
        m.add_command(label="Đổi label: hoán đổi mattrai và matphai", command=self.swap_labels)
        m.add_command(label=f"Đổi màu ({self.kl('change_color')})", command=self.object_color_next)
        m.add_command(label="Phóng vào đối tượng (Focus)", command=self.focus_object)
        m.add_separator()
        m.add_command(label=f"Xoá mắt (Remove, {self.kl('delete')})", command=self.delete_label)
        m.add_command(label="Kết thúc nhãn từ frame này (Outside)", command=self.end_label_here)
        m.add_command(label="Bỏ keyframe ở frame này", command=self.object_remove)
        m.add_command(label="Chạy hành động… (Run annotation action)", command=self.show_run_actions)
        self.obj_menu = m

    def popup_obj_menu(self, x: int, y: int):
        """Menu ⋮ của đối tượng đang chọn (nút ⋮ hoặc chuột phải trên thẻ: thẻ/dòng điểm đã được chọn trước, xem `_on_object_action`)."""
        label, _ = self._selected()
        self._pinned_var.set(label in self.pinned_eyes if label else False)
        self.obj_menu.tk_popup(x, y)

    # ---------- sắp xếp, ẩn/khoá tất cả ----------
    def _object_rows(self) -> list[tuple[int, str]]:
        """Các dòng của panel: (chỉ số bộ đối tượng, nhãn mắt), theo cách sắp xếp đang chọn. Mắt track: bộ đầu luôn hiện cả hai mắt (kể cả
        mắt đã xoá), các bộ khác chỉ hiện mắt đang có. Mắt shape (mọi bộ, kể cả bộ đầu) chỉ có dòng ở frame có shape của nó, như CVAT: mỗi
        shape là một đối tượng của riêng frame đó."""
        s = self.s

        def shown(i: int, l: str) -> bool:
            with s.layer_ctx(i):
                if s.eye_kind(l) == "shape":
                    return s.has_shape(l, self.f)
            return i == 0 or l in s.layers[i].obj_ids

        def key_id(r) -> int:
            with s.layer_ctx(r[0]):
                n = s.object_id(r[1], self.f)
            return n if n is not None else 10 ** 9 + r[0] * 10 + list(EYES).index(r[1])

        rows = [(i, l) for i in range(len(s.layers)) for l in EYES if shown(i, l)]
        mode = self.sort_var.get() if hasattr(self, "sort_var") else SORTS[0]
        if mode == SORTS[1]:
            return sorted(rows, key=key_id, reverse=True)
        if mode == SORTS[2]:
            return sorted(rows, key=lambda r: (r[1], key_id(r)))
        if mode == SORTS[3]:
            return sorted(rows, key=lambda r: -s.touched.get(r[1], 0.0))
        return sorted(rows, key=key_id)

    def _eye_order(self) -> list[str]:
        return [l for _, l in self._object_rows()] if self.s else list(EYES)

    @edit_command
    def new_object(self):
        """Đối tượng mới (người mới) như tạo object mới trong CVAT: thêm một bộ mattrai và matphai trống, chọn nó và vào chế độ ghim 8 điểm;
        khi ghim xong hai mắt nhận ID mới."""
        if not self.s:
            return
        # bỏ chọn trong panel trước: thẻ đang chọn của người cũ sẽ kéo `cur` về người đó ở lần vẽ kế (`_selected`) và 8 điểm sẽ ghi đè người cũ
        sel = self.tree.selection()
        if sel:
            self.tree.selection_remove(*sel)
        self.s.add_layer()
        self.notice = "Đối tượng mới: bấm 4 điểm mỗi mắt (8 điểm); hai mắt sẽ nhận ID mới."
        self.start_pin("full")

    def hide_all_eyes(self):
        any_visible = any(self.look.eyes.values())
        for l in EYES:
            self._layer_vars[l].set(not any_visible)
            self.look.eyes[l] = not any_visible
        self.notice = "Đã ẩn cả hai mắt." if any_visible else "Đã hiện cả hai mắt."
        self.refresh()

    def collapse_all(self):
        """Mở / thu gọn DETAILS của mọi thẻ (một lần đồng bộ widget). Thu gọn khi đang chọn một điểm thì lựa chọn về cả mắt (spec 7b.4)."""
        kids = self.tree.get_children()
        if not kids:
            return
        open_any = any(self.tree.item(i, "open") for i in kids)
        self.tree.begin_update()
        try:
            for i in kids:
                self.tree.item(i, open=not open_any)
        finally:
            self.tree.end_update()
        self._sync_object_header()

    # ---------- menu ⋮ ----------
    def _sel_eye(self, need_frame_labels: bool = False):
        label, _ = self._selected() if self.s else (None, None)
        if label is None:
            self.notice = "Chọn một mắt trong panel Đối tượng trước."
            self.refresh()
            return None
        if need_frame_labels and self._eye_points(label) is None:
            self.notice = "Frame này chưa có nhãn."
            self.refresh()
            return None
        return label

    def object_url(self):
        label = self._sel_eye()
        if label:
            url = f"{self.s.frames_dir or self.s.source_key}#frame={self.f}#{label}"
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.notice = f"Đã sao chép: {url}"
            self.refresh()

    def object_copy(self):
        """Make a copy: nhớ nhãn của riêng mắt đang chọn; Ctrl+V dán lên frame hiện tại (thành frame ghim, giữ nguyên mắt kia)."""
        label = self._sel_eye(need_frame_labels=True)
        if label:
            self.clipboard = {i: tuple(p) for i, p in self._eye_points(label).items()}
            self.notice = f"Đã sao chép {label} (frame {self.f}); bấm {self.kl('paste')} để dán vào frame khác."
            self.refresh()

    def ask_propagate(self):
        """Hộp "Confirm propagation" như CVAT: hướng (trước/sau), số bản sao, hoặc khoảng frame từ-tới. Trả về dict hoặc None nếu huỷ."""
        n = self.s.n_frames
        d = tk.Toplevel(self.root)
        d.title("Confirm propagation")
        d.transient(self.root)
        out = {}
        direction = tk.IntVar(value=1)
        count = tk.IntVar(value=max(1, n - 1 - self.f))
        lo, hi = tk.IntVar(value=self.f), tk.IntVar(value=n - 1)
        use_range = tk.BooleanVar(value=False)
        ttk.Label(d, text="Hướng nhân:").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        fr = ttk.Frame(d)
        fr.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(fr, text="← trước", value=-1, variable=direction).pack(side="left", padx=4)
        ttk.Radiobutton(fr, text="sau →", value=1, variable=direction).pack(side="left", padx=4)
        ttk.Label(d, text="Số bản sao:").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        ttk.Spinbox(d, from_=1, to=max(1, n), textvariable=count, width=8).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(d, text="Hoặc chọn khoảng frame:", variable=use_range).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 2))
        rf = ttk.Frame(d)
        rf.grid(row=3, column=0, columnspan=2, sticky="w", padx=10)
        ttk.Label(rf, text="Từ").pack(side="left")
        ttk.Spinbox(rf, from_=0, to=n - 1, textvariable=lo, width=6).pack(side="left", padx=4)
        ttk.Label(rf, text="tới").pack(side="left")
        ttk.Spinbox(rf, from_=0, to=n - 1, textvariable=hi, width=6).pack(side="left", padx=4)

        def ok():
            try:
                out.update(count=int(count.get()), direction=int(direction.get()),
                           start=int(lo.get()) if use_range.get() else None, end=int(hi.get()) if use_range.get() else None)
            except (tk.TclError, ValueError):
                return
            d.destroy()
        bt = ttk.Frame(d)
        bt.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(bt, text="Huỷ", command=d.destroy).pack(side="left", padx=6)
        ttk.Button(bt, text="Yes", command=ok).pack(side="left", padx=6)
        self._propagate_dlg = d
        d.grab_set()
        self.root.wait_window(d)
        return out or None

    @edit_command
    def object_propagate(self, count: int | None = None, direction: int = 1, start: int | None = None, end: int | None = None):
        if not self.s:
            return
        label = self._sel_eye(need_frame_labels=True)
        if not label:
            return
        if count is None and start is None:
            opts = self.ask_propagate()
            if not opts:
                return
            count, direction, start, end = opts["count"], opts["direction"], opts["start"], opts["end"]
        try:
            eyes = self.s.propagate_eyes(self.f)
            n = self.s.propagate(self.f, count or 0, direction, start, end)
            where = f"frame {start}–{end}" if start is not None else ("các frame sau" if direction >= 0 else "các frame trước")
            shapes = [l for l in eyes if self.s.eye_kind(l) == "shape"]
            if not shapes:
                self.notice = f"Đã nhân nhãn sang {n} frame ({where}); mỗi frame thành frame ghim."
            else:                                                       # mắt shape thành shape mới (không phải frame ghim); mắt kia giữ nguyên
                parts = [f"{l} thành {'shape mới' if l in shapes else 'keyframe'}" for l in eyes]
                rest = [l for l in EYES if l not in eyes]
                tail = f"; {', '.join(rest)} ở các frame đó giữ nguyên" if rest else ""
                self.notice = f"Đã nhân nhãn sang {n} frame ({where}): {', '.join(parts)} ở mỗi frame{tail}."
        except ValueError as err:
            self.notice = str(err)
        self.refresh()

    def object_layer(self, action: str):
        """Thứ tự vẽ giữa hai mắt (chỉ có hai lớp): front/forward đưa mắt đang chọn lên trên, back/backward đưa xuống dưới."""
        label = self._sel_eye()
        if not label:
            return
        other = next(l for l in EYES if l != label)
        self.look.top = label if action in ("front", "forward") else other
        self._sync_top()
        self.notice = f"{label} ở lớp {'trên' if self.look.top == label else 'dưới'}."
        self.refresh()

    def object_move_to_layer(self, layer: int | None = None):
        label = self._sel_eye()
        if not label:
            return
        if layer is None:
            layer = simpledialog.askinteger("Chuyển tới lớp", "Lớp số (0 = dưới, 1 = trên):", initialvalue=1, minvalue=0, maxvalue=1,
                                            parent=self.root)
            if layer is None:
                return
        self.object_layer("front" if layer >= 1 else "back")

    @edit_command
    def object_remove(self):
        """Menu ⋮ "Bỏ keyframe ở frame này". Mắt track: bỏ frame ghim này (như trước); frame có shape (của mắt kia) thì chỉ bỏ keyframe của
        RIÊNG mắt track đó (như K), để không xoá theo đối tượng shape. Mắt shape không có keyframe: xoá shape của RIÊNG mắt đó ở frame này
        (như Del), keyframe của mắt khác ở frame này giữ nguyên."""
        label = self._sel_eye()
        if not label:
            return
        s = self.s
        if s.eye_kind(label) == "shape" and label in self.locked:
            self.notice = f"{label} đang bị khoá; mở khoá trước khi xoá shape."
        elif s.eye_kind(label) == "shape":
            self._delete_shape_here(label)
        elif any(s.has_shape(l, self.f) for l in EYES):
            if self.f in s.eye_keyframes(label):
                s.toggle_eye_key(label, self.f)
                self.notice = f"Đã bỏ keyframe của {label} ở frame này; shape ở frame này giữ nguyên."
            else:
                self.notice = f"Frame này không phải keyframe của {label}."
        elif self.f in s.pins:
            self.s.remove_pin(self.f)
            self.notice = "Đã bỏ keyframe ở frame này."
        else:
            self.notice = "Frame này không phải keyframe."
        self.refresh()

    @edit_command
    def delete_label(self, force: bool = False):
        """Xoá mắt khỏi mọi frame (như phím Del của CVAT xoá đối tượng); Shift+Del xoá cả mắt đang khoá. Ctrl+Z hoàn tác.
        Như CVAT: mắt ĐANG HIỆN có con trỏ chuột trỏ vào được xoá trước; không trỏ vào mắt hiện nào thì xoá mắt đang chọn trong panel.
        Khoá, ẩn riêng và Pinned của mắt đã xoá được bỏ (vẽ lại mắt này thì nó là đối tượng mới: hiện, không khoá): `delete_eye` cấp mã mới
        cho mắt (`Layer.eye_uid`) nên trạng thái gắn với mã cũ không còn áp vào; Ctrl+Z trả mã cũ nên trạng thái về cùng mắt (B08).
        Không bỏ trạng thái theo chỉ số người ở đây: xoá mắt cuối của một người bỏ luôn người đó và chỉ số của người sau dịch lại (B09)."""
        label = self._eye_under_pointer()
        label = label or self._sel_eye()
        if not label:
            return
        if label in self.locked and not force:
            self.notice = f"{label} đang bị khoá; bấm Shift+Del để xoá cả mắt khoá."
        else:
            if self.s.eye_kind(label) == "shape":                    # shape chỉ ở một frame: Del xoá shape ở frame này, không phải cả mắt
                self._delete_shape_here(label)
            else:
                try:
                    n = self.s.delete_eye(label)
                    self.notice = f"Đã xoá {label} ở {n} frame ghim (Ctrl+Z để hoàn tác). Bấm {self.kl('draw_eye')} để vẽ lại mắt này."
                except ValueError as err:
                    self.notice = str(err)
        self.refresh()

    def _delete_shape_here(self, label: str):
        """Xoá shape của mắt `label` ở frame đang xem (Del và menu "Bỏ keyframe ở frame này" của mắt shape); lỗi của session thành thông báo.
        Người gọi lo kiểm khoá và `refresh`."""
        try:
            self.s.delete_shape(label, self.f)
            self.notice = f"Đã xoá shape {label} ở frame {self.f} (Ctrl+Z để hoàn tác)."
        except ValueError as err:
            self.notice = str(err)

    @edit_command
    def end_label_here(self):
        label = self._sel_eye(need_frame_labels=True)
        if not label:
            return
        try:
            self.s.end_eye_here(label, self.f)
            self.notice = f"{label} kết thúc từ frame {self.f} (8 điểm Outside)."
        except ValueError as err:
            self.notice = str(err)
        self.refresh()

    def toggle_pinned(self):
        """Pinned (như CVAT): mắt Pinned không dời nguyên mắt, không xoay bằng tay cầm hay phím; vẫn sửa từng điểm được."""
        self._cancel_drag()                              # giữa lúc kéo: huỷ kéo (B21), thả chuột sau đó không sửa mắt vừa khoá / ẩn / Pinned
        label = self._sel_eye()
        if not label:
            return
        if label in self.pinned_eyes:
            self.pinned_eyes.discard(label)
            self.notice = f"Đã bỏ Pinned cho {label}."
        else:
            self.pinned_eyes.add(label)
            self.notice = f"{label} đã Pinned: không dời nguyên mắt hay xoay được."
        self.refresh()

    @edit_command
    def swap_labels(self):
        """Đổi label (ô label trên thẻ, menu ⋮): hoán đổi dữ liệu mattrai ↔ matphai của người đang chọn. Ẩn riêng, khoá và Pinned đi theo
        MẮT: `swap_eyes` đổi chỗ mã mắt (`Layer.eye_uid`) cùng dữ liệu trong một bước hoàn tác, nên Ctrl+Z / Ctrl+Y đổi lại cả trạng thái (B08).
        Một trong hai mắt đang khoá thì từ chối: đổi label sẽ ghi đè dữ liệu của mắt khoá.
        Người có mắt shape (I6): như CVAT, đổi label của shape chỉ đổi ở frame đang xem (`Session.swap_shapes_at`, cần cả hai mắt là shape và
        frame có shape của cả hai); một mắt track một mắt shape thì từ chối, không đổi gì. Người chỉ có track: hoán đổi ở mọi frame như cũ."""
        if not self.s or not self.s.pins:
            self.notice = "Chưa có frame ghim để đổi label."
        elif any(l in self.locked for l in EYES):
            self.notice = f"{' và '.join(l for l in EYES if l in self.locked)} đang bị khoá: mở khoá trước khi đổi label."
        elif any(self.s.eye_kind(l) == "shape" for l in EYES):
            try:
                self.s.swap_shapes_at(self.f)
                self.notice = f"Đã đổi label hai shape ở frame {self.f} (mattrai ↔ matphai); các frame khác giữ nguyên."
            except ValueError as err:
                self.notice = str(err)
        else:
            self.s.swap_eyes()
            self.notice = "Đã hoán đổi mattrai và matphai ở mọi frame ghim."
        self.refresh()

    def object_color_next(self):
        """Phím Enter: đổi màu của mắt đang chọn sang màu kế trong bảng màu."""
        label = self._sel_eye()
        if not label:
            return
        cur = (self.look.colors or {}).get(label)
        pal = list(INSTANCE_COLORS)
        nxt = pal[(pal.index(cur) + 1) % len(pal)] if cur in pal else pal[0]
        self.look.colors = {**(self.look.colors or {}), label: nxt}
        self.notice = f"Đã đổi màu {label}."
        self.refresh()

    # ---------- tab Labels ----------
    def _label_dot_color(self, label: str) -> str:
        """Màu chấm của label ở tab Labels = màu mắt `label` của người đang chọn trên ảnh và trên thẻ đối tượng: chỉ số màu là ID đối tượng - 1
        (như `render` và thẻ), không phải thứ tự label (B20); chưa có ID (chưa ghim) thì dùng thứ tự label + 1."""
        n = self.s.object_id(label, self.f) if self.s else None          # mắt shape: ID của shape ở frame này (như thẻ và ảnh)
        b, g, r = self.look.color_of(label, (n or list(EYES).index(label) + 1) - 1)
        return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

    def build_labels_tab(self, tab):
        self.items_labels_var = tk.StringVar(value=f"Items: {len(EYES)}")
        ttk.Label(tab, textvariable=self.items_labels_var).pack(anchor="w", padx=4, pady=(4, 6))
        self._label_btns = {}
        for label in EYES:
            r = tk.Frame(tab, bg=theme.WHITE, highlightthickness=1, highlightbackground=theme.PAPER_LINE)
            r.pack(fill="x", padx=4, pady=2)
            dot = tk.Canvas(r, width=14, height=14, bg=theme.WHITE, highlightthickness=0)
            dot.pack(side="left", padx=(8, 6))
            dot.create_oval(2, 2, 12, 12, fill=self._label_dot_color(label), outline="")
            tk.Label(r, text=label, bg=theme.WHITE, fg=theme.INK).pack(side="left")
            # CVAT label-item: Lock (LockFilled / UnlockOutlined), Hidden (EyeInvisibleFilled / EyeOutlined); tác động mọi người
            lk = IconButton(r, "unlock", lambda b, l=label: self._toggle_label_lock(l), tip="Khoá / mở khoá label (mọi đối tượng)",
                            kind="tool", size=13)
            ey = IconButton(r, "eye", lambda b, l=label: self._toggle_label_visible(l), tip="Ẩn / hiện label (mọi đối tượng)",
                            kind="tool", size=13)
            ey.pack(side="right", padx=2)
            lk.pack(side="right", padx=2)
            self._label_btns[label] = (lk, ey, dot)

    def _n_layers(self) -> int:
        return len(self.s.layers) if self.s else 1

    def _eye_key(self, layer: int, label: str):
        """Khoá lưu ẩn riêng / khoá / Pinned của mắt (người `layer`, `label`): mã ổn định `Layer.eye_uid` của Session, không phải chỉ số người
        (B08–B10). Chưa mở phiên, hay chỉ số không có người, thì dùng chính cặp đó (không trùng với mã nào)."""
        s = self.s
        if s is not None and 0 <= layer < len(s.layers) and label in s.layers[layer].eye_uid:
            return s.layers[layer].eye_uid[label]
        return (layer, label)

    def _toggle_label_lock(self, label: str):
        """Nút Lock ở tab Labels: khoá / mở khoá label cho mọi người (khác nút Lock trên thẻ đối tượng, chỉ một mắt của một người)."""
        n = self._n_layers()
        self.locked.set_all(label, not self.locked.all_have(label, n), n)
        self.refresh()

    def _toggle_label_visible(self, label: str):
        self._layer_vars[label].set(not self.look.eyes[label])
        self.set_layer(label)

    def refresh_labels_tab(self):
        if not hasattr(self, "_label_btns"):
            return
        for label, (lk, ey, dot) in self._label_btns.items():
            locked = self.locked.all_have(label, self._n_layers())
            if lk.name != ("lock" if locked else "unlock"):
                lk.set_icon("lock" if locked else "unlock")
            lk.set_active(locked)
            if ey.name != ("eye" if self.look.eyes[label] else "eye_off"):
                ey.set_icon("eye" if self.look.eyes[label] else "eye_off")
            ey.set_active(not self.look.eyes[label])
            dot.delete("all")
            dot.create_oval(2, 2, 12, 12, fill=self._label_dot_color(label), outline="")

    # ---------- tab Issues ----------
    def build_issues_tab(self, att_tab):
        head = ttk.Frame(att_tab)
        head.pack(fill="x", pady=(2, 3))
        self.issues_var = tk.StringVar(value="Items: 0")
        ttk.Label(head, textvariable=self.issues_var).pack(side="left", padx=4)
        self.show_issues = True
        self._issue_btns = {}
        for name, cmd, tip in (("check", self.issue_resolve, "Đã xử lý: bỏ vấn đề đang chọn khỏi danh sách"),
                               ("eye", self.issue_toggle_show, "Ẩn / hiện vạch vấn đề trên dải thời gian"),
                               ("next", lambda: self.issue_step(1), "Vấn đề kế tiếp"),
                               ("prev", lambda: self.issue_step(-1), "Vấn đề trước")):
            b = self._issue_btns[name] = IconButton(head, name, lambda b, c=cmd: c(), tip=tip, kind="tool", size=13)
            b.pack(side="right", padx=2)
        self._issues_head = head

    def _turn_rows(self) -> list[tuple[int, int, object]]:
        """Các đoạn quay đầu của mọi người: (chỉ số người, số thứ tự đoạn trong người đó từ 1, đoạn), theo người rồi theo frame đầu."""
        return [(i, k, t) for i, rep in enumerate(self.s.turns if self.s else []) for k, t in enumerate(rep.turns, 1)]

    def _turns_signature(self) -> tuple:
        """Mọi trường của mọi đoạn quay đầu (và số người, vì tiền tố "Người N:" phụ thuộc vào đó); () khi không có đoạn nào."""
        rows = tuple(self._turn_rows())
        return (len(self.s.layers), rows) if rows else ()

    def _auto_runs(self) -> list[tuple[int, str, int, int]]:
        """Các đoạn shape điền tự động mà người dùng chưa xem, của mọi người: (chỉ số người, nhãn, frame đầu, frame cuối); mỗi đoạn là các frame
        liền nhau. Frame đã xoá không tính (không còn gì để xem), nên một frame đã xoá giữa chừng cắt đôi đoạn. Xếp theo (frame đầu, người, nhãn)."""
        s = self.s
        out: list[tuple[int, str, int, int]] = []
        for i in range(len(s.layers) if s else 0):
            with s.layer_ctx(i):
                for label in EYES:
                    for f in (f for f in s.unreviewed(label) if f not in s.deleted):
                        if out and out[-1][:2] == (i, label) and out[-1][3] == f - 1:
                            out[-1] = (i, label, out[-1][2], f)
                        else:
                            out.append((i, label, f, f))
        return sorted(out, key=lambda r: (r[2], r[0], r[1]))

    def _issues_signature(self) -> tuple:
        """Mọi thứ làm bảng Issues đổi mà không đi qua `_fill_issues`: đoạn quay đầu, đoạn thiếu nhãn, đoạn shape chưa xem của mọi người, và số
        thứ tự lần tải issue CVAT (Task 8, chưa có thì 0). Vẽ lại chỉ dựng lại bảng khi chữ ký này đổi, để không mất dòng đang chọn."""
        if not self.s:
            return ()
        return (self._turns_signature(), tuple(gaps.find_gaps(self.s)), tuple(self._auto_runs()), getattr(self, "_job_issues_seq", 0))

    def _turn_text(self, i: int, k: int, t) -> str:
        return (f"Người {i + 1}: " if len(self.s.layers) > 1 else "") + t.message(k)

    # Ba mức: (tên, màu chấm). Đỏ/vàng cùng tông với dải thời gian (#DC3C3C, #F0AA28); xanh lá là thông tin, không phải lỗi nhãn.
    ISSUE_LEVELS = {"red": ("Đỏ", "#DC3C3C"), "yellow": ("Vàng", "#F0AA28"), "green": ("Xanh lá", "#3FA535")}
    ISSUE_EMPTY = "Không có frame nào cần chú ý."

    @staticmethod
    def _span(first: int, last: int) -> str:
        return f"{first}" if first == last else f"{first}–{last}"

    def _build_issue_table(self, parent):
        """Bảng vấn đề có cột riêng: chấm màu mức (đỏ/vàng/xanh lá, đứng trước số thứ tự) | # | Frame | Vấn đề. Chỉ chấm là màu, cả dòng nền trắng
        (dòng chọn thì cam); tên mức bằng chữ nằm ở dòng đầu khung chi tiết."""
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        t = self.issue_table = ttk.Treeview(wrap, columns=("n", "frame", "desc"), show="tree headings", selectmode="browse", height=14)
        # Kéo mép tiêu đề để đổi độ rộng cột: minwidth nhỏ thì thu hẹp được; rộng hơn panel thì cuộn ngang. Tổng mặc định vừa panel (~380 px).
        for col, text, w, stretch in (("#0", "", 28, False), ("n", "#", 48, False), ("frame", "Frame", 70, False),
                                      ("desc", "Vấn đề", 200, True)):
            t.heading(col, text=text, anchor="w")
            t.column(col, width=w, minwidth=24, stretch=stretch, anchor="w")
        ybar = ttk.Scrollbar(wrap, orient="vertical", command=t.yview)
        self.issue_xbar = xbar = ttk.Scrollbar(wrap, orient="horizontal", command=t.xview)
        t.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        t.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        self._issue_dots = {}                                    # PhotoImage phải được giữ, không thì Tk xoá hình
        for level, (_, color) in self.ISSUE_LEVELS.items():
            img = tk.PhotoImage(width=12, height=12)
            for y in range(12):
                for x in range(12):
                    if (x - 5.5) ** 2 + (y - 5.5) ** 2 <= 5.2 ** 2:
                        img.put(color, (x, y))
            self._issue_dots[level] = img
        t.bind("<Double-Button-1>", self.on_list)
        t.bind("<<TreeviewSelect>>", self.on_issue_select)

    def _issue_selected(self) -> int | None:
        """Chỉ số (từ 0) của dòng đang chọn trong bảng vấn đề; None nếu chưa chọn hoặc bảng chỉ có dòng "không có vấn đề"."""
        sel = self.issue_table.selection()
        if not sel or not sel[0].isdigit():
            return None
        return int(sel[0])

    def _turn_entry(self, i: int, k: int, t) -> tuple[str, str, str]:
        """(mô tả ngắn, mức, chi tiết) của một đoạn quay đầu. Mức xanh lá: tool tự phát hiện từ điểm ghim, không phải lỗi của nhãn."""
        who = f"Người {i + 1}: " if len(self.s.layers) > 1 else ""
        short = who + "Quay đầu" + (f" {t.level}, co {t.shrink * 100:.0f}%" if t.shrink is not None else ", mất một mắt")
        lines = [who + f"Quay đầu · {self._span(t.first, t.last)} ({t.last - t.first + 1} frame)",
                 f"Mức co: {t.shrink * 100:.0f}% ({t.level})" if t.shrink is not None else "Một mắt biến mất trong đoạn này."]
        if t.far_eye:
            lines.append(f"Mắt xa camera: {t.far_eye}")
        lines.append(f"Xác nhận tại {t.confirmed} frame ghim." if t.confirmed else "Chưa xác nhận bằng frame ghim (có thể là đầu tiến/lùi chứ không quay).")
        for n, what in ((t.unsure, "frame không chắc"), (t.one_eye, "frame chỉ còn một mắt"), (t.need_pin, "frame cần ghim")):
            if n:
                lines.append(f"{n} {what}.")
        lines.append("Cách xử lý: nội suy đường thẳng của CVAT dễ lệch trong đoạn này, nên ghim thêm hoặc chỉnh tay ở các frame cần ghim.")
        return short, "green", "\n".join(lines)

    def _finding_entry(self, fd) -> tuple[str, str, str]:
        """(mô tả ngắn, mức, chi tiết) của một vấn đề do Quét tìm thấy."""
        short = SHORT.get(fd.code) or fd.message[:40]
        n_frames = fd.last - fd.frame + 1
        lines = [f"Frame {self._span(fd.frame, fd.last)}" + (f" ({n_frames} frame)" if n_frames > 1 else "") + f" · mắt {fd.label}",
                 f"Vấn đề: {fd.message}"]
        if fd.points:
            lines.append("Điểm liên quan: " + ", ".join(map(str, fd.points)))
        if HINT.get(fd.code):
            lines.append("Cách xử lý: " + HINT[fd.code])
        return short, fd.level, "\n".join(lines)

    def _gap_entry(self, g: gaps.Gap, many: bool) -> IssueEntry:
        """Dòng "Thiếu nhãn" của một đoạn (mức vàng); mắt chưa có nhãn nào (`first` < 0) không có frame để nhảy tới."""
        who = f"Người {g.layer + 1}: " if many else ""
        if g.first < 0:
            lines = [who + f"Mắt {g.label} chưa có shape nào ở frame nào, trong khi mắt kia đã có.",
                     "Cách xử lý: vẽ một shape của mắt này (phím N), rồi dùng \"Điền đoạn thiếu nhãn\" hoặc \"Chép shape gần nhất vào frame này\" ở menu."]
            return IssueEntry("gap", g, None, None, gaps.gap_text(g, many), "yellow", "\n".join(lines))
        lines = [who + f"Frame {self._span(g.first, g.last)} ({g.count} frame) · mắt {g.label}",
                 "Vấn đề: đoạn này chưa có shape của mắt này (frame đã xoá không tính).",
                 "Cách xử lý: đứng trong đoạn rồi chọn \"Điền đoạn thiếu nhãn\" (bám tiến từ shape ngay trước đoạn) hoặc \"Chép shape gần nhất vào frame này\" "
                 "ở menu; hoặc vẽ tay (phím N)."]
        return IssueEntry("gap", g, g.first, g.last, gaps.gap_text(g, many), "yellow", "\n".join(lines))

    def _auto_entry(self, run: tuple[int, str, int, int], many: bool) -> IssueEntry:
        """Dòng "Điền tự động, chưa xem" của một đoạn shape do tool điền (mức vàng)."""
        layer, label, a, b = run
        n = b - a + 1
        short = (f"người {layer + 1} · " if many else "") + f"Điền tự động, chưa xem {label} · frame {self._span(a, b)} ({n} frame)"
        lines = [(f"Người {layer + 1}: " if many else "") + f"Frame {self._span(a, b)} ({n} frame) · mắt {label}",
                 "Vấn đề: shape do tool điền bằng bám tiến, chưa ai xem lại.",
                 "Cách xử lý: xem từng frame và sửa điểm nếu lệch (sửa một shape thì nó tự ra khỏi danh sách); xem xong thì bấm Đã xử lý để đánh dấu cả đoạn là đã xem."]
        return IssueEntry("auto", run, a, b, short, "yellow", "\n".join(lines))

    def _issue_entries(self) -> list[IssueEntry]:
        """Mọi dòng của tab Issues, tính lại từ trạng thái hiện tại của phiên, theo thứ tự nhóm: đoạn quay đầu (do tool tính từ điểm ghim), vấn đề do
        Quét tìm trong file nhãn, thiếu nhãn, shape điền tự động chưa xem, rồi issue CVAT của job (`cvat_issue_entries`; chưa có thì không có nhóm này).
        `payload`: turn = (người, số thứ tự, đoạn); finding = Finding; gap = Gap; auto = (người, nhãn, frame đầu, frame cuối);
        cvat = (frame hoặc None, chữ ngắn, mức, chi tiết)."""
        s = self.s
        if not s:
            return []
        many = len(s.layers) > 1
        out = [IssueEntry("turn", (i, k, t), t.first, t.last, *self._turn_entry(i, k, t)) for i, k, t in self._turn_rows()]
        out += [IssueEntry("finding", fd, fd.frame, fd.last, *self._finding_entry(fd)) for fd in s.findings]
        out += [self._gap_entry(g, many) for g in gaps.find_gaps(s)]
        out += [self._auto_entry(run, many) for run in self._auto_runs()]
        cvat = getattr(self, "cvat_issue_entries", None)
        for frame, short, level, detail in (cvat() if cvat else []):
            out.append(IssueEntry("cvat", (frame, short, level, detail), frame, frame, short, level, detail))
        return out

    def _fill_issues(self):
        """Danh sách vấn đề (thứ tự nhóm: xem `_issue_entries`). Mỗi dòng có cột riêng: chấm màu, #, Frame, mô tả ngắn; bấm vào dòng thì khung dưới hiện
        chi tiết. `issue_rows` giữ (loại, dữ liệu) của từng dòng, `items` giữ frame để nhảy tới (None: dòng không có frame)."""
        entries = self._issue_entries()
        self.issue_rows = [(e.kind, e.payload) for e in entries]
        self.items = [e.first for e in entries]
        self.issue_info = []                                  # chi tiết của từng dòng, hiện khi chọn dòng
        tab = self.issue_table
        tab.delete(*tab.get_children())
        for n, e in enumerate(entries, 1):
            name = self.ISSUE_LEVELS[e.level][0]
            span = "" if e.first is None else self._span(e.first, e.last)
            tab.insert("", "end", iid=str(n - 1), image=self._issue_dots[e.level], values=(f"#{n}", span, e.short))
            self.issue_info.append(f"#{n} · Mức: {name}\n{e.detail}")
        if not entries:
            tab.insert("", "end", iid="empty", values=("", "", self.ISSUE_EMPTY))
            self.issue_info.append("")
        self.issue_detail.config(text="Bấm một dòng để xem chi tiết; bấm đúp để nhảy tới frame.")
        self.issues_var.set(f"Items: {len(entries)}")
        self._issues_sig = self._issues_signature()

    def on_issue_select(self, _):
        """Bấm một dòng trong Issues: hiện chi tiết ở bảng bên dưới danh sách (không nhảy frame; đúp mới nhảy)."""
        i = self._issue_selected()
        if i is not None and i < len(self.issue_info):
            self.issue_detail.config(text=self.issue_info[i])

    def issue_step(self, step: int):
        """Nhảy tới vấn đề kế (step > 0) hoặc trước (step < 0) so với frame đang xem; tính mọi dòng có frame (quay đầu, vấn đề của Quét, thiếu nhãn, shape
        điền tự động chưa xem, issue CVAT). Dòng không có frame (mắt chưa có nhãn nào, issue ngoài job) bị bỏ qua."""
        entries = sorted((e for e in self._issue_entries() if e.first is not None), key=lambda e: e.first)
        cand = [e for e in entries if (e.first > self.f if step > 0 else e.first < self.f)]
        if not cand:
            self.notice = "Không còn vấn đề nào theo hướng này. Bấm Quét để tìm vấn đề."
            self.refresh()
            return
        e = cand[0] if step > 0 else cand[-1]
        self.go(e.first)
        self.notice = f"Vấn đề: {e.payload.message}" if e.kind == "finding" else self._turn_text(*e.payload) if e.kind == "turn" else e.short
        self.refresh(light=True)

    def issue_toggle_show(self):
        self.show_issues = not self.show_issues
        self._issue_btns["eye"].set_icon("eye" if self.show_issues else "eye_off")
        self.refresh()

    def issue_resolve(self):
        """Nút Đã xử lý: bỏ vấn đề của Quét khỏi danh sách; đánh dấu cả đoạn "Điền tự động, chưa xem" là đã xem. Các dòng khác (quay đầu, thiếu nhãn,
        issue CVAT) không bỏ được bằng nút này: mỗi loại tự hết khi nguyên nhân hết."""
        sel = self._issue_selected()
        if not (self.s and sel is not None and sel < len(self.issue_rows)):
            self.notice = "Chọn một vấn đề trong danh sách trước."
            self.refresh()
            return
        kind, payload = self.issue_rows[sel]
        if kind == "turn":
            self.notice = "Đoạn quay đầu không bỏ được: nó được tính lại từ điểm ghim."
        elif kind == "finding":
            self.s.findings[:] = [fd for fd in self.s.findings if fd is not payload]
            self._fill_issues()
            self.notice = f"Đã xử lý: {payload.label} frame {payload.frame}."
        elif kind == "auto":
            layer, label, a, b = payload
            if layer != self.s.cur and layer < len(self.s.layers):
                self.s.select_layer(layer)                    # đánh dấu theo người của dòng, như `_selected` chọn người của thẻ
            frames = [f for f in self.s.unreviewed(label) if a <= f <= b]
            self.s.mark_reviewed(label, frames)
            self._fill_issues()
            self.notice = f"Đã đánh dấu đã xem {len(frames)} shape điền tự động."
        else:
            self.notice = "Dòng này không bỏ được bằng Đã xử lý."
        self.refresh()

    # ---------- lệnh tạo shape (menu trên; chỉ mắt kiểu shape) ----------
    def _selected_gap(self) -> gaps.Gap | None:
        """Đoạn của dòng "Thiếu nhãn" đang chọn trong tab Issues; None khi chưa chọn dòng nào hoặc dòng chọn thuộc loại khác."""
        i = self._issue_selected()
        if i is None or i >= len(self.issue_rows):
            return None
        kind, payload = self.issue_rows[i]
        return payload if kind == "gap" else None

    def _shape_command_ok(self) -> bool:
        """Điều kiện chung của lệnh chép và điền: có phiên, frame đang xem chưa bị xoá, và người đang chọn có ít nhất một mắt kiểu shape. Không đủ thì
        đặt thông báo và trả False."""
        s = self.s
        if not s:
            return False
        if self.f in s.deleted:
            self.notice = "Frame này đã bị xoá."
        elif not any(s.eye_kind(l) == "shape" for l in EYES):
            self.notice = SHAPE_ONLY_MSG
        else:
            return True
        self.refresh(light=True)
        return False

    def _missing_shape_eye(self) -> str | None:
        """Mắt mà lệnh chép và điền tác động ở frame đang xem: trong các mắt kiểu shape của người đang chọn mà KHÔNG có shape ở frame này, lấy mắt đang
        chọn trong panel nếu nó nằm trong số đó, không thì mắt duy nhất còn thiếu, không thì (cả hai cùng thiếu) mattrai. Thẻ của mắt shape chỉ hiện ở
        frame có shape, nên ở frame thiếu thường không chọn được mắt đang thiếu. None khi không mắt nào thiếu."""
        s = self.s
        missing = [l for l in EYES if s.eye_kind(l) == "shape" and not s.has_shape(l, self.f)]
        if not missing:
            return None
        chosen = self._selected()[0]
        return chosen if chosen in missing else "mattrai" if "mattrai" in missing else missing[0]

    @edit_command
    def copy_nearest_shape(self):
        """Menu "Chép shape gần nhất vào frame này": chép shape gần nhất của mắt đang thiếu (`_missing_shape_eye`) sang frame đang xem."""
        if not self._shape_command_ok():
            return
        label = self._missing_shape_eye()
        if label is None:
            self.notice = "Frame này đã có shape của cả hai mắt."
            self.refresh(light=True)
            return
        try:
            src = self.s.copy_nearest_shape(label, self.f)
        except ValueError as err:
            if str(err) == QC_MSG:
                raise
            self.notice = str(err)
            self.refresh(light=True)
            return
        self.notice = f"Đã chép shape {label} từ frame {src} sang frame {self.f}."
        self.refresh()

    @edit_command
    def fill_gap_here(self):
        """Menu "Điền đoạn thiếu nhãn": điền bằng bám tiến đoạn của dòng "Thiếu nhãn" đang chọn (dòng của người khác thì chọn người đó trước); không có
        dòng đó thì đoạn thiếu chứa frame đang xem của mắt đang thiếu (`_missing_shape_eye`)."""
        s = self.s
        if not s:
            return
        gap = self._selected_gap()
        if gap is not None and gap.layer != s.cur and gap.layer < len(s.layers):
            s.select_layer(gap.layer)
        if not self._shape_command_ok():
            return
        if gap is None:
            label = self._missing_shape_eye()
            gap = gaps.gap_at(s, label, self.f) if label else None
            if gap is None:
                self.notice = "Đứng trong một đoạn thiếu nhãn (hoặc chọn dòng Thiếu nhãn) rồi điền."
                self.refresh(light=True)
                return
        elif gap.first < 0:
            self.notice = f"{gap.label} chưa có nhãn nào: vẽ một shape của mắt đó trước rồi mới điền được."
            self.refresh(light=True)
            return
        was_stale = s.stale
        try:
            res = s.fill_gap(gap.label, gap.first, gap.last)
        except ValueError as err:
            if str(err) == QC_MSG:
                raise
            self.notice = str(err)
            self.refresh(light=True)
            return
        except CvatError as err:
            if s.stale and not was_stale:
                raise                                         # shape đã ghi, chỉ bước tính lại lỗi: `edit_command` báo như mọi lệnh sửa khác
            self.notice = f"Không điền được: {err} Chưa tạo shape nào."
            self.refresh(light=True)
            return
        n = len(res.created)
        if res.stopped_at is None:
            self.notice = f"Đã điền đủ {n} frame." if n else "Đoạn này không còn frame nào thiếu."
        elif n:
            self.notice = (f"Đã tạo {n} shape (frame {self._span(res.created[0], res.created[-1])}); "
                           f"dừng ở frame {res.stopped_at} vì khớp kém ({res.score:.2f}).")
        else:
            self.notice = f"Không tạo được shape nào: khớp kém ở frame {res.stopped_at} ({res.score:.2f})."
        self.refresh()
