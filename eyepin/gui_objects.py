"""Panel Đối tượng, tab Labels và tab Issues của EyePin (phần mở rộng của `App`, tách khỏi gui.py cho gọn).

Mô phỏng thẻ đối tượng của CVAT 2.75 (đã khảo sát trên CVAT local, xem design/cvat-parity.md): Sort by, khoá tất cả / ẩn tất cả,
menu ⋮ (Make a copy, Propagate, đổi lớp, Remove, Create object URL, Run annotation action), Pinned, đổi label, đổi màu (Enter),
tab Labels (khoá và ẩn theo label), tab Issues (đếm, trước/sau, ẩn, đã xử lý).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import theme
from .geometry import EYES
from .gui_cvat import edit_command
from .icons import IconButton
from .render import INSTANCE_COLORS
from .scan import HINT, SHORT

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
        """Các dòng của panel: (chỉ số bộ đối tượng, nhãn mắt), theo cách sắp xếp đang chọn. Bộ đầu luôn hiện cả hai mắt (kể cả mắt đã xoá),
        các bộ khác chỉ hiện mắt đang có."""
        s = self.s
        rows = [(0, l) for l in EYES] + [(i, l) for i, L in enumerate(s.layers) if i > 0 for l in EYES if l in L.obj_ids]
        mode = self.sort_var.get() if hasattr(self, "sort_var") else SORTS[0]
        key_id = lambda r: s.layers[r[0]].obj_ids.get(r[1], 10 ** 9 + r[0] * 10 + list(EYES).index(r[1]))
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
            n = self.s.propagate(self.f, count or 0, direction, start, end)
            where = f"frame {start}–{end}" if start is not None else ("các frame sau" if direction >= 0 else "các frame trước")
            self.notice = f"Đã nhân nhãn sang {n} frame ({where}); mỗi frame thành frame ghim."
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
        if not self._sel_eye():
            return
        if self.f in self.s.pins:
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
            try:
                n = self.s.delete_eye(label)
                self.notice = f"Đã xoá {label} ở {n} frame ghim (Ctrl+Z để hoàn tác). Bấm {self.kl('draw_eye')} để vẽ lại mắt này."
            except ValueError as err:
                self.notice = str(err)
        self.refresh()

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
        Một trong hai mắt đang khoá thì từ chối: đổi label sẽ ghi đè dữ liệu của mắt khoá."""
        if not self.s or not self.s.pins:
            self.notice = "Chưa có frame ghim để đổi label."
        elif any(l in self.locked for l in EYES):
            self.notice = f"{' và '.join(l for l in EYES if l in self.locked)} đang bị khoá: mở khoá trước khi đổi label."
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
        n = self.s.obj_ids.get(label) if self.s else None
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

    def _fill_issues(self):
        """Danh sách vấn đề: đoạn quay đầu (do tool tính từ điểm ghim) đứng trước, rồi các vấn đề do Quét tìm trong file nhãn.
        Mỗi dòng có cột riêng: chấm màu, #, Frame, mô tả ngắn, Mức; bấm vào dòng thì khung dưới hiện chi tiết."""
        found = self.s.findings if self.s else []
        rows = self._turn_rows()
        self.items = [t.first for _, _, t in rows] + [fd.frame for fd in found]
        self.issue_info = []                                  # chi tiết của từng dòng, hiện khi chọn dòng
        tab = self.issue_table
        tab.delete(*tab.get_children())
        entries = [(t.first, t.last, *self._turn_entry(i, k, t)) for i, k, t in rows]
        entries += [(fd.frame, fd.last, *self._finding_entry(fd)) for fd in found]
        for n, (first, last, short, level, detail) in enumerate(entries, 1):
            name = self.ISSUE_LEVELS[level][0]
            tab.insert("", "end", iid=str(n - 1), image=self._issue_dots[level], values=(f"#{n}", self._span(first, last), short))
            self.issue_info.append(f"#{n} · Mức: {name}\n{detail}")
        if not entries:
            tab.insert("", "end", iid="empty", values=("", "", self.ISSUE_EMPTY))
            self.issue_info.append("")
        self.issue_detail.config(text="Bấm một dòng để xem chi tiết; bấm đúp để nhảy tới frame.")
        self.issues_var.set(f"Items: {len(entries)}")
        self._turns_sig = self._turns_signature()

    def on_issue_select(self, _):
        """Bấm một dòng trong Issues: hiện chi tiết ở bảng bên dưới danh sách (không nhảy frame; đúp mới nhảy)."""
        i = self._issue_selected()
        if i is not None and i < len(self.issue_info):
            self.issue_detail.config(text=self.issue_info[i])

    def issue_step(self, step: int):
        """Nhảy tới vấn đề kế (step > 0) hoặc trước (step < 0) so với frame đang xem; tính cả đoạn quay đầu."""
        found = [(fd.frame, f"Vấn đề: {fd.message}") for fd in (self.s.findings if self.s else [])]
        found += [(t.first, self._turn_text(i, k, t)) for i, k, t in self._turn_rows()]
        found.sort(key=lambda p: p[0])
        cand = [p for p in found if (p[0] > self.f if step > 0 else p[0] < self.f)]
        if not cand:
            self.notice = "Không còn vấn đề nào theo hướng này. Bấm Quét để tìm vấn đề."
            self.refresh()
            return
        frame, text = cand[0] if step > 0 else cand[-1]
        self.go(frame)
        self.notice = text
        self.refresh(light=True)

    def issue_toggle_show(self):
        self.show_issues = not self.show_issues
        self._issue_btns["eye"].set_icon("eye" if self.show_issues else "eye_off")
        self.refresh()

    def issue_resolve(self):
        sel = self._issue_selected()
        n_turns = len(self._turn_rows())
        if self.s and sel is not None and sel < n_turns:
            self.notice = "Đoạn quay đầu không bỏ được: nó được tính lại từ điểm ghim."
            self.refresh()
            return
        if not (self.s and sel is not None and sel - n_turns < len(self.s.findings)):
            self.notice = "Chọn một vấn đề trong danh sách trước."
            self.refresh()
            return
        fd = self.s.findings.pop(sel - n_turns)
        self._fill_issues()
        self.notice = f"Đã xử lý: {fd.label} frame {fd.frame}."
        self.refresh()
