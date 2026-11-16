"""Giao diện của EyePin: ba màu chính kiểu Y Combinator (cam, nền giấy, chữ đen) cộng vài sắc nhạt suy ra từ ba màu đó.

Chữ trên nền cam luôn là chữ đen (tương phản khoảng 6:1); chữ trắng trên cam chỉ đạt khoảng 3:1 nên không dùng.
Mọi màu nằm ở đây để đổi một chỗ; phần vẽ nhãn trên ảnh (render.py) giữ màu riêng để dễ phân biệt hai mắt trên da mặt.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

ORANGE = "#FF6600"        # màu nhấn duy nhất
PAPER = "#F6F6EF"         # nền
INK = "#1F1F1F"           # chữ
# sắc suy ra
PAPER_DEEP = "#E9E8DC"    # nền nút, tab, thanh trượt
PAPER_LINE = "#D2D0C0"    # đường viền
ORANGE_SOFT = "#FFB380"   # nút khi rê chuột
WHITE = "#FFFFFF"         # ô nhập, danh sách
MUTED = "#5C5B52"         # chữ phụ (tương phản 6.5:1 trên nền giấy)
CANVAS = "#2B2A27"        # nền khung ảnh (tối để ảnh mặt nổi)

FONT = "Segoe UI"


def apply(root: tk.Tk) -> ttk.Style:
    """Áp giao diện cho toàn bộ cửa sổ (kể cả cửa sổ phụ tạo sau này)."""
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(name).configure(family=FONT, size=10)
        except tk.TclError:
            pass
    root.configure(bg=PAPER)
    # widget tk thường (không phải ttk): Listbox, Menu, Label, Button, Toplevel
    root.option_add("*Background", PAPER)
    root.option_add("*Foreground", INK)
    root.option_add("*Listbox.background", WHITE)
    root.option_add("*Listbox.selectBackground", ORANGE)
    root.option_add("*Listbox.selectForeground", INK)
    root.option_add("*Listbox.relief", "flat")
    root.option_add("*Listbox.highlightThickness", 1)
    root.option_add("*Listbox.highlightColor", PAPER_LINE)
    root.option_add("*Listbox.highlightBackground", PAPER_LINE)
    root.option_add("*Menu.background", PAPER)
    root.option_add("*Menu.foreground", INK)
    root.option_add("*Menu.activeBackground", ORANGE)
    root.option_add("*Menu.activeForeground", INK)
    root.option_add("*Menu.selectColor", INK)
    root.option_add("*Menu.relief", "flat")
    root.option_add("*Menu.borderWidth", 1)
    root.option_add("*Button.background", PAPER_DEEP)
    root.option_add("*Button.activeBackground", ORANGE_SOFT)
    root.option_add("*Button.activeForeground", INK)
    root.option_add("*Button.relief", "flat")
    root.option_add("*Button.borderWidth", 0)
    root.option_add("*Button.padX", 8)
    root.option_add("*Button.padY", 5)

    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=PAPER, foreground=INK, fieldbackground=WHITE, bordercolor=PAPER_LINE,
                 lightcolor=PAPER, darkcolor=PAPER, troughcolor=PAPER_DEEP, focuscolor=ORANGE, font=(FONT, 10))
    st.configure("TFrame", background=PAPER)
    st.configure("TLabel", background=PAPER, foreground=INK)
    st.configure("Muted.TLabel", foreground=MUTED)
    # nút thường: nền giấy đậm, rê chuột thì cam nhạt, bấm thì cam
    st.configure("TButton", background=PAPER_DEEP, foreground=INK, borderwidth=0, padding=(10, 5), relief="flat")
    st.map("TButton", background=[("pressed", ORANGE), ("active", ORANGE_SOFT)])
    st.configure("Accent.TButton", background=ORANGE, foreground=INK, padding=(12, 5), font=(FONT, 10, "bold"))
    st.map("Accent.TButton", background=[("pressed", INK), ("active", "#FF8533")], foreground=[("pressed", PAPER)])
    st.configure("TMenubutton", background=PAPER_DEEP, foreground=INK, borderwidth=0, padding=(10, 5), arrowcolor=INK)
    st.map("TMenubutton", background=[("active", ORANGE_SOFT)])
    # thanh trên: nền cam như thanh đầu trang Y Combinator; nút trên đó là nền giấy chữ đen
    st.configure("Bar.TFrame", background=ORANGE)
    st.configure("Bar.TLabel", background=ORANGE, foreground=INK)
    st.configure("Bar.TButton", background=PAPER, foreground=INK, padding=(8, 4))
    st.map("Bar.TButton", background=[("pressed", INK), ("active", PAPER_DEEP)], foreground=[("pressed", PAPER)])
    st.configure("Bar.TMenubutton", background=PAPER, foreground=INK, padding=(10, 4), arrowcolor=INK)
    st.map("Bar.TMenubutton", background=[("active", PAPER_DEEP)])
    st.configure("BarPlay.TButton", background=INK, foreground=PAPER, padding=(12, 4), font=(FONT, 10, "bold"))
    st.map("BarPlay.TButton", background=[("pressed", PAPER), ("active", "#3A3A3A")], foreground=[("pressed", INK)])
    st.configure("TEntry", fieldbackground=WHITE, foreground=INK, bordercolor=PAPER_LINE, padding=3)
    st.map("TEntry", bordercolor=[("focus", INK)])
    st.configure("TCheckbutton", background=PAPER, foreground=INK, indicatorcolor=WHITE)
    st.map("TCheckbutton", indicatorcolor=[("selected", ORANGE)], background=[("active", PAPER)])
    st.configure("TNotebook", background=PAPER, borderwidth=0, tabmargins=(0, 2, 0, 0))
    st.configure("TNotebook.Tab", background=PAPER_DEEP, foreground=INK, padding=(12, 5), borderwidth=0)
    st.map("TNotebook.Tab", background=[("selected", ORANGE), ("active", ORANGE_SOFT)], foreground=[("selected", INK)])
    st.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK, rowheight=24, borderwidth=0)
    st.map("Treeview", background=[("selected", ORANGE)], foreground=[("selected", INK)])
    st.configure("Treeview.Heading", background=PAPER_DEEP, foreground=INK, relief="flat", font=(FONT, 10, "bold"))
    st.map("Treeview.Heading", background=[("active", PAPER_LINE)])
    st.configure("Horizontal.TScale", background=PAPER, troughcolor=PAPER_DEEP)
    st.configure("TSpinbox", fieldbackground=WHITE, foreground=INK, arrowcolor=INK)
    st.configure("TScrollbar", background=PAPER_DEEP, troughcolor=PAPER, arrowcolor=INK, borderwidth=0)
    return st
