"""Issue CVAT của job đang mở, hiện ở tab Issues (design/2026-11-19-qc-edit-design.md mục 6.6): `CvatClient.job_issues`, `issuereport.job_rows` và
`gui_jobissues.JobIssuesMixin`.

Server giả `FakeCvat`; ảnh frame và job dựng như `test_gui_cvat`. Bỏ qua phần giao diện nếu máy không mở được cửa sổ Tk. Mỗi test giao diện cài một bộ
ghi lỗi hàm gọi lại của Tk (như `test_gui_report`): hẹn giờ còn sót sau khi đóng mà ném lỗi thì test hỏng."""
import gc
import os
import shutil
import sys
import tempfile
import time
import tkinter as tk
import traceback
import unittest
from datetime import datetime, timezone
from unittest import mock

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")

from eyepin import issuereport as ir  # noqa: E402
from eyepin.cvatapi import CvatClient, CvatError  # noqa: E402
from eyepin.scan import Finding  # noqa: E402
from fake_cvat import FakeCvat, FakeJob, fake_comment, fake_issue  # noqa: E402
import test_gui_cvat as G  # noqa: E402
import test_tracking as T  # noqa: E402

N = G.N
NOT_LOGGED_IN = "Chưa đăng nhập CVAT: không tải được issue."
NOT_IN_JOB = "Frame của issue này không có trong job đang mở."
ROW_2 = "Issue CVAT · Chưa sửa · Mí trên lệch 3 px"
ROW_5 = "Issue CVAT · Chưa sửa · Thiếu điểm 16"


class TestApi(unittest.TestCase):
    def setUp(self):
        self.srv = FakeCvat([FakeJob(7, task_id=3, task_name="clip", n_frames=5), FakeJob(8, task_id=3, task_name="clip", n_frames=5)])
        self.srv.issues = [fake_issue(1, 7, 2), fake_issue(2, 8, 4), fake_issue(3, 7, 0)]
        self.srv.start()
        self.addCleanup(self.srv.stop)
        self.cl = CvatClient(self.srv.url, timeout=5)
        self.addCleanup(self.cl.close)
        self.cl.login("minh", "pw")

    def test_job_issues_uses_job_filter(self):
        got = self.cl.job_issues(7)
        self.assertEqual([i["id"] for i in got], [3, 1])                               # chỉ issue của job 7, id giảm dần như CVAT trả
        last = self.srv.requests[-1]
        self.assertEqual((last["method"], last["path"], last["query"]), ("GET", "/api/issues", {"job_id": "7", "page_size": "all"}))
        self.assertEqual(self.srv.calls["GET /api/issues"], 1)

    def test_incomplete_list_is_an_error(self):
        self.srv.tamper = {"/api/issues": lambda d: dict(d, count=d["count"] + 1)}
        with self.assertRaises(CvatError) as cm:
            self.cl.job_issues(7)
        self.assertIn("issue", str(cm.exception))
        self.assertIn("không trọn vẹn", str(cm.exception))


class TestJobRows(unittest.TestCase):
    URL = "http://localhost:8080"

    def test_job_rows(self):
        issues = [fake_issue(1, 7, 87), fake_issue(2, 7, 0, resolved=True, owner="hv_03")]
        comments = [fake_comment(3, 2, "Đã sửa lại khoé", owner="hv_03", created="2026-11-18T08:00:00.000000Z"),
                    fake_comment(1, 1, "Mí trên mắt trái lệch 3 px"),
                    fake_comment(2, 2, "Khoé ngoài mắt phải sai")]
        rows = ir.job_rows(self.URL + "/", 3, issues, comments, tz=timezone.utc)
        self.assertEqual([r.issue_id for r in rows], [2, 1])                            # xếp theo frame
        fixed, open_ = rows
        self.assertEqual((fixed.job, fixed.frame, fixed.status, fixed.owner, fixed.assignee), (7, 0, "Đã sửa", "hv_03", ""))
        self.assertEqual(fixed.message, "Khoé ngoài mắt phải sai")                      # bình luận có id nhỏ nhất là mô tả
        self.assertEqual(fixed.replies, "hv_03 (2026-11-18 08:00): Đã sửa lại khoé")
        self.assertEqual(fixed.link, self.URL + "/tasks/3/jobs/7?frame=0")
        self.assertEqual((open_.message, open_.replies, open_.status, open_.owner, open_.assignee),
                         ("Mí trên mắt trái lệch 3 px", "", "Chưa sửa", "qa_01", ""))
        self.assertEqual(open_.created, datetime(2026, 11, 18, 7, 5))
        self.assertEqual(open_.link, self.URL + "/tasks/3/jobs/7?frame=87")

    def test_same_frame_ordered_by_id_and_issue_without_comment(self):
        rows = ir.job_rows(self.URL, 3, [fake_issue(9, 7, 4), fake_issue(5, 7, 4), fake_issue(7, 7, 1)], [fake_comment(1, 9, "  ")], tz=timezone.utc)
        self.assertEqual([r.issue_id for r in rows], [7, 5, 9])
        self.assertEqual([r.message for r in rows], [ir.NO_MESSAGE] * 3)                # không có bình luận, hay chỉ có khoảng trắng

    def test_inconsistent_comment_count_is_an_error(self):
        with self.assertRaises(CvatError):
            ir.job_rows(self.URL, 3, [fake_issue(1, 7, 2, comments=2)], [fake_comment(1, 1, "chỉ một")])


class JobIssuesCase(G.CvatGuiCase):
    def setUp(self):
        super().setUp()
        root, had = self.root, "report_callback_exception" in vars(self.root)
        previous = vars(root).get("report_callback_exception")
        self.callback_errors = []
        root.report_callback_exception = lambda *exc: self.callback_errors.append(exc)     # lỗi trong hàm gọi lại của Tk không bị nuốt

        def restore():
            if had:
                root.report_callback_exception = previous
            else:
                del root.report_callback_exception
            self.assertEqual(self.callback_errors, [], "hàm gọi lại của Tk ném lỗi:\n" + "".join(
                "".join(traceback.format_exception(*exc)) for exc in self.callback_errors))

        self.addCleanup(restore)

    def serve_issues(self, job7=None):
        """Task 3 "clip": job 7 có issue 1 (frame 2) và 2 (frame 5, mô tả hai dòng); job 8 có issue 3 (frame 4)."""
        self.serve(job7 or self.empty_job(7), self.empty_job(8))
        self.srv.issues = [fake_issue(1, 7, 2), fake_issue(2, 7, 5), fake_issue(3, 8, 4)]
        self.srv.comments = [fake_comment(1, 1, "Mí trên lệch 3 px"), fake_comment(2, 2, "Thiếu điểm 16\nxem lại"),
                             fake_comment(3, 2, "Đã xem", owner="hv_03"), fake_comment(4, 3, "Ở job 8")]

    def open_app(self, job7=None):
        self.serve_issues(job7)
        app = self.make_app()
        self.open_job(app)
        self.wait_issues(app)
        return app

    def pump(self, until=None, seconds=30.0):
        """Chạy vòng sự kiện Tk tới khi `until()` đúng (hoặc hết `seconds`); không có `until` thì chạy đủ `seconds`."""
        end = time.monotonic() + seconds
        gc.disable()                           # như `CvatGuiCase.wait`: biến Tk chỉ giải phóng được ở luồng chính
        try:
            while time.monotonic() < end and not (until and until()):
                self.root.update()
                time.sleep(0.01)
        finally:
            gc.enable()
        self.root.update()

    def wait_issues(self, app):
        self.pump(lambda: not app._job_issues_loading)
        self.assertFalse(app._job_issues_loading, "lần tải issue chưa xong")

    @staticmethod
    def texts(app):
        """Chữ cột "Vấn đề" của các dòng thật trong bảng Issues."""
        t = app.issue_table
        return [t.item(iid, "values")[2] for iid in t.get_children() if iid.isdigit()]

    @staticmethod
    def pick(app, i):
        app.issue_table.selection_set(str(i))

    def spy_polls(self):
        """Ghi lại mọi hẹn giờ `root.after` của việc tải issue; trả (danh sách, bộ vá). Dùng trong `with`."""
        polls, real = [], self.root.after

        def after(ms, func=None, *args):
            if func is not None and "job_issues" in getattr(func, "__qualname__", ""):
                polls.append(func)
            return real(ms) if func is None else real(ms, func, *args)

        return polls, mock.patch.object(self.root, "after", after)

    def requests_to(self, path):
        return [r for r in self.srv.requests if r["path"] == path]


class TestRows(JobIssuesCase):
    def test_rows_shown_and_jump(self):
        app = self.open_app()
        self.assertEqual(self.texts(app), [ROW_2, ROW_5])
        self.assertEqual([k for k, _ in app.issue_rows], ["cvat", "cvat"])
        self.assertEqual(app.items, [2, 5])
        self.assertEqual(app.issues_var.get(), "Items: 2")
        self.assertIn(str(app._issue_dots["yellow"]), str(app.issue_table.item("0", "image")))
        self.pick(app, 0)
        app.on_list(None)                                                               # bấm đúp
        self.assertEqual(app.f, 2)
        self.pick(app, 1)
        app.on_list(None)
        self.assertEqual(app.f, 5)

    def test_detail_has_description_replies_and_link(self):
        app = self.open_app()
        detail = app.issue_info[1]
        self.assertIn("Mức: Vàng", detail)
        self.assertIn("Thiếu điểm 16\nxem lại", detail)                                 # mô tả đủ, không chỉ dòng đầu
        self.assertIn("hv_03", detail)
        self.assertIn("Đã xem", detail)                                                 # trả lời
        self.assertIn(f"{self.srv.url}/tasks/3/jobs/7?frame=5", detail)

    def test_resolved_issue_is_green(self):
        self.serve_issues()
        self.srv.issues = [fake_issue(1, 7, 3, resolved=True)]
        self.srv.comments = [fake_comment(1, 1, "Đã sửa xong")]
        app = self.make_app()
        self.open_job(app)
        self.wait_issues(app)
        self.assertEqual(self.texts(app), ["Issue CVAT · Đã sửa · Đã sửa xong"])
        self.assertIn(str(app._issue_dots["green"]), str(app.issue_table.item("0", "image")))
        self.assertIn("Mức: Xanh lá", app.issue_info[0])

    def test_issue_of_other_job_not_shown(self):
        app = self.open_app()
        self.assertNotIn("Issue CVAT · Chưa sửa · Ở job 8", self.texts(app))
        self.assertEqual(len(self.texts(app)), 2)
        self.assertEqual({r["query"]["job_id"] for r in self.requests_to("/api/issues")}, {"7"})
        self.assertEqual({r["query"]["job_id"] for r in self.requests_to("/api/comments")}, {"7"})
        app8 = self.make_app()                                                          # mở job 8 thì chỉ thấy issue của job 8
        app8.load_cvat(self.cl, 8)
        self.wait(app8)
        self.wait_issues(app8)
        self.assertEqual(self.texts(app8), ["Issue CVAT · Chưa sửa · Ở job 8"])

    def test_issue_numbers_follow_the_job_frame_list(self):
        app = self.open_app(self.empty_job(7, start_frame=10))                          # issue.frame là số frame của task: 12 là frame thứ 2 của job
        self.srv.issues = [fake_issue(1, 7, 12), fake_issue(2, 7, 3)]
        self.srv.comments = [fake_comment(1, 1, "trong job"), fake_comment(2, 2, "ngoài job")]
        app.load_job_issues()
        self.wait_issues(app)
        self.assertEqual(self.texts(app), ["Issue CVAT · Chưa sửa · ngoài job", "Issue CVAT · Chưa sửa · trong job"])   # xếp theo số frame của issue
        self.assertEqual(app.items, [None, 2])
        self.pick(app, 1)
        app.on_list(None)
        self.assertEqual(app.f, 2)

    def test_issue_outside_the_job_is_listed_but_does_not_jump(self):
        self.serve_issues()
        self.srv.issues = [fake_issue(1, 7, 99)]
        self.srv.comments = [fake_comment(1, 1, "frame lạ")]
        app = self.make_app()
        self.open_job(app)
        self.wait_issues(app)
        self.assertEqual(self.texts(app), ["Issue CVAT · Chưa sửa · frame lạ"])
        self.assertEqual(app.items, [None])
        app.go(3)
        self.pick(app, 0)
        app.on_list(None)
        self.assertEqual(app.f, 3)
        self.assertEqual(app.notice, NOT_IN_JOB)
        app.issue_step(1)                                                               # nút kế bỏ qua dòng không có frame
        self.assertEqual(app.f, 3)
        self.assertIn("Không còn vấn đề nào", app.notice)

    def test_step_visits_issue_rows(self):
        app = self.open_app()
        app.go(0)
        app.issue_step(1)
        self.assertEqual((app.f, app.notice), (2, ROW_2))
        app.issue_step(1)
        self.assertEqual((app.f, app.notice), (5, ROW_5))

    def test_cvat_rows_come_last(self):
        app = self.open_app()
        app.s.findings.append(Finding("red", "order", "mattrai", 7, 7, (), "thứ tự khoé sai"))     # frame sau cả hai issue, vẫn đứng trước nhóm CVAT
        app._fill_issues()
        self.assertEqual([k for k, _ in app.issue_rows], ["finding", "cvat", "cvat"])

    def test_resolve_refused_on_cvat_row(self):
        app = self.open_app()
        self.pick(app, 0)
        app.issue_resolve()
        self.assertEqual(app.notice, "Dòng này không bỏ được bằng Đã xử lý.")
        self.assertEqual(self.texts(app), [ROW_2, ROW_5])

    def test_folder_session_has_no_group(self):
        d = tempfile.mkdtemp(prefix="eyepin_dir_")
        self.addCleanup(shutil.rmtree, d, True)
        for t in range(6):
            cv2.imwrite(os.path.join(d, f"f{t:03d}.png"), T.render(t))
        app = self.open_app()
        self.assertEqual(len(app.cvat_issue_entries()), 2)
        app.load(d, None)                                                               # mở thư mục ảnh thay cho job CVAT
        self.assertIsNone(app.s.cvat)
        self.assertEqual(app.cvat_issue_entries(), [])
        self.assertEqual(self.texts(app), [])
        self.assertEqual(app.issues_var.get(), "Items: 0")
        self.assertFalse(app._job_issues_loading)
        app.load_job_issues()                                                           # "Tải lại issue CVAT" không phải job CVAT: không làm gì
        self.assertEqual(self.texts(app), [])
        self.assertFalse(app._job_issues_loading)


class TestFailures(JobIssuesCase):
    def test_not_logged_in_line(self):
        app = self.open_app()
        app.cvat_client = self.client_for(self.srv.url)                                 # chưa đăng nhập: không có khoá
        self.assertIsNone(app.cvat_client.token)
        before = len(self.requests_to("/api/issues"))
        app.load_job_issues()
        self.assertEqual(self.texts(app), [NOT_LOGGED_IN])
        self.assertEqual(len(app.cvat_issue_entries()), 1)
        self.assertEqual(app.items, [None])
        self.assertEqual(len(self.requests_to("/api/issues")), before)                  # không hỏi CVAT khi không có khoá
        self.assertNotIn("cvat", app._dialogs)                                          # không mở hộp đăng nhập
        self.assertIsNone(app._cvat_after_login)
        self.assertFalse(app._job_issues_loading)
        self.pick(app, 0)
        app.on_list(None)                                                               # bấm đúp dòng lỗi: nói lỗi, không nói "frame không có trong job"
        self.assertEqual(app.notice, NOT_LOGGED_IN)

    def test_server_error_is_one_line_in_the_group(self):
        app = self.open_app()
        self.srv.fail_500 = True
        app.load_job_issues()
        self.wait_issues(app)
        lines = self.texts(app)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("Không tải được issue: "), lines[0])
        self.assertIn("500", lines[0])
        self.assertEqual(app.items, [None])

    def test_expired_login_is_one_line_without_login_box(self):
        app = self.open_app()
        self.srv.fail_401 = True
        app.load_job_issues()
        self.wait_issues(app)
        lines = self.texts(app)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("Không tải được issue: "), lines[0])
        self.assertNotIn("cvat", app._dialogs)
        self.assertIsNone(app._cvat_after_login)
        self.assertIsNone(app.busy)

    def test_reload_after_error_brings_rows_back(self):
        app = self.open_app()
        self.srv.fail_500 = True
        app.load_job_issues()
        self.wait_issues(app)
        self.srv.fail_500 = False
        app.load_job_issues()
        self.wait_issues(app)
        self.assertEqual(self.texts(app), [ROW_2, ROW_5])


class TestLoading(JobIssuesCase):
    def test_busy_untouched(self):
        app = self.open_app()
        app.load_job_issues()
        self.assertTrue(app._job_issues_loading)
        self.assertIsNone(app.busy)
        self.assertFalse(app._edit_blocked())                                           # gán nhãn không bị chặn trong lúc tải
        self.wait_issues(app)
        self.assertIsNone(app.busy)

    def test_each_load_has_its_own_client_and_only_gets(self):
        self.serve_issues()
        app = self.make_app()
        made = []

        def new_client(url):
            c = self.client_for(url)
            c.closed, close = False, c.close
            c.close = lambda: (setattr(c, "closed", True), close())
            made.append(c)
            return c

        app.new_client = new_client
        self.open_job(app)
        self.wait_issues(app)
        app.load_job_issues()
        self.wait_issues(app)
        self.assertEqual(len(made), 2)
        self.assertNotIn(self.cl, made)                                                 # không dùng chung client của cửa sổ chính
        self.assertTrue(all(c.closed and c.token == self.cl.token for c in made))
        for r in self.srv.requests:
            if r["path"] in ("/api/issues", "/api/comments"):
                self.assertEqual(r["method"], "GET")

    def test_reload_menu_item_reloads(self):
        app = self.open_app()
        idx = app._menu.index("Tải lại issue CVAT")
        self.assertEqual(idx, app._menu.index("Báo cáo issue CVAT…") + 1)
        before = len(self.requests_to("/api/issues"))
        app._menu.invoke(idx)
        self.assertTrue(app._job_issues_loading)
        self.wait_issues(app)
        self.assertEqual(len(self.requests_to("/api/issues")), before + 1)
        self.assertEqual(self.texts(app), [ROW_2, ROW_5])

    def test_stale_result_dropped(self):
        app = self.open_app()
        old = app._job_issues_seq
        app.load_job_issues()                                                           # lần tải mới: số thứ tự đổi, nhóm rỗng tới khi có kết quả
        self.assertNotEqual(app._job_issues_seq, old)
        self.assertEqual(self.texts(app), [])
        stale = [ir.Row(99, 7, 1, "http://x/tasks/3/jobs/7?frame=1", "cũ", False, "qa_01", None, "", "")]
        app._job_issues_done(old, stale, None)
        app._job_issues_done(old, None, CvatError("cũ"))
        self.assertEqual(self.texts(app), [])
        self.assertTrue(app._job_issues_loading)                                        # kết quả cũ không tắt cờ đang tải của lần mới
        self.wait_issues(app)
        self.assertEqual(self.texts(app), [ROW_2, ROW_5])
        done = app._job_issues_seq
        app._job_issues_done(old, stale, None)                                          # kết quả cũ về muộn sau khi xong
        self.assertEqual((app._job_issues_seq, self.texts(app)), (done, [ROW_2, ROW_5]))

    def test_result_of_closed_job_dropped(self):
        app = self.open_app()
        app.load_job_issues()                                                           # đang tải job 7...
        app.load_cvat(self.cl, 8)                                                       # ...thì mở job 8
        self.wait(app)
        self.wait_issues(app)
        self.assertEqual(self.texts(app), ["Issue CVAT · Chưa sửa · Ở job 8"])
        self.pump(seconds=0.3)
        self.assertEqual(self.texts(app), ["Issue CVAT · Chưa sửa · Ở job 8"])

    def test_result_for_other_job_with_same_seq_dropped(self):
        app = self.open_app()
        app._job_issues_job = 8                                                         # phiên đang mở là job 7, kết quả này đáng lẽ của job khác
        rows = [ir.Row(5, 8, 1, "http://x", "của job 8", False, "qa_01", None, "", "")]
        app._job_issues_done(app._job_issues_seq, rows, None)
        self.assertEqual(self.texts(app), [ROW_2, ROW_5])

    def test_mixin_not_shadowed(self):
        from eyepin.gui import App
        from eyepin.gui_jobissues import JobIssuesMixin
        self.assertIs(App.cvat_issue_entries, JobIssuesMixin.cvat_issue_entries)
        self.assertEqual([c for c in App.__mro__ if "cvat_issue_entries" in vars(c)], [JobIssuesMixin])


class TestClose(JobIssuesCase):
    def test_no_poll_after_close(self):
        app = self.open_app()
        polls, patch = self.spy_polls()
        with patch, mock.patch.object(app, "_job_issues_done") as done:
            app.load_job_issues()
            self.assertEqual(len(polls), 1)
            app.teardown()                                                              # đóng giữa lúc tải
            self.pump(seconds=0.5)
        done.assert_not_called()
        self.assertEqual(len(polls), 1)                                                 # hẹn giờ cũ đã bị huỷ, không hẹn lại
        self.assertEqual(self.root.tk.splitlist(self.root.tk.call("after", "info")), ())

    def assert_poll_stops(self, disturb):
        app = self.open_app()
        polls, patch = self.spy_polls()
        with patch, mock.patch.object(app, "_job_issues_done") as done:
            app.load_job_issues()
            self.assertEqual(len(polls), 1)
            disturb(app)
            self.pump(seconds=0.5)
        done.assert_not_called()
        self.assertEqual(len(polls), 1)                                                 # chạy một lần rồi dừng, không hẹn lại

    def test_poll_stops_when_app_is_torn_down(self):
        def disturb(app):
            app._torn = True
            self.addCleanup(setattr, app, "_torn", False)
        self.assert_poll_stops(disturb)

    def test_poll_stops_when_the_issue_table_is_gone(self):
        def disturb(app):
            real = app.issue_table
            app.issue_table = mock.Mock(winfo_exists=mock.Mock(side_effect=tk.TclError("bad window path name")))
            self.addCleanup(setattr, app, "issue_table", real)
        self.assert_poll_stops(disturb)

    def test_poll_stops_when_the_result_is_stale(self):
        self.assert_poll_stops(lambda app: setattr(app, "_job_issues_seq", app._job_issues_seq + 1))


if __name__ == "__main__":
    unittest.main()
