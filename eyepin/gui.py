"""Cửa sổ EyePin (Tkinter). Mỏng: mọi tính toán nằm trong Session, mọi phần vẽ nằm trong render.

Thanh điều hướng:  |<  <<  <  [ số frame ]  / N  >  >>  >|   ▶   ghim<  >ghim     (số frame tính từ 0, như id frame trong file nhãn)
  trong ô số frame: Enter nhảy tới frame đó, ↑/↓ đổi ±1 frame.

Phím (theo thói quen của CVAT khi có thể):
  ←/→ hoặc D/F  frame trước/sau (Shift: ±10) · Home/End  frame đầu/cuối · Space  phát/dừng
  H  ẩn/hiện nhãn · C/V  frame ghim trước/sau · K  ghim frame hiện tại từ nhãn tool đã tính (bấm lại để bỏ ghim) · Delete  bỏ frame ghim
  P  ghim 4 điểm mỗi mắt (bấm 8 điểm, thứ tự tuỳ ý) · G  ghim khi một khoé bị che (bấm 7 điểm: 4 điểm mắt đủ + 3 điểm mắt bị che khoé)
  Q  bật/tắt Occluded cho điểm đang trỏ chuột · O  bật/tắt Outside · Ctrl+Z / Ctrl+Y  hoàn tác / làm lại · Esc  huỷ ghim dở
  cuộn chuột hoặc +/−  phóng to thu nhỏ · kéo chuột (trái vào chỗ trống, giữa hoặc phải)  dời ảnh · 0  về khung tự động · I  ẩn hiện số điểm
  S  quét · E  xuất file import
"""
from __future__ import annotations

import hashlib
import math
from contextlib import contextmanager
import json
import os

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from .geometry import EYES, MATTRAI, assign_roles, assign_three, derive, four_in_box
from .render import (PIN_IDS, Look, RESIZE_HIT, ROTATE_DIST, ROTATE_HIT, draw_overlay, make_view, max_shift, render_base, render_main,
                     render_thumb, render_timeline, resize_handles, status_text)
from . import imagefx
from . import shortcuts as sc
from . import theme
from .cvatapi import CvatError
from .gui_cvat import CvatMixin, edit_command, net_safe
from .gui_frames import FramesMixin
from .gui_objects import LayerSet, ObjectsMixin
from .icons import IconButton, Tooltip
from .session import Session

MAIN = (960, 460)
THUMB = (300, 140)
PIN_SEQ = [(label, pid) for label, spec in EYES.items() for pid in spec.pins]       # 8 điểm (chỉ dùng để đếm và cho test)
PIN_COUNT = {"full": 8, "hidden": 7, "one": 4, "draw4": 4}
DRAW_LABELS = {"mattrai": "mattrai (mắt trái)", "matphai": "matphai (mắt phải)"}
DISPLAY_KEYS = ("size", "opacity", "brightness", "contrast", "saturation", "gamma", "grid", "grid_size", "grid_color", "grid_opacity", "axis_guide", "top", "outline", "points", "ids", "selected_opacity", "color_by",
                "outlined")


def to_photo(bgr):
    return ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))


def _hex(bgr) -> str:
    return "#%02x%02x%02x" % (int(bgr[2]), int(bgr[1]), int(bgr[0]))


class CanvasPainter:
    """Bút vẽ ra đối tượng vector của Canvas (như CVAT vẽ nhãn bằng SVG đè lên ảnh). Kéo điểm, xoay nhãn chỉ dựng lại vài chục đối tượng thay vì
    vẽ và đổ lại cả vùng ảnh vào Tk, nên không chậm theo cỡ khung. Cùng giao diện với `render.CvPainter`; `tf` đổi toạ độ khung vẽ (chưa xoay)
    sang toạ độ Canvas (đã xoay ảnh). Canvas không có độ trong suốt nên `group` bỏ qua alpha; cửa sổ chỉ dùng bút này khi nhãn đặc 100%."""
    TAG = "ov"

    def __init__(self, canvas, tf):
        self.c, self.tf = canvas, tf

    def _tags(self, tag):
        return (self.TAG, tag) if tag else (self.TAG,)

    def poly(self, pts, color, width, tag=None):
        xy = [v for q in list(pts) + [pts[0]] for v in self.tf(q)]
        self.c.create_line(*xy, fill=_hex(color), width=width, tags=self._tags(tag))

    def line(self, a, b, color, width=1):
        self.c.create_line(*self.tf(a), *self.tf(b), fill=_hex(color), width=width, tags=self._tags(None))

    def circle(self, c, r, color, width=1, tag=None):
        x, y = self.tf(c)
        if width < 0:
            self.c.create_oval(x - r, y - r, x + r, y + r, fill=_hex(color), outline="", tags=self._tags(tag))
        else:
            self.c.create_oval(x - r, y - r, x + r, y + r, outline=_hex(color), width=width, tags=self._tags(tag))

    def dashed_circle(self, c, r, color):
        x, y = self.tf(c)
        self.c.create_oval(x - r, y - r, x + r, y + r, outline=_hex(color), dash=(3, 3), tags=self._tags(None))

    def text(self, org, txt, scale, color=(255, 255, 255), halo=True):
        x, y = self.tf(org)
        font = ("Segoe UI", -max(8, int(round(26 * scale))))
        if halo:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                self.c.create_text(x + dx, y + dy, text=txt, anchor="sw", fill="#000000", font=font, tags=self._tags(None))
        self.c.create_text(x, y, text=txt, anchor="sw", fill=_hex(color), font=font, tags=self._tags(None))

    @contextmanager
    def group(self, alpha: float):
        yield


class _Pt:
    """Toạ độ chuột đã đổi hệ (cùng dạng với sự kiện Tk: có .x và .y)."""

    def __init__(self, x, y, delta=0):
        self.x, self.y, self.delta = x, y, delta


ICON_PNG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "eyepin.png")
MOUSE_SPEED_MIN, MOUSE_SPEED_MAX = 0.1, 3.0       # độ nhạy chuột khi kéo: 1 = như cũ, nhỏ hơn = chậm hơn


class App(ObjectsMixin, FramesMixin, CvatMixin):
    @staticmethod
    def _set_window_icon(root: tk.Tk) -> None:
        """Icon cửa sổ và thanh tác vụ là ảnh eyepin.png. Thiếu file hoặc lỗi thì bỏ qua, tool vẫn mở bình thường."""
        try:
            root._icon_photo = ImageTk.PhotoImage(Image.open(ICON_PNG))
            root.iconphoto(True, root._icon_photo)
        except (OSError, tk.TclError):
            pass

    def __init__(self, root: tk.Tk):
        self.root = root
        theme.apply(root)
        self.settings = sc.load_settings()
        self.bind_map = sc.bindings(self.settings)
        self._bound: list[str] = []
        self.clipboard: dict | None = None
        self._dialogs: dict[str, tk.Toplevel] = {}
        root.title("EyePin — gán nhãn mắt cho CVAT")
        self._set_window_icon(root)
        self.s: Session | None = None
        self.f = 0
        self.anchor = None
        self.clicks: list = []
        self.pinning: str | None = None            # None | "full" | "hidden"
        self.drag = None
        self._m0 = None                 # chỗ bấm chuột (toạ độ khung chưa xoay) làm gốc để nhân độ nhạy chuột khi kéo
        self.drag_eye = None            # (nhãn mắt, điểm bấm đầu, điểm hiện tại) khi kéo cả mắt
        self.view = None
        self.manual = None
        self.show_ids = True
        self.look = Look(eyes={l: True for l in EYES})
        self._apply_settings_to_look()
        self.hide_labels = False
        self.main_size = MAIN
        self.drag_rot = None              # (nhãn mắt, tâm, góc tay cầm lúc đầu, góc hiện tại) khi xoay mắt bằng tay cầm
        self.drag_resize = None           # (nhãn mắt, tay cầm "nw".."w", hộp lúc đầu, điểm bấm, điểm hiện tại) khi kéo cạnh/góc khung chọn
        self.draft = None                 # mắt đang vẽ dở, chưa Apply: {"label": nhãn mắt, "four": {id điểm ghim: toạ độ}}
        self.draw_label = None            # label đã chọn trong bảng Vẽ mắt
        self.draft_drag = None            # id điểm của bản nháp đang kéo
        self._box0 = None                 # góc đầu (toạ độ frame) khi kéo khung để vẽ mắt
        self.rot_frames: dict[int, int] = {}
        self.rot = 0                      # số lần xoay 90 độ theo chiều kim đồng hồ (0..3), chỉ đổi cách nhìn
        self.tool = "cursor"             # cursor: kéo nhãn; hand: kéo chuột là dời ảnh
        self.filter = "all"
        self.locked = LayerSet(lambda: self.s.cur if self.s else 0)      # khoá theo từng bộ đối tượng
        self.playing = False
        self.hover: tuple[int, int] | None = None
        self._pan = None
        self._left_pan = False
        self.notice = ""
        self.scratch = False                 # True khi mở bằng --pins: không khôi phục, không ghi file phiên (bản demo không đụng phiên đã lưu)
        self._scratch_pins: dict | None = None   # dữ liệu --pins đã nạp (để mở lại file nhãn cùng thư mục mà không mất ghim)
        self._turns_sig: tuple = ()          # chữ ký các đoạn quay đầu đang hiện ở tab Issues
        self._turns_seen: set = set()        # đoạn quay đầu đã báo (người, frame đầu, frame cuối): chỉ báo lại khi có đoạn mới
        self._turn_target = None             # (người, frame) của đoạn quay đầu mới nhất, cho nút "Tới đoạn quay đầu"
        self._auto_view = None               # khung tự động đã canh cho frame hiện tại (giữ nguyên khi sửa nhãn, như CVAT)
        self._auto_key = None
        self._init_cvat()
        self._build()
        self.sync_look_vars()
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.ask_restore = self._ask_restore
        self._autosave_job = None
        self._schedule_autosave()

    # ---- dựng giao diện ----
    def _build(self):
        # --- thanh ngang phía trên (kiểu header CVAT): menu, lưu, hoàn tác, điều hướng frame | thông tin, toàn màn hình, lọc, hiển thị ---
        top = tk.Frame(self.root, bg=theme.ORANGE)
        top.pack(fill="x")
        self._top_bar = top
        self._build_name_row()
        B = lambda name, cmd, tip, **kw: IconButton(top, name, lambda b: cmd(), tip=tip, kind="bar", **kw)

        def popup(menu):
            return lambda b: menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

        menu = tk.Menu(top, tearoff=0)
        menu.add_command(label="Mở thư mục ảnh…", command=self.open_dir)
        menu.add_command(label="Mở file nhãn…", command=self.open_xml)
        self._cvat_menu_items(menu)
        menu.add_separator()
        menu.add_command(label=f"Chạy hành động ({self.kl('run_actions')})…", command=self.show_run_actions)
        menu.add_command(label=f"Quét nhãn có sẵn ({self.kl('scan')})", command=self.scan)
        menu.add_command(label="Xoá toàn bộ nhãn (Remove annotations)…", command=self.remove_annotations)
        menu.add_command(label=f"Xuất file import ({self.kl('export')})", command=self.export)
        menu.add_command(label="Hoàn tất job (Finish the job)…", command=self.finish_job)
        menu.add_separator()
        menu.add_command(label=f"Cài đặt ({self.kl('settings')})", command=self.show_settings)
        menu.add_command(label=f"Phím tắt ({self.kl('shortcuts')})", command=self.show_shortcuts)
        IconButton(top, "menu", popup(menu), tip="Menu", kind="bar").pack(side="left", padx=(6, 0))
        B("save", self.save_work, f"Lưu phiên ({self.kl('save')})").pack(side="left")
        B("undo", self.undo, f"Hoàn tác ({self.kl('undo')})").pack(side="left")
        B("redo", self.redo, f"Làm lại ({self.kl('redo')})").pack(side="left", padx=(0, 10))
        B("first", lambda: self.step("first"), f"Frame đầu ({self.kl('first')})").pack(side="left")
        B("back10", lambda: self.step(-10), f"Lùi 10 frame ({self.kl('jump_back')})").pack(side="left")
        B("prev", lambda: self.step(-1), f"Frame trước ({self.kl('frame_prev')})").pack(side="left")
        self.entry_var = tk.StringVar(value="0")
        self.entry = ttk.Entry(top, textvariable=self.entry_var, width=6, justify="center")
        self.entry.pack(side="left", padx=3)
        self.entry.bind("<Return>", self.on_entry)
        self.entry.bind("<Up>", self.on_entry_up)
        self.entry.bind("<Down>", self.on_entry_down)
        self.entry.bind("<FocusOut>", lambda e: self._sync_entry())
        self.root.bind_all("<ButtonPress>", self._click_focus, add="+")
        self.total = tk.StringVar(value="/ 0")
        ttk.Label(top, style="Bar.TLabel", textvariable=self.total, width=7).pack(side="left")
        B("next", lambda: self.step(1), f"Frame kế ({self.kl('frame_next')})").pack(side="left")
        B("fwd10", lambda: self.step(10), f"Tiến 10 frame ({self.kl('jump_fwd')})").pack(side="left")
        B("last", lambda: self.step("last"), f"Frame cuối ({self.kl('last')})").pack(side="left")
        self.play_btn = B("play", self.toggle_play, f"Phát / dừng ({self.kl('play')})")
        self.play_btn.pack(side="left", padx=(10, 0))
        B("prev", lambda: self.jump_pin(-1), f"Keyframe trước ({self.kl('prev_keyframe')})", caption="◀ KF").pack(side="left", padx=(10, 0))
        B("next", lambda: self.jump_pin(1), f"Keyframe kế ({self.kl('next_keyframe')})", caption="KF ▶").pack(side="left")
        # nhóm bên phải, có chữ nhỏ dưới biểu tượng như CVAT
        flt_menu = tk.Menu(top, tearoff=0)
        self._filter_var = tk.StringVar(value="all")
        for key_, text in Session.FILTERS.items():
            flt_menu.add_radiobutton(label=text, value=key_, variable=self._filter_var, command=self.set_filter)
        view_menu = tk.Menu(top, tearoff=0)
        self._layer_vars = {}
        for name, text in (("image", "Ảnh"), ("mattrai", "Mắt trái"), ("matphai", "Mắt phải"), ("outline", "Viền"),
                           ("points", "Điểm"), ("ids", "Số điểm")):
            v = tk.BooleanVar(value=True)
            self._layer_vars[name] = v
            view_menu.add_checkbutton(label=text, variable=v, command=lambda n=name: self.set_layer(n))
        view_menu.add_separator()
        view_menu.add_command(label=f"Ẩn/hiện toàn bộ nhãn ({self.kl('hide_all')})", command=self.toggle_labels)
        view_menu.add_command(label=f"Đổi mắt nằm trên ({self.kl('swap_top')})", command=self.swap_top)
        view_menu.add_command(label="Cỡ điểm, độ đặc…", command=self.show_display_dialog)
        view_menu.add_command(label=f"Image setups: lưới, độ sáng, gamma… ({self.kl('image_setups')})", command=self.show_image_setups)
        view_menu.add_command(label=f"Bật/tắt lưới ({self.kl('grid')})", command=self.toggle_grid)
        self.view_btn = IconButton(top, "display", popup(view_menu), tip="Lớp, cỡ điểm, lưới, độ sáng", caption="Hiển thị", kind="bar")
        self.fullscreen_btn = B("fullscreen", self.toggle_fullscreen, f"Toàn màn hình ({self.kl('fullscreen')})", caption="Toàn màn hình")
        self.filter_btn = IconButton(top, "filter", popup(flt_menu), caption="Lọc", kind="bar",
                                     tip=lambda: f"Lọc frame (đang: {Session.FILTERS[self.filter]}). {self.kl('search_prev')}/{self.kl('search_next')} nhảy tới frame thoả")
        info_btn = B("info", self.show_info, f"Thông tin job ({self.kl('info')})", caption="Thông tin")
        for w in (self.view_btn, self.filter_btn, self.fullscreen_btn, info_btn, *self._cvat_buttons(top)):
            w.pack(side="right", padx=2)
        # --- thân: thanh công cụ dọc bên trái | ảnh | panel phải ---
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=(0, 6), pady=3)
        tools = tk.Frame(body, bg=theme.PAPER_DEEP)
        tools.pack(side="left", fill="y", padx=(0, 6))
        T = lambda name, cmd, tip: IconButton(tools, name, lambda b: cmd(), tip=tip, kind="tool", size=16)
        self.tool_btns = {}
        for name, tip in (("cursor", "Con trỏ: kéo điểm hoặc cả mắt"), ("hand", "Dời ảnh: kéo chuột để dời ảnh (chuột phải, giữa cũng được)")):
            b = T(name, lambda n=name: self.set_tool(n), tip)
            b.pack(pady=1)
            self.tool_btns[name] = b
        self.tool_btns["cursor"].set_active(True)
        for name, cmd, tip in (("zoom_in", lambda: self.zoom(1.25), f"Phóng to ({self.kl('zoom_in')}, hoặc cuộn chuột)"),
                               ("zoom_out", lambda: self.zoom(0.8), f"Thu nhỏ ({self.kl('zoom_out')})"),
                               ("fit", self.fit, f"Vừa khung ({self.kl('fit')})"),
                               ("rot_ccw", lambda: self.rotate(-1), f"Xoay ngược chiều kim đồng hồ ({self.kl('rotate_ccw')})"),
                               ("rot_cw", lambda: self.rotate(1), f"Xoay theo chiều kim đồng hồ ({self.kl('rotate_cw')})")):
            T(name, cmd, tip).pack(pady=1)
        tk.Frame(tools, bg=theme.PAPER_LINE, height=1).pack(fill="x", padx=6, pady=6)
        for name, cmd, tip in (("pin", self.start_draw, f"Vẽ một mắt: chọn label, bấm 4 điểm hoặc kéo khung, rồi Apply ({self.kl('draw_eye')})"),
                               ("pin_hidden", lambda: self.start_pin("hidden"), f"Ghim khi che khoé, 7 điểm ({self.kl('draw_hidden')})"),
                               ("keyframe", self.toggle_pin_here, f"Ghim / bỏ ghim frame này ({self.kl('keyframe')})")):
            T(name, cmd, tip).pack(pady=1)
        self.eye_btn = T("eye", self.toggle_labels, f"Ẩn/hiện toàn bộ nhãn ({self.kl('hide_all')})")
        self.eye_btn.pack(pady=1)
        tk.Frame(tools, bg=theme.PAPER_LINE, height=1).pack(fill="x", padx=6, pady=6)
        T("scan", self.scan, f"Quét nhãn có sẵn ({self.kl('scan')})").pack(pady=1)
        T("export", self.export, f"Xuất file import cho CVAT ({self.kl('export')})").pack(pady=1)
        tk.Frame(tools, bg=theme.PAPER_DEEP).pack(fill="y", expand=True)
        T("keyboard", self.show_shortcuts, f"Phím tắt ({self.kl('shortcuts')})").pack(pady=1)
        T("settings", self.show_settings, f"Cài đặt ({self.kl('settings')})").pack(pady=(1, 4))
        self.canvas = tk.Canvas(body, width=MAIN[0], height=MAIN[1], bg=theme.CANVAS, highlightthickness=0)
        self.draft_bar = ttk.Frame(self.canvas, padding=4)        # nổi trên ảnh khi có mắt vẽ dở: Apply / Huỷ
        ttk.Button(self.draft_bar, text="✓ Apply", command=self.apply_draft).pack(side="left", padx=2)
        ttk.Button(self.draft_bar, text="Huỷ (Esc)", command=self.cancel_pin).pack(side="left", padx=2)
        self._build_qc_bar()
        self.turn_text = tk.StringVar(value="")                  # thanh báo nổi ở đáy ảnh khi phát hiện đoạn quay đầu mới
        self.turn_bar = ttk.Frame(self.canvas, padding=(8, 4))
        ttk.Label(self.turn_bar, textvariable=self.turn_text, wraplength=640).pack(side="left")
        ttk.Button(self.turn_bar, text="Tới đoạn quay đầu", command=self.turn_jump).pack(side="left", padx=(8, 2))
        ttk.Button(self.turn_bar, text="Đóng", command=self.dismiss_turns).pack(side="left", padx=2)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<ButtonPress-3>", self.on_pan_start)
        self.canvas.bind("<B3-Motion>", self.on_pan)
        self.canvas.bind("<ButtonRelease-3>", self.on_pan_end)
        self.canvas.bind("<ButtonPress-2>", self.on_pan_start)
        self.canvas.bind("<B2-Motion>", self.on_pan)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_end)
        self.canvas.bind("<Motion>", self.on_hover)
        self.canvas.bind("<Leave>", self.on_leave)
        side = self.side = ttk.Notebook(body, width=350)
        side.pack(side="right", fill="y", padx=(8, 0))                 # panel phải cố định; ảnh chiếm phần còn lại khi phóng cửa sổ
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self._base_item = self.canvas.create_image(0, 0, anchor="nw")
        self._patch_item = self.canvas.create_image(0, 0, anchor="nw", state="hidden")
        self._base_key = None
        self._thumb_job = None
        cmp_tab = ttk.Frame(side)
        att_tab = self.issues_tab = ttk.Frame(side)
        obj_tab = self.objects_tab = ttk.Frame(side)
        side.add(obj_tab, text="Đối tượng")
        side.add(cmp_tab, text="Frame lân cận")
        side.add(att_tab, text="Issues")
        labels_tab = ttk.Frame(side)
        side.add(labels_tab, text="Labels")
        self.build_labels_tab(labels_tab)
        ttk.Label(cmp_tab, text="Frame trước (chỉ để so sánh)").pack(anchor="w")
        self.t_prev = tk.Label(cmp_tab)
        self.t_prev.pack()
        self.c_prev = tk.StringVar()
        ttk.Label(cmp_tab, textvariable=self.c_prev).pack(anchor="w")
        ttk.Label(cmp_tab, text="Frame sau (sẽ đổi theo frame này)").pack(anchor="w", pady=(6, 0))
        self.t_next = tk.Label(cmp_tab)
        self.t_next.pack()
        self.c_next = tk.StringVar()
        ttk.Label(cmp_tab, textvariable=self.c_next).pack(anchor="w")
        self.tree = ttk.Treeview(obj_tab, columns=("vai", "sao", "trang"), height=14, selectmode="browse")
        self.tree.heading("#0", text="Đối tượng")
        self.tree.heading("vai", text="Loại")
        self.tree.heading("sao", text="★")
        self.tree.heading("trang", text="Trạng thái")
        self.tree.column("#0", width=140)
        self.tree.column("vai", width=100, anchor="center")
        self.tree.column("sao", width=34, anchor="center")
        self.tree.column("trang", width=76, anchor="center")
        self.tree.bind("<Button-1>", self.on_tree_click, add="+")
        self.tree.pack(fill="both", expand=True)
        nav = ttk.Frame(obj_tab)                                       # hàng điều hướng keyframe của đối tượng (như thẻ đối tượng CVAT)
        nav.pack(fill="x", pady=(3, 0))
        for name, cmd, tip in (("first", self.first_keyframe, "Keyframe đầu tiên"),
                               ("prev", lambda: self.jump_pin(-1), f"Keyframe trước ({self.kl('prev_keyframe')})"),
                               ("next", lambda: self.jump_pin(1), f"Keyframe kế ({self.kl('next_keyframe')})"),
                               ("last", self.last_keyframe, "Keyframe cuối cùng"),
                               ("keyframe", self.toggle_pin_here, f"Ghim / bỏ ghim keyframe ★ ({self.kl('keyframe')})")):
            IconButton(nav, name, lambda b, c=cmd: c(), tip=tip, kind="tool").pack(side="left", padx=2)
        row = ttk.Frame(obj_tab)
        row.pack(fill="x", pady=3)
        for name, cmd, tip in (("lock", self.toggle_lock, f"Khoá/mở khoá mắt đang chọn ({self.kl('lock')})"),
                               ("eye", self.toggle_eye_hidden, f"Ẩn/hiện mắt đang chọn ({self.kl('hide')})")):
            IconButton(row, name, lambda b, c=cmd: c(), tip=tip, kind="tool").pack(side="left", padx=2)
        ttk.Button(row, text="Occluded", width=9, command=lambda: self.toggle_flag("occluded")).pack(side="left", padx=(10, 2))
        ttk.Button(row, text="Outside", width=8, command=lambda: self.toggle_flag("outside")).pack(side="left", padx=2)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._objects_extras(obj_tab, nav, row)
        self.build_issues_tab(att_tab)
        self.listbox = tk.Listbox(att_tab, height=14, width=44)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", self.on_list)
        self.items: list[int] = []
        self.status = tk.StringVar(value="Mở một thư mục ảnh để bắt đầu. Cuộn chuột để phóng to; kéo chuột để dời ảnh.")
        ttk.Label(self.root, textvariable=self.status, anchor="w").pack(fill="x", padx=8)
        self.timeline = tk.Label(self.root)
        self.timeline.pack(padx=6, pady=4)
        self.timeline.bind("<Button-1>", self.on_timeline)
        self._build_display_dialog()
        self._build_image_setups()
        self.setups_btn = ttk.Button(self.canvas, text="^", width=3, command=self.show_image_setups)   # như CVAT: giữa mép dưới khung ảnh
        self.setups_btn.place(relx=0.5, rely=1.0, y=-2, anchor="s")
        Tooltip(self.setups_btn, f"Image setups: lưới, độ sáng, tương phản, bão hoà, gamma ({self.kl('image_setups')})")

    def _build_display_dialog(self):
        """Hộp chứa các thanh trượt hiển thị (cỡ điểm, độ đặc, độ sáng, tương phản, bão hoà); ẩn khi chưa mở."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Chỉnh hiển thị")
        dlg.withdraw()
        dlg.protocol("WM_DELETE_WINDOW", dlg.withdraw)
        self._display_dlg = dlg
        self._adj_vars = {}
        rows = (("size", f"Cỡ điểm ({self.kl('marker_down')} {self.kl('marker_up')})", 0.4, 3.0, 1.0), ("opacity", "Độ đặc nhãn", 0.15, 1.0, 1.0),
                ("selected_opacity", "Độ đặc mắt đang chọn", 0.15, 1.0, 1.0))      # độ sáng, tương phản, bão hoà, gamma: hộp Image setups
        for r, (name, text, lo, hi, init) in enumerate(rows):
            ttk.Label(dlg, text=text).grid(row=r, column=0, sticky="w", padx=8, pady=3)
            v = tk.DoubleVar(value=init)
            self._adj_vars[name] = v
            ttk.Scale(dlg, from_=lo, to=hi, variable=v, length=200,
                      command=lambda val, n=name: self.set_look(**{n: float(val)})).grid(row=r, column=1, padx=8)
        self.size_var, self.opacity_var = self._adj_vars["size"], self._adj_vars["opacity"]
        r0 = len(rows)
        ttk.Label(dlg, text="Tô màu theo (Color by)").grid(row=r0, column=0, sticky="w", padx=8, pady=3)
        cb_fr = ttk.Frame(dlg)
        cb_fr.grid(row=r0, column=1, sticky="w", padx=8)
        self._color_by_var = tk.StringVar(value="label")
        for text, val in (("Label", "label"), ("Instance", "instance"), ("Group", "group")):
            ttk.Radiobutton(cb_fr, text=text, value=val, variable=self._color_by_var,
                            command=lambda: self.set_look(color_by=self._color_by_var.get())).pack(side="left", padx=3)
        self._outlined_var = tk.BooleanVar(value=False)
        of = ttk.Frame(dlg)
        of.grid(row=r0 + 1, column=0, columnspan=2, sticky="w", padx=8, pady=3)
        ttk.Checkbutton(of, text="Viền ngoài (Outlined borders)", variable=self._outlined_var,
                        command=lambda: self.set_look(outlined=self._outlined_var.get())).pack(side="left")
        ttk.Button(of, text="Màu viền…", command=self.pick_outline_color).pack(side="left", padx=8)
        self.top_btn = ttk.Button(dlg, text="", command=self.swap_top)
        self.top_btn.grid(row=r0 + 2, column=0, columnspan=2, pady=4)
        ttk.Button(dlg, text="Đặt lại ảnh", command=self.reset_adjust).grid(row=r0 + 3, column=0, columnspan=2, pady=(0, 8))
        self._sync_top()

    def pick_outline_color(self):
        from tkinter import colorchooser
        c = colorchooser.askcolor(title="Màu viền", parent=self._display_dlg)
        if c and c[0]:
            r, g, b = (int(v) for v in c[0])
            self.set_look(outline_color=(b, g, r), outlined=True)
            self._outlined_var.set(True)

    def show_display_dialog(self):
        self._display_dlg.deiconify()
        self._display_dlg.lift()

    # ---- hộp Image setups (như CVAT: nút ^ giữa mép dưới khung ảnh) ----
    SETUP_RANGES = {**imagefx.COLOR_RANGES, "grid_size": imagefx.GRID_SIZE_RANGE, "grid_opacity": (0, 100)}

    def _build_image_setups(self):
        """Hộp lưới và màu ảnh, dựng sẵn và ẩn (như hộp Chỉnh hiển thị); `_setup_vars` có từ đầu để phím g và Reset đồng bộ được."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Image setups")
        dlg.withdraw()
        dlg.protocol("WM_DELETE_WINDOW", dlg.withdraw)
        dlg.transient(self.root)
        dlg.bind("<Escape>", lambda e: dlg.withdraw())
        self._setups_dlg = dlg
        v = self._setup_vars = {"grid": tk.BooleanVar(value=self.look.grid), "grid_size": tk.IntVar(value=self.look.grid_size),
                                "grid_color": tk.StringVar(value=self.look.grid_color), "grid_opacity": tk.DoubleVar(value=self.look.grid_opacity),
                                "axis_guide": tk.BooleanVar(value=self.look.axis_guide),
                                **{n: tk.DoubleVar(value=getattr(self.look, n)) for n in imagefx.COLOR_DEFAULTS}}
        g = ttk.LabelFrame(dlg, text="Image grid", padding=8)
        g.grid(row=0, column=0, sticky="we", padx=8, pady=(8, 4))
        ttk.Checkbutton(g, text=f"Bật lưới ({self.kl('grid')})", variable=v["grid"],
                        command=lambda: self._apply_setup("grid", v["grid"].get())).grid(row=0, column=0, sticky="w")
        ttk.Label(g, text="Size (px ảnh)").grid(row=0, column=1, padx=(12, 4))
        lo, hi = imagefx.GRID_SIZE_RANGE
        size = ttk.Spinbox(g, from_=lo, to=hi, increment=1, width=6, textvariable=v["grid_size"],
                           command=lambda: self._apply_setup("grid_size", self._var_value("grid_size")))
        size.grid(row=0, column=2)
        for ev in ("<Return>", "<FocusOut>"):
            size.bind(ev, lambda e: self._apply_setup("grid_size", self._var_value("grid_size")))
        ttk.Label(g, text="Màu").grid(row=0, column=3, padx=(12, 4))
        color = ttk.Combobox(g, values=list(imagefx.GRID_COLORS), textvariable=v["grid_color"], state="readonly", width=7)
        color.grid(row=0, column=4)
        color.bind("<<ComboboxSelected>>", lambda e: self._apply_setup("grid_color", v["grid_color"].get()))
        ttk.Label(g, text="Opacity").grid(row=1, column=0, sticky="w", pady=(6, 0))
        tk.Scale(g, from_=0, to=100, resolution=1, orient="horizontal", length=260, variable=v["grid_opacity"],
                 command=lambda val: self._apply_setup("grid_opacity", val)).grid(row=1, column=1, columnspan=4, sticky="we")
        ttk.Checkbutton(g, text="Thước theo trục mắt (mắt đang chọn, vạch tỉ lệ guideline)", variable=v["axis_guide"],
                        command=lambda: self._apply_setup("axis_guide", v["axis_guide"].get())).grid(row=2, column=0, columnspan=5, sticky="w", pady=(6, 0))
        c = ttk.LabelFrame(dlg, text="Color settings", padding=8)
        c.grid(row=1, column=0, sticky="we", padx=8, pady=4)
        for r, (n, text, res) in enumerate((("brightness", "Brightness (%)", 1), ("contrast", "Contrast (%)", 1),
                                           ("saturation", "Saturation (%)", 1), ("gamma", "Gamma", 0.01))):
            ttk.Label(c, text=text).grid(row=r, column=0, sticky="w")
            lo, hi = imagefx.COLOR_RANGES[n]
            tk.Scale(c, from_=lo, to=hi, resolution=res, orient="horizontal", length=300, variable=v[n],
                     command=lambda val, n=n: self._apply_setup(n, val)).grid(row=r, column=1, sticky="we")
        ttk.Button(dlg, text="Reset color settings", command=self.reset_adjust).grid(row=2, column=0, pady=(4, 10))

    def _var_value(self, name: str):
        try:
            return self._setup_vars[name].get()
        except (tk.TclError, ValueError):                    # ô Size đang gõ dở (rỗng, chữ): giữ giá trị cũ
            return getattr(self.look, name)

    def _apply_setup(self, name: str, value) -> None:
        """Đặt một giá trị của hộp Image setups vào `self.look` (kẹp theo thang như CVAT), đồng bộ ô trong hộp, vẽ lại."""
        if name in ("grid", "axis_guide"):
            value = bool(value)
        elif name == "grid_color":
            value = value if value in imagefx.GRID_COLORS else "White"
        else:
            try:
                x = float(value)
            except (TypeError, ValueError):
                return
            lo, hi = self.SETUP_RANGES[name]
            x = min(max(x, lo), hi)
            value = int(round(x)) if name == "grid_size" else round(x, 2)
        setattr(self.look, name, value)
        var = self._setup_vars.get(name)
        if var is not None and self._var_value(name) != value:
            var.set(value)
        self.refresh()

    def show_image_setups(self):
        """Ctrl+G hoặc nút ^: mở hộp Image setups ngay trên mép dưới khung ảnh."""
        dlg = self._setups_dlg
        dlg.deiconify()
        dlg.update_idletasks()
        cx = self.canvas.winfo_rootx() + self.canvas.winfo_width() // 2
        bottom = self.canvas.winfo_rooty() + self.canvas.winfo_height()
        dlg.geometry(f"+{max(0, cx - dlg.winfo_reqwidth() // 2)}+{max(0, bottom - dlg.winfo_reqheight() - 48)}")
        dlg.lift()

    def toggle_grid(self):
        """Phím g: bật/tắt lưới ảnh (ô Image grid của CVAT)."""
        self._apply_setup("grid", not self.look.grid)
        if self.look.grid:
            step = imagefx.grid_step(self.look.grid_size, self.view.k) if self.view else self.look.grid_size
            self.notice = f"Lưới: bật (Size {self.look.grid_size}" + (f", đang vẽ mỗi {step} px vì ảnh đang thu nhỏ" if step != self.look.grid_size else "") + ")."
        else:
            self.notice = "Lưới: tắt."
        self.refresh(light=True)

    def _preview_pts(self):
        """Mắt đang ghim dở: vẽ luôn mắt đầu tiên, không chờ đủ số điểm. Ghim 8 điểm: khi 4 điểm đầu là một mắt hợp lệ. Ghim khi che khoé
        (7 điểm): khi 4 điểm đầu là mắt thấy đủ, hoặc 3 điểm đầu là mắt bị che khoé (khoé bị che được ước lượng như lúc ghim thật).
        Chỉ nhìn các điểm đầu; nếu chúng không giống một mắt (bấm xen kẽ hai mắt) thì không vẽ gì và chờ đủ số điểm.
        Có mắt vẽ dở (bảng Vẽ mắt) thì vẽ mắt đó cho người dùng chỉnh trước khi Apply."""
        if self.draft:
            return derive(EYES[self.draft["label"]], self.draft["four"])
        if self.pinning not in ("full", "hidden") or len(self.clicks) >= PIN_COUNT[self.pinning]:
            return None
        pts = [p for _, p in self.clicks]
        narrow = lambda four: math.dist(four[14], four[18]) <= 0.2 * self.s.width   # quá rộng cho một mắt: nhiều khả năng bấm xen kẽ hai mắt
        if len(pts) >= 4:
            try:
                four = assign_roles(MATTRAI, pts[:4])
                if narrow(four):
                    return derive(MATTRAI, four)
            except ValueError:
                pass
        if self.pinning == "hidden" and len(pts) >= 3:
            try:
                known, hidden, est = assign_three(MATTRAI, pts[:3])
            except ValueError:
                return None
            four = {**known, hidden: est}
            if narrow(four):
                return derive(MATTRAI, four)
        return None

    def kl(self, aid: str) -> str:
        """Tên phím đầu tiên của hành động (để ghi trên nút và menu)."""
        keys = self.bind_map.get(aid) or ()
        return sc.pretty(keys[0]) if keys else "—"

    def _actions(self) -> dict:
        return {
            "shortcuts": self.show_shortcuts, "settings": self.show_settings, "fullscreen": self.toggle_fullscreen, "info": self.show_info, "undo": self.undo, "redo": self.redo,
            "save": self.save_work, "export": self.export, "scan": self.scan, "run_actions": self.show_run_actions,
            "remove_annotations": self.remove_annotations, "finish_job": self.finish_job, "pinned": self.toggle_pinned,
            "propagate": self.object_propagate, "change_color": self.object_color_next, "swap_labels": self.swap_labels,
            "focus_object": self.focus_object, "delete_frame": self.toggle_delete_frame, "search_frame": self.search_frame_by_name, "cancel": self.cancel_pin,
            "frame_next": lambda: self.step(1), "frame_prev": lambda: self.step(-1),
            "step_fwd": lambda: self.step(self.settings["player"]["step"]), "step_back": lambda: self.step(-self.settings["player"]["step"]),
            "search_next": lambda: self.search(1), "search_prev": lambda: self.search(-1),
            "jump_fwd": lambda: self.step(10), "jump_back": lambda: self.step(-10),
            "first": lambda: self.step("first"), "last": lambda: self.step("last"), "play": self.toggle_play,
            "focus_frame": self.focus_frame, "next_keyframe": lambda: self.jump_pin(1), "prev_keyframe": lambda: self.jump_pin(-1),
            "next_object": lambda: self.select_object(1), "prev_object": lambda: self.select_object(-1),
            "label_mattrai": lambda: self.select_eye("mattrai"), "label_matphai": lambda: self.select_eye("matphai"),
            "lock": self.toggle_lock, "lock_all": self.toggle_lock_all, "hide": self.toggle_eye_hidden, "hide_all": self.toggle_labels,
            "occluded": lambda: self.toggle_flag("occluded"), "outside": lambda: self.toggle_flag("outside"),
            "keyframe": self.toggle_pin_here, "new_object": self.new_object, "delete": self.delete_label, "delete_force": lambda: self.delete_label(True),
            "end_label": self.end_label_here, "copy": self.copy_pins, "paste": self.paste_pins,
            "draw_eye": self.start_draw, "draw_full": lambda: self.start_pin("full"), "draw_hidden": lambda: self.start_pin("hidden"),
            "eye_rot_cw": lambda: self.rotate_eye(1), "eye_rot_ccw": lambda: self.rotate_eye(-1),
            "eye_rot_cw5": lambda: self.rotate_eye(5), "eye_rot_ccw5": lambda: self.rotate_eye(-5),
            "rotate_cw": lambda: self.rotate(1), "rotate_ccw": lambda: self.rotate(-1),
            "tool_cursor": lambda: self.set_tool("cursor"), "tool_hand": lambda: self.set_tool("hand"),
            "zoom_in": lambda: self.zoom(self.zoom_step()), "zoom_out": lambda: self.zoom(1 / self.zoom_step()), "fit": self.fit, "toggle_ids": self.toggle_ids,
            "marker_up": lambda: self.resize_markers(1.25), "marker_down": lambda: self.resize_markers(0.8), "swap_top": self.swap_top,
            "image_setups": self.show_image_setups, "grid": self.toggle_grid,
            "open_cvat": self.open_cvat, "send_cvat": self.send_cvat, "qc_clear": self.qc_clear,
        }

    def _bind_keys(self):
        """Gắn phím theo `self.bind_map` (gọi lại sau khi người dùng gán lại phím). `handlers` tra theo id hành động."""
        r = self.root
        for seq in self._bound:
            r.unbind(seq)
        self._bound = []
        self.handlers = {}
        funcs = self._actions()
        assert set(funcs) == set(sc.BY_ID), set(funcs) ^ set(sc.BY_ID)
        always = {"shortcuts", "settings"}
        for aid, fn in funcs.items():
            def handler(e=None, fn=fn, aid=aid):
                if aid not in always and self._typing():
                    return None
                fn()
                return "break"
            self.handlers[aid] = handler
            for seq in self.bind_map[aid]:
                r.bind(seq, handler)
                self._bound.append(seq)

    # ---- cài đặt, phím tắt, đối tượng (bước 3, 4) ----
    def _apply_settings_to_look(self):
        """Nạp cài đặt hiển thị đã lưu và cài đặt Player vào `self.look`."""
        pl = self.settings["player"]
        self.look.smooth = bool(pl["smooth"])
        try:
            h = pl["bg"].lstrip("#")
            self.look.bg = (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))
        except (ValueError, AttributeError):
            pass
        ws = self.settings["workspace"]
        self.look.text_always = bool(ws.get("text_always", False))
        self.look.text_content = tuple(ws.get("text_content", ("id", "label", "source")))
        self.look.font_size = float(ws.get("font_size", 1.0))
        if imagefx.migrate_display(self.settings["display"]):           # thang cũ (cộng) không đổi được sang thang % của CVAT
            self.save_settings()
            if self.settings["workspace"]["remember_display"]:
                self.notice = "Độ sáng, tương phản, bão hoà đã về mặc định vì EyePin đổi sang thang của CVAT (50–200%)."
        if self.settings["workspace"]["remember_display"]:
            for k, v in self.settings["display"].items():
                if k in DISPLAY_KEYS and hasattr(self.look, k):
                    setattr(self.look, k, v)
        self.show_ids = self.look.ids

    def sync_look_vars(self):
        """Đưa giá trị trong `self.look` lên các ô tick và thanh trượt."""
        for k in ("image", "outline", "points", "ids"):
            self._layer_vars[k].set(getattr(self.look, k))
        for l in EYES:
            self._layer_vars[l].set(self.look.eyes[l])
        for k, v in self._adj_vars.items():
            v.set(getattr(self.look, k))
        for k, v in getattr(self, "_setup_vars", {}).items():
            v.set(getattr(self.look, k))
        self._color_by_var.set(self.look.color_by)
        self._outlined_var.set(self.look.outlined)
        self._sync_top()
        self.canvas.configure(bg=self.settings["player"]["bg"])

    # ---- lưu phiên làm việc và tự lưu ----
    def state_path(self) -> str:
        """File phiên làm việc của thư mục ảnh đang mở: nằm trong thư mục cài đặt, không đặt cạnh ảnh."""
        key = hashlib.sha1(self.s.source_key.encode("utf-8")).hexdigest()[:12]
        return str(sc.settings_path().parent / "sessions" / f"{key}.json")

    def _ask_restore(self, n: int) -> bool:
        what = "job CVAT" if self.s is not None and self.s.cvat is not None else "thư mục ảnh"
        extra = ("\nJob này đã có nhãn mắt: khôi phục sẽ bỏ nhãn mắt cũ khỏi phiên (CVAT chưa đổi gì cho tới khi gửi)."
                 if self.s is not None and self.s.qc else "")
        return messagebox.askyesno("EyePin", f"Có phiên làm việc đã lưu cho {what} này ({n} frame ghim). Khôi phục không?{extra}")

    def try_restore(self) -> bool:
        p = self.state_path()
        if not os.path.exists(p):
            return False
        cleared = False
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
            n = sum(len(part.get("pins", {})) for part in data.get("layers", [data]))
            if n == 0 or not self.ask_restore(n):
                return False
            live = (self.s.cvat or {}).get("updated")
            if self.s.qc:                                # job đã có nhãn mắt mà người dùng khôi phục ghim = chọn xoá nhãn cũ và gán lại (spec mục 8)
                self.s.clear_old_eyes()
                cleared = True
            self.s.load_state(data)                      # lỗi CVAT khi bám lại (mất kết nối, 401): load_state trả phiên về như trước
        except (OSError, ValueError, KeyError, TypeError, CvatError) as err:
            if cleared:
                self.s.restore_old_eyes()                # khôi phục lỗi: nhãn mắt cũ còn nguyên, vẫn ở chế độ QC
            self.notice = f"Không khôi phục được phiên đã lưu: {err}"
            if isinstance(err, CvatError):
                self.notice += " File phiên vẫn còn: mở lại job khi CVAT trả lời lại để khôi phục."
            return False
        self.notice = f"Đã khôi phục phiên làm việc: {n} frame ghim."
        if cleared:
            self.notice += " Nhãn mắt cũ của job đã được bỏ khỏi phiên (gửi lên CVAT sẽ thay chúng)."
        if self.s.cvat is not None and (self.s.cvat.get("updated") != live):
            self.notice += " Chú ý: job đã bị sửa trên CVAT kể từ lần làm việc trước; gửi lên sẽ ghi đè các sửa đó."
        return True

    def save_work(self, auto: bool = False):
        """Ctrl+S / tự lưu: ghi các frame ghim và cờ ra file phiên (chưa phải file import; xuất file import là Ctrl+Shift+S)."""
        if not self.s:
            return
        if self.scratch:
            if not auto:
                self.notice = "Đang mở bằng --pins: không ghi file phiên (xuất file import vẫn dùng được)."
                self.refresh(light=True)
            return
        if auto and not self.s.dirty:
            return
        try:
            self.s.save_state(self.state_path())
        except OSError as err:
            self.notice = f"Không lưu được: {err}"
        else:
            self.notice = ("Tự lưu lúc " if auto else "Đã lưu lúc ") + __import__("time").strftime("%H:%M:%S") + "."
        self.refresh(light=True)

    def _schedule_autosave(self):
        ws = self.settings["workspace"]
        try:
            ms = max(10, int(float(ws["autosave_min"]) * 60_000))
        except (TypeError, ValueError):
            ms = 120_000
        self._autosave_job = self.root.after(ms, self._autosave_tick)

    def _autosave_tick(self):
        if self.settings["workspace"]["autosave"]:
            self.save_work(auto=True)
        self._schedule_autosave()

    def confirm_close(self) -> bool:
        """Hỏi trước khi thoát khi còn thay đổi chưa lưu. True = được đóng cửa sổ, False = ở lại."""
        if not (self.s and self.s.dirty):
            return True
        if self.scratch:                                     # mở bằng --pins: không có file phiên để lưu
            return bool(messagebox.askyesno(
                "Thoát EyePin", "Có thay đổi chưa lưu. Đang mở bằng --pins nên tool không ghi file phiên: thoát sẽ mất các thay đổi này "
                "(xuất file import bằng Ctrl+Shift+S nếu cần giữ).\n\nVẫn thoát?",
                icon="warning", default="no", parent=self.root))
        ans = messagebox.askyesnocancel(
            "Thoát EyePin", "Có thay đổi chưa lưu.\n\nCó: lưu rồi thoát\nKhông: thoát, bỏ thay đổi\nHuỷ: ở lại làm tiếp",
            icon="warning", default="yes", parent=self.root)
        if ans is None:
            return False
        if ans:
            self.save_work()
            if self.s.dirty:                                 # lưu lỗi (đĩa đầy, không có quyền...): đừng thoát kẻo mất việc
                messagebox.showerror("EyePin", self.notice or "Không lưu được.", parent=self.root)
                return False
        return True

    def confirm_close_busy(self) -> bool:
        """Đang có việc nền (gửi, khôi phục, mở job...): hỏi trước khi đóng, mặc định Không. True = vẫn đóng."""
        if not self.busy:
            return True
        return bool(messagebox.askyesno(
            "Thoát EyePin", f"{self.busy} Đóng cửa sổ có thể làm mất kết quả gửi (không biết CVAT đã nhận nhãn hay chưa).\n\nVẫn đóng?",
            icon="warning", default="no", parent=self.root))

    def on_close(self):
        if not self.confirm_close_busy():
            return
        if not self.confirm_close():
            return
        self.settings["display"] = {k: getattr(self.look, k) for k in DISPLAY_KEYS} | {"color_scale": "cvat"}
        try:
            sc.save_settings(self.settings)
        except OSError:
            pass
        if self.cvat_client is not None:
            self.cvat_client.close()
        self.root.destroy()

    def save_settings(self):
        try:
            sc.save_settings(self.settings)
        except OSError as err:
            self.notice = f"Không lưu được cài đặt: {err}"

    def rebind(self, aid: str, seq: str | None) -> str | None:
        """Gán phím `seq` cho hành động `aid` (None = về mặc định). Trả về thông báo lỗi nếu trùng phím với hành động khác."""
        new = (seq,) if seq else sc.BY_ID[aid].keys
        clash = [o for o, keys in self.bind_map.items() if o != aid and set(keys) & set(new)]
        if clash:
            return f"Phím {sc.pretty(new[0])} đang dùng cho \"{sc.BY_ID[clash[0]].label}\"."
        self.bind_map[aid] = tuple(new)
        if seq:
            self.settings["shortcuts"][aid] = [seq]
        else:
            self.settings["shortcuts"].pop(aid, None)
        self._bind_keys()
        self.save_settings()
        return None

    def toggle_fullscreen(self):
        full = not bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", full)
        self.fullscreen_btn.set_icon("window" if full else "fullscreen")
        self.fullscreen_btn.set_active(full)
        self.notice = f"Toàn màn hình: bấm {self.kl('fullscreen')} hoặc Esc để thoát." if full else ""
        self.refresh()

    def show_info(self):
        """Hộp Thông tin job: thư mục ảnh, số frame, kích thước, số frame ghim, file nhãn, file phiên."""
        d, new = self._toplevel("info", "Thông tin job")
        for w in d.winfo_children():
            w.destroy()
        rows = [("Chưa mở thư mục ảnh nào.", "")] if not self.s else [
            ("Thư mục ảnh" if self.s.frames_dir else "Nguồn ảnh", self.s.frames_dir or self.s.title), ("Số frame", str(self.s.n_frames)),
            ("Kích thước ảnh", f"{self.s.width} × {self.s.height}"),
            ("Frame hiện tại", f"{self.f}  ({self.s.names[self.f]})"),
            ("Frame ghim", f"{len(self.s.pins)}   cần ghim: {len(self.s.need_pin)}"),
            ("Frame có nhãn", str(sum(1 for f in range(self.s.n_frames) if self.s.points_at(f)))),
            ("File nhãn đã mở", getattr(self.s, "ann_path", None) or ("nhãn đọc từ job CVAT" if self.s.cvat else "không có")),
            ("File phiên", self.state_path()), ("Chưa lưu", "có" if self.s.dirty else "không"), *self._stat_rows()]
        for r, (k, v) in enumerate(rows):
            ttk.Label(d, text=k, style="Muted.TLabel").grid(row=r, column=0, sticky="nw", padx=(12, 8), pady=3)
            ttk.Label(d, text=v, wraplength=520).grid(row=r, column=1, sticky="w", padx=(0, 12), pady=3)
        if self.s:
            box: list = []

            def compute():
                for w in box:
                    w.destroy()
                text = self.accuracy_report()
                t = tk.Text(d, width=118, height=min(26, text.count("\n") + 3), wrap="word", font=("Consolas", 9), relief="flat")
                t.insert("1.0", text)
                t.configure(state="disabled")
                t.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="we", padx=12, pady=(0, 10))
                box[:] = [t]
            ttk.Label(d, text="Độ chính xác nội suy", style="Muted.TLabel").grid(row=len(rows), column=0, sticky="nw", padx=(12, 8), pady=3)
            ttk.Button(d, text="Tính độ chính xác tại frame ghim bị giấu", command=compute).grid(row=len(rows), column=1, sticky="w", pady=3)
        d.bind("<Escape>", lambda e: d.destroy())

    def accuracy_report(self) -> str:
        """Bảng sai số tại frame ghim bị giấu của phiên đang mở (MVP 2). Chỉ tính khi được gọi: phép đo đi qua mọi frame ghim."""
        from .evaluate import evaluate, format_table
        return format_table(evaluate(self.s), "file --pins" if self.scratch else "các điểm ghim trong phiên đang mở")

    def _stat_rows(self):
        """Thống kê kiểu bảng Annotations statistics của CVAT: Manually (frame ghim), Interpolated (tool tính), Total, và số keyframe khi xuất."""
        s = self.s
        if not s.pins:
            return [("Thống kê nhãn", "chưa có frame ghim")]
        manual = len(s.pins)
        total = len(s.labels)
        rows = [("Thống kê (mỗi mắt)", f"Manually {manual} · Interpolated {total - manual} · Total {total}")]
        try:
            kf = len(next(iter(s.build_tracks().values())).keys)
            rows.append(("Keyframe khi xuất", f"{kf} (sai số nội suy CVAT tối đa 2 px), tiết kiệm {total - kf} frame so với ghim hết"))
        except ValueError:
            pass
        return rows

    def focus_frame(self):
        self.entry.focus_set()
        self.entry.selection_range(0, "end")

    def select_object(self, step: int):
        """Tab / Shift+Tab: chọn mắt kế/trước trong panel Đối tượng."""
        labels = list(EYES)
        cur, _ = self._selected()
        i = labels.index(cur) if cur in labels else (-1 if step > 0 else 0)
        self.select_eye(labels[(i + step) % len(labels)])

    def _iid(self, kind: str, key, layer: int | None = None) -> str:
        layer = self.s.cur if layer is None and self.s else (layer or 0)
        return f"{kind}:{key}" + (f"@{layer}" if layer else "")

    def select_eye(self, label: str, quiet: bool = False):
        iid = self._iid("eye", label)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            if not quiet:
                self.notice = f"Đã chọn {label}."
                self.refresh(light=True)

    def toggle_lock_all(self):
        if self.locked:
            self.locked.clear()
        else:
            self.locked.update(EYES)
        self.notice = "Đã khoá cả hai mắt." if self.locked else "Đã mở khoá cả hai mắt."
        self.refresh()

    def copy_pins(self):
        pts = self._current_points() if self.s else None
        if not pts:
            self.notice = "Frame này chưa có nhãn để sao chép."
        else:
            self.clipboard = {i: tuple(p) for i, p in pts.items()}
            self.notice = f"Đã sao chép nhãn frame {self.f}."
        self.refresh()

    @edit_command
    def paste_pins(self):
        if not self.s or not self.clipboard:
            self.notice = "Chưa sao chép nhãn nào."
        else:
            try:
                self.s.paste_points(self.f, self.clipboard)
                self.notice = f"Đã dán nhãn vào frame {self.f}; frame này thành frame ghim."
            except ValueError as err:
                self.notice = str(err)
        self.refresh()

    def _toplevel(self, name: str, title: str) -> tuple[tk.Toplevel, bool]:
        """Cửa sổ phụ dùng một lần: nếu đã mở thì đưa lên trước, trả (cửa sổ, vừa tạo mới)."""
        d = self._dialogs.get(name)
        if d is not None and d.winfo_exists():
            d.deiconify()
            d.lift()
            return d, False
        d = tk.Toplevel(self.root)
        d.title(title)
        self._dialogs[name] = d
        return d, True

    def show_shortcuts(self):
        """F1: guide phím tắt (chỉ đọc), đối chiếu với CVAT; nút lưu thành file Markdown."""
        d, new = self._toplevel("shortcuts", "Phím tắt của EyePin")
        if not new:
            return
        cols = ("eye", "cvat", "note")
        tv = ttk.Treeview(d, columns=cols, height=26)
        for c, t, w in (("#0", "Hành động", 330), ("eye", "Phím EyePin", 150), ("cvat", "Phím CVAT", 150), ("note", "Ghi chú", 330)):
            tv.heading(c, text=t)
            tv.column(c, width=w)
        for group in dict.fromkeys(a.group for a in sc.ACTIONS):
            g = tv.insert("", "end", text=group, open=True)
            for a in (x for x in sc.ACTIONS if x.group == group):
                tv.insert(g, "end", text=a.label, values=(" / ".join(sc.pretty(k) for k in self.bind_map[a.id]), a.cvat or "—", a.note))
        g = tv.insert("", "end", text="Phím CVAT không áp dụng cho mắt", open=False)
        for k, v in sc.NOT_APPLICABLE:
            tv.insert(g, "end", text=v, values=("—", k, ""))
        tv.pack(fill="both", expand=True, padx=6, pady=6)
        bar = ttk.Frame(d)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(bar, text="Chuột: cuộn = zoom · chuột phải/giữa hoặc kéo chỗ trống = dời ảnh · kéo điểm = dời điểm · kéo thân mắt = dời cả mắt").pack(side="left")
        ttk.Button(bar, text="Lưu guide ra file .md…", command=self.save_guide).pack(side="right")
        d.bind("<Escape>", lambda e: d.destroy())

    def save_guide(self):
        p = filedialog.asksaveasfilename(title="Lưu guide phím tắt", defaultextension=".md", filetypes=[("Markdown", "*.md")],
                                         initialfile="shortcuts.md")
        if p:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(sc.guide_markdown(self.bind_map))
            self.notice = f"Đã lưu guide phím tắt: {p}"

    def show_settings(self):
        """F2: Cài đặt gồm tab Player, Workspace và Phím tắt (gán lại phím)."""
        d, new = self._toplevel("settings", "Cài đặt")
        if not new:
            return
        nb = ttk.Notebook(d)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        pl, ws = self.settings["player"], self.settings["workspace"]
        t1, t2, t3 = ttk.Frame(nb), ttk.Frame(nb), ttk.Frame(nb)
        nb.add(t1, text="Player")
        nb.add(t2, text="Workspace")
        nb.add(t3, text="Phím tắt")
        step = tk.IntVar(value=pl["step"])
        speed = tk.IntVar(value=pl["speed_ms"])
        fit = tk.BooleanVar(value=pl["fit_on_frame"])
        smooth = tk.BooleanVar(value=pl["smooth"])
        bg = tk.StringVar(value=pl["bg"])

        def apply_player(*_):
            try:
                pl["step"] = max(1, int(step.get()))
                pl["speed_ms"] = max(10, int(speed.get()))
            except (tk.TclError, ValueError):
                return
            pl["fit_on_frame"], pl["smooth"], pl["bg"] = fit.get(), smooth.get(), bg.get()
            self._apply_settings_to_look_player()
            self.save_settings()
            self.refresh()

        for r, (text, w) in enumerate((("Bước nhảy frame (phím V/C)", ttk.Spinbox(t1, from_=1, to=500, textvariable=step, width=8, command=apply_player)),
                                       ("Tốc độ phát: ms mỗi frame", ttk.Spinbox(t1, from_=10, to=2000, increment=10, textvariable=speed, width=8, command=apply_player)),
                                       ("Màu nền ngoài ảnh (#rrggbb)", ttk.Entry(t1, textvariable=bg, width=10)))):
            ttk.Label(t1, text=text).grid(row=r, column=0, sticky="w", padx=8, pady=4)
            w.grid(row=r, column=1, sticky="w")
        bg_entry = t1.grid_slaves(row=2, column=1)[0]
        bg_entry.bind("<Return>", apply_player)
        ttk.Checkbutton(t1, text="Vừa khung ảnh mỗi khi đổi frame", variable=fit, command=apply_player).grid(row=3, column=0, columnspan=2, sticky="w", padx=8)
        ttk.Checkbutton(t1, text="Làm mịn ảnh khi phóng to", variable=smooth, command=apply_player).grid(row=4, column=0, columnspan=2, sticky="w", padx=8)
        rot_all = tk.BooleanVar(value=pl.get("rotate_all", True))
        show_del = tk.BooleanVar(value=pl.get("show_deleted", False))

        def apply_more(*_):
            pl["rotate_all"], pl["show_deleted"] = rot_all.get(), show_del.get()
            self.save_settings()
        ttk.Checkbutton(t1, text="Xoay tất cả ảnh (tắt: mỗi frame một hướng xoay)", variable=rot_all, command=apply_more).grid(row=5, column=0, columnspan=2, sticky="w", padx=8)
        ttk.Checkbutton(t1, text="Hiện frame đã xoá khi điều hướng", variable=show_del, command=apply_more).grid(row=6, column=0, columnspan=2, sticky="w", padx=8)
        rem = tk.BooleanVar(value=ws["remember_display"])

        def apply_ws():
            ws["remember_display"] = rem.get()
            self.save_settings()
        ttk.Checkbutton(t2, text="Nhớ cài đặt hiển thị (cỡ điểm, độ sáng, lớp…) cho lần mở sau", variable=rem, command=apply_ws).pack(anchor="w", padx=8, pady=8)
        auto = tk.BooleanVar(value=ws["autosave"])
        mins = tk.DoubleVar(value=ws["autosave_min"])

        def apply_auto(*_):
            ws["autosave"] = auto.get()
            try:
                ws["autosave_min"] = max(0.25, float(mins.get()))
            except (tk.TclError, ValueError):
                pass
            self.save_settings()
        ttk.Checkbutton(t2, text="Tự lưu phiên làm việc", variable=auto, command=apply_auto).pack(anchor="w", padx=8)
        fr = ttk.Frame(t2)
        fr.pack(anchor="w", padx=8, pady=4)
        ttk.Label(fr, text="Mỗi").pack(side="left")
        ttk.Spinbox(fr, from_=0.5, to=60, increment=0.5, textvariable=mins, width=6, command=apply_auto).pack(side="left", padx=4)
        ttk.Label(fr, text="phút (chỉ lưu khi có thay đổi)").pack(side="left")
        txt_on = tk.BooleanVar(value=ws.get("text_always", False))
        content = {k: tk.BooleanVar(value=k in ws.get("text_content", ())) for k in ("id", "label", "source")}
        fsize = tk.DoubleVar(value=ws.get("font_size", 1.0))
        pad = tk.IntVar(value=ws.get("focus_padding", 60))
        zstep = tk.DoubleVar(value=ws.get("zoom_step", 1.25))

        def apply_text(*_):
            ws["text_always"] = txt_on.get()
            ws["text_content"] = [k for k, v in content.items() if v.get()]
            try:
                ws["font_size"] = max(0.5, float(fsize.get()))
                ws["focus_padding"] = max(0, int(pad.get()))
                ws["zoom_step"] = max(1.05, float(zstep.get()))
            except (tk.TclError, ValueError):
                return
            self.look.text_always, self.look.text_content, self.look.font_size = ws["text_always"], tuple(ws["text_content"]), ws["font_size"]
            self.save_settings()
            self.refresh()
        ttk.Separator(t2).pack(fill="x", padx=8, pady=6)
        ttk.Checkbutton(t2, text="Luôn hiện chữ cạnh mắt (không chỉ khi chọn)", variable=txt_on, command=apply_text).pack(anchor="w", padx=8)
        cf = ttk.Frame(t2)
        cf.pack(anchor="w", padx=8, pady=2)
        ttk.Label(cf, text="Nội dung chữ:").pack(side="left")
        for k, text in (("id", "ID"), ("label", "Label"), ("source", "Nguồn")):
            ttk.Checkbutton(cf, text=text, variable=content[k], command=apply_text).pack(side="left", padx=4)
        for text, var, lo, hi, inc in (("Cỡ chữ (lần)", fsize, 0.5, 3.0, 0.1), ("Đệm khi phóng vào mắt (px)", pad, 0, 300, 10),
                                       ("Hệ số zoom mỗi nấc", zstep, 1.05, 2.0, 0.05)):
            rf = ttk.Frame(t2)
            rf.pack(anchor="w", padx=8, pady=2)
            ttk.Label(rf, text=text, width=26).pack(side="left")
            ttk.Spinbox(rf, from_=lo, to=hi, increment=inc, textvariable=var, width=7, command=apply_text).pack(side="left")
        self._mouse_speed_var = tk.DoubleVar(value=self.mouse_speed())
        mf = ttk.Frame(t2)
        mf.pack(anchor="w", padx=8, pady=2)
        ttk.Label(mf, text="Độ nhạy chuột khi kéo (lần)", width=26).pack(side="left")
        ms = ttk.Spinbox(mf, from_=MOUSE_SPEED_MIN, to=MOUSE_SPEED_MAX, increment=0.1, format="%.1f", textvariable=self._mouse_speed_var,
                         width=7, command=self._apply_mouse_speed)
        ms.pack(side="left")
        ms.bind("<Return>", self._apply_mouse_speed)
        ms.bind("<FocusOut>", self._apply_mouse_speed)
        ttk.Label(t2, text="1 = như cũ; nhỏ hơn 1 = chuột chậm hơn (đỡ nhạy) khi kéo điểm, kéo mắt, xoay, vẽ khung và dời ảnh.",
                  wraplength=420, foreground=theme.MUTED).pack(anchor="w", padx=8, pady=(0, 4))
        # --- tab phím tắt ---
        tv = ttk.Treeview(t3, columns=("keys", "cvat"), height=18, selectmode="browse")
        for c, t, w in (("#0", "Hành động", 300), ("keys", "Phím EyePin", 160), ("cvat", "Phím CVAT", 140)):
            tv.heading(c, text=t)
            tv.column(c, width=w)
        self._keys_tv = tv

        def fill():
            tv.delete(*tv.get_children())
            for group in dict.fromkeys(a.group for a in sc.ACTIONS):
                g = tv.insert("", "end", iid=f"g:{group}", text=group, open=True)
                for a in (x for x in sc.ACTIONS if x.group == group):
                    mark = "*" if a.id in self.settings["shortcuts"] else ""
                    tv.insert(g, "end", iid=a.id, text=a.label, values=(mark + " / ".join(sc.pretty(k) for k in self.bind_map[a.id]), a.cvat or "—"))
        fill()
        tv.pack(fill="both", expand=True, padx=4, pady=4)
        msg = tk.StringVar(value="Chọn một hành động rồi bấm \"Gán phím…\". Dấu * là phím đã đổi khỏi mặc định.")
        ttk.Label(t3, textvariable=msg, wraplength=560).pack(anchor="w", padx=6)
        row = ttk.Frame(t3)
        row.pack(fill="x", pady=4)

        def pick():
            sel = tv.selection()
            if not sel or sel[0] not in sc.BY_ID:
                msg.set("Hãy chọn một hành động (không phải tên nhóm).")
                return
            self.capture_key(sel[0], lambda err: (msg.set(err or "Đã đổi phím."), fill()))

        def default_one():
            sel = tv.selection()
            if sel and sel[0] in sc.BY_ID:
                err = self.rebind(sel[0], None)
                msg.set(err or "Đã về mặc định.")
                fill()

        def default_all():
            self.settings["shortcuts"].clear()
            self.bind_map = sc.bindings(self.settings)
            self._bind_keys()
            self.save_settings()
            msg.set("Đã đặt lại toàn bộ phím về mặc định.")
            fill()
        ttk.Button(row, text="Gán phím…", command=pick).pack(side="left", padx=3)
        ttk.Button(row, text="Về mặc định", command=default_one).pack(side="left", padx=3)
        ttk.Button(row, text="Đặt lại tất cả", command=default_all).pack(side="left", padx=3)
        ttk.Button(row, text="Mở guide (F1)", command=self.show_shortcuts).pack(side="right", padx=3)
        d.bind("<Escape>", lambda e: d.destroy())

    def _apply_settings_to_look_player(self):
        pl = self.settings["player"]
        self.look.smooth = bool(pl["smooth"])
        try:
            h = pl["bg"].lstrip("#")
            self.look.bg = (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))
            self.canvas.configure(bg=pl["bg"])
        except (ValueError, AttributeError, tk.TclError):
            pass

    def capture_key(self, aid: str, done):
        """Hộp 'bấm phím mới': bắt tổ hợp phím kế tiếp và gán cho `aid`. Esc để huỷ."""
        d = tk.Toplevel(self.root)
        d.title("Gán phím")
        ttk.Label(d, text=f"Bấm phím mới cho:\n{sc.BY_ID[aid].label}\n(Esc để huỷ)", padding=16).pack()
        d.grab_set()
        d.focus_force()

        def on_key(e):
            if e.keysym == "Escape":
                d.destroy()
                return
            seq = sc.event_to_seq(e.keysym, e.state)
            if seq is None:
                return
            err = self.rebind(aid, seq)
            d.destroy()
            done(err)
        d.bind("<KeyPress>", on_key)

    def _typing(self) -> bool:
        return self.root.focus_get() is self.entry

    # ---- mở dữ liệu ----
    def open_dir(self):
        d = filedialog.askdirectory(title="Thư mục chứa các frame (ảnh)")
        if d:
            self.load(d, getattr(self.s, "ann_path", None) if self.s else None)

    def open_xml(self):
        if not self.s:
            messagebox.showinfo("EyePin", "Hãy mở thư mục ảnh trước.")
            return
        if self.s.frames_dir is None:
            self.notice = "Đang mở từ CVAT: nhãn lấy từ chính job, không nạp file nhãn. Muốn dùng file nhãn thì mở thư mục ảnh trước."
            self.refresh(light=True)
            return
        p = filedialog.askopenfilename(title="File nhãn CVAT 1.1 (annotations.xml)", filetypes=[("XML", "*.xml")])
        if p:
            self.load(self.s.frames_dir, p, pins=self._scratch_pins if self.scratch else None)   # cùng thư mục ảnh: giữ ghim --pins và chế độ scratch

    def load(self, frames_dir: str, xml: str | None, pins: dict | None = None):
        """Mở một thư mục ảnh. `pins` (dữ liệu file --pins) thì ghim sẵn các frame đó và vào chế độ scratch: bỏ qua phiên đã lưu, không ghi đè nó.
        Dữ liệu ghim sai ném ValueError và giữ nguyên phiên đang mở."""
        if self.busy:
            self.notice = f"{self.busy} Chờ việc này xong đã."
            return
        self.playing = False
        s = Session(frames_dir, xml)
        s.ann_path = xml
        if pins is not None:
            s.load_pins(pins)
            s.dirty = False
        if self.s is not None and self.s.cvat is not None:
            self._save_outgoing()                        # đang rời một job CVAT: không để mất ghim chưa lưu
        self.s, self.scratch, self._scratch_pins = s, pins is not None, pins
        if self.scratch:
            self.notice = f"Mở bằng --pins: {len(s.pins)} frame ghim; không khôi phục và không ghi file phiên."
        else:
            self.try_restore()
        self._show_session()

    def _show_session(self):
        """Đưa cửa sổ về frame đầu của phiên `self.s` vừa đặt (mở thư mục hoặc job CVAT)."""
        self.f, self.anchor, self.clicks, self.pinning, self.manual = 0, None, [], None, None
        self.draft, self.draft_drag, self._box0 = None, None, None
        self.items = []
        self._turns_sig = ()
        self._turns_seen, self._turn_target = set(), None
        self.turn_bar.place_forget()
        self._auto_key = None
        self.listbox.delete(0, "end")
        self.total.set(f"/ {self.s.n_frames - 1}")
        self.canvas.focus_set()
        self._open_extras()                              # job CVAT đã có nhãn mắt: chế độ QC (quét, mở tab Issues)
        self.refresh()

    # ---- điều hướng ----
    def go(self, f: int):
        if self.s:
            f = max(0, min(self.s.n_frames - 1, int(f)))
            if self.draft and f != self.f:                           # mắt vẽ dở thuộc frame cũ: bỏ, không tự ghim
                self.draft, self.draft_drag = None, None
                self.notice = "Đã bỏ mắt vẽ dở (chưa Apply) vì đổi frame."
            self.f = f
            if not self.settings["player"].get("rotate_all", True):
                self.rot = self.rot_frames.get(self.f, 0)                # mỗi frame một hướng xoay riêng
            if self.settings["player"]["fit_on_frame"]:
                self.manual = None
            self.refresh()

    def step(self, delta):
        if not self.s:
            return
        if delta == "first":
            self.go(0)
        elif delta == "last":
            self.go(self.s.n_frames - 1)
        elif delta in (1, -1):
            g = self.s.next_visible(self.f, delta, bool(self.settings["player"].get("show_deleted", False)))
            if g is not None:
                self.go(g)
        else:
            self.go(self.f + delta)

    def on_entry(self, _):
        try:
            self.go(int(self.entry_var.get()))
        except ValueError:
            self.notice = "Số frame không hợp lệ."
            self._sync_entry()
        self.canvas.focus_set()

    def _click_focus(self, e, focused="now"):
        """Bấm chuột ở bất cứ đâu ngoài ô số frame khi ô đó đang giữ focus: trả focus về ảnh và trả ô về số frame hiện tại.
        Nút trên thanh và dải thời gian không lấy focus, nên nếu không có bước này mọi phím tắt sẽ lọt vào ô số frame."""
        if focused == "now":
            try:
                focused = self.root.focus_get()
            except (KeyError, tk.TclError):                  # focus ở hộp đã đóng hoặc widget lạ
                focused = None
        if focused is not self.entry or e.widget is self.entry:
            return
        self._sync_entry()
        self.canvas.focus_set()

    def on_entry_up(self, _):
        self.step(1)
        return "break"

    def on_entry_down(self, _):
        self.step(-1)
        return "break"

    def _sync_entry(self):
        self.entry_var.set(str(self.f))

    def toggle_play(self):
        if not self.s:
            return
        self.playing = not self.playing
        self.play_btn.set_icon("pause" if self.playing else "play")
        if self.playing:
            self.root.after(self.settings["player"]["speed_ms"], self._tick)

    def _tick(self):
        if not (self.playing and self.s):
            return
        if self.f >= self.s.n_frames - 1:
            self.toggle_play()
            return
        self.f += 1
        self.refresh(light=True)
        self.root.after(self.settings["player"]["speed_ms"], self._tick)

    def _key_frames(self) -> list[int]:
        """Keyframe để điều hướng: của mắt đang chọn nếu có, không thì của cả job."""
        label, _ = self._selected() if self.s else (None, None)
        return self.s.eye_keyframes(label) if label else sorted(self.s.pins)

    def first_keyframe(self):
        ks = self._key_frames() if self.s else []
        if ks:
            self.go(ks[0])
        else:
            self.notice = "Chưa có keyframe nào."
            self.refresh()

    def last_keyframe(self):
        ks = self._key_frames() if self.s else []
        if ks:
            self.go(ks[-1])
        else:
            self.notice = "Chưa có keyframe nào."
            self.refresh()

    def jump_pin(self, step: int):
        if not self.s:
            return
        ks = self._key_frames()
        cand = [g for g in ks if g > self.f] if step > 0 else [g for g in ks if g < self.f][::-1]
        if not cand:
            self.notice = "Không còn keyframe nào theo hướng này."
            self.refresh()
        else:
            self.go(cand[0])

    @edit_command
    def start_pin(self, mode: str = "full"):
        if self.s:
            self.playing = False
            if mode == "full" and self.s.missing_eyes():          # một mắt đã bị xoá: chỉ cần ghim lại mắt đó (4 điểm)
                mode = "one"
            self.pinning, self.clicks = mode, []
            self.canvas.focus_set()
            self.refresh()

    def cancel_pin(self):
        if not self.pinning and not self.draft and self.root.attributes("-fullscreen"):
            self.toggle_fullscreen()
            return
        self.pinning, self.clicks = None, []
        self.draft, self.draft_drag, self._box0 = None, None, None
        self.refresh()

    # ---- vẽ từng mắt kiểu CVAT: chọn label, bấm 4 điểm hoặc kéo khung, chỉnh, Apply ----
    @edit_command
    def start_draw(self):
        """Phím N / nút vẽ: bảng nhỏ chọn label (mắt trái, mắt phải), kiểu và cách vẽ, như bảng vẽ skeleton của CVAT.
        Đang có mắt vẽ dở thì N là Apply (CVAT cũng dùng N để kết thúc lần vẽ)."""
        if not self.s:
            return
        if self.draft:
            self.apply_draft()
            return
        self.playing = False
        d, _ = self._toplevel("draw", "Vẽ mắt")
        for w in d.winfo_children():
            w.destroy()
        d.transient(self.root)
        pts = self.s.points_at(self.f) or {}
        here = [l for l in EYES if all(i in pts for i in EYES[l].ids)]
        default = next((l for l in EYES if l not in here), self._selected()[0] or "mattrai")
        self._draw_label_values = [DRAW_LABELS[l] for l in EYES]
        self._draw_label_var = tk.StringVar(value=DRAW_LABELS[default])
        self._draw_kind_var = tk.StringVar(value="track")
        ttk.Label(d, text="Label").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
        ttk.Combobox(d, textvariable=self._draw_label_var, values=self._draw_label_values, state="readonly",
                     width=24).grid(row=0, column=1, columnspan=2, sticky="we", padx=(0, 10), pady=(10, 4))
        ttk.Label(d, text="Kiểu").grid(row=1, column=0, sticky="w", padx=10)
        ttk.Radiobutton(d, text="Track", value="track", variable=self._draw_kind_var).grid(row=1, column=1, sticky="w")
        shape = ttk.Radiobutton(d, text="Shape (chưa hỗ trợ)", value="shape", variable=self._draw_kind_var)
        shape.state(["disabled"])
        shape.grid(row=1, column=2, sticky="w", padx=(0, 10))

        def go(method):
            label = self._draw_label_var.get().split()[0]
            d.destroy()
            self.begin_draw(label, method)
        ttk.Label(d, text="Vẽ bằng").grid(row=2, column=0, sticky="w", padx=10, pady=(8, 10))
        ttk.Button(d, text="Bấm 4 điểm", command=lambda: go("points")).grid(row=2, column=1, sticky="we", pady=(8, 10))
        ttk.Button(d, text="Kéo khung", command=lambda: go("box")).grid(row=2, column=2, sticky="we", padx=(0, 10), pady=(8, 10))
        d.bind("<Escape>", lambda e: d.destroy())
        d.geometry(f"+{self.root.winfo_rootx() + 70}+{self.root.winfo_rooty() + 140}")

    @edit_command
    def begin_draw(self, label: str, method: str = "points"):
        """Bắt đầu vẽ mắt `label`: method "points" = bấm 4 điểm (2 khoé, giữa hai mí, thứ tự tuỳ ý); "box" = kéo khung, mắt mẫu hiện ra."""
        if not self.s:
            return
        self.playing = False
        self.draft, self.draft_drag, self._box0 = None, None, None
        self.draw_label = label
        self.pinning, self.clicks = ("draw4" if method == "points" else "drawbox"), []
        self.notice = ""
        self.canvas.focus_set()
        self.refresh()

    @edit_command
    def apply_draft(self):
        """Nút Apply: ghim mắt vừa vẽ thành keyframe (track) của riêng mắt đó ở frame này; tool bám nó sang các frame sau."""
        if not (self.s and self.draft):
            return
        label, four = self.draft["label"], self.draft["four"]
        try:
            self.s.pin_eye(self.f, label, dict(four))
        except ValueError as err:
            self.notice = f"Không ghim được: {err}. Kéo lại các điểm rồi bấm Apply, hoặc Esc để huỷ."
            self.refresh()
            return
        self.draft, self.draft_drag = None, None
        self.notice = f"Đã ghim {label} ở frame {self.f} (track): tool bám mắt này sang các frame sau."
        self.refresh()
        self.select_eye(label, quiet=True)

    def _press_draw(self, e, p):
        if self.pinning == "drawbox":
            self._box0 = p
            return
        if self.pinning == "draw4":
            self.clicks.append((len(self.clicks) + 1, p))
            if len(self.clicks) == PIN_COUNT["draw4"]:
                try:
                    self.draft = {"label": self.draw_label, "four": assign_roles(EYES[self.draw_label], [q for _, q in self.clicks])}
                    self.pinning = None
                except ValueError as err:
                    self.notice = f"Chưa vẽ được: {err}"
                self.clicks = []
            self.refresh()
            return
        # đang có bản nháp: bấm trúng một trong 4 điểm to thì kéo điểm đó, không thì dời ảnh
        pid, q = min(self.draft["four"].items(), key=lambda kv: math.dist(self.view.to_screen(kv[1]), (e.x, e.y)))
        if math.dist(self.view.to_screen(q), (e.x, e.y)) <= 10:
            self.draft_drag = pid
            return
        self._pan = (e.x, e.y)
        self._left_pan = True

    def _draft_box(self, a, b) -> dict:
        """Mắt mẫu trong khung từ góc a tới góc b (toạ độ frame). Khung quá dẹt thì cho cao bằng 0,4 lần bề rộng."""
        x0, y0, x1, y1 = a[0], a[1], b[0], b[1]
        w = abs(x1 - x0)
        if abs(y1 - y0) < 0.15 * w:
            cy = (y0 + y1) / 2
            y0, y1 = cy - 0.2 * w, cy + 0.2 * w
        return {"label": self.draw_label, "four": four_in_box(EYES[self.draw_label], (x0, y0, x1, y1))}

    @edit_command
    def remove_pin(self):
        if self.s and self.f in self.s.pins:
            self.s.remove_pin(self.f)
            self.notice = "Đã bỏ frame ghim."
            self.refresh()

    @edit_command
    def toggle_pin_here(self):
        if not self.s:
            return
        try:
            label, _ = self._selected()
            if label:                                                 # có mắt đang chọn: chỉ đổi keyframe của mắt đó (như phím K của CVAT)
                on = self.s.toggle_eye_key(label, self.f)
                self.notice = f"{label}: đã ghim keyframe ★ ở frame này." if on else f"{label}: đã bỏ keyframe ở frame này."
            else:
                self.notice = "Đã ghim frame này từ nhãn tool tính." if self.s.toggle_pin_here(self.f) else "Đã bỏ ghim frame này."
        except ValueError as err:
            self.notice = str(err)
        self.refresh()

    # ---- xoay ảnh và công cụ canvas ----
    @property
    def render_size(self) -> tuple[int, int]:
        """Kích thước vẽ ảnh trước khi xoay: đổi chỗ rộng và cao khi đang xoay 90 hoặc 270 độ."""
        w, h = self.main_size
        return (h, w) if self.rot % 2 else (w, h)

    def _unrot(self, e):
        """Đổi toạ độ chuột trên khung đã xoay về toạ độ trên ảnh chưa xoay (nơi mọi phép tính hình học diễn ra)."""
        r = self.rot % 4
        if r == 0:
            return e
        w0, h0 = self.render_size
        x, y = e.x, e.y
        if r == 1:
            nx, ny = y, h0 - x
        elif r == 2:
            nx, ny = w0 - x, h0 - y
        else:
            nx, ny = w0 - y, x
        return _Pt(nx, ny, getattr(e, "delta", 0))

    def mouse_speed(self) -> float:
        """Độ nhạy chuột khi kéo (Cài đặt > Workspace), kẹp trong 0,1–3; giá trị hỏng thì dùng 1 (như cũ)."""
        try:
            v = float(self.settings["workspace"].get("mouse_speed", 1.0))
        except (TypeError, ValueError):
            return 1.0
        if v != v:                                                  # NaN
            return 1.0
        return min(MOUSE_SPEED_MAX, max(MOUSE_SPEED_MIN, v))

    def _scaled(self, e):
        """Nhân quãng chuột đã kéo từ chỗ bấm với độ nhạy: nhỏ hơn 1 thì con trỏ đi xa mà điểm chỉ đi một phần.
        Tính từ chỗ bấm nên bấm xong chưa kéo thì không có gì nhảy; độ nhạy 1 trả nguyên sự kiện."""
        s = self.mouse_speed()
        if self._m0 is None or s == 1.0:
            return e
        x0, y0 = self._m0
        return _Pt(x0 + (e.x - x0) * s, y0 + (e.y - y0) * s, getattr(e, "delta", 0))

    def _apply_mouse_speed(self, *_):
        try:
            v = float(self._mouse_speed_var.get())
        except (tk.TclError, ValueError):
            return
        self.settings["workspace"]["mouse_speed"] = round(min(MOUSE_SPEED_MAX, max(MOUSE_SPEED_MIN, v)), 2)
        self.save_settings()

    def _to_canvas(self, q):
        """Toạ độ trên khung vẽ chưa xoay -> toạ độ trên Canvas đã xoay ảnh (phép ngược của `_unrot`)."""
        r = self.rot % 4
        if r == 0:
            return q
        w0, h0 = self.render_size
        x, y = q
        return (h0 - y, x) if r == 1 else (w0 - x, h0 - y) if r == 2 else (y, w0 - x)

    def set_tool(self, name: str):
        self.tool = name
        for n, b in self.tool_btns.items():
            b.set_active(n == name)
        self.canvas.configure(cursor="fleur" if name == "hand" else "")
        self.notice = "Công cụ Dời ảnh: kéo chuột để dời ảnh." if name == "hand" else "Công cụ Con trỏ: kéo điểm hoặc cả mắt."
        self.refresh(light=True)

    def rotate(self, step: int):
        """Xoay cách nhìn 90 độ (chỉ ảnh và nhãn hiển thị, toạ độ nhãn không đổi); khung nhìn tự vừa lại."""
        self.rot = (self.rot + step) % 4
        if not self.settings["player"].get("rotate_all", True):
            self.rot_frames[self.f] = self.rot
        self.manual = None
        self._auto_key = None
        self.notice = f"Đã xoay ảnh {self.rot * 90}°." if self.rot else "Đã bỏ xoay ảnh."
        self.refresh()

    # ---- xoay nhãn (một mắt quanh tâm của nó) ----
    def _eye_points(self, label: str):
        pts = self._current_points()
        if not pts or not all(i in pts for i in EYES[label].ids):
            return None
        return {i: pts[i] for i in EYES[label].ids}

    @staticmethod
    def _rotated(pts: dict, center, delta: float) -> dict:
        c, sn, cs = center, math.sin(delta), math.cos(delta)
        return {i: (c[0] + (x - c[0]) * cs - (y - c[1]) * sn, c[1] + (x - c[0]) * sn + (y - c[1]) * cs) for i, (x, y) in pts.items()}

    @staticmethod
    def _bbox(pts: dict):
        xs, ys = [p[0] for p in pts.values()], [p[1] for p in pts.values()]
        return min(xs), min(ys), max(xs), max(ys)

    def _handle_for(self, label: str):
        """Giống CVAT (đã thử trên CVAT 2.75 local): khung chữ nhật thẳng bao skeleton, tâm xoay là tâm khung đó, tay cầm là chấm tròn
        cách cạnh trên khung một đoạn cố định. Khi đang kéo, tay cầm quay theo góc kéo; thả ra thì khung tính lại thẳng như CVAT.
        Trả (gốc tay cầm, tay cầm, tâm xoay, khung (x0, y0, x1, y1)). Đang kéo cạnh/góc khung thì khung theo hình mới."""
        pts = self._resize_override() if self.drag_resize and self.drag_resize[0] == label else self._eye_points(label)
        if not pts or self.view is None:
            return None
        x0, y0, x1, y1 = self._bbox(pts)
        c = ((x0 + x1) / 2, (y0 + y1) / 2)
        d = ROTATE_DIST / self.view.k
        a, h = (c[0], y0), (c[0], y0 - d)
        if self.drag_rot and self.drag_rot[0] == label:
            c = self.drag_rot[1]
            delta = self.drag_rot[3] - self.drag_rot[2]
            rot = self._rotated(pts, c, delta)
            box = self._bbox(rot)
            a, h = self._rotated({0: (c[0], y0), 1: (c[0], y0 - d)}, c, delta).values()
            return a, h, c, box
        return a, h, c, (x0, y0, x1, y1)

    def _handle_arg(self):
        label, _ = self._selected() if self.s else (None, None)
        if label is None or self.hide_labels or label in self.locked or label in self.pinned_eyes or not self.look.eyes.get(label, True):
            return None
        h = self._handle_for(label)
        if not h:
            return None
        n = self.s.obj_ids.get(label)
        return h[0], h[1], h[3], ("" if self.look.text_always else f"{label.upper()}" + (f" #{n}" if n else ""))

    def _resize_hit(self, e) -> str | None:
        """Tay cầm đổi kích thước dưới con trỏ (trong 8 px). Tay cầm cạnh trái/phải nằm sát khoé mắt, nên nếu một điểm của nhãn gần con trỏ
        hơn thì nhường cho việc kéo điểm."""
        hh = self._handle_arg()
        if hh is None or len(hh) < 3 or not hh[2]:
            return None
        name, q = min(resize_handles(self.view, hh[2]).items(), key=lambda kv: math.dist(kv[1], (e.x, e.y)))
        d = math.dist(q, (e.x, e.y))
        if d > RESIZE_HIT:
            return None
        pid = self._nearest_pin_point((e.x, e.y))
        if pid is not None and math.dist(self.view.to_screen(self._current_points()[pid]), (e.x, e.y)) <= d:
            return None
        return name

    def _resize_override(self):
        """Điểm mới của mắt đang đổi kích thước: cạnh (hoặc góc) đang kéo dời theo chuột, cạnh đối diện đứng yên, các điểm co giãn theo tỉ lệ."""
        label, name, box, a, b = self.drag_resize
        x0, y0, x1, y1 = box
        dx, dy = b[0] - a[0], b[1] - a[1]
        nx0, nx1 = x0 + (dx if "w" in name else 0), x1 + (dx if "e" in name else 0)
        ny0, ny1 = y0 + (dy if "n" in name else 0), y1 + (dy if "s" in name else 0)
        m = 4 / self.view.k                                           # không cho lật ngược hay co về một đường: tối thiểu 4 px màn hình
        if nx1 - nx0 < m:
            nx0, nx1 = (nx1 - m, nx1) if "w" in name else (nx0, nx0 + m)
        if ("n" in name or "s" in name) and ny1 - ny0 < m:
            ny0, ny1 = (ny1 - m, ny1) if "n" in name else (ny0, ny0 + m)
        sx = (nx1 - nx0) / (x1 - x0) if x1 - x0 > 1e-6 else 1.0
        sy = (ny1 - ny0) / (y1 - y0) if y1 - y0 > 1e-6 else 1.0
        return {i: (nx0 + (x - x0) * sx, ny0 + (y - y0) * sy) for i, (x, y) in self._eye_points(label).items()}

    def _rot_override(self):
        if not self.drag_rot:
            return None
        label, c, a0, a1 = self.drag_rot
        return self._rotated(self._eye_points(label), c, a1 - a0)

    @edit_command
    def rotate_eye(self, deg: float):
        """Phím: xoay mắt đang chọn `deg` độ (dương = theo chiều kim đồng hồ trên màn hình) quanh tâm của nó."""
        label, _ = self._selected() if self.s else (None, None)
        if label is None:
            self.notice = "Chọn một mắt trong panel Đối tượng (hoặc bấm vào mắt) trước khi xoay."
        elif label in self.locked or label in self.pinned_eyes:
            self.notice = "Mắt này đang bị khoá hoặc Pinned."
        elif self._eye_points(label) is None:
            self.notice = "Frame này chưa có nhãn để xoay."
        else:
            h = self._handle_for(label)
            try:
                new = self._rotated(self._eye_points(label), h[2], math.radians(deg))
                self.s.drag_points(self.f, new)
                self.notice = f"Đã xoay {label} {deg:+g}°."
            except ValueError as err:
                self.notice = str(err)
        self.refresh()

    def on_canvas_resize(self, e):
        """Khung ảnh đổi kích thước theo cửa sổ (kể cả toàn màn hình); vẽ lại ảnh cho vừa."""
        size = (max(200, e.width), max(120, e.height))
        if size == self.main_size:
            return
        self.main_size = size
        if self.manual is not None:
            rw, rh = self.render_size
            self.manual = type(self.manual)(self.manual.x0, self.manual.y0, self.manual.k, rw, rh)
        if self.s:
            self.refresh()

    def set_filter(self):
        self.filter = self._filter_var.get()
        self.filter_btn.set_active(self.filter != "all")
        self.notice = f"Bộ lọc: {Session.FILTERS[self.filter]}" + ("" if self.filter == "all" else " — ←/→ nhảy tới frame thoả bộ lọc.")
        self.refresh()

    def search(self, step: int):
        """←/→: frame kế/trước thoả bộ lọc; không lọc thì đi từng frame."""
        if not self.s:
            return
        if self.filter == "all":
            self.step(step)
            return
        g = self.s.next_match(self.f, step, self.filter)
        if g is None:
            self.notice = f"Không còn frame nào thoả '{Session.FILTERS[self.filter]}' theo hướng này."
            self.refresh()
        else:
            self.go(g)

    # ---- panel Đối tượng ----
    def _on_tree_select(self, _=None):
        """Chọn dòng của bộ đối tượng khác thì chuyển sang bộ đó (mọi thao tác sau đó tác động lên đối tượng vừa chọn)."""
        sel = self.tree.selection()
        if self.s and sel:
            layer = int(sel[0].partition("@")[2] or 0)
            if layer != self.s.cur and layer < len(self.s.layers):
                self.s.select_layer(layer)
                self.refresh()
                return
        self.refresh(light=True)

    def _pick_layer(self, sx: float, sy: float) -> None:
        """Bấm trúng mắt của bộ đối tượng khác (và không trúng mắt nào của bộ đang chọn) thì chuyển sang bộ đó."""
        s = self.s
        if len(s.layers) < 2 or self.pinning or self.hide_labels:
            return
        if self._nearest_pin_point((sx, sy)) is not None or self._eye_at((sx, sy)) is not None:
            return
        for i in range(len(s.layers)):
            if i == s.cur:
                continue
            with s.layer_ctx(i):
                hit = self._nearest_pin_point((sx, sy)) is not None or self._eye_at((sx, sy)) is not None
                label = self._eye_at((sx, sy))
            if hit:
                s.select_layer(i)
                iid = self._iid("eye", label or "mattrai", i)       # chọn dòng của mắt vừa bấm để phần chọn trong panel khớp với bộ mới
                if self.tree.exists(iid):
                    self.tree.selection_set(iid)
                self.refresh()
                return

    def _selected(self):
        """(mắt, điểm hoặc None) đang chọn trong panel Đối tượng."""
        sel = self.tree.selection()
        if not sel:
            return None, None
        kind, _, val = sel[0].partition(":")
        layer = int(val.partition("@")[2] or 0)                  # dòng của bộ đối tượng thứ hai trở đi có hậu tố @chỉ_số
        if self.s and layer != self.s.cur and layer < len(self.s.layers):
            self.s.select_layer(layer)                           # chọn đối tượng của người nào thì thao tác tác động lên người đó
        val = val.partition("@")[0]
        if kind == "eye":
            return val, None
        pid = int(val)
        return next(l for l, sp in EYES.items() if pid in sp.ids), pid

    def toggle_lock(self):
        label, _ = self._selected()
        if label is None:
            self.notice = "Chọn một mắt trong panel Đối tượng trước."
        elif label in self.locked:
            self.locked.discard(label)
            self.notice = f"Đã mở khoá {label}."
        else:
            self.locked.add(label)
            self.notice = f"Đã khoá {label}: không kéo được."
        self.refresh()

    def toggle_eye_hidden(self):
        label, _ = self._selected()
        if label is None:
            self.notice = "Chọn một mắt trong panel Đối tượng trước."
            self.refresh()
            return
        self._layer_vars[label].set(not self.look.eyes[label])
        self.set_layer(label)

    def refresh_objects(self):
        keep = self.tree.selection()
        open_ = {i: self.tree.item(i, "open") for i in self.tree.get_children()}
        self.tree.delete(*self.tree.get_children())
        if not self.s:
            return
        s = self.s
        rows = self._object_rows()
        self.items_var.set(f"Items: {len(rows)}")
        for layer, label in rows:
            with s.layer_ctx(layer):
                pts = self._current_points()
                flags = s.flags_at(self.f)
                keys = s.eye_keyframes(label)
                eye = self._eye_points(label)
                star = "★" if self.f in keys else "☆"                     # ngôi sao đặc = frame này là keyframe của riêng đối tượng đó
                in_file = s.qc and (s.points_at(self.f) or {}).keys() >= set(EYES[label].ids)        # QC: nhãn đọc từ job, chưa có điểm ghim nào
                src = "keyframe" if self.f in keys else ("tool tính" if self.f in s.labels and eye else ("từ file" if eye or in_file else "chưa có"))
                n = s.obj_ids.get(label)
                gone = bool(s.pins) and eye is None
                mark = ("[khoá] " if label in self.locked else "") + ("[pinned] " if label in self.pinned_eyes else "") + ("[ẩn] " if not self.look.eyes[label] else "")
            eid = self._iid("eye", label, layer)
            self.tree.insert("", "end", iid=eid, text=(f"#{n}  " if n else "") + f"{mark}{label}" + ("  (không có nhãn)" if gone else ""),
                             values=("skeleton track", star, "đã xoá" if gone else src), open=open_.get(eid, False))
            for pid in EYES[label].ids:
                k = flags.get(pid)
                state = {"occluded": "Occluded", "outside": "Outside"}.get(k, "" if pts and pid in pts else "—")
                self.tree.insert(eid, "end", iid=self._iid("pt", pid, layer), text=f"điểm {pid}",
                                 values=("ghim" if pid in PIN_IDS else "suy ra", star, state))
        for i in keep:
            if self.tree.exists(i):
                self.tree.selection_set(i)

    @net_safe
    def on_tree_click(self, e):
        """Bấm vào ngôi sao trong panel Đối tượng = ghim / bỏ ghim keyframe tại frame hiện tại (như nút ngôi sao của CVAT)."""
        if self.tree.identify_region(e.x, e.y) == "cell" and self.tree.identify_column(e.x) == "#2" and self.s:
            if self._edit_blocked():                                  # QC hoặc đang có việc nền: bấm ★ cũng là sửa nhãn
                return "break"
            try:
                row = self.tree.identify_row(e.y)
                lab = None
                layer = int(row.partition("@")[2] or 0) if row else 0
                if layer != self.s.cur and layer < len(self.s.layers):
                    self.s.select_layer(layer)
                if row.startswith("eye:"):
                    lab = row.split(":")[1].partition("@")[0]
                elif row.startswith("pt:"):
                    pid = int(row.split(":")[1].partition("@")[0])
                    lab = next(l for l, sp in EYES.items() if pid in sp.ids)
                on = self.s.toggle_eye_key(lab, self.f) if lab else self.s.toggle_pin_here(self.f)
                self.notice = "Đã ghim frame này (keyframe ★)." if on else "Đã bỏ keyframe ở frame này."
            except ValueError as err:
                self.notice = str(err)
            self.refresh()
            return "break"

    def hover_on_point(self) -> bool:
        return bool(self.hover and self.view and self.s and self._current_points() and self._nearest_pin_point(self.hover) is not None)

    # ---- báo đoạn quay đầu cho người dùng chỉnh tay ----
    def _announce_turns(self):
        """Có đoạn quay đầu mới (không trùng đoạn nào đã báo) thì hiện thanh báo ở đáy ảnh: các đoạn, mức co, mắt xa, và lời nhắc chỉnh tay.
        Đoạn chỉ xê dịch ranh giới sau khi ghim thêm thì không báo lại."""
        rows = self._turn_rows()
        seen = self._turns_seen
        new = [(i, k, t) for i, k, t in rows
               if not any(i == j and t.first <= b and a <= t.last for j, a, b in seen)]
        self._turns_seen = {(i, t.first, t.last) for i, _, t in rows}
        if not new:
            return
        self._turn_target = (new[0][0], new[0][2].first)
        parts = []
        for i, k, t in rows:
            detail = (f"co {t.shrink * 100:.0f}%" if t.shrink is not None else "mất một mắt") + (f", mắt xa {t.far_eye}" if t.far_eye else "")
            parts.append((f"Người {i + 1} " if len(self.s.layers) > 1 else "") + f"#{k} frame {t.first}–{t.last} ({detail})")
        self.turn_text.set("Phát hiện quay đầu: " + "; ".join(parts) +
                           ". Mắt xa có thể bị che hoặc bộ bám trôi: kiểm tra và chỉnh tay các frame này.")
        self.turn_bar.place(relx=0.5, rely=1.0, y=-36, anchor="s")         # nằm trên nút ^ (Image setups) ở giữa mép dưới

    def turn_jump(self):
        """Nút "Tới đoạn quay đầu": nhảy tới frame đầu của đoạn mới nhất (chọn đúng người nếu job nhiều người)."""
        if not (self.s and self._turn_target):
            return
        layer, f = self._turn_target
        if layer != self.s.cur and layer < len(self.s.layers):
            self.s.select_layer(layer)
        self.go(f)

    def dismiss_turns(self):
        self.turn_bar.place_forget()

    def on_leave(self, _e=None):
        """Chuột rời khung ảnh: quên vị trí cũ, để phím Q/O và nút ở panel dùng phần đang chọn chứ không dùng một điểm cũ trên ảnh."""
        self.hover = None

    @edit_command
    def toggle_flag(self, kind: str):
        """Q / O và nút Occluded, Outside ở panel. Thứ tự: điểm gần con trỏ trên ảnh; điểm đang chọn trong panel; cả mắt đang chọn (như cờ của
        cả đối tượng trong CVAT). Ở frame do tool tính, như CVAT, frame thành keyframe của riêng mắt đó."""
        if not self.s:
            return
        if self.hide_labels:
            self.notice = f"Nhãn đang ẩn; bấm {self.kl('hide_all')} để hiện lại trước khi đánh dấu điểm."
            self.refresh()
            return
        name = {"occluded": "Occluded", "outside": "Outside"}[kind]
        label, sel_pid = self._selected()
        pid = self._nearest_pin_point(self.hover) if self.hover and self.view and self._current_points() else None
        pid = pid if pid is not None else sel_pid
        target = next((l for l, sp in EYES.items() if pid in sp.ids), None) if pid is not None else label
        if target is None:
            self.notice = ("Hãy đưa con trỏ chuột lại gần một điểm rồi bấm phím." if self.hover
                           else "Chọn một điểm hoặc một mắt trong panel Đối tượng trước.")
            self.refresh()
            return
        was_key = self.f in self.s.eye_keyframes(target)
        if pid is not None:
            new = self.s.toggle_flag(self.f, pid, kind)
            what = f"Điểm {pid} ({target})"
        else:
            new = self.s.toggle_eye_flag(self.f, target, kind)
            what = f"{target}: cả 8 điểm"
        if not was_key and self.f not in self.s.eye_keyframes(target):
            self.notice = f"Frame này chưa có nhãn của {target}; hãy vẽ hoặc ghim mắt đó trước."
        else:
            self.notice = f"{what}: " + (name if new else f"bỏ {name}") + ("" if was_key else f". Frame này đã thành keyframe của {target}.")
        self.refresh()

    def _current_points(self):
        return self.s.labels[self.f].points if self.f in self.s.labels else self.s.pins.get(self.f)

    def _eye_at(self, screen_xy):
        """Mắt (nhãn) nằm dưới con trỏ: bên trong hoặc sát đường viền (trong 14 px màn hình)."""
        pts = self._current_points()
        if not pts:
            return None
        p = self.view.to_frame(*screen_xy)
        best = None
        for label, spec in EYES.items():
            if not all(i in pts for i in spec.ids):
                continue
            poly = np.array([pts[i] for i in spec.ids], np.float32).reshape(-1, 1, 2)
            d = cv2.pointPolygonTest(poly, (float(p[0]), float(p[1])), True) * self.view.k      # >0 bên trong (px màn hình)
            if d > -14 and (best is None or d > best[0] or (d == best[0] and label == self.look.top)):
                best = (d, label)
        return best[1] if best else None

    def _eye_shift(self):
        """Điểm mới của mắt đang kéo: mọi điểm dời cùng một vectơ."""
        label, a, b = self.drag_eye
        pts = self._current_points()
        dx, dy = b[0] - a[0], b[1] - a[1]
        return {i: (pts[i][0] + dx, pts[i][1] + dy) for i in EYES[label].ids}

    def _nearest_pin_point(self, screen_xy, radius: float = 14):
        p = self.view.to_frame(*screen_xy)
        pts = self.s.labels[self.f].points if self.f in self.s.labels else self.s.pins.get(self.f)
        if not pts:
            return None
        pid, q = min(pts.items(), key=lambda kv: (kv[1][0] - p[0]) ** 2 + (kv[1][1] - p[1]) ** 2)
        return pid if ((q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2) ** 0.5 * self.view.k < radius else None

    @edit_command
    def undo(self):
        if not self.s:
            return
        if self.pinning and self.clicks:
            self.clicks.pop()
            self.notice = "Đã bỏ điểm vừa bấm."
        elif self.s.undo():
            self.notice = "Đã hoàn tác."
        elif self.leave_qc_by_undo():
            pass                                                     # vừa xoá nhãn mắt cũ và chưa ghim gì: về lại chế độ QC
        else:
            self.notice = "Không còn gì để hoàn tác."
        self.refresh()

    @edit_command
    def redo(self):
        if self.s:
            self.notice = "Đã làm lại." if self.s.redo() else "Không còn gì để làm lại."
            self.refresh()

    def scan(self):
        if not self.s:
            return
        self.s.run_scan()
        self._fill_issues()
        self.refresh()

    def export(self):
        if not self.s or not self.s.pins:
            messagebox.showinfo("EyePin", "Chưa có frame ghim nào để xuất.")
            return
        p = filedialog.asksaveasfilename(title="Lưu file import", defaultextension=".xml", filetypes=[("XML", "*.xml")],
                                         initialfile="eyepin_import.xml")
        if p:
            info = self.s.export(p)
            messagebox.showinfo("EyePin", f"Đã ghi {info['keyframes']} keyframe cho {info['frames']} frame.\n{p}\n\n"
                                          "File chứa mọi nhãn của job; import vào job sẽ thay thế toàn bộ nhãn cũ.")

    def on_list(self, _):
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.items):
            self.go(self.items[sel[0]])

    def on_timeline(self, e):
        if self.s:
            self.go(int(e.x / max(1, self.timeline.winfo_width()) * self.s.n_frames))

    # ---- zoom và dời ảnh ----
    def zoom(self, factor: float, at: tuple[float, float] | None = None):
        if self.s and self.view:
            sx, sy = at or (self.render_size[0] / 2, self.render_size[1] / 2)
            self.manual = self.view.zoomed_at(sx, sy, factor)
            self.refresh(light=True)

    def fit(self):
        self.manual = None
        self._auto_key = None                # canh lại theo nhãn hiện tại kể cả khi vẫn ở frame cũ
        self.refresh()

    def toggle_labels(self):
        """Ẩn/hiện toàn bộ nhãn để nhìn rõ ảnh (như phím H của CVAT). Khi ẩn, không kéo hay đánh cờ được điểm."""
        self.hide_labels = not self.hide_labels
        self.eye_btn.set_icon("eye_off" if self.hide_labels else "eye")
        self.eye_btn.set_active(self.hide_labels)
        self.notice = f"Đã ẩn nhãn (bấm {self.kl('hide_all')} để hiện lại)." if self.hide_labels else "Đã hiện nhãn."
        self.refresh()

    def set_layer(self, name: str):
        on = self._layer_vars[name].get()
        if name in EYES:
            self.look.eyes[name] = on
        else:
            setattr(self.look, name, on)
        self.show_ids = self.look.ids
        self.refresh()

    def set_look(self, **kw):
        for k, v in kw.items():
            setattr(self.look, k, v)
        self.refresh()

    def reset_adjust(self):
        """Như nút "Reset color settings" của CVAT: độ sáng, tương phản, bão hoà, gamma về mặc định; không đụng lưới."""
        for n, init in imagefx.COLOR_DEFAULTS.items():
            self._setup_vars[n].set(init)
            setattr(self.look, n, init)
        self.notice = "Đã đặt lại độ sáng, tương phản, bão hoà, gamma."
        self.refresh()

    def _sync_top(self):
        names = {"mattrai": "mắt trái", "matphai": "mắt phải"}
        self.top_btn.configure(text=f"Lớp trên cùng: {names[self.look.top]} ({self.kl('swap_top')} đổi)")

    def swap_top(self):
        self.look.top = "mattrai" if self.look.top == "matphai" else "matphai"
        self._sync_top()
        self.refresh()

    def resize_markers(self, factor: float):
        self.look.size = min(3.0, max(0.4, self.look.size * factor))
        self.size_var.set(self.look.size)
        self.notice = f"Cỡ điểm ×{self.look.size:.2f}"
        self.refresh()

    def toggle_ids(self):
        self.look.ids = not self.look.ids
        self.show_ids = self.look.ids
        self._layer_vars["ids"].set(self.look.ids)
        self.refresh()

    def on_wheel(self, e):
        e = self._unrot(e)
        z = self.zoom_step()
        self.zoom(z if e.delta > 0 else 1 / z, (e.x, e.y))

    def on_pan_start(self, e):
        e = self._unrot(e)
        self._m0 = (e.x, e.y)
        self._pan = (e.x, e.y)

    def on_pan_end(self, _e=None):
        self._m0 = None

    def on_pan(self, e):
        self._pan_to(self._scaled(self._unrot(e)))

    def _pan_to(self, e):
        """Dời ảnh theo quãng chuột từ lần dời trước; `e` đã đổi về khung chưa xoay và đã nhân độ nhạy."""
        if self.s and self.view and self._pan:
            self.manual = self.view.panned(e.x - self._pan[0], e.y - self._pan[1])
            self._pan = (e.x, e.y)
            self.refresh(light=True)

    # ---- chuột trên khung chính ----
    def on_hover(self, e):
        e = self._unrot(e)
        self.hover = (e.x, e.y)

    @net_safe
    def on_press(self, e):
        e = self._unrot(e)
        self._m0 = (e.x, e.y)
        if not self.s or self.view is None:
            return
        self.canvas.focus_set()
        if self.tool == "hand" and not self.pinning:
            self._pan = (e.x, e.y)
            self._left_pan = True
            return
        if self.busy or self.s.qc:                                   # QC hoặc đang có việc nền: không vào chế độ vẽ, không kéo nhãn
            self._press_read_only(e)
            return
        p = self.view.to_frame(e.x, e.y)
        if self.pinning in ("draw4", "drawbox") or self.draft:
            self._press_draw(e, p)
            return
        self._pick_layer(e.x, e.y)
        if not self.pinning and (hh := self._handle_arg()) is not None:
            hs = self.view.to_screen(hh[1])
            if math.hypot(hs[0] - e.x, hs[1] - e.y) <= ROTATE_HIT:      # bấm trúng tay cầm xoay
                label = self._selected()[0]
                c = self._handle_for(label)[2]
                a = math.atan2(hh[1][1] - c[1], hh[1][0] - c[0])
                self.manual = self.view
                self.drag_rot = (label, c, a, a)
                return
        if not self.pinning and (name := self._resize_hit(e)) is not None:      # bấm trúng tay cầm cạnh/góc: đổi kích thước
            label = self._selected()[0]
            self.manual = self.view
            self.drag_resize = (label, name, self._handle_for(label)[3], p, p)
            return
        if self.pinning:
            self.clicks.append((len(self.clicks) + 1, p))
            if len(self.clicks) == PIN_COUNT[self.pinning]:
                pts = [pt for _, pt in self.clicks]
                try:
                    if self.pinning == "one":
                        lab = self.s.add_pin_one(self.f, pts)
                        self.notice = f"Đã ghim {lab} từ 4 điểm; mắt kia giữ nguyên."
                    elif self.pinning == "full":
                        self.s.add_pin_free(self.f, pts)
                        self.notice = "Đã ghim: tool tự gán vai trò các điểm theo hình học (thứ tự bấm không quan trọng)."
                    else:
                        info = self.s.add_pin_hidden(self.f, pts)
                        self.notice = (f"Đã ghim. Khoé {info['hidden']} ({info['eye']}) được ước lượng, sai số khoảng ±4,5 px; "
                                       f"điểm {', '.join(map(str, info['occluded']))} đã đánh Occluded. Kéo để chỉnh nếu cần.")
                    self.pinning, self.clicks = None, []
                except ValueError as err:
                    self.notice = f"Không ghim được: {err}"
                    self.clicks = []
            self.refresh()
            return
        if (self.f in self.s.pins or self.f in self.s.labels) and not self.hide_labels:
            pid = self._nearest_pin_point((e.x, e.y))
            if pid is not None and any(pid in EYES[l].ids for l in self.locked):
                self.notice = "Mắt này đang bị khoá; mở khoá trong panel Đối tượng."
                self.refresh()
                return
            if pid is not None:
                self.select_eye(next(l for l, sp in EYES.items() if pid in sp.ids), quiet=True)
                self.manual = self.view            # giữ nguyên khung nhìn trong lúc kéo
                self.drag = (pid, p)
                return
            label = self._eye_at((e.x, e.y))
            if label in self.pinned_eyes:
                self.notice = "Mắt này đang Pinned: chỉ kéo từng điểm được (bỏ Pinned trong menu ⋮)."
                self.refresh()
                return
            if label in self.locked:
                self.notice = "Mắt này đang bị khoá; mở khoá trong panel Đối tượng."
                self.refresh()
                return
            if label is not None:                  # bấm vào thân mắt (không trúng điểm nào): kéo cả mắt
                self.select_eye(label, quiet=True)
                self.manual = self.view
                self.drag_eye = (label, p, p)
                return
        self._pan = (e.x, e.y)
        self._left_pan = True

    def _motion_refresh(self):
        """Gộp các sự kiện kéo chuột dồn dập: mỗi lượt rảnh chỉ vẽ lại một lần (tránh hàng đợi sự kiện làm cửa sổ bị trễ)."""
        if getattr(self, "_motion_job", None) is None:
            self._motion_job = self.root.after_idle(self._motion_draw)

    def _motion_draw(self):
        self._motion_job = None
        self.refresh(light=True)

    def on_motion(self, e):
        e = self._unrot(e)
        self.hover = (e.x, e.y)
        e = self._scaled(e)
        if self.pinning == "drawbox" and self._box0 is not None and self.view:
            p = self.view.to_frame(e.x, e.y)
            if abs(p[0] - self._box0[0]) * self.view.k >= 3:          # mắt mẫu hiện ngay trong lúc kéo khung
                self.draft = self._draft_box(self._box0, p)
            self._motion_refresh()
            return
        if self.draft_drag is not None and self.draft and self.view:
            self.draft["four"][self.draft_drag] = self.view.to_frame(e.x, e.y)
            self._motion_refresh()
            return
        if self.drag and self.view:
            self.drag = (self.drag[0], self.view.to_frame(e.x, e.y))
            self._motion_refresh()
        elif self.drag_resize and self.view:
            self.drag_resize = (*self.drag_resize[:4], self.view.to_frame(e.x, e.y))
            self._motion_refresh()
        elif self.drag_rot and self.view:
            c = self.drag_rot[1]
            p = self.view.to_frame(e.x, e.y)
            self.drag_rot = (*self.drag_rot[:3], math.atan2(p[1] - c[1], p[0] - c[0]))
            self._motion_refresh()
        elif self.drag_eye and self.view:
            self.drag_eye = (self.drag_eye[0], self.drag_eye[1], self.view.to_frame(e.x, e.y))
            self._motion_refresh()
        elif self._left_pan:
            self._pan_to(e)

    @net_safe
    def on_release(self, e):
        e = self._scaled(self._unrot(e))
        self._m0 = None
        self._left_pan = False
        if self.pinning == "drawbox" and self._box0 is not None and self.view:
            p, a = self.view.to_frame(e.x, e.y), self._box0
            if abs(p[0] - a[0]) * self.view.k < 8:                     # chỉ bấm, không kéo: mắt mẫu rộng 60 px màn hình quanh điểm bấm
                hw = 30 / self.view.k
                a, p = (a[0] - hw, a[1]), (a[0] + hw, a[1])
            self.draft = self._draft_box(a, p)
            self.pinning, self._box0 = None, None
            self.refresh()
            return
        if self.draft_drag is not None:
            self.draft_drag = None
            self.refresh()
            return
        if self.drag_resize and self.s:
            label, moved = self.drag_resize[0], self.drag_resize[3] != self.drag_resize[4]
            new = self._resize_override()
            self.drag_resize = None
            if moved:
                try:
                    newly = self.s.drag_points(self.f, new)
                    self.notice = f"Đã đổi kích thước {label}." + (" Frame này đã tự thành frame ghim." if newly else "")
                except ValueError as err:
                    self.notice = str(err)
            self.refresh()
            return
        if self.drag_rot and self.s:
            label, c, a0, a1 = self.drag_rot
            new = self._rotated(self._eye_points(label), c, a1 - a0)
            self.drag_rot = None
            if abs(a1 - a0) > 1e-4:
                try:
                    self.s.drag_points(self.f, new)
                    self.notice = f"Đã xoay {label} {math.degrees(a1 - a0):+.1f}°."
                except ValueError as err:
                    self.notice = str(err)
            self.refresh()
        if self.drag_eye and self.s:
            new = self._eye_shift()
            self.drag_eye = None
            try:
                newly = self.s.drag_points(self.f, new)
                self.notice = "Đã dời cả mắt." + (" Frame này đã tự thành frame ghim." if newly else "")
            except ValueError as err:
                self.notice = str(err)
            self.refresh()
        if self.drag and self.s:
            pid, p = self.drag
            self.drag = None
            try:
                newly = self.s.drag_point(self.f, pid, p)
                if newly:
                    self.notice = "Frame này đã tự thành frame ghim; các frame sau tính lại theo điểm vừa kéo."
            except ValueError as err:
                self.notice = str(err)
            self.refresh()

    # ---- vẽ ----
    def refresh(self, light: bool = False):
        """Vẽ lại cửa sổ. Nguồn CVAT đọc frame qua mạng ngay trong lúc vẽ: lỗi mạng hoặc hết hạn đăng nhập thành thông báo / hộp đăng nhập, không ném ra Tk."""
        try:
            self._refresh(light)
        except CvatError as err:
            self._frame_read_failed(err)

    def _refresh(self, light: bool = False):
        if not self.s:
            return
        s = self.s
        pts = s.points_at(self.f)
        if pts:
            xs, ys = [p[0] for p in pts.values()], [p[1] for p in pts.values()]
            self.anchor = (min(xs), min(ys), max(xs), max(ys))
        if not light and self._turns_signature() != self._turns_sig:
            self._fill_issues()                       # đoạn quay đầu đổi sau khi ghim/sửa: cập nhật tab Issues (không dựng lại khi không đổi)
            self._announce_turns()
        override = ({self.drag[0]: self.drag[1]} if self.drag else self._eye_shift() if self.drag_eye
                    else self._resize_override() if self.drag_resize else self._rot_override())
        size, look = self.render_size, self.look
        # Như CVAT: sửa nhãn (xoay, kéo, dán, ghim lại) không dời hay phóng ảnh. Khung tự động chỉ canh lại khi đổi frame, đổi cỡ khung,
        # xoay ảnh, khi frame vừa có nhãn lần đầu, hoặc khi bấm Vừa khung; trước đây nó canh theo hộp bao nhãn ở mỗi lần vẽ nên ảnh chạy theo nhãn.
        fit_key = (self.f, size, self.rot, bool(pts))
        held = self._auto_view if self.manual is None and self._auto_key == fit_key else self.manual
        view = make_view(s, self.f, size, self.anchor, held)
        if self.manual is None:
            self._auto_view, self._auto_key = view, fit_key
        # ảnh nền chỉ dựng lại khi frame, khung nhìn, hướng xoay hoặc chỉnh ảnh đổi; kéo điểm, xoay nhãn chỉ vẽ lại phần nhãn
        key = (self.f, round(view.x0, 3), round(view.y0, 3), round(view.k, 5), size, self.rot, look.image, look.brightness, look.contrast,
               look.saturation, look.gamma, look.smooth, look.bg, look.grid, look.grid_size, look.grid_color, look.grid_opacity)
        if key != self._base_key:
            base = render_base(s, self.f, size, view, look)
            self._base_raw = base
            self._base_rot = np.ascontiguousarray(np.rot90(base, -self.rot)) if self.rot else base
            self._main = to_photo(self._base_rot)
            self.canvas.itemconfigure(self._base_item, image=self._main)
            self._base_key = key
        kw = dict(clicks=self.clicks, override=override, show_ids=self.show_ids, hide_labels=self.hide_labels, look=look,
                  preview=self._preview_pts(), handle=self._handle_arg(), selected=self._selected()[0], ids=s.obj_ids)
        self.canvas.delete(CanvasPainter.TAG)
        if look.opacity >= 0.999 and look.selected_opacity >= 0.999:
            # nhãn là đối tượng vector của Canvas: không vẽ lại ảnh, không đổ ảnh vào Tk (nhanh như nhau ở mọi cỡ khung)
            self.view = view
            self.canvas.itemconfigure(self._patch_item, state="hidden")
            draw_overlay(CanvasPainter(self.canvas, self._to_canvas), s, self.f, view, **kw)
        else:
            # nhãn mờ (< 100%): Canvas không có độ trong suốt, nên vẽ lên ảnh để trộn màu đúng, rồi chỉ đổ phần ảnh có đổi
            img, self.view = render_main(s, self.f, size, anchor=self.anchor, manual=held, base=self._base_raw, **kw)
            if self.rot:
                img = np.ascontiguousarray(np.rot90(img, -self.rot))
            self._paint_patch(img)
        text = status_text(s, self.f)
        self.root.title(self._window_title())
        self._sync_cvat_ui()
        if self.pinning == "full":
            text = (f"ĐANG GHIM ({len(self.clicks)}/8): bấm 4 điểm mỗi mắt (2 khoé, giữa mí trên, giữa mí dưới), thứ tự tuỳ ý · "
                    "Ctrl+Z bỏ điểm vừa bấm · Esc huỷ")
            if self._preview_pts():
                text = (f"Đã vẽ mắt đầu (8 điểm, màu cam) từ 4 điểm bạn bấm. Bấm tiếp 4 điểm của mắt còn lại ({len(self.clicks)}/8) · "
                        "Ctrl+Z bỏ điểm vừa bấm · Esc huỷ")
        elif self.pinning == "one":
            text = (f"ĐANG GHIM MỘT MẮT ({len(self.clicks)}/4): bấm 4 điểm (2 khoé, giữa mí trên, giữa mí dưới), thứ tự tuỳ ý · "
                    "Ctrl+Z bỏ điểm vừa bấm · Esc huỷ")
        elif self.pinning == "hidden":
            text = (f"ĐANG GHIM KHI CHE KHOÉ ({len(self.clicks)}/7): bấm 4 điểm của mắt thấy đủ và 3 điểm của mắt bị che khoé "
                    "(khoé còn thấy + 2 điểm giữa mí), thứ tự tuỳ ý · Ctrl+Z bỏ điểm vừa bấm · Esc huỷ")
            if self._preview_pts():
                text = (f"Đã vẽ mắt đầu (8 điểm, màu cam). Bấm tiếp các điểm của mắt còn lại ({len(self.clicks)}/7) · "
                        "Ctrl+Z bỏ điểm vừa bấm · Esc huỷ")
        elif self.pinning == "draw4":
            text = f"VẼ {self.draw_label} ({len(self.clicks)}/4): bấm 2 khoé, giữa mí trên, giữa mí dưới, thứ tự tuỳ ý · Esc huỷ"
        elif self.pinning == "drawbox":
            text = f"VẼ {self.draw_label}: kéo một khung quanh mắt (hoặc bấm vào giữa mắt), mắt mẫu hiện ra để chỉnh · Esc huỷ"
        if not self.pinning and 0 <= s.cur < len(s.turns):            # frame đang xem nằm trong đoạn quay đầu: nhắc chỉnh tay
            hit = next(((k, t) for k, t in enumerate(s.turns[s.cur].turns, 1) if t.first <= self.f <= t.last), None)
            if hit:
                text = (f"QUAY ĐẦU #{hit[0]} (frame {hit[1].first}–{hit[1].last}): kiểm tra và chỉnh tay"
                        + (f" mắt xa {hit[1].far_eye}" if hit[1].far_eye else "") + " · " + text)
        if self.draft:
            text = (f"CHỈNH {self.draft['label']}: kéo 4 điểm to (2 khoé, giữa hai mí) cho khớp mắt rồi bấm Apply "
                    f"(hoặc {self.kl('draw_eye')}) · Esc huỷ")
            self.draft_bar.place(relx=0.5, y=8, anchor="n")
        else:
            self.draft_bar.place_forget()
        if look.grid:                                                    # bước lưới đang vẽ thật (tự thưa khi thu nhỏ)
            text += f" · lưới {imagefx.grid_step(look.grid_size, view.k)} px"
        text = self._cvat_status(text)
        if self.notice:
            text = f"{self.notice}   |   {text}"
        self.status.set(text)
        if not self._typing():
            self._sync_entry()
        if not light:
            self.refresh_objects()
            self.refresh_labels_tab()
            self.update_name_row()
        if light:
            self._schedule_thumbs()                       # ảnh thu nhỏ và dải thời gian cập nhật sau khi ngừng thao tác một chút
            if self.playing:
                self._update_timeline()
            return
        self._update_thumbs()
        self._update_timeline()

    def _paint_patch(self, img):
        """Chỉ gửi cho Tk vùng ảnh khác với ảnh nền (thường là quanh hai mắt) thay vì cả khung: gửi cả khung tốn khoảng 16 ms mỗi lần vẽ."""
        d = cv2.absdiff(img, self._base_rot)
        h, w = d.shape[:2]
        flat = d.reshape(h, w * 3)                                   # cv2.reduce nhanh hơn nhiều so với numpy any trên ảnh lớn
        rows = np.flatnonzero(cv2.reduce(flat, 1, cv2.REDUCE_MAX).ravel())
        cols = np.flatnonzero(cv2.reduce(flat, 0, cv2.REDUCE_MAX).reshape(-1, 3).max(axis=1))
        if rows.size == 0:
            self.canvas.itemconfigure(self._patch_item, state="hidden")
            return
        y0, y1 = max(0, rows[0] - 1), min(img.shape[0], rows[-1] + 2)
        x0, x1 = max(0, cols[0] - 1), min(img.shape[1], cols[-1] + 2)
        self._patch = to_photo(np.ascontiguousarray(img[y0:y1, x0:x1]))
        self.canvas.itemconfigure(self._patch_item, image=self._patch, state="normal")
        self.canvas.coords(self._patch_item, x0, y0)

    def _schedule_thumbs(self):
        if self._thumb_job is not None:
            self.root.after_cancel(self._thumb_job)
        self._thumb_job = self.root.after(150, self._thumbs_tick)

    def _thumbs_tick(self):
        self._thumb_job = None
        if self.s:
            try:
                self._update_thumbs()
            except CvatError as err:
                self._frame_read_failed(err)
                return
            self._update_timeline()

    def _update_thumbs(self):
        s = self.s
        for var, widget, g in ((self.c_prev, self.t_prev, self.f - 1), (self.c_next, self.t_next, self.f + 1)):
            th = render_thumb(s, g, self.view, THUMB, self.hide_labels, self.look)
            if th is not None and self.rot:
                th = np.ascontiguousarray(np.rot90(th, -self.rot))
            if th is None:
                widget.configure(image="")
                var.set("")
                continue
            widget.photo = to_photo(th)
            widget.configure(image=widget.photo)
            shift = max_shift(s.points_at(self.f), s.points_at(g))
            var.set("chưa có nhãn" if shift is None else f"khác frame này nhiều nhất: điểm {shift[0]}, {shift[1]:.1f} px")

    def _update_timeline(self):
        tl = render_timeline(self.s, self.f, max(600, self.root.winfo_width() - 30), show_issues=self.show_issues)
        self._tl = to_photo(tl)
        self.timeline.configure(image=self._tl)


def run(frames_dir: str | None, xml: str | None, selftest: bool = False, pins: str | None = None, cvat: str | None = None,
        job: int | None = None) -> int:
    data = None
    if pins:
        try:
            with open(pins, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as err:
            print(f"Lỗi: không đọc được file ghim {pins}: {err}")
            return 2
        if not isinstance(data, dict):                  # null hay mảng: không được lặng lẽ mở ở chế độ thường (tự lưu được)
            print(f"Lỗi: file ghim {pins} phải là một đối tượng JSON {{frame: {{id: [x, y]}}}}")
            return 2
    root = tk.Tk()
    app = App(root)
    if cvat:                                             # --cvat [--job]: hộp đăng nhập (hỏi mật khẩu trong cửa sổ); có --job thì tự mở job đó sau khi đăng nhập
        app.open_cvat(url=cvat, job=job)
    elif frames_dir:
        try:
            app.load(frames_dir, xml, pins=data)
        except ValueError as err:
            print(f"Lỗi: {err}")
            root.destroy()
            return 2
    if selftest:
        root.update()
        app.go(min(5, app.s.n_frames - 1) if app.s else 0)
        root.update()
        root.destroy()
        print("gui selftest: OK")
        return 0
    root.mainloop()
    return 0
