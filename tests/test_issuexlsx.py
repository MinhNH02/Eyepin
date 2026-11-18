import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import issuexlsx as ix  # noqa: E402
from eyepin.issuereport import JobInfo, Report, Row  # noqa: E402

FETCHED, NOW = datetime(2026, 11, 18, 14, 32), datetime(2026, 11, 18, 15, 1)
WARNING = "Job 7: CVAT báo 5 issue, báo cáo lấy được 3. Có thể tài khoản này không xem được hết, hoặc issue vừa thay đổi; bấm Làm mới để kiểm lại."


def row(issue_id, job, frame, message, resolved=False, owner="qa_01", created=datetime(2026, 11, 18, 14, 5), assignee="hv_03", replies=""):
    return Row(issue_id, job, frame, "http://localhost:8080/tasks/3/jobs/%d?frame=%d" % (job, frame), message, resolved, owner, created,
               assignee, replies)


def report(rows, warnings=()):
    jobs = (JobInfo(7, "annotation", "hv_03", 3), JobInfo(8, "ground_truth", "", 1))
    return Report("http://localhost:8080", "qa_01", 3, "clip", FETCHED, jobs, tuple(rows), tuple(warnings), frozenset())


ROWS = [row(2, 7, 0, "Không chắc điểm 16", owner="hv_03"),
        row(4, 7, 0, "Khoé ngoài mắt phải sai", resolved=True, replies="hv_03 (2026-11-18 14:09): Đã sửa lại khoé"),
        row(5, 7, 87, "=> Mí trên mắt trái lệch 3 px", created=None),
        row(6, 8, 3, "Thiếu điểm 16", assignee="")]


class XlsxCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="eyepin_xlsx_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "bao-cao.xlsx")

    def write(self, rows=None, **kw):
        rows = ROWS if rows is None else rows
        ix.write(self.path, kw.pop("report", None) or report(ROWS), rows, now=NOW, **kw)
        wb = openpyxl.load_workbook(self.path)
        self.addCleanup(wb.close)
        return wb

    def summary_table(self, ws):
        """Các dòng của bảng tổng hợp, tính từ dòng tiêu đề 'Job'."""
        start = next(i for i, r in enumerate(ws.iter_rows(values_only=True)) if r[0] == "Job")
        return [tuple(r[:6]) for r in list(ws.iter_rows(values_only=True))[start:]]


class TestIssueSheet(XlsxCase):
    def test_sheets_headers_and_rows(self):
        wb = self.write()
        self.assertEqual(wb.sheetnames, ["Issue", "Tổng hợp"])
        ws = wb["Issue"]
        self.assertEqual(tuple(c.value for c in ws[1]), ix.HEADERS)
        self.assertTrue(ws["A1"].font.bold)
        self.assertEqual(ws.freeze_panes, "A2")
        self.assertEqual(ws.auto_filter.ref, "A1:J5")
        self.assertEqual(tuple(c.value for c in ws[3]),
                         (2, 7, 0, "http://localhost:8080/tasks/3/jobs/7?frame=0", "Khoé ngoài mắt phải sai", "Đã sửa", "qa_01",
                          datetime(2026, 11, 18, 14, 5), "hv_03", "hv_03 (2026-11-18 14:09): Đã sửa lại khoé"))
        self.assertEqual(ws["D3"].hyperlink.target, "http://localhost:8080/tasks/3/jobs/7?frame=0")
        self.assertEqual(ws["F2"].value, "Chưa sửa")
        self.assertIsNone(ws["H4"].value)                                            # issue không có ngày tạo
        self.assertTrue(ws["E2"].alignment.wrap_text)
        self.assertEqual(ws.max_row, 5)

    def test_text_starting_with_equals_stays_text(self):
        ws = self.write()["Issue"]
        self.assertEqual((ws["E4"].value, ws["E4"].data_type), ("=> Mí trên mắt trái lệch 3 px", "s"))

    def test_long_and_dirty_text(self):
        rows = [row(1, 7, 1, "a\x07b\x00c"), row(2, 7, 2, "x\ud83dy"), row(3, 7, 3, "dòng 1\ndòng 2"), row(4, 7, 4, "=" + "ă" * 40000)]
        ws = self.write(rows)["Issue"]
        self.assertEqual(ws["E2"].value, "abc")
        self.assertEqual(ws["E3"].value, "xy")
        self.assertEqual(ws["E4"].value, "dòng 1\ndòng 2")
        self.assertEqual(len(ws["E5"].value), 32767)
        self.assertTrue(ws["E5"].value.endswith("…"))
        self.assertEqual(ws["E5"].data_type, "s")

    def test_clean_text(self):
        self.assertEqual(ix.clean_text(None), "")
        self.assertEqual(ix.clean_text(12), "12")
        self.assertEqual(ix.clean_text("ổn"), "ổn")

    def test_limit_counts_utf16_units(self):
        out = ix.clean_text("😀" * 20000)                                            # mỗi emoji là 2 đơn vị UTF-16 trong Excel
        self.assertLessEqual(len(out.encode("utf-16-le")) // 2, 32767)
        self.assertTrue(out.endswith("…"))
        self.assertEqual(out[:-1], "😀" * 16383)
        ws = self.write([row(1, 7, 1, "😀" * 20000)])["Issue"]
        self.assertEqual(ws["E2"].value, out)


class TestSummarySheet(XlsxCase):
    def test_info_lines_warnings_and_table(self):
        ws = self.write(report=report(ROWS, [WARNING]), excluded={8}, resolved=False, owner=None)["Tổng hợp"]
        rows = list(ws.iter_rows(values_only=True))
        self.assertEqual([r[:2] for r in rows[:4]], [("Báo cáo issue CVAT", None), ("CVAT", "http://localhost:8080"), ("Task", "#3 clip"),
                                                      ("Tài khoản", "qa_01")])
        self.assertEqual(rows[4][0], "Dữ liệu lấy từ CVAT lúc")
        self.assertRegex(rows[4][1], r"^2026-11-18 14:32 \(UTC[+-]\d\d:\d\d\)$")
        self.assertEqual(rows[5][:2], ("Xuất file lúc", "2026-11-18 15:01"))
        self.assertEqual(rows[6][:2], ("Bộ lọc", "Trạng thái: Chưa sửa; Người báo: Tất cả"))
        self.assertEqual(rows[7][:2], ("Cảnh báo", WARNING))
        self.assertEqual(self.summary_table(ws), [ix.SUMMARY_HEADERS, (7, "hv_03", 3, 2, 1, None),
                                                  (8, None, 1, 1, 0, "loại ground_truth; không đưa vào báo cáo"),
                                                  ("Tổng", None, 3, 2, 1, None)])

    def test_owner_filter_changes_counts_but_status_filter_does_not(self):
        ws = self.write(resolved=True, owner="hv_03")["Tổng hợp"]
        self.assertEqual(self.summary_table(ws)[1:], [(7, "hv_03", 1, 1, 0, None), (8, None, 0, 0, 0, "loại ground_truth"),
                                                      ("Tổng", None, 1, 1, 0, None)])
        self.assertIn(("Bộ lọc", "Trạng thái: Đã sửa; Người báo: hv_03"), [r[:2] for r in ws.iter_rows(values_only=True)])


class TestSaving(XlsxCase):
    def test_ensure_available(self):
        self.assertIsNone(ix.ensure_available())
        gone = {k: None for k in list(sys.modules) if k == "openpyxl" or k.startswith("openpyxl.")}   # chặn cả `from openpyxl.x import y`
        with mock.patch.dict(sys.modules, gone):
            with self.assertRaises(ix.MissingOpenpyxl) as cm:
                ix.ensure_available()
        self.assertEqual(str(cm.exception), "Máy chưa có thư viện openpyxl nên chưa xuất được Excel. Cài bằng lệnh: pip install openpyxl")

    def test_default_name(self):
        self.assertEqual(ix.default_name(report(ROWS), NOW), "bao-cao-issue_task-3_20261118-1501.xlsx")

    def test_failed_save_keeps_the_old_file(self):
        self.write()
        with open(self.path, "rb") as fh:
            before = fh.read()

        def half_written(wb, filename):                                              # openpyxl lưu hỏng: để lại một file dở rồi ném lỗi
            with open(filename, "wb") as fh:
                fh.write(b"hong")
            raise OSError("đĩa đầy")

        with mock.patch("openpyxl.workbook.workbook.Workbook.save", autospec=True, side_effect=half_written):
            with self.assertRaises(OSError):
                ix.write(self.path, report(ROWS), ROWS, now=NOW)
        with open(self.path, "rb") as fh:
            self.assertEqual(fh.read(), before)                                      # ghi thẳng vào đích thì chỗ này thành b"hong"
        self.assertEqual(os.listdir(self.dir), ["bao-cao.xlsx"])                     # không để lại file tạm

    def test_unwritable_folder_raises_oserror(self):
        with self.assertRaises(OSError):
            ix.write(os.path.join(self.dir, "khong-co", "a.xlsx"), report(ROWS), ROWS, now=NOW)

    def test_missing_openpyxl(self):
        gone = {k: None for k in list(sys.modules) if k == "openpyxl" or k.startswith("openpyxl.")}   # chặn cả `from openpyxl.x import y`
        with mock.patch.dict(sys.modules, gone):
            with self.assertRaises(ix.MissingOpenpyxl) as cm:
                ix.write(self.path, report(ROWS), ROWS, now=NOW)
        self.assertEqual(str(cm.exception), "Máy chưa có thư viện openpyxl nên chưa xuất được Excel. Cài bằng lệnh: pip install openpyxl")
        self.assertFalse(os.path.exists(self.path))


if __name__ == "__main__":
    unittest.main()
