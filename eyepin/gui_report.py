"""Cửa sổ "Báo cáo issue CVAT": lấy issue của một task từ CVAT và hiện thành bảng (thiết kế: design/2026-11-18-issue-report-design.md mục 6.3).

`ReportMixin` là mixin của `App`. Cửa sổ là một cửa sổ phụ (`App._toplevel`), nên không khoá cửa sổ chính, không cần job nào đang mở và bị
`App.teardown` đóng khi đăng xuất. Việc lấy dữ liệu chạy trên luồng nền RIÊNG của màn này (mẫu `LoginScreen._bg`), với một client riêng cho mỗi
lần lấy; nó KHÔNG dùng `App._run_bg` và không đụng `App.busy`, nên không chặn gán nhãn và không đổi dòng trạng thái chính. Luồng nền không chạm
Tk: kết quả đi qua hàng đợi, luồng chính lấy bằng `root.after`. Mỗi lần lấy có một số thứ tự (`_report_seq`); kết quả của lần lấy cũ, hoặc về
sau khi màn đã đóng, bị bỏ. Lấy lỗi thì bảng để trống (không ai xuất nhầm dữ liệu cũ).

Mọi thứ hiện trên màn nằm trong `self._report_ui` (dict rỗng khi màn đóng); dữ liệu hiện ra luôn suy từ `ui["report"]`, không từ ô chọn task.
File Excel cũng ghi từ `ui["report"]` và đúng bộ lọc lúc bấm "Xuất Excel…" (chụp trước hộp chọn nơi lưu). Việc đăng nhập: 401 lúc lấy mở lại hộp đăng nhập của `CvatMixin` rồi tự lấy lại (không
giành chỗ của việc khác đang chờ đăng nhập, `_cvat_after_login`); đổi tài khoản thì `cvat_login` gọi `_report_reset` để màn không hiện dữ liệu của người
trước. Mọi đường lấy vẫn chỉ đi qua `_report_fetch` và `_report_done`.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import traceback
import webbrowser
from tkinter import filedialog, ttk

from . import issuereport, issuexlsx
from .cvatapi import CvatError, LoginNeeded
from .issuereport import Row

REPORT_TITLE = "Báo cáo issue CVAT"
FILTER_ALL = issuexlsx.ALL
STATUS_CHOICES = {FILTER_ALL: None, issuereport.STATUS_OPEN: False, issuereport.STATUS_RESOLVED: True}   # ô Trạng thái -> `resolved` của `select`
NOT_LOGGED_IN = "CVAT báo chưa đăng nhập hoặc phiên đăng nhập đã hết hạn. Hãy đăng nhập lại."
LOGIN_EXPIRED = "Phiên đăng nhập CVAT đã hết hạn. Đăng nhập lại ở hộp vừa mở thì báo cáo tự lấy lại; nếu đóng hộp đó, hãy bấm Làm mới."
LOGIN_PENDING = "Hãy đăng nhập lại (menu Mở từ CVAT…) rồi bấm Làm mới."      # đã có việc khác chờ đăng nhập: không giành chỗ của nó
LOGIN_FIRST = "Hãy đăng nhập CVAT (menu Mở từ CVAT…) rồi mở lại Báo cáo issue."
MESSAGE_CHARS = 120                                   # dòng đầu của mô tả dài hơn ngần này ký tự thì cắt
POLL_MS = 40


def _task_label(task: dict) -> str:
    return "#%d  %s  (%d frame)" % (task["id"], task["name"], task["size"])


def _first_line(message: str) -> str:
    """Dòng đầu của mô tả để hiện trong bảng; còn dòng sau thì thêm " …". Dữ liệu để xuất vẫn là mô tả nguyên văn."""
    lines = message.strip().splitlines()
    first = lines[0] if lines else ""
    if len(first) > MESSAGE_CHARS:
        return first[:MESSAGE_CHARS] + "…"
    return first + " …" if len(lines) > 1 else first


def _row_values(r: Row) -> tuple:
    return (r.job, r.frame, _first_line(r.message), r.status, r.owner, r.created.strftime("%d/%m %H:%M") if r.created else "")


def _job_values(job: issuereport.JobInfo, line: issuereport.SummaryLine, ticked: bool, flagged: bool) -> tuple:
    name = str(job.id)
    if job.type != issuereport.DEFAULT_JOB_TYPE:
        name += " (%s)" % job.type
    if not job.listed:
        name += " (không xem được)"
    count = "%d (%d)" % (line.total, line.open) if line.total else "0"
    return ("☑" if ticked else "☐", name, job.assignee, count + " ⚠" if flagged else count)


def _warning_tail(warnings) -> str:
    """Cảnh báo ở cuối dòng trạng thái: chỉ hiện cảnh báo đầu và số cảnh báo còn lại, để nhiều cảnh báo không đẩy các bảng ra khỏi cửa sổ (đủ cả ở sheet Tổng hợp)."""
    if not warnings:
        return ""
    tail = "  ⚠ " + warnings[0]
    if len(warnings) > 1:
        tail += " (và %d cảnh báo khác; xem đủ ở sheet Tổng hợp khi xuất)" % (len(warnings) - 1)
    return tail


def _status_text(report: issuereport.Report, shown: list[Row], excluded) -> str:
    tail = _warning_tail(report.warnings)
    if not report.rows:
        return "Task này chưa có issue nào." + tail
    text = "Đang hiện %d / %d issue" % (len(shown), len(report.rows))
    skipped = sum(1 for r in report.rows if r.job in excluded)
    if skipped:
        text += " · %d issue ở job không chọn" % skipped
    return text + " · %d chưa sửa · tài khoản %s · lấy lúc %s" % (
        sum(1 for r in shown if not r.resolved), report.user, report.fetched.strftime("%H:%M")) + tail


def _table(parent, columns, **kw) -> ttk.Treeview:
    """Bảng có thanh cuộn dọc; mỗi cột là (mã, tiêu đề, rộng, căn lề, co giãn)."""
    tv = ttk.Treeview(parent, columns=[c[0] for c in columns], show="headings", **kw)
    for key, title, width, anchor, stretch in columns:
        tv.heading(key, text=title, anchor=anchor)
        tv.column(key, width=width, anchor=anchor, stretch=stretch)
    bar = ttk.Scrollbar(parent, orient="vertical", command=tv.yview)
    tv.configure(yscrollcommand=bar.set)
    bar.pack(side="right", fill="y")
    tv.pack(side="left", fill="both", expand=True)
    return tv


def _refill(tv: ttk.Treeview, items) -> None:
    """Thay mọi dòng của bảng bằng `items` (mỗi phần tử là (mã dòng, giá trị)), giữ chỗ đã cuộn tới."""
    top = tv.yview()[0]
    tv.delete(*tv.get_children())
    for iid, values in items:
        tv.insert("", "end", iid=iid, values=values)
    tv.yview_moveto(top)


class ReportMixin:
    # ---------- khởi dựng và dựng cửa sổ ----------
    def _init_report(self) -> None:
        self._report_ui: dict = {}                    # rỗng khi màn đóng
        self._report_seq = 0                          # số thứ tự lần lấy; chỉ tăng, không bao giờ đặt lại

    def show_issue_report(self, task_id: int | None = None) -> None:
        """Mở cửa sổ và lấy issue của `task_id`; None thì lấy task mặc định (`_report_default_task`), không có thì chỉ lấy danh sách task.
        Cửa sổ đã mở thì chỉ đưa lên trước: không lấy lại, không đổi các ô đã bỏ tick, không tính task mặc định (tính thì bấm menu lần nữa có thể đổi
        task). Chỉ khi `task_id` khác None và khác task đang chọn thì đổi sang task đó. Chưa đăng nhập thì cửa sổ không mở (`_report_need_login`)."""
        if self._report_alive():
            self._toplevel("issue_report", REPORT_TITLE)
            if task_id is not None and task_id != self._report_ui["task_id"]:
                self._report_switch_task(task_id)
            return
        cl = self.cvat_client
        if cl is None or cl.token is None:
            self._report_need_login(task_id)
            return
        d, _ = self._toplevel("issue_report", REPORT_TITLE)
        self._report_build(d)
        self._report_ui["task_id"] = task_id if task_id is not None else self._report_default_task()
        self._report_fetch()

    def _report_default_task(self) -> int | None:
        """Task của job CVAT đang mở; không có thì task đang chọn trong hộp "Mở từ CVAT…"; không có nữa thì None."""
        s = self.s
        if s is not None and s.cvat is not None:
            return s.source.job.get("task_id")
        return self._cvat_selected_task()

    def _report_need_login(self, task_id: int | None) -> None:
        """Chưa đăng nhập: mở hộp đăng nhập sẵn có và tự mở báo cáo sau khi đăng nhập xong. Đã có việc khác chờ đăng nhập (hoặc đang bận) thì không
        giành chỗ của nó, chỉ báo người dùng."""
        if self._cvat_after_login is None and not self.busy:
            self._login_again(lambda: self.show_issue_report(task_id))
            return
        self.notice = LOGIN_FIRST
        if self.s is None:
            self.status.set(self.notice)
        else:
            self.refresh(light=True)

    def _report_build(self, d: tk.Toplevel) -> None:
        d.geometry("1120x560")
        d.minsize(780, 340)
        ui = {"tasks": [], "task_id": None, "report": None, "excluded": set(), "loading": False,
              "status_filter": tk.StringVar(d, FILTER_ALL), "owner_filter": tk.StringVar(d, FILTER_ALL), "status": tk.StringVar(d)}
        bar = ttk.Frame(d)
        bar.pack(fill="x", padx=10, pady=(10, 6))
        ttk.Label(bar, text="Task:").pack(side="left")
        ui["task_cb"] = ttk.Combobox(bar, state="readonly", width=40)
        ui["task_cb"].pack(side="left", padx=(6, 14))
        ui["task_cb"].bind("<<ComboboxSelected>>", lambda e: self.report_pick_task())
        ttk.Label(bar, text="Trạng thái:").pack(side="left")
        status_cb = ttk.Combobox(bar, textvariable=ui["status_filter"], values=list(STATUS_CHOICES), state="readonly", width=10)
        status_cb.pack(side="left", padx=(6, 14))
        ttk.Label(bar, text="Người báo:").pack(side="left")
        ui["owner_cb"] = ttk.Combobox(bar, textvariable=ui["owner_filter"], values=[FILTER_ALL], state="readonly", width=16)
        ui["owner_cb"].pack(side="left", padx=(6, 0))
        for cb in (status_cb, ui["owner_cb"]):
            cb.bind("<<ComboboxSelected>>", lambda e: self._report_fill())
        ui["export_btn"] = ttk.Button(bar, text="Xuất Excel…", command=self.report_export)
        ui["export_btn"].pack(side="right")
        ui["refresh_btn"] = ttk.Button(bar, text="Làm mới", command=self.report_refresh)
        ui["refresh_btn"].pack(side="right", padx=(0, 8))

        line = ttk.Label(d, textvariable=ui["status"], anchor="w", justify="left")
        line.pack(side="bottom", fill="x", padx=10, pady=(6, 8))
        line.bind("<Configure>", lambda e: line.configure(wraplength=max(200, e.width - 4)))
        panes = ttk.Panedwindow(d, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=10)
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=4)
        ui["jobs_tv"] = _table(left, (("tick", "Chọn", 46, "center", False), ("job", "Job", 140, "w", True),
                                      ("assignee", "Được giao", 90, "w", True), ("issues", "Issue", 70, "e", False)), selectmode="none")
        ui["jobs_tv"].bind("<Button-1>", self._report_click_job)
        ui["rows_tv"] = _table(right, (("job", "Job", 60, "center", False), ("frame", "Frame", 60, "center", False),
                                       ("message", "Mô tả lỗi", 260, "w", True), ("status", "Trạng thái", 80, "w", False),
                                       ("owner", "Người báo", 100, "w", False), ("created", "Ngày báo", 100, "w", False)), selectmode="browse")
        ui["rows_tv"].bind("<Double-Button-1>", self._report_double_click)
        self._report_ui = ui
        self._report_controls()
        d.bind("<Destroy>", lambda e: self._report_closed() if e.widget is d else None)

    def _report_closed(self) -> None:
        self._report_ui = {}

    def _report_alive(self) -> bool:
        d = self._dialogs.get("issue_report")
        try:
            return bool(self._report_ui) and d is not None and bool(d.winfo_exists())
        except tk.TclError:
            return False

    # ---------- lấy dữ liệu (luồng nền riêng) ----------
    def _report_fetch(self) -> None:
        """Mọi đường lấy (mở màn, Làm mới, đổi task) đi qua đây. Lỗi nào cũng về `_report_done`, không để ném ra Tk."""
        ui = self._report_ui
        self._report_seq += 1
        seq, task_id, cl = self._report_seq, ui["task_id"], self.cvat_client
        if cl is None or cl.token is None:
            self._report_done(seq, None, LoginNeeded(NOT_LOGGED_IN, 401))
            return
        c = None
        try:
            c = self.new_client(cl.url)                   # client riêng cho mỗi lần lấy: không dùng chung kết nối với luồng chính đang đọc ảnh
            c.use_token(cl.token)
        except Exception as err:
            if c is not None:
                c.close()
            self._report_done(seq, None, err)
            return
        out: queue.Queue = queue.Queue(maxsize=1)

        def work():
            try:
                res = (issuereport.load(c, task_id), None)
            except Exception as err:                      # mọi lỗi đều phải về `_report_done`, không thì các nút bị khoá mãi
                res = (None, err)
            finally:
                c.close()
            out.put(res)

        def poll():
            if not self._report_alive() or seq != self._report_seq:
                return                                    # màn đã đóng hoặc đã có lần lấy mới hơn: bỏ kết quả, không hẹn lại
            try:
                res, err = out.get_nowait()
            except queue.Empty:
                self.root.after(POLL_MS, poll)
                return
            self._report_done(seq, res, err)

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception as err:
            c.close()
            self._report_done(seq, None, err)
            return
        self.root.after(POLL_MS, poll)
        ui["loading"] = True
        ui["status"].set("Đang lấy issue của task #%d…" % task_id if task_id is not None else "Đang lấy danh sách task…")
        self._report_controls()

    def _report_done(self, seq: int, result, err) -> None:
        """Kết quả một lần lấy, ở luồng chính. Lần lấy cũ hoặc màn đã đóng thì bỏ."""
        if not self._report_alive() or seq != self._report_seq:
            return
        ui = self._report_ui
        ui["loading"] = False
        if err is not None:
            ui["report"] = None
            if isinstance(err, LoginNeeded):
                self._report_login_lost()
            elif isinstance(err, CvatError):
                ui["status"].set(str(err))
            else:
                traceback.print_exception(type(err), err, err.__traceback__)
                ui["status"].set("Lỗi không mong đợi: %s: %s" % (type(err).__name__, err))
        else:
            tasks, report = result
            ui["tasks"], ui["report"] = tasks, report
            ui["task_cb"]["values"] = [_task_label(t) for t in tasks]
            ids = [t["id"] for t in tasks]
            if ui["task_id"] in ids:
                ui["task_cb"].current(ids.index(ui["task_id"]))
            else:
                ui["task_cb"].set("")
            ui["excluded"] = ui["excluded"] & {j.id for j in report.jobs} if report is not None else set()
            names = [FILTER_ALL] + (issuereport.owners(report) if report is not None else [])
            ui["owner_cb"]["values"] = names
            if ui["owner_filter"].get() not in names:
                ui["owner_filter"].set(FILTER_ALL)
            if report is None:
                ui["status"].set("Không còn thấy task #%d trên CVAT." % ui["task_id"] if ui["task_id"] is not None else "Chọn một task để xem issue.")
        self._report_fill()

    def _report_login_lost(self) -> None:
        """Lúc lấy mà CVAT trả 401 (hoặc thiếu khoá): mở lại hộp đăng nhập và tự lấy lại sau khi đăng nhập. Đã có việc khác chờ đăng nhập (hoặc đang bận)
        thì KHÔNG đụng vào việc chờ đó, chỉ dặn người dùng tự đăng nhập rồi bấm Làm mới."""
        if self._cvat_after_login is None and not self.busy:
            self._report_ui["status"].set(LOGIN_EXPIRED)
            self._login_again(self.report_refresh)
        else:
            self._report_ui["status"].set(LOGIN_PENDING)

    # ---------- thao tác của người dùng ----------
    def report_pick_task(self) -> None:
        """Ô chọn task đổi: task khác thì xoá bảng ngay rồi lấy task mới; vẫn task đó thì như Làm mới (giữ job đã bỏ tick)."""
        ui = self._report_ui
        if not ui:
            return
        i, tasks = ui["task_cb"].current(), ui["tasks"]
        if not 0 <= i < len(tasks):
            return
        if tasks[i]["id"] == ui["task_id"]:
            self.report_refresh()
            return
        self._report_switch_task(tasks[i]["id"])

    def _report_switch_task(self, task_id: int) -> None:
        """Đổi sang task khác: xoá bảng và các ô đã bỏ tick ngay (chúng thuộc task cũ), rồi lấy task mới."""
        ui = self._report_ui
        ui["task_id"], ui["report"], ui["excluded"] = task_id, None, set()
        ids = [t["id"] for t in ui["tasks"]]
        if task_id in ids:
            ui["task_cb"].current(ids.index(task_id))
        self._report_fill()
        self._report_fetch()

    def report_refresh(self) -> None:
        if self._report_alive():
            self._report_fetch()

    def _report_reset(self, text: str) -> None:
        """Bỏ dữ liệu đang hiện (đổi tài khoản: nó là của người khác) và ghi `text` lên dòng trạng thái. Lần lấy đang bay bị bỏ kết quả. GIỮ task
        đang chọn và các job đã bỏ tick, để Làm mới lấy lại đúng task đó. Màn đóng thì không làm gì."""
        if not self._report_alive():
            return
        ui = self._report_ui
        self._report_seq += 1
        ui["loading"], ui["report"] = False, None
        self._report_fill()
        ui["status"].set(text)

    def report_toggle_job(self, job_id: int) -> None:
        ui = self._report_ui
        if not ui or ui["report"] is None or job_id not in {j.id for j in ui["report"].jobs}:
            return
        ui["excluded"] ^= {job_id}
        self._report_fill()

    def _report_click_job(self, event) -> str | None:
        """Bấm vào một ô của dòng job thì đổi tick và chặn xử lý mặc định; bấm tiêu đề hay đường biên cột thì để Tk làm việc của nó (kéo đổi cỡ cột)."""
        tv = self._report_ui["jobs_tv"]
        iid = tv.identify_row(event.y)
        if tv.identify_region(event.x, event.y) == "cell" and iid:
            self.report_toggle_job(int(iid))
            return "break"
        return None

    # ---------- hiện dữ liệu ----------
    def _report_owner(self) -> str | None:
        name = self._report_ui["owner_filter"].get()
        return None if name == FILTER_ALL else name

    def report_rows(self) -> list[Row]:
        """Các dòng bảng đang hiện, đúng thứ tự; rỗng khi màn đóng hoặc chưa có dữ liệu."""
        ui = self._report_ui
        if not ui or ui["report"] is None:
            return []
        return issuereport.select(ui["report"], ui["excluded"], STATUS_CHOICES.get(ui["status_filter"].get()), self._report_owner())

    def _report_fill(self) -> None:
        """Vẽ lại danh sách job, bảng issue, dòng trạng thái và trạng thái nút. Chưa có dữ liệu (đổi task, lấy lỗi) thì chỉ xoá hai bảng: dòng
        trạng thái giữ nguyên để lời báo lỗi không mất khi đổi bộ lọc; đang lấy thì cũng giữ dòng "Đang lấy…"."""
        ui = self._report_ui
        if not ui:
            return
        report, rows = ui["report"], self.report_rows()
        if report is None:
            _refill(ui["jobs_tv"], ())
            _refill(ui["rows_tv"], ())
        else:
            excluded = ui["excluded"]
            lines = issuereport.summary(report, excluded, self._report_owner())
            _refill(ui["jobs_tv"], ((str(j.id), _job_values(j, line, j.id not in excluded, j.id in report.flagged))
                                    for j, line in zip(report.jobs, lines)))
            _refill(ui["rows_tv"], ((str(r.issue_id), _row_values(r)) for r in rows))
            if not ui["loading"]:
                ui["status"].set(_status_text(report, rows, excluded))
        self._report_controls()

    def _report_controls(self) -> None:
        """Ô chọn task và nút Làm mới tắt khi đang lấy; nút Xuất chỉ bật khi không lấy và bảng có dòng."""
        ui = self._report_ui
        loading = ui["loading"]
        for w in (ui["task_cb"], ui["refresh_btn"]):
            w.state(["disabled" if loading else "!disabled"])
        ui["export_btn"].state(["disabled" if loading or not self.report_rows() else "!disabled"])

    # ---------- xuất Excel và mở link ----------
    def ask_report_path(self, initialdir: str, initialfile: str) -> str:
        """Hộp chọn nơi lưu file Excel (thay được trong test). Người dùng huỷ thì trả chuỗi rỗng (hoặc tuple rỗng)."""
        return filedialog.asksaveasfilename(title="Xuất báo cáo issue", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                            initialdir=initialdir, initialfile=initialfile, parent=self._dialogs.get("issue_report") or self.root)

    def open_link(self, url: str) -> None:
        """Mở `url` bằng trình duyệt mặc định (thay được trong test)."""
        webbrowser.open(url)

    def _report_dir(self) -> str:
        """Thư mục gợi ý cho hộp lưu: thư mục lần xuất trước nếu còn; không thì Documents; không thì thư mục nhà (không bao giờ là thư mục chương trình)."""
        saved = self.settings["workspace"].get("report_dir") or ""
        if saved and os.path.isdir(saved):
            return saved
        home = os.path.expanduser("~")
        docs = os.path.join(home, "Documents")
        return docs if os.path.isdir(docs) else home

    def report_export(self) -> None:
        """Ghi các dòng đang hiện ra file Excel. Mọi thông tin task, tài khoản, giờ lấy lấy từ dữ liệu đã tải (`ui["report"]`), không từ ô chọn task:
        ô chọn có thể đã đổi mà chưa lấy. Dòng, bộ lọc và dữ liệu được chụp trước hộp chọn nơi lưu và file chỉ ghi từ bản chụp đó. Kết quả và lỗi hiện
        trên dòng trạng thái của màn, trừ khi màn đã đóng hoặc đã có trạng thái mới hơn."""
        ui = self._report_ui
        if not ui or ui["loading"] or ui["report"] is None:
            return
        rows = self.report_rows()
        if not rows:
            ui["status"].set("Không có issue nào để xuất.")
            return
        try:
            issuexlsx.ensure_available()                  # thiếu openpyxl thì báo ngay, không bắt người dùng chọn nơi lưu rồi mới biết
        except issuexlsx.MissingOpenpyxl as err:
            ui["status"].set(str(err))
            return
        # Chụp mọi thứ file cần TRƯỚC hộp lưu: hộp của hệ điều hành chạy vòng lặp sự kiện riêng, người dùng có thể đổi bộ lọc, đổi task hay đăng nhập
        # lại trong lúc đó. File ghi đúng những gì đã hiện lúc bấm nút.
        report, seq, excluded = ui["report"], self._report_seq, frozenset(ui["excluded"])
        resolved, owner = STATUS_CHOICES.get(ui["status_filter"].get()), self._report_owner()
        path = self.ask_report_path(self._report_dir(), issuexlsx.default_name(report))
        if not path:                                      # người dùng huỷ: hộp trả "" hoặc ()
            return
        path = str(path)
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            issuexlsx.write(path, report, rows, excluded=excluded, resolved=resolved, owner=owner)
        except issuexlsx.MissingOpenpyxl as err:
            message = str(err)
        except PermissionError as err:
            message = "Không ghi được file %s: %s (file có đang mở trong Excel không?)" % (path, err)
        except OSError as err:
            message = "Không ghi được file %s: %s" % (path, err)
        except Exception as err:                          # lỗi lập trình: để lại dấu vết trên console, người dùng thấy một dòng
            traceback.print_exception(type(err), err, err.__traceback__)
            message = "Lỗi không mong đợi khi xuất: %s: %s" % (type(err).__name__, err)
        else:
            self.settings["workspace"]["report_dir"] = os.path.dirname(os.path.abspath(path))
            self.save_settings()
            message = "Đã xuất %d issue ra %s." % (len(rows), path)
        if self._report_alive() and self._report_seq == seq:   # màn đã đóng hoặc đã có trạng thái mới hơn (lấy lại, đổi tài khoản): dòng trạng thái là của nó
            ui["status"].set(message)

    def report_open_row(self) -> None:
        """Mở link của dòng đang chọn (frame đó trong job, trên CVAT) bằng trình duyệt. Không chọn dòng nào thì không làm gì."""
        ui = self._report_ui
        selected = ui["rows_tv"].selection() if ui else ()
        if not selected:
            return
        for r in self.report_rows():
            if str(r.issue_id) == selected[0]:
                self.open_link(r.link)
                return

    def _report_double_click(self, event) -> None:
        if self._report_ui and self._report_ui["rows_tv"].identify_row(event.y):         # đúp lên tiêu đề hay chỗ trống thì không mở gì
            self.report_open_row()
