import gc
import os
import shutil
import sys
import tempfile
import time
import traceback
import types
import unittest
from unittest import mock

import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")

from eyepin import issuereport as ir  # noqa: E402
from eyepin import issuexlsx  # noqa: E402
from eyepin import shortcuts as sc  # noqa: E402
from fake_cvat import FakeJob, fake_comment, fake_issue  # noqa: E402
from test_gui_cvat import CvatGuiCase, buttons  # noqa: E402


class ReportCase(CvatGuiCase):
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

    def test_status_line_shows_the_first_warning_and_counts_the_rest(self):
        self.serve_report()
        self.srv.jobs[8].type = "ground_truth"
        self.srv.jobs[10] = FakeJob(10, task_id=3, task_name="clip", listed=False)
        self.srv.issues.append(fake_issue(4, 10, 1))
        self.srv.comments.append(fake_comment(4, 4, "ở job không xem được"))
        app = self.make_app()
        app.cvat_client = self.cl
        app.show_issue_report(3)
        self.wait_report(app)
        status = app._report_ui["status"].get()
        self.assertIn("Task có 3 job, tài khoản này chỉ xem được 2; issue ở các job còn lại có thể không có trong báo cáo. "
                      "(và 1 cảnh báo khác; xem đủ ở sheet Tổng hợp khi xuất)", status)
        self.assertNotIn("Job 10: tài khoản này không xem được job", status)

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

    def test_only_clicks_on_a_job_cell_toggle(self):
        app, ui = self.open_report()
        tv, click = ui["jobs_tv"], types.SimpleNamespace(x=1, y=1)
        tv.identify_row = lambda y: "7"                                              # dòng nào cũng "tìm thấy": chỉ vùng bấm quyết định
        tv.identify_region = lambda x, y: "heading"
        self.assertIsNone(app._report_click_job(click))                              # tiêu đề, đường biên cột: để Tk xử lý (kéo đổi cỡ cột)
        self.assertNotIn(7, ui["excluded"])
        tv.identify_region = lambda x, y: "cell"
        self.assertEqual(app._report_click_job(click), "break")
        self.assertIn(7, ui["excluded"])
        tv.identify_row = lambda y: ""                                               # bấm vào ô trống dưới danh sách
        self.assertIsNone(app._report_click_job(click))
        self.assertEqual(ui["excluded"], {7})


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


class TestExport(ReportCase):
    def out_dir(self):
        d = tempfile.mkdtemp(prefix="eyepin_out_")
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_export_writes_the_rows_shown_from_the_loaded_dataset(self):
        app, ui = self.open_report()
        out = os.path.join(self.out_dir(), "bc.xlsx")
        asked = []
        app.ask_report_path = lambda initialdir, initialfile: asked.append((initialdir, initialfile)) or out
        ui["status_filter"].set("Chưa sửa")
        app._report_fill()
        ui["task_cb"].current(1)                                                     # ô chọn bị đổi nhưng chưa lấy: file vẫn là của task 3
        app.report_export()
        wb = openpyxl.load_workbook(out)
        self.addCleanup(wb.close)
        self.assertEqual([c.value for c in wb["Issue"]["E"]], ["Mô tả lỗi", "Mí trên mắt trái lệch 3 px"])
        self.assertEqual(wb["Issue"]["D2"].value, self.srv.url + "/tasks/3/jobs/7?frame=87")
        info = dict(r[:2] for r in wb["Tổng hợp"].iter_rows(values_only=True) if r[0])
        self.assertEqual((info["Task"], info["Tài khoản"], info["Bộ lọc"]), ("#3 clip", "minh", "Trạng thái: Chưa sửa; Người báo: Tất cả"))
        self.assertEqual(ui["status"].get(), "Đã xuất 1 issue ra %s." % out)
        self.assertRegex(asked[0][1], r"^bao-cao-issue_task-3_\d{8}-\d{4}\.xlsx$")
        self.assertEqual(app.settings["workspace"]["report_dir"], os.path.dirname(out))
        app.report_export()
        self.assertEqual(asked[1][0], os.path.dirname(out))                          # lần sau gợi ý thư mục vừa dùng

    def test_first_export_suggests_documents_or_home_never_the_program_folder(self):
        app, ui = self.open_report()
        asked = []
        app.ask_report_path = lambda initialdir, initialfile: asked.append(initialdir) or ""
        app.report_export()                                                          # người dùng huỷ
        docs = os.path.join(os.path.expanduser("~"), "Documents")
        self.assertEqual(asked[0], docs if os.path.isdir(docs) else os.path.expanduser("~"))
        self.assertTrue(ui["status"].get().startswith("Đang hiện 2 / 2 issue"))      # huỷ thì không đổi gì

    def test_export_adds_xlsx_extension(self):
        app, ui = self.open_report()
        base = os.path.join(self.out_dir(), "bao cao tuan 47")
        app.ask_report_path = lambda initialdir, initialfile: base
        app.report_export()
        self.assertTrue(os.path.isfile(base + ".xlsx"))
        self.assertFalse(os.path.exists(base))

    def test_export_errors_are_reported_in_the_status_line(self):
        app, ui = self.open_report()
        bad = os.path.join(self.out_dir(), "khong-co", "bc.xlsx")
        app.ask_report_path = lambda initialdir, initialfile: bad
        app.report_export()
        self.assertTrue(ui["status"].get().startswith("Không ghi được file %s: " % bad))
        self.assertEqual(self.ids(app), [2, 1])
        with mock.patch("eyepin.issuexlsx.write", side_effect=issuexlsx.MissingOpenpyxl("Máy chưa có thư viện openpyxl nên chưa xuất được Excel. Cài bằng lệnh: pip install openpyxl")):
            app.report_export()
        self.assertIn("pip install openpyxl", ui["status"].get())

    def test_export_uses_the_filters_captured_before_the_dialog(self):
        app, ui = self.open_report()
        out = os.path.join(self.out_dir(), "bc.xlsx")

        def ask(initialdir, initialfile):                                            # hộp lưu của hệ điều hành chạy vòng lặp sự kiện riêng:
            ui["status_filter"].set("Đã sửa")                                        # người dùng đổi bộ lọc và bỏ tick job trong lúc đó
            app.report_toggle_job(7)
            return out

        app.ask_report_path = ask
        app.report_export()
        wb = openpyxl.load_workbook(out)
        self.addCleanup(wb.close)
        self.assertEqual([c.value for c in wb["Issue"]["E"]], ["Mô tả lỗi", "dòng 1\ndòng 2", "Mí trên mắt trái lệch 3 px"])   # issue 2 rồi 1
        info = dict(r[:2] for r in wb["Tổng hợp"].iter_rows(values_only=True) if r[0])
        self.assertEqual(info["Bộ lọc"], "Trạng thái: Tất cả; Người báo: Tất cả")
        cells = [c for r in wb["Tổng hợp"].iter_rows(values_only=True) for c in r]
        self.assertFalse(any("không đưa vào báo cáo" in str(c) for c in cells))
        self.assertEqual(ui["status"].get(), "Đã xuất 2 issue ra %s." % out)

    def test_export_does_not_overwrite_the_status_of_a_newer_state(self):
        app, ui = self.open_report()
        out = os.path.join(self.out_dir(), "bc.xlsx")
        text = "Tài khoản CVAT vừa đổi. Chọn task hoặc bấm Làm mới."

        def ask(initialdir, initialfile):                                            # trong lúc hộp lưu mở, tài khoản đổi và màn bị làm trống
            app._report_reset(text)
            return out

        app.ask_report_path = ask
        app.report_export()
        self.assertTrue(os.path.isfile(out))
        self.assertEqual(ui["status"].get(), text)                                   # trạng thái mới hơn thuộc về dòng trạng thái
        self.assertEqual(app.settings["workspace"]["report_dir"], os.path.dirname(out))

    def test_missing_openpyxl_is_reported_before_the_save_dialog(self):
        app, ui = self.open_report()
        asked = []
        app.ask_report_path = lambda initialdir, initialfile: asked.append(1) or ""
        gone = issuexlsx.MissingOpenpyxl("Máy chưa có thư viện openpyxl nên chưa xuất được Excel. Cài bằng lệnh: pip install openpyxl")
        with mock.patch("eyepin.issuexlsx.ensure_available", side_effect=gone):
            app.report_export()
        self.assertEqual(asked, [])
        self.assertIn("pip install openpyxl", ui["status"].get())

    def test_locked_file_gets_a_hint(self):
        app, ui = self.open_report()
        app.ask_report_path = lambda initialdir, initialfile: os.path.join(self.out_dir(), "bc.xlsx")
        with mock.patch("eyepin.issuexlsx.write", side_effect=PermissionError(13, "Access is denied")):
            app.report_export()
        text = ui["status"].get()
        self.assertTrue(text.startswith("Không ghi được file "))
        self.assertTrue(text.endswith("(file có đang mở trong Excel không?)"))

    def test_unexpected_export_error_is_shown(self):
        app, ui = self.open_report()
        app.ask_report_path = lambda initialdir, initialfile: os.path.join(self.out_dir(), "bc.xlsx")
        with mock.patch("eyepin.issuexlsx.write", side_effect=ValueError("x")), mock.patch("traceback.print_exception"):
            app.report_export()
        self.assertEqual(ui["status"].get(), "Lỗi không mong đợi khi xuất: ValueError: x")

    def test_export_refused_while_loading(self):
        app, ui = self.open_report()
        asked = []
        app.ask_report_path = lambda initialdir, initialfile: asked.append(1) or ""
        app.report_refresh()
        self.assertTrue(ui["loading"])
        app.report_export()
        self.assertEqual(asked, [])
        self.wait_report(app)

    def test_nothing_to_export(self):
        app, ui = self.open_report()
        app.report_toggle_job(7)
        app.report_export()
        self.assertEqual(ui["status"].get(), "Không có issue nào để xuất.")

    def test_double_click_opens_the_frame_link(self):
        app, ui = self.open_report()
        links = []
        app.open_link = links.append
        app.report_open_row()
        self.assertEqual(links, [])                                                  # chưa chọn dòng nào
        ui["rows_tv"].selection_set("1")
        app.report_open_row()
        self.assertEqual(links, [self.srv.url + "/tasks/3/jobs/7?frame=87"])


class TestEntryPoints(ReportCase):
    def test_menu_item_and_action(self):
        self.serve_report()
        app = self.make_app()
        self.assertEqual(sc.BY_ID["issue_report"].keys, ())
        self.assertIn("issue_report", app.handlers)
        app._menu.index("Báo cáo issue CVAT…")                                       # ném TclError nếu không có mục này
        self.assertEqual(app._menu.entrycget(app._cvat_menu["send"], "label"), "Gửi lên CVAT")
        self.assertEqual(app._menu.entrycget(app._cvat_menu["clear"], "label"), "Xoá nhãn mắt cũ và gán lại…")

    def test_button_in_open_dialog_uses_the_selected_task(self):
        self.serve_report()
        app = self.make_app()
        app.cvat_client = self.cl
        app.open_cvat()
        self.wait(app)
        app._cvat_ui["tasks_lb"].selection_set(1)                                    # task #4
        buttons(app._dialogs["cvat"], "Báo cáo issue…")[0].invoke()
        self.wait_report(app)
        self.assertEqual((app._report_ui["task_id"], self.ids(app)), (4, [3]))

    def test_default_task_is_the_task_of_the_open_job(self):
        self.serve_report()
        app = self.make_app()
        app.load_cvat(self.cl, 7)
        self.wait(app)
        app.show_issue_report()
        self.wait_report(app)
        self.assertEqual(app._report_ui["task_id"], 3)

    def test_reopen_keeps_data_and_unticked_jobs(self):
        app, ui = self.open_report()
        app.report_toggle_job(8)
        calls = self.srv.calls["GET /api/issues"]
        app.show_issue_report()
        self.assertFalse(ui["loading"])
        self.assertEqual((self.srv.calls["GET /api/issues"], ui["excluded"], self.ids(app)), (calls, {8}, [2, 1]))
        app.show_issue_report(4)                                                     # gọi với task khác thì đổi task
        self.wait_report(app)
        self.assertEqual((ui["task_id"], self.ids(app), ui["excluded"]), (4, [3], set()))

    def test_not_logged_in_goes_through_the_login_dialog(self):
        self.serve_report()
        app = self.make_app()
        app.show_issue_report(3)
        self.assertNotIn("issue_report", app._dialogs)
        ui = app._cvat_ui
        ui["url"].set(self.srv.url), ui["user"].set("minh"), ui["password"].set("pw")
        app.cvat_login()
        self.wait(app)
        self.wait_report(app)
        self.assertEqual(self.ids(app), [2, 1])

    def test_not_logged_in_while_another_relogin_is_pending_only_tells_the_user(self):
        self.serve_report()
        app = self.make_app()
        pending = lambda: None
        app._cvat_after_login = pending
        app.show_issue_report(3)
        self.assertIs(app._cvat_after_login, pending)
        self.assertNotIn("issue_report", app._dialogs)
        self.assertEqual(app.notice, "Hãy đăng nhập CVAT (menu Mở từ CVAT…) rồi mở lại Báo cáo issue.")


class TestLoginChanges(ReportCase):
    def test_expired_login_during_fetch_asks_to_log_in_and_refetches(self):
        app, ui = self.open_report()
        self.srv.fail_401 = True
        app.report_refresh()
        self.wait_report(app)
        self.assertEqual(self.ids(app), [])
        self.assertEqual(ui["status"].get(), "Phiên đăng nhập CVAT đã hết hạn. Đăng nhập lại ở hộp vừa mở thì báo cáo tự lấy lại; nếu đóng hộp đó, hãy bấm Làm mới.")
        self.assertFalse(self.off(ui["refresh_btn"]))
        self.assertIn("cvat", app._dialogs)                                          # hộp đăng nhập sẵn có
        self.srv.fail_401 = False
        cv = app._cvat_ui
        cv["url"].set(self.srv.url), cv["user"].set("minh"), cv["password"].set("pw")
        app.cvat_login()
        self.wait(app)
        self.wait_report(app)
        self.assertEqual(self.ids(app), [2, 1])

    def test_expired_login_does_not_steal_a_pending_relogin(self):
        app, ui = self.open_report()
        pending = lambda: None
        app._cvat_after_login = pending
        self.srv.fail_401 = True
        app.report_refresh()
        self.wait_report(app)
        self.assertIs(app._cvat_after_login, pending)
        self.assertEqual(ui["status"].get(), "Hãy đăng nhập lại (menu Mở từ CVAT…) rồi bấm Làm mới.")

    def test_switching_account_clears_the_report(self):
        app, ui = self.open_report()
        app.report_toggle_job(8)
        app.open_cvat()
        self.wait(app)
        cv = app._cvat_ui
        cv["url"].set(self.srv.url), cv["user"].set("minh"), cv["password"].set("pw")
        app.cvat_login()
        self.wait(app)
        self.assertEqual((self.ids(app), ui["report"], ui["excluded"], ui["task_id"]), ([], None, {8}, 3))
        self.assertEqual(ui["status"].get(), "Tài khoản CVAT vừa đổi. Chọn task hoặc bấm Làm mới.")
        self.assertFalse(self.off(ui["refresh_btn"]))
        self.assertTrue(self.off(ui["export_btn"]))
        app.report_refresh()
        self.wait_report(app)
        self.assertEqual((self.ids(app), ui["excluded"]), ([2, 1], {8}))

    def test_refresh_after_a_failed_relogin_does_not_lock_the_window(self):
        app, ui = self.open_report()
        app.open_cvat()
        self.wait(app)
        cv = app._cvat_ui
        cv["url"].set(self.srv.url), cv["user"].set("minh"), cv["password"].set("sai")
        app.cvat_login()
        self.wait(app)
        self.assertIsNone(app.cvat_client.token)                                     # login() bỏ khoá cũ trước khi gửi
        app.report_refresh()
        self.assertFalse(ui["loading"])
        self.assertFalse(self.off(ui["refresh_btn"]))
        self.assertFalse(self.off(ui["task_cb"]))
        self.assertEqual(self.ids(app), [])
        self.assertIn("đăng nhập", ui["status"].get())

    def test_logout_teardown_closes_the_report_window(self):
        app, ui = self.open_report()
        d = app._dialogs["issue_report"]
        app.teardown()
        self.assertFalse(d.winfo_exists())
        self.assertEqual(app._report_ui, {})


if __name__ == "__main__":
    unittest.main()
