"""Issue CVAT của job đang mở, hiện thành nhóm cuối của tab Issues (thiết kế: design/2026-11-19-qc-edit-design.md mục 6.6).

`JobIssuesMixin` là mixin của `App`. Mỗi lần mở một phiên (`App._open_extras`) và mỗi lần bấm menu "Tải lại issue CVAT" thì `load_job_issues` lấy issue của
job đang mở (chỉ GET) trên một luồng nền RIÊNG với một client riêng, như `ReportMixin._report_fetch`: không dùng `App._run_bg`, không đặt `App.busy`, nên
không chặn gán nhãn. Luồng nền không chạm Tk: kết quả đi qua hàng đợi, luồng chính lấy bằng `root.after`. Mỗi lần tải có một số thứ tự
(`_job_issues_seq`, cũng nằm trong chữ ký bảng Issues: `ObjectsMixin._issues_signature`); kết quả của lần tải cũ, hoặc của job không còn là phiên đang mở,
bị bỏ. Lỗi (không có khoá đăng nhập, mạng, 401...) chỉ thành MỘT dòng trong nhóm: không mở hộp đăng nhập.

Dòng của nhóm do `cvat_issue_entries` trả cho `ObjectsMixin._issue_entries`: `(chỉ số EyePin hoặc None, chữ ngắn, mức, chi tiết)`. Chỉ số EyePin là vị trí của
`issue.frame` (số frame của task) trong danh sách frame của job; không có trong danh sách thì None (dòng vẫn hiện, không nhảy tới được).
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import traceback

from . import issuereport
from .cvatapi import CvatError
from .issuereport import Row

POLL_MS = 40
NOT_LOGGED_IN = "Chưa đăng nhập CVAT: không tải được issue."
NOT_IN_JOB = "Frame của issue này không có trong job đang mở."
LEVEL_OPEN, LEVEL_RESOLVED = "yellow", "green"      # chưa sửa / đã sửa; khoá của `ObjectsMixin.ISSUE_LEVELS`


def _line(text: str) -> tuple:
    """Dòng duy nhất của nhóm khi không tải được: không có frame để nhảy tới."""
    return None, text, LEVEL_OPEN, text


def _first_line(message: str) -> str:
    lines = message.strip().splitlines()
    return lines[0].strip() if lines else ""


def _entry(r: Row, index: int | None) -> tuple:
    """Dòng của một issue: chữ ngắn là dòng đầu của mô tả, chi tiết có mô tả đủ, các trả lời và link mở frame đó trên CVAT."""
    head = f"Issue CVAT #{r.issue_id} · frame {r.frame} · {r.status} · người báo {r.owner}" + (f" · {r.created:%d/%m/%Y %H:%M}" if r.created else "")
    lines = [head, "Mô tả:", r.message]
    if r.replies:
        lines += ["Trả lời:", r.replies]
    lines.append(f"Mở trên CVAT: {r.link}")
    return index, f"Issue CVAT · {r.status} · {_first_line(r.message)}", LEVEL_RESOLVED if r.resolved else LEVEL_OPEN, "\n".join(lines)


class JobIssuesMixin:
    # ---------- khởi dựng ----------
    def _init_job_issues(self) -> None:
        self._job_issues_seq = 0                      # số thứ tự lần tải; chỉ tăng. Đổi ở mỗi lần tải mới và mỗi lần nhóm đổi dòng (bảng Issues dựng lại)
        self._job_issues: list[tuple] = []            # các dòng của nhóm, đúng dạng `cvat_issue_entries` trả
        self._job_issues_error: str | None = None     # lời lỗi khi nhóm chỉ có dòng lỗi
        self._job_issues_job: int | None = None       # job mà `_job_issues` và lần tải đang bay thuộc về
        self._job_issues_loading = False              # có một lần tải còn đang bay

    def cvat_issue_entries(self) -> list[tuple[int | None, str, str, str]]:
        """Dòng nhóm "Issue CVAT" của tab Issues: (chỉ số EyePin hoặc None nếu không nhảy được, chữ ngắn, mức, chi tiết)."""
        return list(self._job_issues)

    def job_issue_unjumpable_notice(self) -> str:
        """Lời báo khi bấm đúp một dòng của nhóm mà không nhảy tới frame nào: dòng lỗi tải thì chính lời lỗi, issue ngoài job thì nói frame không có."""
        return self._job_issues_error or NOT_IN_JOB

    # ---------- tải (luồng nền riêng) ----------
    def load_job_issues(self) -> None:
        """Tải lại issue của job CVAT đang mở. Nhóm cũ bị bỏ ngay; không phải job CVAT thì nhóm rỗng và không tải gì; chưa có khoá đăng nhập thì nhóm chỉ
        có dòng lỗi (không mở hộp đăng nhập)."""
        s, cl = self.s, self.cvat_client
        job = s.cvat["job"] if s is not None and s.cvat is not None else None
        self._job_issues_seq += 1                     # kết quả của lần tải cũ (còn bay) từ đây là cũ
        seq, had = self._job_issues_seq, bool(self._job_issues)
        self._job_issues, self._job_issues_error, self._job_issues_job = [], None, job
        self._job_issues_loading = job is not None and cl is not None and cl.token is not None
        if job is not None and not self._job_issues_loading:
            self._job_issues, self._job_issues_error = [_line(NOT_LOGGED_IN)], NOT_LOGGED_IN
        if s is not None and (had or self._job_issues):
            self.refresh()                            # nhóm cũ biến mất, dòng lỗi hiện, ngay chứ không đợi lần vẽ sau
        if self._job_issues_loading:
            self._job_issues_fetch(seq, job, cl)

    def _job_issues_fetch(self, seq: int, job: int, cl) -> None:
        """Lấy issue và bình luận của `job` bằng client riêng. Mọi lỗi về `_job_issues_done`, không để ném ra Tk."""
        c = None
        try:
            c = self.new_client(cl.url)               # client riêng cho mỗi lần tải: không dùng chung kết nối với luồng chính đang đọc ảnh
            c.use_token(cl.token)
            task_id = self.s.source.job.get("task_id")
        except Exception as err:
            if c is not None:
                c.close()
            self._job_issues_done(seq, None, err)
            return
        out: queue.Queue = queue.Queue(maxsize=1)

        def work():
            try:
                issues = c.job_issues(job)
                comments = c.comments(job) if issues else []
                res = (issuereport.job_rows(c.url, task_id, issues, comments), None)
            except Exception as err:                  # mọi lỗi đều phải về `_job_issues_done`
                res = (None, err)
            finally:
                c.close()
            out.put(res)

        def poll():
            if self._torn or seq != self._job_issues_seq or not self._job_issues_table_alive():
                return                                # cửa sổ đã đóng hoặc đã có lần tải mới hơn: bỏ kết quả, không hẹn lại
            try:
                res, err = out.get_nowait()
            except queue.Empty:
                self.root.after(POLL_MS, poll)
                return
            self._job_issues_done(seq, res, err)

        try:
            threading.Thread(target=work, daemon=True).start()
        except Exception as err:
            c.close()
            self._job_issues_done(seq, None, err)
            return
        self.root.after(POLL_MS, poll)

    def _job_issues_table_alive(self) -> bool:
        try:
            return bool(self.issue_table.winfo_exists())
        except (AttributeError, tk.TclError):
            return False

    def _job_issues_done(self, seq: int, result, err) -> None:
        """Kết quả một lần tải, ở luồng chính: `result` là danh sách `Row` của job. Lần tải cũ hoặc phiên đang mở không còn là job đó thì bỏ."""
        if self._torn or seq != self._job_issues_seq:
            return
        self._job_issues_loading = False
        s = self.s
        if s is None or s.cvat is None or s.cvat["job"] != self._job_issues_job:
            return
        if err is not None:
            if not isinstance(err, CvatError):        # lỗi lập trình: để lại dấu vết trên console, người dùng thấy một dòng
                traceback.print_exception(type(err), err, err.__traceback__)
            text = f"Không tải được issue: {err}" if isinstance(err, CvatError) else f"Không tải được issue: {type(err).__name__}: {err}"
            self._job_issues_show([_line(text)], text)
            return
        index = {n: i for i, n in enumerate(s.source.frame_numbers)}
        self._job_issues_show([_entry(r, index.get(r.frame)) for r in result])

    def _job_issues_show(self, rows: list[tuple], error: str | None = None) -> None:
        """Đặt dòng của nhóm; đổi số thứ tự để chữ ký bảng Issues đổi, rồi vẽ lại."""
        self._job_issues, self._job_issues_error = rows, error
        self._job_issues_seq += 1
        self.refresh()
