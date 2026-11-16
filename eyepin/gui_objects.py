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

class LayerSet:
    """Tập nhãn mắt riêng cho từng bộ đối tượng (người): `label in s` chỉ nói về bộ đang chọn, nên khoá hay Pinned của người này không
    ảnh hưởng người kia. Dùng như `set` thông thường trên bộ đang chọn."""

    def __init__(self, cur):
        self._cur, self._d = cur, {}

    def _s(self) -> set:
        return self._d.setdefault(self._cur(), set())

    def __contains__(self, x):
        return x in self._s()

    def __iter__(self):
        return iter(sorted(self._s()))

    def __len__(self):
        return len(self._s())

    def __bool__(self):
        return bool(self._s())

    def __eq__(self, other):
        return self._s() == set(other)

    def add(self, x):
        self._s().add(x)

    def discard(self, x):
        self._s().discard(x)

    def clear(self):
        self._s().clear()

    def update(self, xs):
        self._s().update(xs)


SORTS = ("ID - tăng dần", "ID - giảm dần", "Tên label", "Cập nhật gần nhất")


class ObjectsMixin:
    # ---------- khởi dựng ----------
    def _objects_extras(self, obj_tab, nav, row):
        """Thêm đầu panel (Items, Sort by, khoá/ẩn/thu gọn tất cả), nút ⋮ và menu chuột phải cho panel Đối tượng."""
        head = ttk.Frame(obj_tab)
        head.pack(fill="x", pady=(0, 3), before=self.tree)
        self.items_var = tk.StringVar(value="Items: 0")
        ttk.Label(head, textvariable=self.items_var).pack(side="left")
        self.sort_var = tk.StringVar(value=SORTS[0])
        cb = ttk.Combobox(head, textvariable=self.sort_var, values=SORTS, state="readonly", width=17)
        cb.pack(side="right")
        ttk.Label(head, text="Sort by", style="Muted.TLabel").pack(side="right", padx=(0, 4))
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh(light=False))
        bar = ttk.Frame(obj_tab)
        bar.pack(fill="x", pady=(0, 3), before=self.tree)
        for name, cmd, tip in (("add", self.new_object, f"Đối tượng mới (người mới), ID mới ({self.kl('new_object')})"),
                               ("lock", self.toggle_lock_all, f"Khoá / mở khoá tất cả ({self.kl('lock_all')})"),
                               ("eye", self.hide_all_eyes, "Ẩn / hiện cả hai mắt"),
                               ("collapse", self.collapse_all, "Thu gọn / mở rộng danh sách"),
                               ("trash", self.delete_label, f"Xoá mắt đang chọn ({self.kl('delete')}); Ctrl+Z hoàn tác")):
            IconButton(bar, name, lambda b, c=cmd: c(), tip=tip, kind="tool").pack(side="left", padx=2)
        self.pinned_eyes = LayerSet(lambda: self.s.cur if self.s else 0)
        self._build_obj_menu()
        IconButton(nav, "more", lambda b: self.popup_obj_menu(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height()),
                   tip="Menu của đối tượng (cũng bấm chuột phải vào dòng)", kind="tool").pack(side="right", padx=2)
        IconButton(nav, "pinned", lambda b: self.toggle_pinned(), tip=f"Pinned: không dời nguyên mắt hay xoay ({self.kl('pinned')})",
                   kind="tool").pack(side="right", padx=2)
        self.tree.bind("<Button-3>", self._tree_right_click, add="+")
        self.tree.bind("<Double-Button-1>", lambda e: self.focus_object(), add="+")

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
        label, _ = self._selected()
        self._pinned_var.set(label in self.pinned_eyes if label else False)
        self.obj_menu.tk_popup(x, y)

    def _tree_right_click(self, e):
        iid = self.tree.identify_row(e.y)
        if iid:
            self.tree.selection_set(iid)
        self.popup_obj_menu(e.x_root, e.y_root)
        return "break"

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
        if not self.tree.get_children():
            return
        open_any = any(self.tree.item(i, "open") for i in self.tree.get_children())
        for i in self.tree.get_children():
            self.tree.item(i, open=not open_any)

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
        Như CVAT: mắt đang có con trỏ chuột trỏ vào được xoá trước; không trỏ vào mắt nào thì xoá mắt đang chọn trong panel."""
        label = self._eye_at(self.hover) if self.s and self.hover and self.view else None
        label = label or self._sel_eye()
        if not label:
            return
        if label in self.locked and not force:
            self.notice = f"{label} đang bị khoá; bấm Shift+Del để xoá cả mắt khoá."
        else:
            try:
                n = self.s.delete_eye(label)
                self.locked.discard(label)
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
        if not self.s or not self.s.pins:
            self.notice = "Chưa có frame ghim để đổi label."
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
    def build_labels_tab(self, tab):
        self.items_labels_var = tk.StringVar(value=f"Items: {len(EYES)}")
        ttk.Label(tab, textvariable=self.items_labels_var).pack(anchor="w", padx=4, pady=(4, 6))
        self._label_btns = {}
        for label in EYES:
            r = tk.Frame(tab, bg=theme.WHITE, highlightthickness=1, highlightbackground=theme.PAPER_LINE)
            r.pack(fill="x", padx=4, pady=2)
            dot = tk.Canvas(r, width=14, height=14, bg=theme.WHITE, highlightthickness=0)
            dot.pack(side="left", padx=(8, 6))
            dot.create_oval(2, 2, 12, 12, fill="#%02x%02x%02x" % tuple(reversed(self.look.color_of(label, list(EYES).index(label)))), outline="")
            tk.Label(r, text=label, bg=theme.WHITE, fg=theme.INK).pack(side="left")
            lk = IconButton(r, "lock", lambda b, l=label: self._toggle_label_lock(l), tip="Khoá / mở khoá label", kind="tool", size=13)
            ey = IconButton(r, "eye", lambda b, l=label: self._toggle_label_visible(l), tip="Ẩn / hiện label", kind="tool", size=13)
            ey.pack(side="right", padx=2)
            lk.pack(side="right", padx=2)
            self._label_btns[label] = (lk, ey, dot)

    def _toggle_label_lock(self, label: str):
        if label in self.locked:
            self.locked.discard(label)
        else:
            self.locked.add(label)
        self.refresh()

    def _toggle_label_visible(self, label: str):
        self._layer_vars[label].set(not self.look.eyes[label])
        self.set_layer(label)

    def refresh_labels_tab(self):
        if not hasattr(self, "_label_btns"):
            return
        for label, (lk, ey, dot) in self._label_btns.items():
            lk.set_active(label in self.locked)
            ey.set_icon("eye" if self.look.eyes[label] else "eye_off")
            ey.set_active(not self.look.eyes[label])
            dot.delete("all")
            dot.create_oval(2, 2, 12, 12, fill="#%02x%02x%02x" % tuple(reversed(self.look.color_of(label, list(EYES).index(label)))), outline="")

    # ---------- tab Issues ----------
    def build_issues_tab(self, att_tab):
        head = ttk.Frame(att_tab)
        head.pack(fill="x", pady=(2, 3))
        self.issues_var = tk.StringVar(value="Items: 0")
        ttk.Label(head, textvariable=self.issues_var).pack(side="left", padx=4)
        self.show_issues = True
        for name, cmd, tip in (("check", self.issue_resolve, "Đã xử lý: bỏ vấn đề đang chọn khỏi danh sách"),
                               ("eye", self.issue_toggle_show, "Ẩn / hiện vạch vấn đề trên dải thời gian"),
                               ("next", lambda: self.issue_step(1), "Vấn đề kế tiếp"),
                               ("prev", lambda: self.issue_step(-1), "Vấn đề trước")):
            IconButton(head, name, lambda b, c=cmd: c(), tip=tip, kind="tool", size=13).pack(side="right", padx=2)
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

    def _fill_issues(self):
        """Danh sách vấn đề: đoạn quay đầu (do tool tính từ điểm ghim) đứng trước, rồi các vấn đề do Quét tìm trong file nhãn."""
        found = self.s.findings if self.s else []
        rows = self._turn_rows()
        self.items = [t.first for _, _, t in rows] + [fd.frame for fd in found]
        self.listbox.delete(0, "end")
        for i, k, t in rows:
            self.listbox.insert("end", self._turn_text(i, k, t))
        for fd in found:
            rng = f"{fd.frame}" if fd.frame == fd.last else f"{fd.frame}-{fd.last}"
            self.listbox.insert("end", f"{'ĐỎ ' if fd.level == 'red' else 'VÀNG'} {rng:>9}  {fd.label}  {fd.message}")
        if not found and not rows:
            self.listbox.insert("end", "Không có frame nào cần chú ý.")
        self.issues_var.set(f"Items: {len(found) + len(rows)}")
        self._turns_sig = self._turns_signature()

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
        self.refresh()

    def issue_resolve(self):
        sel = self.listbox.curselection()
        n_turns = len(self._turn_rows())
        if self.s and sel and sel[0] < n_turns:
            self.notice = "Đoạn quay đầu không bỏ được: nó được tính lại từ điểm ghim."
            self.refresh()
            return
        if not (self.s and sel and sel[0] - n_turns < len(self.s.findings)):
            self.notice = "Chọn một vấn đề trong danh sách trước."
            self.refresh()
            return
        fd = self.s.findings.pop(sel[0] - n_turns)
        self._fill_issues()
        self.notice = f"Đã xử lý: {fd.label} frame {fd.frame}."
        self.refresh()
