"""Menu, thao tác với frame và phóng vào đối tượng của EyePin (phần mở rộng của `App`, tách khỏi gui.py).

Mô phỏng các mục của CVAT 2.75 (xem design/cvat-parity.md): Remove annotations, Run actions, Finish the job, tên frame kèm sao chép tên và
đường dẫn, xoá frame và Show deleted frames, tìm frame theo tên, focused object padding, hệ số zoom.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import theme
from .geometry import EYES
from .gui_cvat import edit_command, net_safe
from .icons import IconButton
from .render import View


class FramesMixin:
    # ---------- hàng tên frame (dưới thanh trên) ----------
    def _build_name_row(self):
        row = tk.Frame(self.root, bg=theme.ORANGE)
        row.pack(fill="x", pady=(0, 4), after=self._top_bar)
        self.name_var = tk.StringVar(value="")
        tk.Label(row, textvariable=self.name_var, bg=theme.ORANGE, fg=theme.INK, font=(theme.FONT, 10, "bold")).pack(side="left", padx=(10, 6))
        for name, cmd, tip in (("copy", self.copy_frame_name, "Sao chép tên frame"),
                               ("link", self.copy_frame_path, "Sao chép đường dẫn frame"),
                               ("trash", self.toggle_delete_frame, f"Xoá / khôi phục frame ({self.kl('delete_frame')})"),
                               ("search", self.search_frame_by_name, f"Tìm frame theo tên ({self.kl('search_frame')})")):
            IconButton(row, name, lambda b, c=cmd: c(), tip=tip, kind="bar", size=12).pack(side="left", padx=1)
        self._name_row = row

    def update_name_row(self):
        if not self.s:
            self.name_var.set("")
            return
        gone = " (đã xoá)" if self.f in self.s.deleted else ""
        self.name_var.set(f"{self.s.names[self.f]}{gone}")

    def copy_frame_name(self):
        if self.s:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.s.names[self.f])
            self.notice = f"Đã sao chép tên frame: {self.s.names[self.f]}"
            self.refresh(light=True)

    def copy_frame_path(self):
        if self.s:
            path = os.path.join(self.s.frames_dir or self.s.title, self.s.names[self.f])
            self.root.clipboard_clear()
            self.root.clipboard_append(path)
            self.notice = f"Đã sao chép đường dẫn: {path}"
            self.refresh(light=True)

    def toggle_delete_frame(self):
        """Xoá frame (đánh dấu, khôi phục được): frame bị xoá bị bỏ qua khi điều hướng trừ khi bật 'Hiện frame đã xoá' trong Cài đặt."""
        if not self.s:
            return
        if self.s.cvat is not None:                              # xoá bằng import không đưa lên CVAT được; frame đã xoá từ CVAT chỉ đọc
            self.notice = ("Job CVAT: EyePin không xoá hay khôi phục frame (import không đưa việc đó lên CVAT được). "
                           "Frame đã xoá trên CVAT chỉ đọc; muốn đổi thì làm trên CVAT.")
            self.refresh(light=True)
            return
        if self.f in self.s.deleted:
            self.s.restore_frame(self.f)
            self.notice = f"Đã khôi phục frame {self.f}."
        else:
            self.s.delete_frame(self.f)
            self.notice = f"Đã xoá frame {self.f} (bấm lại để khôi phục)."
        self.refresh()

    def search_frame_by_name(self, text: str | None = None):
        if not self.s:
            return
        if text is None:
            text = simpledialog.askstring("Tìm frame", "Tên frame chứa:", parent=self.root)
        if not text:
            return
        key = text.lower()
        hit = next((i for i, n in enumerate(self.s.names) if key in n.lower()), None)
        if hit is None:
            self.notice = f"Không có frame nào có tên chứa '{text}'."
            self.refresh()
        else:
            self.go(hit)

    # ---------- Menu: Remove annotations, Run actions, Finish the job ----------
    @edit_command
    def remove_annotations(self, confirmed: bool | None = None):
        if not self.s:
            return
        n = len(self.s.pins)
        if not n:
            self.notice = "Chưa có nhãn nào để xoá."
            self.refresh()
            return
        if confirmed is None:
            confirmed = messagebox.askyesno("Remove annotations", f"Xoá toàn bộ {n} frame ghim, cờ Occluded/Outside? Bấm Ctrl+Z để hoàn tác.", parent=self.root)
        if confirmed:
            self.s.clear_all()
            self.notice = f"Đã xoá {n} frame ghim (Ctrl+Z để hoàn tác)."
            self.refresh()

    ACTIONS = (("Quét nhãn có sẵn (đỏ, vàng, EAR)", "scan"), ("Nhân nhãn frame này sang N frame sau", "propagate"),
               ("Xoá mọi keyframe sau frame này", "clear_after"), ("Hoán đổi mattrai và matphai", "swap"),
               ("Khoá / mở khoá tất cả", "lock_all"), ("Xoá toàn bộ nhãn (Remove annotations)", "remove_all"))

    def show_run_actions(self):
        """Hộp Run actions (Ctrl+E trong CVAT): chọn một hành động rồi bấm Chạy."""
        d, new = self._toplevel("actions", "Chạy hành động")
        if not new:
            return
        ttk.Label(d, text="Chọn hành động:").pack(anchor="w", padx=12, pady=(10, 4))
        lb = tk.Listbox(d, height=len(self.ACTIONS), width=48, exportselection=False)
        for text, _ in self.ACTIONS:
            lb.insert("end", text)
        lb.selection_set(0)
        lb.pack(padx=12, pady=4)

        def run():
            sel = lb.curselection()
            if sel:
                d.destroy()
                self.run_action(self.ACTIONS[sel[0]][1])
        ttk.Button(d, text="Chạy", command=run).pack(pady=(4, 10))
        lb.bind("<Double-Button-1>", lambda e: run())
        d.bind("<Return>", lambda e: run())
        d.bind("<Escape>", lambda e: d.destroy())

    @net_safe
    def run_action(self, name: str):
        if not self.s:
            return
        if name in ("clear_after", "propagate", "swap", "remove_all") and self._edit_blocked():     # QC hoặc đang có việc nền
            return
        if name == "scan":
            self.scan()
        elif name == "propagate":
            if not self._selected()[0]:
                self.select_eye(next(iter(EYES)), quiet=True)           # Propagate cần một mắt đang chọn: lấy mắt đầu
            self.object_propagate()
        elif name == "clear_after":
            later = [g for g in self.s.pins if g > self.f]
            if later:
                self.s._push_undo()
                for g in later:
                    self.s.pins.pop(g, None)
                    self.s.flags.pop(g, None)
                    self.s.estimates.pop(g, None)
                self.s.recompute()
            self.notice = f"Đã xoá {len(later)} keyframe sau frame {self.f}."
            self.refresh()
        elif name == "swap":
            self.swap_labels()
        elif name == "lock_all":
            self.toggle_lock_all()
        elif name == "remove_all":
            self.remove_annotations()

    def finish_job(self, export: bool | None = None):
        """Finish the job: lưu phiên rồi mời xuất file import (nơi CVAT sẽ import)."""
        if not self.s:
            return
        self.save_work()
        if export is None:
            export = messagebox.askyesno("Hoàn tất job", "Đã lưu phiên. Xuất file import cho CVAT ngay bây giờ?", parent=self.root)
        if export:
            self.export()

    # ---------- phóng vào đối tượng, hệ số zoom ----------
    def zoom_step(self) -> float:
        try:
            return max(1.05, float(self.settings["workspace"].get("zoom_step", 1.25)))
        except (TypeError, ValueError):
            return 1.25

    def focus_object(self):
        """Phóng vào mắt đang chọn với phần đệm (pixel màn hình) lấy từ Cài đặt, giống Focused object padding của CVAT."""
        label = self._sel_eye(need_frame_labels=True) if hasattr(self, "_sel_eye") else None
        if not label:
            return
        pts = self._eye_points(label)
        x0, y0, x1, y1 = self._bbox(pts)
        pad = float(self.settings["workspace"].get("focus_padding", 60))
        w, h = self.render_size
        k = min((w - 2 * pad) / max(x1 - x0, 1), (h - 2 * pad) / max(y1 - y0, 1))
        k = max(0.2, min(40.0, k))
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        self.manual = View(cx - w / (2 * k), cy - h / (2 * k), k, w, h)
        self.notice = f"Đã phóng vào {label}."
        self.refresh()
