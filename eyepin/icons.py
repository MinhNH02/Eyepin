"""Biểu tượng và nút biểu tượng của EyePin (kiểu thanh công cụ CVAT: không chữ cố định, chú thích hiện khi rê chuột).

Biểu tượng là icon gốc của CVAT và Ant Design (giấy phép MIT, xem assets/icons/NOTICE.md), đã dựng thành PNG mặt nạ trắng
(`eyepin/assets/icons/<tên>-<16|20|24>.png`, script `tools/build_icons.py`). Lúc chạy, Pillow nhuộm mặt nạ sang màu cần dùng
(thường, mờ, ...) rồi lưu `PhotoImage` vào bộ nhớ đệm. Thiếu file PNG thì nút rơi về một ký tự chữ ngắn để vẫn dùng được.
"""
from __future__ import annotations

import tkinter as tk
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageTk

from . import theme

# Thư mục PNG. Luôn tra qua `ICON_DIR` lúc gọi (không giữ bản sao) để test đổi được.
ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"

# Chữ thay thế khi thiếu PNG (ASCII/ký tự ngắn, dùng được ở mọi máy).
FALLBACK_TEXT = {
    "menu": "≡", "save": "S", "undo": "↶", "redo": "↷",
    "first": "|<", "last": ">|", "back10": "<<", "fwd10": ">>",
    "prev": "<", "next": ">", "play": "▶", "pause": "II",
    "fullscreen": "[]", "window": "][", "info": "i", "filter": "▽",
    "display": "≣", "pin": "P", "pin_hidden": "G", "keyframe": "★",
    "eye": "o", "eye_off": "x", "add": "+", "scan": "Q", "search": "?", "more": "...", "copy": "C", "trash": "x",
    "pinned": "P", "link": "@", "collapse": "v", "check": "ok", "export": "E",
    "settings": "⚙", "keyboard": "F1", "lock": "L", "unlock": "U", "open": "…",
    "cursor": "V", "hand": "H", "zoom_in": "+", "zoom_out": "-", "fit": "0",
    "rot_ccw": "<", "rot_cw": ">", "kf_prev": "<", "kf_next": ">",
}

# Tên cũ → (tên PNG, lật ngang?). Tên đã trùng tên PNG thì không cần ghi. "open", "search" không có PNG nên dùng chữ.
ALIASES = {
    "kf_prev": ("prev", False), "kf_next": ("next", False),
    "rot_ccw": ("rotate", True), "rot_cw": ("rotate", False),
    "zoom_in": ("zoom", False), "zoom_out": ("zoom", False),
    "pin": ("skeleton", False), "pin_hidden": ("point", False),
    "keyframe": ("star", False), "collapse": ("caret_down", False),
    "window": ("fullscreen", False),
}


def _px(size: int) -> int:
    """Cỡ PNG gần nhất không nhỏ hơn `size`: 16, 20 hoặc 24."""
    return 16 if size <= 16 else 20 if size <= 20 else 24


def resolve(name: str) -> tuple[str, bool]:
    """(tên PNG, lật ngang) cho một tên biểu tượng, đi qua bảng bí danh."""
    return ALIASES.get(name, (name, False))


def fallback_text(name: str) -> str:
    return FALLBACK_TEXT.get(name) or FALLBACK_TEXT.get(resolve(name)[0]) or name[:2]


@lru_cache(maxsize=None)
def _mask(path: str, mtime: float):
    """Kênh alpha của PNG (mtime nằm trong khoá để file đổi thì nạp lại)."""
    with Image.open(path) as im:
        return im.convert("RGBA").getchannel("A")


def icon_image(widget: tk.Misc, name: str, px: int, color: str, flip: bool = False):
    """PhotoImage của biểu tượng `name` cỡ `px` nhuộm `color`; None khi thiếu file PNG. Có nhận tên cũ (bí danh).

    Bộ nhớ đệm theo (tên, px, màu, lật) và gắn vào cửa sổ gốc của `widget` (PhotoImage chết cùng cửa sổ gốc)."""
    png, alias_flip = resolve(name)
    flip = flip != alias_flip
    root = widget._root()
    cache = root.__dict__.setdefault("_eyepin_icon_cache", {})
    key = (str(ICON_DIR), png, px, color, flip)
    if key in cache:
        return cache[key]
    path = Path(ICON_DIR) / f"{png}-{px}.png"
    try:
        alpha = _mask(str(path), path.stat().st_mtime)
    except (OSError, ValueError):
        return None
    if flip:
        alpha = alpha.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    img = Image.new("RGBA", alpha.size, color)
    img.putalpha(alpha)
    cache[key] = photo = ImageTk.PhotoImage(img, master=root)
    return photo


class Tooltip:
    """Chú thích nhỏ hiện sau khi rê chuột vào widget một lúc rất ngắn (CVAT khoảng 100 ms)."""

    DELAY_MS = 150

    # Chỉ có tối đa MỘT chú thích trên toàn app. Trước đây mỗi lần <Enter> lặp (con trỏ vào nút con rồi ra khung) tạo thêm một
    # hẹn giờ mồ côi và một Toplevel mới ghi đè cái cũ → chú thích rò rỉ, không ai huỷ được, lại còn `-topmost` đè lên cửa sổ khác.
    _current: "Tooltip | None" = None

    def __init__(self, widget: tk.Misc, text):
        self.w, self.text, self.tip, self.job, self.watch = widget, text, None, None, None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")
        widget.bind("<Destroy>", self._leave, add="+")

    def _enter(self, _=None):
        self._cancel_job()
        if Tooltip._current is not None and Tooltip._current is not self:
            Tooltip._current.hide()
        self.job = self.w.after(self.DELAY_MS, self._show)

    def _cancel_job(self):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    def _leave(self, _=None):
        # <Leave> cũng bắn khi con trỏ chỉ chuyển sang widget con của nút; chỉ ẩn khi con trỏ thật sự ra ngoài.
        if _ is not None and getattr(_, "type", None) is not None and str(_.type) == "Leave" and self._pointer_inside():
            return
        self.hide()

    def hide(self):
        self._cancel_job()
        if self.watch:
            try:
                self.w.after_cancel(self.watch)
            except tk.TclError:
                pass
            self.watch = None
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None
        if Tooltip._current is self:
            Tooltip._current = None

    def _pointer_inside(self) -> bool:
        try:
            px, py = self.w.winfo_pointerxy()
            x, y = self.w.winfo_rootx(), self.w.winfo_rooty()
            return x <= px < x + self.w.winfo_width() and y <= py < y + self.w.winfo_height()
        except tk.TclError:
            return False

    def _app_active(self) -> bool:
        try:
            return self.w.winfo_toplevel().focus_displayof() is not None
        except (tk.TclError, KeyError):
            return False

    def _show(self):
        self.job = None
        if self.tip is not None or not self._pointer_inside() or not self._app_active():
            return
        text = self.text() if callable(self.text) else self.text
        if not text:
            return
        self.tip = t = tk.Toplevel(self.w)
        t.wm_overrideredirect(True)
        tk.Label(t, text=text, bg=theme.INK, fg=theme.PAPER, padx=8, pady=3, font=(theme.FONT, 9)).pack()
        t.update_idletasks()
        # Giữ chú thích trong màn hình (trước đây bị cắt ở mép phải).
        sw, sh = self.w.winfo_screenwidth(), self.w.winfo_screenheight()
        x = min(self.w.winfo_rootx() + 4, max(0, sw - t.winfo_reqwidth() - 4))
        y = self.w.winfo_rooty() + self.w.winfo_height() + 4
        if y + t.winfo_reqheight() > sh:
            y = max(0, self.w.winfo_rooty() - t.winfo_reqheight() - 4)
        t.wm_geometry(f"+{x}+{y}")
        Tooltip._current = self
        self.watch = self.w.after(200, self._watchdog)

    def _watchdog(self):
        """Lưới an toàn: còn hiện mà con trỏ đã ra ngoài hoặc cửa sổ mất focus (Alt+Tab, chuyển tab) thì ẩn."""
        self.watch = None
        if self.tip is None:
            return
        if not self._pointer_inside() or not self._app_active():
            self.hide()
            return
        self.watch = self.w.after(200, self._watchdog)


class IconButton(tk.Frame):
    """Nút biểu tượng (ảnh PNG nhuộm màu, không vẽ chữ cố định; chữ chỉ hiện trong chú thích khi rê chuột).

    kind: "bar" (trên thanh cam) hoặc "tool" (thanh công cụ nền giấy). `active` tô cam để báo chế độ đang bật.
    `caption` vẫn được nhận cho code cũ nhưng không vẽ gì (`cap` luôn None)."""

    def __init__(self, parent, name: str, command, *, tip="", caption: str = "", kind: str = "tool", size: int = 16):
        self.kind = kind
        self.base = theme.ORANGE if kind == "bar" else theme.PAPER
        super().__init__(parent, bg=self.base, cursor="hand2")
        self.size, self.name, self._enabled = size, name, True
        self.icon = tk.Label(self, bg=self.base, fg=theme.INK, pady=4)
        self.icon.pack(padx=4, pady=3)
        self.cap = None
        self.command, self._active = command, False
        self.glyph = ""
        self._render()
        for w in (self, self.icon):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._hover, add="+")
            w.bind("<Leave>", self._unhover, add="+")
        Tooltip(self, tip)

    def _render(self):
        """Vẽ biểu tượng hiện tại theo trạng thái bật/mờ: ảnh PNG, hoặc chữ thay thế khi thiếu file."""
        color = theme.INK if self._enabled else theme.MUTED
        img = icon_image(self, self.name, _px(self.size), color)
        if img is not None:
            self.glyph = ""
            self.icon.image = img  # giữ tham chiếu
            self.icon.configure(image=img, text="", width=0, fg=color)
        else:
            self.glyph = fallback_text(self.name)
            self.icon.image = None
            self.icon.configure(image="", text=self.glyph, fg=color, width=2,
                                font=(theme.FONT, max(8, self.size - 3), "bold"))

    def _paint(self, bg: str):
        for w in (self, self.icon):
            w.configure(bg=bg)

    def _hover(self, _):
        if self._enabled:
            self._paint(theme.PAPER if self.kind == "bar" else theme.ORANGE_SOFT)

    def _unhover(self, _):
        self._paint(self._resting())

    def _resting(self) -> str:
        if self._active:
            return theme.PAPER if self.kind == "bar" else theme.ORANGE
        return self.base

    def _click(self, _):
        if self._enabled and self.command:
            self.command(self)

    def set_active(self, on: bool):
        self._active = on
        self._paint(self._resting())

    def set_icon(self, name: str):
        self.name = name
        self._render()

    def set_enabled(self, on: bool):
        """Tắt = biểu tượng mờ, bỏ qua bấm; bật lại = như cũ."""
        self._enabled = bool(on)
        cur = "hand2" if self._enabled else "arrow"
        for w in (self, self.icon):
            w.configure(cursor=cur)
        self._render()
        self._paint(self._resting())
