"""Phần nối cửa sổ EyePin với CVAT trên máy (mixin của `App`, tách khỏi gui.py): hộp "Mở từ CVAT…", chế độ QC, "Gửi lên CVAT",
việc nền (`_run_bg`) và khoá sửa nhãn trong lúc chạy. Thiết kế: design/2026-11-16-cvat-direct-design.md mục 2, 7, 8.

Việc mạng chạy trên một luồng nền; luồng nền không đụng vào Tk: kết quả đi qua một hàng đợi và được lấy ra bằng `root.after` ở luồng chính.
Trong lúc có việc nền (`App.busy` là chữ "Đang …") và khi job ở chế độ QC, mọi lệnh sửa nhãn bị chặn (`edit_command`, `_edit_blocked`).
Khoá đăng nhập chỉ nằm trong `CvatClient` (RAM); mật khẩu bị xoá khỏi ô nhập ngay sau khi đăng nhập được; chỉ {url, user} được nhớ.
"""
from __future__ import annotations

import functools
import math
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np

from . import cvatsync, qc
from .cvatapi import CvatClient, CvatError, LoginNeeded
from .cvatsource import open_job
from .geometry import EYES
from .icons import BAR_SIZE, IconButton
from .session import QC_MSG

DEFAULT_URL = "http://localhost:8080"
TITLE = "EyePin — gán nhãn mắt cho CVAT"
RESTORE_LIMIT = ("Giới hạn của việc khôi phục: bản chụp là bản xuất nền (các nhãn khác mắt) trước khi gửi. Nhãn mắt cũ chỉ được trả lại đúng loại khi "
                 "định dạng nền cũng là định dạng hiện nhãn mắt cũ; ví dụ nền \"CVAT for images\" trả track mắt cũ về thành shape ở mọi frame. "
                 "Nhãn mắt cũ đã được bạn đồng ý xoá lúc gửi; khôi phục chủ yếu để lấy lại nhãn nền.")


def edit_command(fn):
    """Lệnh sửa nhãn: ở chế độ QC hoặc khi đang có việc nền thì không chạy mà báo lý do; ValueError QC_MSG lọt ra từ Session cũng thành thông báo.
    Lỗi CVAT khi bám lại (đọc ảnh từ CVAT trên luồng chính) thành thông báo, không thành traceback (xem `net_safe`).
    Lệnh tới giữa lúc đang giữ chuột kéo nhãn (Ctrl+Z, Del, Ctrl+N...) thì huỷ lần kéo đó trước: nó được tính trên dữ liệu trước lệnh (`_cancel_drag`)."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kw):
        if self.s is not None and self._edit_blocked():
            return None
        self._cancel_drag()
        try:
            return fn(self, *args, **kw)
        except CvatError as err:
            self._edit_net_failed(err)
            return None
        except ValueError as err:
            if str(err) != QC_MSG:
                raise
            self.notice = QC_MSG
            self.refresh(light=True)
            return None
    return wrapper


def net_safe(fn):
    """Thao tác chuột có thể sửa nhãn (kéo điểm, ghim bằng chuột, ★): lỗi CVAT khi bám lại thành thông báo như `edit_command`."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kw):
        try:
            return fn(self, *args, **kw)
        except CvatError as err:
            self._edit_net_failed(err)
            return None
    return wrapper


class CvatMixin:
    # ---------- khởi dựng ----------
    def _init_cvat(self):
        self.cvat_client: CvatClient | None = None   # khoá đăng nhập nằm trong đối tượng này, chỉ trong RAM
        self.busy: str | None = None                 # "Đang …" khi có việc nền: chặn sửa nhãn
        self._cvat_after_login = None                # việc làm tiếp sau khi đăng nhập lại (401 giữa chừng)
        self._after_send = None                      # việc chờ kết quả lần gửi (Đăng xuất bấm "Gửi rồi đăng xuất"): gọi `hook(ok)` một lần khi gửi có kết quả cuối
        self._cvat_job: int | None = None            # job tự mở sau khi đăng nhập (từ --cvat --job)
        self._cvat_ui: dict = {}
        self._cvat_menu: dict[str, int] = {}
        self._cvat_ui_state = None
        self._menu = None

    def _cvat_menu_items(self, menu):
        """Ba mục menu: Mở từ CVAT…, Gửi lên CVAT, Xoá nhãn mắt cũ và gán lại… (hai mục sau bật/tắt theo trạng thái phiên)."""
        self._menu = menu
        menu.add_command(label="Mở từ CVAT…", command=self.open_cvat)
        menu.add_command(label="Gửi lên CVAT", command=self.send_cvat)
        self._cvat_menu["send"] = menu.index("end")
        menu.add_command(label="Xoá nhãn mắt cũ và gán lại…", command=self.qc_clear)
        self._cvat_menu["clear"] = menu.index("end")
        menu.add_separator()
        menu.add_command(label="Đăng xuất…", command=self.logout)          # LoginMixin (gui_login.py)

    def _cvat_buttons(self, top) -> list:
        """Hai nút icon trên thanh cam (cạnh Info, Filters như CVAT), chữ chỉ hiện khi trỏ chuột: Mở job CVAT (HomeOutlined) và Gửi lên CVAT
        (CloudUploadOutlined, mờ khi không gửi được)."""
        self.cvat_open_btn = IconButton(top, "open", lambda b: self.open_cvat(), tip="Mở một job từ CVAT trên máy", kind="bar", size=BAR_SIZE)
        self.cvat_send_btn = IconButton(top, "upload", lambda b: self.send_cvat(), tip=self._send_tip, kind="bar", size=BAR_SIZE)
        self.cvat_send_btn.set_enabled(False)                    # chưa mở job CVAT nào
        return [self.cvat_send_btn, self.cvat_open_btn]

    def _build_qc_bar(self):
        """Thanh nổi trên ảnh khi job ở chế độ QC: báo chế độ và nút "Xoá nhãn mắt cũ và gán lại"."""
        self.qc_bar = ttk.Frame(self.canvas, padding=(8, 4))
        ttk.Label(self.qc_bar, text="CHẾ ĐỘ QC: job đã có nhãn mắt, chỉ xem và quét.").pack(side="left")
        ttk.Button(self.qc_bar, text="Xoá nhãn mắt cũ và gán lại", command=self.qc_clear).pack(side="left", padx=(8, 2))

    def _send_tip(self) -> str:
        s = self.s
        if s is None or s.cvat is None:
            return "Gửi lên CVAT: chỉ dùng khi đang mở một job từ CVAT"
        if s.qc:
            return "Gửi lên CVAT đang tắt: job đã có nhãn mắt (chế độ QC)"
        return "Gửi nhãn mắt lên job CVAT đang mở (thay toàn bộ nhãn của job; có hỏi trước và đối chiếu sau)"

    # ---------- trạng thái giao diện ----------
    def cvat_send_allowed(self) -> bool:
        s = self.s
        return s is not None and s.cvat is not None and not s.qc and not self.busy

    def _sync_cvat_ui(self):
        """Bật/tắt các mục và nút theo phiên đang mở (chỉ đụng widget khi trạng thái đổi)."""
        s = self.s
        state = (s is not None and s.cvat is not None, bool(s is not None and s.qc), bool(self.busy))
        if state == self._cvat_ui_state:
            return
        self._cvat_ui_state = state
        is_cvat, in_qc, busy = state
        send_ok = is_cvat and not in_qc and not busy
        if self._menu is not None:
            self._menu.entryconfigure(self._cvat_menu["send"], state="normal" if send_ok else "disabled")
            self._menu.entryconfigure(self._cvat_menu["clear"], state="normal" if in_qc and not busy else "disabled")
        self.cvat_send_btn.set_enabled(send_ok)                  # icon mờ (màu MUTED) và không bấm được khi không gửi được
        if in_qc:
            self.qc_bar.place(relx=0.5, y=8, anchor="n")
        else:
            self.qc_bar.place_forget()

    def _window_title(self) -> str:
        s = self.s
        if s is not None and s.cvat is not None:
            return f"EyePin — {s.title}" + (" — QC (chỉ xem)" if s.qc else "") + (" *" if s.dirty else "")
        return TITLE + (" *" if s is not None and s.dirty else "")

    def _cvat_status(self, text: str) -> str:
        if self.s is not None and self.s.qc:
            text = "CHẾ ĐỘ QC (chỉ xem và quét; muốn sửa thì bấm \"Xoá nhãn mắt cũ và gán lại\") · " + text
        if self.busy:
            text = f"{self.busy}  ·  {text}"
        return text

    # ---------- khoá sửa nhãn ----------
    def _edit_blocked(self) -> bool:
        """True (và đã đặt thông báo) nếu lúc này không được sửa nhãn: đang có việc nền hoặc job ở chế độ QC."""
        if self.busy:
            self.notice = f"{self.busy} Chờ xong rồi mới sửa nhãn được."
        elif self.s is not None and self.s.qc:
            self.notice = QC_MSG
        else:
            return False
        if self.s is not None:
            self.refresh(light=True)
        return True

    def _eye_hit(self, e) -> bool:
        """Chuột (toạ độ chưa xoay) đang ở trên hoặc sát một mắt đang hiện (kể cả nhãn đọc từ job)."""
        pts = self.s.points_at(self.f) if self.s is not None and self.view is not None else None
        if not pts:
            return False
        if any(math.dist(self.view.to_screen(q), (e.x, e.y)) <= 14 for q in pts.values()):
            return True
        p = self.view.to_frame(e.x, e.y)
        for spec in EYES.values():
            if all(i in pts for i in spec.ids):
                poly = np.array([pts[i] for i in spec.ids], np.float32).reshape(-1, 1, 2)
                if cv2.pointPolygonTest(poly, (float(p[0]), float(p[1])), True) * self.view.k > -14:
                    return True
        return False

    def _press_read_only(self, e):
        """Bấm chuột khi không được sửa nhãn (QC hoặc đang bận): bấm vào mắt thì báo lý do, bấm chỗ khác vẫn dời ảnh."""
        if self._eye_hit(e):
            self._edit_blocked()
            return
        self._pan = (e.x, e.y)
        self._left_pan = True

    # ---------- việc nền ----------
    def _run_bg(self, fn, done, text: str = "Đang xử lý…"):
        """Chạy `fn()` trên luồng nền; xong thì gọi `done(kết_quả, lỗi)` ở luồng chính (lỗi là ngoại lệ hoặc None). Mỗi lúc một việc: đang bận thì
        trả None và không chạy. Trong lúc chạy `self.busy` là `text` (chặn sửa nhãn, hiện trên dòng trạng thái)."""
        if self.busy:
            self.notice = f"{self.busy} Chờ việc này xong đã."
            return None
        self.busy = text
        self.playing = False
        out: queue.Queue = queue.Queue(maxsize=1)
        idle_status = self.status.get()

        def work():
            try:
                out.put((fn(), None))
            except Exception as err:                       # mọi lỗi đều phải về `done`, không thì cửa sổ bị khoá mãi
                out.put((None, err))

        def poll():
            try:
                res, err = out.get_nowait()
            except queue.Empty:
                self.root.after(40, poll)
                return
            self.busy = None
            if self.s is None:
                self.status.set(idle_status)
            self._sync_cvat_ui()
            done(res, err)
            if self.s is not None:
                self.refresh(light=True)

        threading.Thread(target=work, daemon=True).start()
        self.root.after(40, poll)                           # hẹn lấy kết quả trước mọi việc có thể ném lỗi, để `busy` không kẹt
        if self.s is not None:
            self.refresh(light=True)
        else:
            self.status.set(text)
        self._sync_cvat_ui()
        return True

    # ---------- hộp thoại (thay được trong test) ----------
    def show_error(self, text: str):
        messagebox.showerror("EyePin", text, parent=self.root)

    def ask_send(self, text: str, warn: bool) -> bool:
        return messagebox.askyesno("Gửi lên CVAT", text, icon="warning" if warn else "question", default="no", parent=self.root)   # mọi lần gửi thay cả nhãn của job: mặc định là Không

    def ask_clear_eyes(self, text: str) -> bool:
        return messagebox.askyesno("Xoá nhãn mắt cũ và gán lại", text, icon="warning", default="no", parent=self.root)

    def ask_restore_job(self, text: str) -> bool:
        return messagebox.askyesno("Khôi phục job", text, icon="warning", default="no", parent=self.root)

    def new_client(self, url: str) -> CvatClient:
        return CvatClient(url)

    def _frame_read_failed(self, err):
        """Đọc frame từ CVAT lỗi lúc vẽ: hết hạn đăng nhập thì mở hộp đăng nhập (vẽ lại sau khi đăng nhập), lỗi khác thì báo trên dòng trạng thái."""
        self.notice = str(err)
        if self.s is not None:
            self.status.set(self._cvat_status(self.notice))
        if isinstance(err, LoginNeeded) and self._cvat_after_login is None and not self.busy:
            self._login_again(self.refresh)

    def _edit_net_failed(self, err):
        """Sửa nhãn được lưu nhưng bám lại lỗi vì CVAT (Session.stale): báo, chặn gửi (cvatsync.prepare), hết hạn đăng nhập thì mở hộp đăng nhập
        và tính lại nhãn sau khi đăng nhập."""
        self.notice = (f"{err} Thao tác đã được ghi nhưng nhãn tool tính chưa cập nhật; chưa gửi lên CVAT được cho tới khi làm lại thao tác "
                       "(hoặc Ctrl+Z) lúc CVAT trả lời lại.")
        if getattr(self, "pinning", None) in ("one", "full", "hidden"):   # ghim bằng chuột đã vào phiên: thoát chế độ bấm điểm, đừng gom thêm điểm
            self.pinning, self.clicks = None, []
        if isinstance(err, LoginNeeded) and self._cvat_after_login is None and not self.busy:
            self._login_again(self._recompute_after_login)
        if self.s is not None:
            self.refresh(light=True)

    def _recompute_after_login(self):
        s = self.s
        if s is None or not s.stale:
            return
        try:
            s.recompute()
        except CvatError as err:
            self.notice = f"{err} Nhãn tool tính vẫn chưa cập nhật."
        else:
            self.notice = "Đã đăng nhập lại và tính lại nhãn."
        self.refresh(light=True)

    def report_error(self, err):
        if not isinstance(err, CvatError):
            traceback.print_exception(err)                   # lỗi lập trình: để lại dấu vết trên console, người dùng chỉ thấy một dòng
        text = str(err) if isinstance(err, CvatError) else f"Lỗi không mong đợi: {type(err).__name__}: {err}"
        self.notice = text
        self.show_error(text)
        if self.s is not None:
            self.refresh(light=True)

    # ---------- hộp "Mở từ CVAT…" ----------
    def open_cvat(self, url: str | None = None, job: int | None = None, relogin: bool = False):
        """Hộp: địa chỉ, tên, mật khẩu, Đăng nhập, danh sách task, danh sách job, Mở. `job` (từ --job) thì tự mở job đó sau khi đăng nhập.
        `relogin`: khoá hết hạn giữa chừng; đăng nhập xong thì làm tiếp việc đang dở (`_cvat_after_login`)."""
        d, new = self._toplevel("cvat", "Mở từ CVAT")
        if job is not None:
            self._cvat_job = job
        if new:
            self._build_cvat_dialog(d, url)
        elif url:
            self._cvat_ui["url"].set(url)
        if relogin:
            self._cvat_ui["status"].set("Phiên đăng nhập CVAT đã hết hạn hoặc chưa đăng nhập. Hãy đăng nhập lại (ghim của bạn vẫn còn nguyên).")
            self._cvat_ui["password"].set("")
        elif new and self.cvat_client is not None:
            self._cvat_list_tasks()

    def _build_cvat_dialog(self, d: tk.Toplevel, url: str | None):
        saved = self.settings.get("cvat") or {}
        ui = self._cvat_ui = {
            "url": tk.StringVar(value=url or (self.cvat_client.url if self.cvat_client else None) or saved.get("url") or DEFAULT_URL),
            "user": tk.StringVar(value=saved.get("user", "")), "password": tk.StringVar(), "status": tk.StringVar(value="Nhập tên đăng nhập và mật khẩu của CVAT trên máy."),
            "tasks": [], "jobs": [],
        }
        d.columnconfigure(1, weight=1)
        for r, (text, key, show) in enumerate((("Địa chỉ CVAT", "url", ""), ("Tên đăng nhập", "user", ""), ("Mật khẩu", "password", "•"))):
            ttk.Label(d, text=text).grid(row=r, column=0, sticky="w", padx=(12, 8), pady=3)
            e = ttk.Entry(d, textvariable=ui[key], width=40, show=show)
            e.grid(row=r, column=1, sticky="we", padx=(0, 6), pady=3)
            if key == "password":
                e.bind("<Return>", lambda ev: self.cvat_login())
                ui["password_entry"] = e
        ttk.Button(d, text="Đăng nhập", command=self.cvat_login).grid(row=2, column=2, padx=(0, 12), pady=3)
        ttk.Label(d, textvariable=ui["status"], wraplength=520, style="Muted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", padx=12, pady=(2, 6))
        ttk.Label(d, text="Task").grid(row=4, column=0, sticky="w", padx=12)
        ttk.Label(d, text="Job (bấm đúp để mở)").grid(row=4, column=1, sticky="w")
        ui["tasks_lb"] = tk.Listbox(d, height=9, width=30, exportselection=False)
        ui["jobs_lb"] = tk.Listbox(d, height=9, width=52, exportselection=False)
        ui["tasks_lb"].grid(row=5, column=0, padx=(12, 6), pady=3, sticky="nsew")
        ui["jobs_lb"].grid(row=5, column=1, columnspan=2, padx=(0, 12), pady=3, sticky="nsew")
        ui["tasks_lb"].bind("<<ListboxSelect>>", lambda ev: self.cvat_pick_task())
        ui["jobs_lb"].bind("<Double-Button-1>", lambda ev: self.cvat_open_selected())
        bar = ttk.Frame(d)
        bar.grid(row=6, column=0, columnspan=3, sticky="e", padx=12, pady=(4, 10))
        ttk.Button(bar, text="Mở", command=self.cvat_open_selected).pack(side="left", padx=4)
        ttk.Button(bar, text="Đóng", command=d.destroy).pack(side="left", padx=4)
        d.bind("<Escape>", lambda ev: d.destroy())
        d.bind("<Destroy>", lambda ev: self._cvat_dialog_closed() if ev.widget is d else None)
        d.transient(self.root)
        if ui["user"].get():
            ui["password_entry"].focus_set()

    def _cvat_dialog_closed(self):
        """Đóng hộp đăng nhập mà chưa đăng nhập: bỏ việc đang chờ (gửi dở, job từ dòng lệnh) để lần đăng nhập sau không tự chạy chúng."""
        if self._cvat_after_login is not None:       # đóng hộp mà chưa đăng nhập lại: lần gửi đang chờ đăng nhập (của Đăng xuất) bỏ luôn
            self._after_send = None
        self._cvat_after_login = self._cvat_job = None

    def _cvat_dialog_alive(self) -> bool:
        d = self._dialogs.get("cvat")
        return bool(self._cvat_ui) and d is not None and d.winfo_exists()

    def _client_for(self, url: str) -> CvatClient:
        """Client của địa chỉ này: dùng lại client đang có nếu cùng địa chỉ (phiên đang mở giữ nó để đọc frame, đăng nhập lại thì khoá mới cũng đến đó)."""
        probe = self.new_client(url)                         # ném CvatError nếu không phải localhost
        if self.cvat_client is not None and probe.url == self.cvat_client.url:
            probe.close()
            return self.cvat_client
        return probe

    def cvat_login(self):
        ui = self._cvat_ui
        if not ui:
            return
        url, user, password = ui["url"].get().strip(), ui["user"].get().strip(), ui["password"].get()
        if not (user and password):
            ui["status"].set("Nhập tên đăng nhập và mật khẩu.")
            return
        try:
            client = self._client_for(url)
        except CvatError as err:
            ui["status"].set(str(err))
            return
        ui["status"].set("Đang đăng nhập…")

        def work():
            client.login(user, password)
            return client.tasks()

        def done(tasks, err):
            if not self._cvat_dialog_alive():
                return
            if err is not None:
                ui["status"].set(str(err) if isinstance(err, CvatError) else f"Lỗi: {err}")
                return
            ui["password"].set("")                           # mật khẩu không ở lại trong cửa sổ
            self.cvat_client = client
            self.settings["cvat"] = {"url": client.url, "user": user}
            self.save_settings()
            self._fill_cvat_tasks(tasks)
            ui["status"].set("Đã đăng nhập. Chọn một task, rồi chọn job và bấm Mở.")
            after, job = self._cvat_after_login, self._cvat_job
            self._cvat_after_login = self._cvat_job = None
            if after is not None or job is not None:
                self._dialogs["cvat"].destroy()
                if after is not None:
                    after()
                else:
                    self.load_cvat(client, job)

        self._run_bg(work, done, "Đang đăng nhập CVAT…")

    def _fill_cvat_tasks(self, tasks: list[dict]):
        ui = self._cvat_ui
        ui["tasks"], ui["jobs"] = list(tasks), []
        ui["tasks_lb"].delete(0, "end")
        ui["jobs_lb"].delete(0, "end")
        for t in tasks:
            ui["tasks_lb"].insert("end", f"#{t['id']}  {t['name']}  ({t['size']} frame)")
        if not tasks:
            ui["status"].set("CVAT chưa có task nào.")

    def _cvat_list_tasks(self):
        """Mở lại hộp khi đã đăng nhập: liệt kê task ngay; khoá hết hạn thì báo đăng nhập lại."""
        client, ui = self.cvat_client, self._cvat_ui

        def done(tasks, err):
            if not self._cvat_dialog_alive():
                return
            if isinstance(err, LoginNeeded):
                ui["status"].set("Phiên đăng nhập CVAT đã hết hạn. Hãy đăng nhập lại.")
            elif err is not None:
                ui["status"].set(str(err))
            else:
                self._fill_cvat_tasks(tasks)
                ui["status"].set("Đã đăng nhập sẵn. Chọn một task, rồi chọn job và bấm Mở.")

        self._run_bg(client.tasks, done, "Đang lấy danh sách task…")

    def cvat_pick_task(self):
        ui = self._cvat_ui
        sel = ui["tasks_lb"].curselection() if ui else ()
        if not sel or self.cvat_client is None:
            return
        task, client = ui["tasks"][sel[0]], self.cvat_client

        def done(jobs, err):
            if not self._cvat_dialog_alive():
                return
            if err is not None:
                ui["status"].set("Phiên đăng nhập CVAT đã hết hạn. Hãy đăng nhập lại." if isinstance(err, LoginNeeded) else str(err))
                return
            ui["jobs"] = list(jobs)
            ui["jobs_lb"].delete(0, "end")
            for j in jobs:
                n = int(j["stop_frame"]) - int(j["start_frame"]) + 1
                ui["jobs_lb"].insert("end", f"Job #{j['id']}   frame {j['start_frame']}–{j['stop_frame']} ({n} frame)   {j['state']} / {j['stage']}")
            ui["status"].set(f"Task #{task['id']}: {len(jobs)} job." if jobs else f"Task #{task['id']} chưa có job nào.")

        self._run_bg(lambda: client.jobs(task["id"]), done, "Đang lấy danh sách job…")

    def cvat_open_selected(self):
        ui = self._cvat_ui
        sel = ui["jobs_lb"].curselection() if ui else ()
        if not sel or self.cvat_client is None:
            if ui:
                ui["status"].set("Chọn một job trong danh sách trước.")
            return
        job = ui["jobs"][sel[0]]
        self._dialogs["cvat"].destroy()
        self.load_cvat(self.cvat_client, int(job["id"]))

    def _login_again(self, retry):
        """CVAT trả 401: mở lại hộp đăng nhập; đăng nhập xong thì gọi `retry()`. Phiên và ghim đang làm không bị đụng tới."""
        self._cvat_after_login = retry
        self.open_cvat(relogin=True)

    # ---------- mở job ----------
    def load_cvat(self, client: CvatClient, job_id: int):
        """Mở job CVAT (luồng nền): job chưa có nhãn mắt thì gán nhãn bình thường, đã có thì chế độ QC (xem và quét)."""
        self.cvat_client = client

        def done(session, err):
            if isinstance(err, LoginNeeded):
                self._login_again(lambda: self.load_cvat(self.cvat_client, job_id))
            elif err is not None:
                self.report_error(err)
            else:
                self._install_cvat(session, client)

        self._run_bg(lambda: open_job(client, job_id), done, f"Đang mở job #{job_id} từ CVAT…")

    def _install_cvat(self, session, client: CvatClient):
        self._save_outgoing()
        self.playing = False
        self.s, self.scratch, self._scratch_pins = session, False, None
        self.cvat_client = client
        self.notice = f"Đã mở {session.title}."
        try:
            self.try_restore()                                # tự bắt lỗi CVAT khi bám lại; đây chỉ là chốt chặn để luôn tới _show_session
        except CvatError as err:
            self.notice = f"Không khôi phục được phiên đã lưu: {err}"
        try:
            self._show_session()
        except CvatError as err:                              # đọc frame đầu lỗi (mất kết nối, 401)
            self.report_error(err)

    def _save_outgoing(self):
        """Phiên sắp bị thay mà có thay đổi chưa lưu thì lưu vào file phiên của nó (không mất ghim khi mở job khác)."""
        s = self.s
        if s is not None and s.dirty and not self.scratch:
            self.save_work(auto=True)

    def _enter_qc_view(self):
        """Vào chế độ QC: tự Quét và mở tab Issues."""
        self.s.run_scan()
        self._fill_issues()
        self.side.select(self.issues_tab)

    def _open_extras(self):
        """Gọi khi một phiên vừa được mở xong: job đã có nhãn mắt thì vào chế độ QC (tự quét, mở tab Issues)."""
        if self.s is not None and self.s.qc:
            self._enter_qc_view()
            if qc.eye_labels(self.s.ann).empty():            # QC chỉ do JSON: bản xuất không còn thấy mắt nào để xem hay quét
                intro = ("Chế độ QC: job có nhãn mắt rỗng hoặc toàn Outside trên CVAT, bản xuất không hiện nhãn nào để xem. "
                         "Muốn gán lại thì bấm \"Xoá nhãn mắt cũ và gán lại\" (lúc gửi, nhãn mắt cũ trên CVAT bị thay). Gửi lên CVAT đang tắt.")
            else:
                n = len(self.s.findings)
                intro = (f"Chế độ QC: job đã có nhãn mắt, quét thấy {n} vấn đề. Chỉ xem; muốn gán lại thì bấm \"Xoá nhãn mắt cũ và gán lại\". "
                         "Gửi lên CVAT đang tắt.")
            self.notice = f"{self.notice} {intro}" if self.notice else intro

    def qc_clear(self):
        """Xoá nhãn mắt cũ và gán lại: hộp xác nhận nêu cái sẽ bỏ; đồng ý thì rời chế độ QC. Trên CVAT chưa đổi gì cho tới khi Gửi."""
        s = self.s
        if s is None or not s.qc:
            self.notice = "Không ở chế độ QC: job này không có nhãn mắt cũ nào để xoá."
            if s is not None:
                self.refresh(light=True)
            return
        if self.busy:
            self._edit_blocked()
            return
        gone = qc.eye_labels(s.ann)
        if gone.empty():             # QC chỉ do JSON (track mắt rỗng hoặc toàn Outside): phiên không giữ gì để bỏ
            text = ("Job có nhãn mắt trên CVAT (track rỗng hoặc toàn Outside) mà bản xuất không còn thấy, nên phiên chưa có gì để bỏ; "
                    "EyePin sẽ rời chế độ QC.\n"
                    "Trên CVAT chưa đổi gì cho tới khi bạn bấm \"Gửi lên CVAT\"; lúc đó nhãn mắt cũ trên CVAT bị thay bằng nhãn bạn gán. "
                    "Trước khi gửi, Ctrl+Z quay lại chế độ QC.\n\nTiếp tục?")
        else:
            text = (f"Sẽ bỏ nhãn mắt cũ của job khỏi phiên làm việc: {gone.message()}.\n"
                    "Nhãn không phải mắt giữ nguyên. Trên CVAT chưa đổi gì cho tới khi bạn bấm \"Gửi lên CVAT\"; lúc đó nhãn mắt cũ bị thay bằng nhãn bạn gán. "
                    "Trước khi gửi, Ctrl+Z đưa nhãn mắt cũ về và quay lại chế độ QC.\n\nTiếp tục?")
        if not self.ask_clear_eyes(text):
            self.notice = "Đã huỷ: vẫn ở chế độ QC."
            self.refresh(light=True)
            return
        s.clear_old_eyes()
        s.findings = []
        self._fill_issues()
        self.notice = "Đã bỏ nhãn mắt cũ khỏi phiên (CVAT chưa đổi). Vẽ hai mắt rồi bấm Gửi lên CVAT; Ctrl+Z quay lại chế độ QC."
        self.refresh()

    def leave_qc_by_undo(self) -> bool:
        """Ctrl+Z khi không còn gì để hoàn tác mà vừa xoá nhãn mắt cũ: khôi phục chúng và vào lại chế độ QC. Trả True nếu đã vào lại."""
        if self.s is None or self.s.qc or not self.s.restore_old_eyes():
            return False
        self._enter_qc_view()
        self.notice = "Đã đưa nhãn mắt cũ về: lại ở chế độ QC."
        return True

    # ---------- gửi lên CVAT ----------
    def send_cvat(self):
        """Gửi lên CVAT: kiểm job (luồng nền) → hộp xác nhận (SendPlan.text) → gửi và đối chiếu (luồng nền) → báo kết quả."""
        s, client = self.s, self.cvat_client
        if s is None or s.cvat is None or client is None:
            self.notice = "Chỉ gửi được khi đang mở một job từ CVAT (menu Mở từ CVAT…)."
        elif s.qc:
            self.notice = QC_MSG.replace("Muốn sửa thì bấm", "Gửi lên CVAT đang tắt; muốn gán lại thì bấm")
        elif self.busy:
            self.notice = f"{self.busy} Chờ việc này xong đã."
        elif not any(L.pins for L in s.layers):
            self.notice = "Chưa có nhãn mắt nào để gửi: hãy vẽ hoặc ghim ít nhất một mắt."
        else:
            self._run_bg(lambda: cvatsync.prepare(s, client), self._after_prepare, "Đang kiểm job trên CVAT…")
            return
        if s is not None:
            self.refresh(light=True)
        self._send_finished(False)                          # không gửi được gì: ai đang chờ kết quả lần gửi (Đăng xuất) biết mà dừng

    def _send_finished(self, ok: bool):
        """Lần gửi có kết quả cuối (xong và khớp, lỗi, hoặc người dùng huỷ ở hộp xác nhận): gọi việc đang chờ nó, một lần. Đăng nhập lại giữa chừng
        (LoginNeeded) chưa phải kết quả cuối: việc chờ ở nguyên đó cho tới lần gửi lại."""
        hook, self._after_send = self._after_send, None
        if hook is not None:
            hook(ok)

    def _send_text(self, plan) -> str:
        return plan.text() + "\n\nGửi lên CVAT?"          # job nền video có tag bị cvatsync.prepare từ chối trước khi tới đây

    def _after_prepare(self, plan, err):
        if isinstance(err, LoginNeeded):
            self._login_again(self.send_cvat)
        elif err is not None:
            self.report_error(err)
            self._send_finished(False)
        elif not self.ask_send(self._send_text(plan), plan.needs_warning()):
            self.notice = "Đã huỷ gửi: chưa gửi gì lên CVAT."
            self.refresh(light=True)
            self._send_finished(False)
        else:
            self._do_send(plan)

    def _do_send(self, plan):
        s, client = self.s, self.cvat_client

        def done(res, err):
            if isinstance(err, LoginNeeded):
                self._login_again(self.send_cvat)
            elif err is not None:
                self.report_error(err)
                self._send_finished(False)
            elif res.ok:
                s.dirty = True                                  # mốc `updated` mới và cờ `unsent` = False vào file phiên
                self.save_work(auto=True)
                self.notice = f"Đã gửi {plan.keyframes} keyframe lên job #{plan.job_id}; đối chiếu khớp với CVAT (vị trí, cờ Occluded/Outside, keyframe)."
                self._send_finished(True)
            else:
                self.notice = res.message
                self.show_send_failure(res, plan.job_id, s)
                self._send_finished(False)

        self._run_bg(lambda: cvatsync.send(s, client, plan), done, "Đang gửi nhãn lên CVAT…")

    def show_send_failure(self, res, job_id: int, session=None):
        """Hộp khi gửi không thành công hoặc đối chiếu lệch: thông điệp, danh sách chỗ lệch; khi đã gửi (có bản chụp) thì thêm giới hạn khôi phục,
        nút khôi phục và lưu bản chụp. Nút khôi phục nhớ phiên và job của lần gửi này (người dùng có thể mở job khác trước khi bấm)."""
        session = session if session is not None else self.s
        d, _ = self._toplevel("send_failed", "Gửi lên CVAT chưa khớp")
        for w in d.winfo_children():
            w.destroy()
        ttk.Label(d, text=res.message, wraplength=640, justify="left").pack(anchor="w", padx=12, pady=(12, 6))
        if res.mismatches:
            fr = ttk.Frame(d)
            fr.pack(fill="both", expand=True, padx=12)
            lb = tk.Listbox(fr, height=min(14, len(res.mismatches)), width=96)
            sb = ttk.Scrollbar(fr, command=lb.yview)
            lb.configure(yscrollcommand=sb.set)
            for line in res.mismatches:
                lb.insert("end", line)
            lb.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
        if res.snapshot is not None:                          # chưa gửi gì thì job chưa bị EyePin đụng tới: không có gì để khôi phục
            ttk.Label(d, text=RESTORE_LIMIT, wraplength=640, justify="left", style="Muted.TLabel").pack(anchor="w", padx=12, pady=8)
        bar = ttk.Frame(d)
        bar.pack(fill="x", padx=12, pady=(8, 12))
        if res.snapshot is not None:
            ttk.Button(bar, text="Khôi phục job về bản trước khi gửi",
                       command=lambda: self.restore_job(job_id, res.snapshot, session)).pack(side="left", padx=(0, 6))
            ttk.Button(bar, text="Lưu bản chụp…", command=lambda: self.save_snapshot(res.snapshot)).pack(side="left", padx=6)
        ttk.Button(bar, text="Đóng", command=d.destroy).pack(side="right")
        d.bind("<Escape>", lambda e: d.destroy())

    def restore_job(self, job_id: int, snapshot: bytes | None, session=None):
        """Khôi phục job `job_id` về bản trước khi gửi (import lại bản chụp). `session` là phiên của lần gửi đó (lúc dựng hộp lỗi): nếu nó vẫn là
        phiên đang mở thì `mark_synced` để lần gửi sau không báo giả là job bị sửa; nếu người dùng đã mở job hoặc thư mục khác thì job cũ vẫn
        được khôi phục nhưng mốc cập nhật của phiên đang mở không bị đụng tới (nếu không, cảnh báo "job bị sửa trên CVAT" của nó sẽ mất)."""
        s = session if session is not None else self.s
        source = getattr(s, "source", None)
        client = getattr(source, "client", None) or self.cvat_client
        if s is None or client is None or snapshot is None:
            return
        if not self.ask_restore_job(f"Khôi phục sẽ thay toàn bộ nhãn của job #{job_id} trên CVAT bằng bản chụp trước khi gửi.\n\n{RESTORE_LIMIT}\n\nTiếp tục?"):
            return
        current = self.s is s and (s.cvat or {}).get("job") == job_id     # trong lúc việc nền chạy không mở được phiên khác (busy)

        def work():
            cvatsync.restore(client, job_id, snapshot)
            return cvatsync.mark_synced(s, client) if current else None

        def done(updated, err):
            if isinstance(err, LoginNeeded):
                self._login_again(lambda: self.restore_job(job_id, snapshot, s))
            elif err is not None:
                self.report_error(err)                         # bản chụp còn trong hộp: bấm lại để thử lại
            elif current:
                s.dirty = True
                self.save_work(auto=True)
                self.notice = (f"Đã khôi phục job #{job_id} về bản trước khi gửi (nhãn nền). Nhãn mắt bạn gán vẫn còn trong EyePin; "
                               "kiểm lại rồi bấm Gửi lên CVAT nếu muốn gửi lại.")
            else:
                self.notice = (f"Đã khôi phục job #{job_id} về bản trước khi gửi (nhãn nền). Bạn đang mở {self.s.title if self.s else 'phiên khác'}: "
                               f"mốc cập nhật của phiên đang mở không đổi. Khi mở lại job #{job_id}, EyePin sẽ báo job đã đổi trên CVAT (do lần khôi phục này).")

        self._run_bg(work, done, f"Đang khôi phục job #{job_id}…")

    def save_snapshot(self, snapshot: bytes | None):
        """Ghi bản chụp (XML chỉ có toạ độ) ra file người dùng chọn."""
        if snapshot is None:
            return
        p = filedialog.asksaveasfilename(title="Lưu bản chụp job trước khi gửi", defaultextension=".xml", filetypes=[("XML", "*.xml")],
                                         initialfile="eyepin_truoc_khi_gui.xml", parent=self._dialogs.get("send_failed") or self.root)
        if not p:
            return
        try:
            with open(p, "wb") as fh:
                fh.write(snapshot)
        except OSError as err:
            self.notice = f"Không lưu được bản chụp: {err}"
        else:
            self.notice = f"Đã lưu bản chụp: {p}"
        if self.s is not None:
            self.refresh(light=True)
