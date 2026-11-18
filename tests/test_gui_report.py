import gc
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")

from eyepin import issuereport as ir  # noqa: E402
from fake_cvat import FakeJob, fake_comment, fake_issue  # noqa: E402
from test_gui_cvat import CvatGuiCase  # noqa: E402


class ReportCase(CvatGuiCase):
    def serve_report(self):
        """Task 3 "clip": job 7 (hv_03) có issue 1 (frame 87, chưa sửa) và 2 (frame 0, đã sửa, hv_03 mở); job 8 chưa có issue. Task 4: job 9, issue 3."""
        self.serve(FakeJob(7, task_id=3, task_name="clip", assignee="hv_03"), FakeJob(8, task_id=3, task_name="clip"),
                   FakeJob(9, task_id=4, task_name="khac"))
        self.srv.issues = [fake_issue(1, 7, 87), fake_issue(2, 7, 0, resolved=True, owner="hv_03"), fake_issue(3, 9, 5)]
        self.srv.comments = [fake_comment(1, 1, "Mí trên mắt trái lệch 3 px"), fake_comment(2, 2, "dòng 1\ndòng 2", owner="hv_03"),
                             fake_comment(3, 3, "Thiếu điểm 16")]

    def open_report(self, task_id=3):
        self.serve_report()
        app = self.make_app()
        app.cvat_client = self.cl
        app.show_issue_report(task_id)
        self.wait_report(app)
        return app, app._report_ui

    def wait_report(self, app, timeout=30):
        end = time.monotonic() + timeout
        gc.disable()
        try:
            while app._report_ui.get("loading") and time.monotonic() < end:
                self.root.update()
                time.sleep(0.01)
        finally:
            gc.enable()
        self.root.update()
        self.assertFalse(app._report_ui.get("loading"), "lần lấy báo cáo chưa xong")

    def ids(self, app):
        return [r.issue_id for r in app.report_rows()]

    @staticmethod
    def off(widget):
        return widget.instate(["disabled"])


class TestShow(ReportCase):
    def test_shows_issues_of_the_task_without_blocking_the_main_window(self):
        self.serve_report()
        app = self.make_app()
        app.cvat_client = self.cl
        main_status = app.status.get()
        app.show_issue_report(3)
        self.assertTrue(app._report_ui["loading"])
        self.assertIsNone(app.busy)                                                  # không dùng _run_bg
        self.assertTrue(self.off(app._report_ui["export_btn"]))
        self.assertTrue(self.off(app._report_ui["refresh_btn"]))
        self.assertTrue(self.off(app._report_ui["task_cb"]))
        self.wait_report(app)
        ui = app._report_ui
        self.assertEqual(self.ids(app), [2, 1])                                      # job 7: frame 0 rồi frame 87
        self.assertEqual(ui["rows_tv"].get_children(), ("2", "1"))
        self.assertEqual(ui["jobs_tv"].get_children(), ("7", "8"))
        self.assertEqual(ui["jobs_tv"].item("7", "values")[0], "☑")
        self.assertIn("hv_03", ui["jobs_tv"].item("7", "values"))
        self.assertIn("2 (1)", ui["jobs_tv"].item("7", "values"))
        self.assertTrue(ui["status"].get().startswith("Đang hiện 2 / 2 issue · 1 chưa sửa · tài khoản minh · lấy lúc "))
        self.assertFalse(self.off(ui["export_btn"]))
        self.assertFalse(self.off(ui["refresh_btn"]))
        self.assertFalse(self.off(ui["task_cb"]))
        self.assertEqual((ui["task_id"], ui["report"].task_name), (3, "clip"))
        self.assertIn("#3", ui["task_cb"].get())
        self.assertEqual(app.status.get(), main_status)
        self.assertIsNone(app.busy)
        self.assertEqual({r["method"] for r in self.srv.requests if r["path"] != "/api/auth/login"}, {"GET"})

    def test_a_background_job_of_the_main_window_does_not_stop_the_report(self):
        self.serve_report()
        app = self.make_app()
        app.cvat_client = self.cl
        app.busy = "Đang gửi nhãn lên CVAT…"                                         # cửa sổ chính đang bận việc khác
        try:
            app.show_issue_report(3)
            self.wait_report(app)
            self.assertEqual(self.ids(app), [2, 1])
            self.assertEqual(app.busy, "Đang gửi nhãn lên CVAT…")
        finally:
            app.busy = None

    def test_each_fetch_has_its_own_client_and_closes_it(self):
        self.serve_report()
        app = self.make_app()
        app.cvat_client = self.cl
        made = []

        def new_client(url):
            c = self.client_for(url)
            c.closed, close = False, c.close
            c.close = lambda: (setattr(c, "closed", True), close())
            made.append(c)
            return c

        app.new_client = new_client
        app.show_issue_report(3)
        self.wait_report(app)
        app.report_refresh()
        self.wait_report(app)
        self.assertEqual(len(made), 2)
        self.assertNotIn(self.cl, made)                                              # không dùng chung client của cửa sổ chính
        self.assertTrue(all(c.closed and c.token == self.cl.token for c in made))

    def test_job_list_marks_job_type_and_jobs_the_account_cannot_see(self):
        self.serve_report()
        self.srv.jobs[8].type = "ground_truth"
        self.srv.jobs[10] = FakeJob(10, task_id=3, task_name="clip", listed=False)
        self.srv.issues.append(fake_issue(4, 10, 1))
        self.srv.comments.append(fake_comment(4, 4, "ở job không xem được"))
        app = self.make_app()
        app.cvat_client = self.cl
        app.show_issue_report(3)
        self.wait_report(app)
        ui = app._report_ui
        self.assertEqual(ui["jobs_tv"].get_children(), ("7", "8", "10"))
        self.assertIn("8 (ground_truth)", ui["jobs_tv"].item("8", "values"))
        self.assertIn("10 (không xem được)", ui["jobs_tv"].item("10", "values"))
        self.assertEqual(self.ids(app), [2, 1, 4])                                   # issue ở job không có trong danh sách vẫn vào báo cáo
        self.assertIn("Task có 3 job, tài khoản này chỉ xem được 2", ui["status"].get())

    def test_multiline_message_shows_first_line_only(self):
        app, ui = self.open_report()
        self.assertIn("dòng 1 …", ui["rows_tv"].item("2", "values"))
        self.assertEqual(app.report_rows()[0].message, "dòng 1\ndòng 2")             # dữ liệu để xuất giữ nguyên văn

    def test_empty_task(self):
        self.serve_report()
        self.srv.issues, self.srv.comments = [], []
        app = self.make_app()
        app.cvat_client = self.cl
        app.show_issue_report(3)
        self.wait_report(app)
        self.assertEqual(app._report_ui["status"].get(), "Task này chưa có issue nào.")
        self.assertTrue(self.off(app._report_ui["export_btn"]))

    def test_no_task_chosen(self):
        self.serve_report()
        app = self.make_app()
        app.cvat_client = self.cl
        app.show_issue_report()
        self.wait_report(app)
        self.assertEqual(app._report_ui["status"].get(), "Chọn một task để xem issue.")
        self.assertEqual(len(app._report_ui["task_cb"]["values"]), 2)
        self.assertEqual(self.srv.calls["GET /api/issues"], 0)

    def test_warning_is_shown_in_status_and_job_list(self):
        self.serve_report()
        self.srv.hidden_issues = {1}
        app = self.make_app()
        app.cvat_client = self.cl
        app.show_issue_report(3)
        self.wait_report(app)
        ui = app._report_ui
        self.assertIn("⚠ Job 7: CVAT báo 2 issue, báo cáo lấy được 1.", ui["status"].get())
        self.assertTrue(any("⚠" in str(v) for v in ui["jobs_tv"].item("7", "values")))


class TestFilters(ReportCase):
    def test_untick_job_and_filters(self):
        app, ui = self.open_report()
        ui["status_filter"].set("Chưa sửa")
        app._report_fill()
        self.assertEqual(self.ids(app), [1])
        ui["status_filter"].set("Tất cả")
        ui["owner_filter"].set("hv_03")
        app._report_fill()
        self.assertEqual(self.ids(app), [2])
        self.assertIn("1 (0)", ui["jobs_tv"].item("7", "values"))                    # số đếm của job theo bộ lọc Người báo
        ui["owner_filter"].set("Tất cả")
        app.report_toggle_job(7)
        self.assertEqual(self.ids(app), [])
        self.assertEqual(ui["jobs_tv"].item("7", "values")[0], "☐")
        self.assertTrue(ui["status"].get().startswith("Đang hiện 0 / 2 issue · 2 issue ở job không chọn · 0 chưa sửa"))
        self.assertTrue(self.off(ui["export_btn"]))
        app.report_toggle_job(7)
        self.assertEqual(self.ids(app), [2, 1])
        self.assertEqual(list(ui["owner_cb"]["values"]), ["Tất cả", "hv_03", "qa_01"])


class TestRefresh(ReportCase):
    def test_refresh_shows_new_issue_of_a_job_that_was_empty_and_keeps_unticks(self):
        app, ui = self.open_report()
        app.report_toggle_job(7)                                                     # người dùng tự bỏ job 7
        self.srv.issues.append(fake_issue(4, 8, 2))
        self.srv.comments.append(fake_comment(4, 4, "issue mới ở job 8"))
        app.report_refresh()
        self.wait_report(app)
        self.assertEqual(self.ids(app), [4])                                         # job 8 trước đó 0 issue vẫn vào báo cáo
        self.assertEqual(ui["excluded"], {7})
        self.assertTrue(ui["status"].get().startswith("Đang hiện 1 / 3 issue · 2 issue ở job không chọn"))

    def test_owner_filter_falls_back_when_owner_disappears(self):
        app, ui = self.open_report()
        ui["owner_filter"].set("hv_03")
        self.srv.issues = [i for i in self.srv.issues if i["id"] != 2]
        self.srv.comments = [c for c in self.srv.comments if c["issue"] != 2]
        app.report_refresh()
        self.wait_report(app)
        self.assertEqual(ui["owner_filter"].get(), "Tất cả")
        self.assertEqual(self.ids(app), [1])

    def test_switching_task_clears_at_once_and_a_failed_fetch_leaves_nothing(self):
        app, ui = self.open_report()
        app.report_toggle_job(8)
        self.srv.fail_500 = True
        ui["task_cb"].current(1)                                                     # task #4
        app.report_pick_task()
        self.assertEqual((self.ids(app), ui["report"], ui["excluded"], ui["task_id"]), ([], None, set(), 4))
        self.wait_report(app)
        self.assertEqual(self.ids(app), [])
        self.assertIn("CVAT báo lỗi 500", ui["status"].get())
        self.assertTrue(self.off(ui["export_btn"]))
        self.assertFalse(self.off(ui["refresh_btn"]))
        self.srv.fail_500 = False
        app.report_refresh()
        self.wait_report(app)
        self.assertEqual((self.ids(app), ui["report"].task_id), ([3], 4))

    def test_result_of_an_older_fetch_is_dropped(self):
        app, ui = self.open_report()
        current = ui["report"]
        other = ir.Report("http://x", "khac", 4, "khac", current.fetched, (), (), (), frozenset())
        app._report_done(app._report_seq - 1, (ui["tasks"], other), None)
        self.assertIs(ui["report"], current)

    def test_closing_the_window_during_a_fetch_drops_the_result(self):
        self.serve_report()
        app = self.make_app()
        app.cvat_client = self.cl
        app.show_issue_report(3)
        app._dialogs["issue_report"].destroy()
        self.assertEqual(app._report_ui, {})
        end = time.monotonic() + 1.0
        gc.disable()
        try:
            while time.monotonic() < end:                                            # để luồng nền xong và nhịp hẹn giờ chạy qua
                self.root.update()
                time.sleep(0.01)
        finally:
            gc.enable()
        self.assertEqual(app._report_ui, {})
        self.assertEqual(app.report_rows(), [])
        app.report_refresh()                                                         # màn đã đóng: không làm gì, không lỗi

    def test_network_error_empties_the_table(self):
        app, ui = self.open_report()
        self.srv.stop()                                                              # CVAT tắt giữa chừng
        app.report_refresh()
        self.wait_report(app)
        self.assertEqual(self.ids(app), [])
        self.assertIn("Không nối được CVAT", ui["status"].get())
        self.assertTrue(self.off(ui["export_btn"]))
        self.assertFalse(self.off(ui["refresh_btn"]))
        ui["status_filter"].set("Chưa sửa")
        app._report_fill()
        self.assertIn("Không nối được CVAT", ui["status"].get())                     # đổi bộ lọc không xoá lời báo lỗi


if __name__ == "__main__":
    unittest.main()
