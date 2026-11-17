"""Màn đăng nhập là cửa trước của EyePin (thiết kế: design/2026-11-16-cvat-home-design.md mục 9, người dùng chọn cách A).

`python -m eyepin gui` (không kèm thư mục ảnh) hiện màn đăng nhập trước khi dựng cửa sổ gán nhãn:
- `LoginScreen`: một khung trong cửa sổ chính (địa chỉ CVAT, tên đăng nhập, mật khẩu, ô "Ghi nhớ đăng nhập", nút Đăng nhập, liên kết "Làm việc
  không cần CVAT → mở thư mục ảnh"). Còn khoá đã nhớ (eyepin.cvatlogin) còn hiệu lực thì bỏ qua màn này. Không đụng tới `App`, nên dựng được trước nó.
- `FrontDoor`: nối `LoginScreen` với cửa sổ chính: đăng nhập xong dựng `App` rồi mở `--job` hoặc hộp "Mở từ CVAT…" đã đăng nhập sẵn; "làm việc không
  cần CVAT" dựng `App` trống như trước đây.
- `LoginMixin` (của `App`): "Đăng xuất…" — xoá khoá đã nhớ, tên đăng nhập và phiên CVAT trên máy này rồi về màn đăng nhập trong cùng cửa sổ
  (`App.back_to_login` → `App.teardown` → `App.to_login`); không tự mở lại job nào. Chỉ đóng cửa sổ (nút X, hoặc nút/mục "Thoát EyePin"
  riêng trên thanh cam, trong menu và trên màn đăng nhập) mới thoát EyePin; Thoát không xoá gì.

Việc mạng chạy trên luồng nền; luồng nền không đụng vào Tk (kết quả đi qua hàng đợi, lấy bằng `root.after`). Mật khẩu bị xoá khỏi ô nhập sau mỗi lần thử.
Màn này chỉ kiểm tài khoản CVAT: nó không khoá được ảnh hay file trên máy.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import cvatlogin, shortcuts as sc, theme
from .cvatapi import CvatClient, CvatError, LoginNeeded

TITLE = "EyePin — đăng nhập"
WIDTH, HEIGHT = 640, 560



class LoginScreen:
    """Khung đăng nhập. `on_login(client, tên)` được gọi (sau khi khung đã đóng) khi đăng nhập được; `on_local()` khi chọn làm việc không cần CVAT.
    `notice` là lời nhắn cho cửa sổ chính (ví dụ không nhớ được đăng nhập)."""

    def __init__(self, root: tk.Tk, *, on_login, on_local, url: str | None = None, settings: dict | None = None, new_client=CvatClient):
        self.root = root
        self.settings = settings if settings is not None else sc.load_settings()
        self._on_login, self._on_local, self._new_client = on_login, on_local, new_client
        self.notice = ""
        self.busy = False
        self._closed = False
        self.hours = cvatlogin.remember_hours(self.settings)
        saved = self.settings.get("cvat") or {}
        self.url_var = tk.StringVar(root, url or saved.get("url") or sc.DEFAULT_SETTINGS["cvat"]["url"])
        self.user_var = tk.StringVar(root, saved.get("user", ""))
        self.password_var = tk.StringVar(root)
        self.remember_var = tk.BooleanVar(root, self.hours > 0)
        self.status_var = tk.StringVar(root)
        self._build()
        self._try_remembered()

    # ---- giao diện ----
    def _build(self):
        root = self.root
        theme.apply(root)
        root.title(TITLE)
        x = max(0, (root.winfo_screenwidth() - WIDTH) // 2)
        y = max(0, (root.winfo_screenheight() - HEIGHT) // 3)
        root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")
        self.frame = tk.Frame(root, bg=theme.PAPER)
        self.frame.pack(fill="both", expand=True)
        tk.Frame(self.frame, bg=theme.ORANGE, height=10).pack(side="top", fill="x")
        card = ttk.Frame(self.frame)
        card.place(relx=0.5, rely=0.1, anchor="n")           # neo phía trên: dòng thông báo hiện ra không làm cả khối nhảy lên xuống
        card.grid_rowconfigure(7, minsize=58)                # chỗ sẵn cho hai dòng thông báo
        ttk.Label(card, text="EyePin", font=(theme.FONT, 30, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(card, text="Đăng nhập CVAT để chọn job gán nhãn mắt.", style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 18))
        entries = {}
        for r, (text, var, show) in enumerate((("Địa chỉ CVAT", self.url_var, ""), ("Tên đăng nhập", self.user_var, ""), ("Mật khẩu", self.password_var, "•")), start=2):
            ttk.Label(card, text=text).grid(row=r, column=0, sticky="w", padx=(0, 12), pady=5)
            e = ttk.Entry(card, textvariable=var, width=34, show=show)
            e.grid(row=r, column=1, sticky="we", pady=5)
            entries[text] = e
        self.url_entry, self.user_entry, self.password_entry = entries["Địa chỉ CVAT"], entries["Tên đăng nhập"], entries["Mật khẩu"]
        self.url_entry.bind("<Return>", lambda e: self.user_entry.focus_set())
        self.user_entry.bind("<Return>", lambda e: self.password_entry.focus_set())
        self.password_entry.bind("<Return>", lambda e: self.submit())
        if self.hours > 0:
            text = f"Ghi nhớ đăng nhập trên máy này ({self.hours:g} giờ)"
        else:
            text = "Ghi nhớ đăng nhập (đang tắt trong Cài đặt)"
        self.remember_btn = ttk.Checkbutton(card, text=text, variable=self.remember_var)
        if self.hours <= 0:
            self.remember_btn.state(["disabled"])
        self.remember_btn.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 10))
        self.login_btn = ttk.Button(card, text="Đăng nhập", style="Accent.TButton", command=self.submit)
        self.login_btn.grid(row=6, column=0, columnspan=2, sticky="we", pady=(0, 8))
        self.status_label = ttk.Label(card, textvariable=self.status_var, wraplength=420, justify="left", style="Muted.TLabel")
        self.status_label.grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Separator(card).grid(row=8, column=0, columnspan=2, sticky="we", pady=6)
        self.local_btn = ttk.Button(card, text="Làm việc không cần CVAT → mở thư mục ảnh", command=self.go_local)
        self.local_btn.grid(row=9, column=0, columnspan=2, sticky="we", pady=(6, 4))
        ttk.Label(card, text="Không cần tài khoản: chỉ mở ảnh và file nhãn trên máy.", style="Muted.TLabel").grid(row=10, column=0, columnspan=2, sticky="w")
        self.quit_btn = ttk.Button(card, text="Thoát EyePin", command=self.quit)
        self.quit_btn.grid(row=11, column=0, columnspan=2, sticky="e", pady=(14, 0))
        self._focus_form()

    def _focus_form(self):
        (self.password_entry if self.user_var.get() else self.user_entry).focus_set()

    def _say(self, text: str, error: bool = False):
        self.status_var.set(text)
        if error:
            self.status_label.configure(style="TLabel", font=(theme.FONT, 10, "bold"))
        else:
            self.status_label.configure(style="Muted.TLabel", font=(theme.FONT, 10))

    def _set_busy(self, busy: bool):
        self.busy = busy
        flag = ["disabled"] if busy else ["!disabled"]
        for w in (self.login_btn, self.url_entry, self.user_entry, self.password_entry):
            w.state(flag)                                    # liên kết "không cần CVAT" luôn bấm được: lối thoát khi CVAT chậm hoặc tắt

    def _alive(self) -> bool:
        try:
            return not self._closed and bool(self.frame.winfo_exists())
        except tk.TclError:
            return False

    # ---- việc nền ----
    def _bg(self, fn, done):
        """Chạy `fn()` trên luồng nền, rồi `done(kết_quả, lỗi)` ở luồng chính. Màn đã đóng thì kết quả bị bỏ."""
        out: queue.Queue = queue.Queue(maxsize=1)

        def work():
            try:
                out.put((fn(), None))
            except Exception as err:                         # mọi lỗi đều phải về `done`, không thì ô nhập bị khoá mãi
                out.put((None, err))

        def poll():
            if not self._alive():
                return
            try:
                res, err = out.get_nowait()
            except queue.Empty:
                self.root.after(40, poll)
                return
            done(res, err)

        threading.Thread(target=work, daemon=True).start()
        self.root.after(40, poll)

    # ---- đăng nhập bằng khoá đã nhớ ----
    def _try_remembered(self):
        if self.hours <= 0:
            cvatlogin.forget_login()                         # người dùng đã tắt việc nhớ: file thừa không được dùng
            return
        saved = cvatlogin.load_login(self.url_var.get())     # khác địa chỉ, hết hạn, hỏng: tự xoá, trả None
        if saved is None:
            return
        user, token = saved
        try:
            client = self._new_client(self.url_var.get())
        except CvatError as err:
            self._say(str(err), True)
            return
        self.user_var.set(user)
        self._set_busy(True)
        self._say(f"Đang vào bằng đăng nhập đã nhớ của {user}…")

        def work():
            client.use_token(token)
            return client.whoami()

        def done(name, err):
            self._set_busy(False)
            if err is None:
                self._enter(client, name)
                return
            client.close()
            if isinstance(err, (LoginNeeded, ValueError)):
                cvatlogin.forget_login()                     # CVAT đã huỷ khoá (hoặc khoá hỏng): không thử lại vô hạn
                self._say("Đăng nhập đã nhớ không còn hiệu lực. Hãy đăng nhập lại.", True)
            elif isinstance(err, CvatError):
                self._say(f"{err} Đăng nhập đã nhớ vẫn được giữ; thử lại khi CVAT chạy.", True)
            else:
                self._say(f"Lỗi: {err}", True)
            self._focus_form()

        self._bg(work, done)

    # ---- đăng nhập bằng mật khẩu ----
    def submit(self):
        if self.busy or not self._alive():
            return
        url, user, password = self.url_var.get().strip(), self.user_var.get().strip(), self.password_var.get()
        if not (user and password):
            self._say("Nhập tên đăng nhập và mật khẩu.", True)
            return
        try:
            client = self._new_client(url)
        except CvatError as err:                             # không phải localhost: từ chối trước khi gửi bất cứ gì
            self.password_var.set("")
            self._say(str(err), True)
            return
        remember = bool(self.remember_var.get()) and self.hours > 0
        self._set_busy(True)
        self._say("Đang đăng nhập…")

        def done(_, err):
            self.password_var.set("")                        # mật khẩu không ở lại trong cửa sổ, đúng hay sai
            self._set_busy(False)
            if err is not None:
                client.close()
                self._say(str(err) if isinstance(err, CvatError) else f"Lỗi: {err}", True)
                self.password_entry.focus_set()
                return
            self.settings.setdefault("cvat", {}).update(url=client.url, user=user)
            try:
                sc.save_settings(self.settings)
            except OSError:
                pass
            if remember and client.token:
                if not cvatlogin.save_login(client.url, user, client.token, self.hours):
                    self.notice = "Không nhớ được đăng nhập trên máy này (lỗi mã hoá hoặc ghi file); lần mở sau phải nhập lại mật khẩu."
            else:
                cvatlogin.forget_login()                     # bỏ ô ghi nhớ: khoá cũ còn trên máy cũng phải đi, không thì lần sau vẫn tự vào
            self._enter(client, user)

        self._bg(lambda: client.login(user, password), done)

    # ---- ra khỏi màn đăng nhập ----
    def _enter(self, client: CvatClient, user: str):
        self.destroy()
        self._on_login(client, user)

    def go_local(self):
        """Làm việc không cần CVAT: đóng màn đăng nhập, dựng cửa sổ trống. Dùng được cả lúc đang đăng nhập dở (kết quả muộn bị bỏ)."""
        if not self._alive():
            return
        self.destroy()
        self._on_local()

    def quit(self):
        """Thoát EyePin từ màn đăng nhập (như nút X): huỷ hẹn giờ còn chờ (kết quả đăng nhập muộn bị bỏ) rồi huỷ cửa sổ. Không xoá gì."""
        self.destroy()
        try:
            for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.after_cancel(job)
            self.root.destroy()
        except tk.TclError:
            pass

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.frame.destroy()
            self.root.geometry("")                           # trả kích thước tự nhiên cho cửa sổ chính dựng sau
        except tk.TclError:
            pass


class FrontDoor:
    """Cửa trước: hiện `LoginScreen`, rồi dựng cửa sổ chính (`app_factory(root)`, mặc định `eyepin.gui.App`) với kết quả đăng nhập.
    `job`: số job tự mở sau khi đăng nhập (từ `--job`)."""

    def __init__(self, root: tk.Tk, *, url: str | None = None, job: int | None = None, new_client=CvatClient, app_factory=None,
                 settings: dict | None = None):
        self.root, self.job, self.app = root, job, None
        self._factory = app_factory
        self._url, self._new_client = url, new_client
        self.screen = LoginScreen(root, on_login=self._login, on_local=self._local, url=url, settings=settings, new_client=new_client)

    def _build_app(self):
        if self._factory is None:
            from .gui import App                             # nạp muộn: gui.py cũng nạp module này
            self._factory = App
        self.app = self._factory(self.root)
        # Đăng xuất dựng lại cửa trước với cùng địa chỉ, client, factory; KHÔNG truyền job (người dùng chốt: sau Đăng xuất không tự mở lại job).
        # Cài đặt đọc lại từ đĩa (settings=None): bản dict ban đầu còn tên đăng nhập mà Đăng xuất vừa xoá.
        self.app.to_login = lambda root: FrontDoor(root, url=self._url, new_client=self._new_client, app_factory=self._factory)
        return self.app

    def _login(self, client: CvatClient, user: str):
        app = self._build_app()
        app.notice = self.screen.notice
        app.cvat_client = client
        if self.job is not None:
            app.load_cvat(client, self.job)
        else:
            app.open_cvat(url=client.url)                    # đã đăng nhập sẵn nên hộp liệt kê task ngay

    def _local(self):
        self._build_app()


MAX_LISTED = 10


def logout_text(n_sessions: int) -> str:
    """Hộp xác nhận chung (không có công nào chưa gửi): nói rõ xoá gì, giữ gì."""
    sessions = (f"• {n_sessions} phiên làm việc đã lưu của job CVAT (đều đã gửi lên CVAT)" if n_sessions
                else "• (không có phiên làm việc CVAT nào đã lưu)")
    return ("Đăng xuất EyePin?\n\nSẽ xoá khỏi máy này:\n• khoá đăng nhập CVAT đã nhớ và tên đăng nhập\n" + sessions + "\n\n"
            "Giữ nguyên: phiên của thư mục ảnh và file bạn tự lưu (bản chụp, file XML xuất); công ty yêu cầu xoá thì bạn tự xoá chúng.\n\n"
            "Chỉ đăng xuất ở máy này, không đăng xuất khỏi CVAT (khoá còn hiệu lực trên CVAT tới khi CVAT tự huỷ). Xong thì EyePin về màn đăng nhập.")


def open_job_text(job, pins: int) -> str:
    """Hộp khi job đang mở còn công chưa gửi: ba lựa chọn Gửi / Bỏ / Huỷ."""
    name = f"Job #{job}" if job is not None else "Job đang mở"
    return (f"{name} có {pins} frame ghim CHƯA gửi lên CVAT.\n\n"
            "Đăng xuất xoá khoá đăng nhập, tên đăng nhập và mọi phiên làm việc CVAT đã lưu trên máy này, kể cả công này.\n\n"
            "Có: gửi lên CVAT rồi đăng xuất\nKhông: đăng xuất và bỏ công này\nHuỷ: ở lại làm tiếp")


def others_text(items) -> str:
    """Hộp liệt kê các phiên đã lưu của job KHÁC còn công chưa gửi (hoặc chưa rõ đã gửi hay chưa)."""
    lines = []
    for u in items[:MAX_LISTED]:
        unclear = "" if u.known else " (phiên cũ, chưa rõ đã gửi hay chưa)"
        lines.append(f"• Job {'#' + str(u.job) if u.job is not None else '?'}: {u.pins} frame ghim{unclear}")
    if len(items) > MAX_LISTED:
        lines.append(f"… và {len(items) - MAX_LISTED} job nữa")
    return ("Còn công chưa gửi (hoặc chưa rõ đã gửi hay chưa) trong các phiên đã lưu của job khác:\n" + "\n".join(lines) + "\n\n"
            "EyePin không tự gửi các job này (cần mở job và đối chiếu). Đăng xuất sẽ xoá chúng cùng khoá đăng nhập và tên đăng nhập.\n\n"
            "Xoá luôn và đăng xuất?")


class LoginMixin:
    """Phần đăng xuất của cửa sổ chính (design/2026-11-16-cvat-home-design.md mục 4.6b, 9b)."""

    # ---- hộp hỏi (thay được trong test) ----
    def ask_logout(self) -> bool:
        return bool(messagebox.askyesno("Đăng xuất", logout_text(len(cvatlogin.cvat_session_files())), icon="warning", default="no", parent=self.root))

    def ask_logout_open_job(self, job, pins: int) -> str:
        """"send" (Gửi rồi đăng xuất) | "discard" (Đăng xuất và bỏ công này) | "cancel" (mặc định)."""
        ans = messagebox.askyesnocancel("Đăng xuất", open_job_text(job, pins), icon="warning", default="cancel", parent=self.root)
        return "cancel" if ans is None else "send" if ans else "discard"

    def ask_logout_others(self, items) -> bool:
        return bool(messagebox.askyesno("Đăng xuất", others_text(items), icon="warning", default="no", parent=self.root))

    # ---- luồng ----
    def logout(self):
        """Đăng xuất = dọn dữ liệu CVAT trên máy rồi về màn đăng nhập trong cùng cửa sổ (`back_to_login`; chỉ đóng cửa sổ mới thoát). Hỏi trước khi xoá (không có gì chưa gửi: một hộp xác nhận; job đang mở chưa gửi:
        Gửi rồi đăng xuất / Đăng xuất và bỏ công này / Huỷ; job khác còn phiên chưa gửi: liệt kê, Xoá luôn / Huỷ). Gửi lỗi hoặc huỷ thì dừng, không xoá gì.
        Xoá lỗi file nào thì báo tên file và ở lại job. Không bao giờ gọi POST /api/auth/logout."""
        self._after_send = None
        if not self.confirm_close_busy(logout=True):
            return
        s = self.s
        cvat_open = s is not None and s.cvat is not None
        if not cvat_open and not self.confirm_close(logout=True):           # phiên thư mục ảnh: hỏi lưu như khi đóng cửa sổ; job CVAT thì bản lưu sắp bị xoá nên khỏi hỏi
            return
        if cvat_open and s.unsent:
            choice = self.ask_logout_open_job(s.cvat.get("job"), sum(len(L.pins) for L in s.layers))
            if choice == "cancel":
                return
            if choice == "send":
                self._after_send = lambda ok: self._logout_after_send(s, ok)
                self.send_cvat()                                 # chạy nền; có kết quả cuối thì gọi `_logout_after_send`
                return
            self._logout_continue(asked=True, discard_open=True)
        else:
            self._logout_continue(asked=False)

    def _logout_after_send(self, session, ok: bool):
        if not ok or self.s is not session or session.unsent:
            self.notice = "Đăng xuất dừng: chưa gửi xong lên CVAT nên không xoá gì. Gửi xong (hoặc bỏ công này) rồi đăng xuất lại."
            if self.s is not None:
                self.refresh(light=True)
            return
        self._logout_continue(asked=True)

    def _logout_continue(self, asked: bool, discard_open: bool = False):
        """Bước hỏi còn lại (job khác chưa gửi, hoặc xác nhận chung nếu chưa hỏi gì) rồi dọn. `discard_open`: người dùng đã chọn bỏ công của job đang mở
        nên file phiên của chính nó không bị hỏi lại như "job khác"."""
        mine = Path(self.state_path()) if discard_open and self.s is not None else None
        others = [u for u in cvatlogin.unsent_sessions() if u.path != mine]
        if others:
            if not self.ask_logout_others(others):
                return
        elif not asked and not self.ask_logout():
            return
        self._logout_wipe()

    def _logout_wipe(self):
        job, self._autosave_job = self._autosave_job, None       # một lần tự lưu không được ghi lại file vừa xoá
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        failed = cvatlogin.wipe_local(self.settings)
        if failed:
            self.show_error("Chưa dọn sạch: không xoá hoặc ghi được\n" + "\n".join(failed) + "\n\nChưa đăng xuất. Đóng chương trình đang giữ các file đó "
                            "rồi bấm Đăng xuất lại, hoặc xoá chúng bằng tay.")
            self._schedule_autosave()                            # còn làm việc tiếp được: bật lại tự lưu
            return
        self.back_to_login()
