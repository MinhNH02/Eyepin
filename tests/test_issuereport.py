import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import issuereport as ir  # noqa: E402
from eyepin.cvatapi import CvatClient, CvatError  # noqa: E402
from fake_cvat import FakeCvat, FakeJob, fake_comment, fake_issue  # noqa: E402

TZ = timezone(timedelta(hours=7))
NOW = datetime(2026, 11, 18, 14, 32)
URL = "http://localhost:8080"
COUNT_WARNING = ("Job 7: CVAT báo 5 issue, báo cáo lấy được 3. Có thể tài khoản này không xem được hết, hoặc issue vừa thay đổi; "
                 "bấm Làm mới để kiểm lại.")


def data():
    task = {"id": 3, "name": "clip", "size": 10, "jobs": 2}
    jobs = [{"id": 8, "type": "ground_truth", "assignee": "", "issues": 0}, {"id": 7, "type": "annotation", "assignee": "hv_03", "issues": 3}]
    issues = [fake_issue(5, 7, 87, comments=1), fake_issue(4, 7, 0, resolved=True, comments=2), fake_issue(2, 7, 0, owner="hv_03", comments=1)]
    comments = [fake_comment(9, 4, "Đã sửa lại khoé", owner="hv_03", created="2026-11-18T07:09:00.000000Z"),
                fake_comment(8, 5, "=> Mí trên mắt trái lệch 3 px"), fake_comment(7, 4, "Khoé ngoài mắt phải sai"),
                fake_comment(6, 2, "Không chắc điểm 16", owner="hv_03")]
    return task, jobs, issues, comments


def build(task=None, jobs=None, issues=None, comments=None):
    t, j, i, c = data()
    return ir.build(URL, "qa_01", task or t, j if jobs is None else jobs, i if issues is None else issues,
                    c if comments is None else comments, now=NOW, tz=TZ)


class TestBuild(unittest.TestCase):
    def test_link(self):
        self.assertEqual(ir.frame_link("http://localhost:8080/", 5, 12, 87), "http://localhost:8080/tasks/5/jobs/12?frame=87")

    def test_local_time(self):
        self.assertEqual(ir.local_time("2026-11-18T16:20:58.054654Z", TZ), datetime(2026, 11, 18, 23, 20, 58, 54654))
        self.assertEqual(ir.local_time("2026-11-18T23:30:00Z", TZ), datetime(2026, 11, 19, 6, 30))      # qua ngày theo giờ máy
        for bad in (None, "", "hôm qua"):
            self.assertIsNone(ir.local_time(bad, TZ))

    def test_rows_in_order_with_first_comment_as_description(self):
        rep = build()
        self.assertEqual([r.issue_id for r in rep.rows], [2, 4, 5])                  # job, frame, mã issue
        r = rep.rows[1]
        self.assertEqual((r.job, r.frame, r.link), (7, 0, "http://localhost:8080/tasks/3/jobs/7?frame=0"))
        self.assertEqual(r.message, "Khoé ngoài mắt phải sai")                       # bình luận id nhỏ nhất, dù nó đứng sau trong danh sách
        self.assertEqual(r.replies, "hv_03 (2026-11-18 14:09): Đã sửa lại khoé")
        self.assertEqual((r.resolved, r.status, r.owner, r.assignee), (True, "Đã sửa", "qa_01", "hv_03"))
        self.assertEqual(r.created, datetime(2026, 11, 18, 14, 5))
        self.assertEqual(rep.rows[2].status, "Chưa sửa")
        self.assertEqual(rep.rows[2].replies, "")
        self.assertEqual((rep.url, rep.user, rep.task_id, rep.task_name, rep.fetched), (URL, "qa_01", 3, "clip", NOW))
        self.assertEqual([(j.id, j.type, j.assignee, j.reported, j.listed) for j in rep.jobs],
                         [(7, "annotation", "hv_03", 3, True), (8, "ground_truth", "", 0, True)])
        self.assertEqual((rep.warnings, rep.flagged), ((), frozenset()))

    def test_missing_people_dates_and_comments(self):
        issues = [fake_issue(1, 7, 3, owner=None, created=None, comments=0),
                  fake_issue(2, 7, 4, comments=2)]
        comments = [fake_comment(11, 2, "trả lời", owner=None, created=None), fake_comment(10, 2, "mô tả")]
        jobs = [{"id": 7, "type": "annotation", "assignee": "", "issues": 2}]
        a, b = build(jobs=jobs, issues=issues, comments=comments).rows
        self.assertEqual((a.owner, a.created, a.message, a.replies, a.assignee), ("(không rõ)", None, "(không có mô tả)", "", ""))
        self.assertEqual((b.message, b.replies), ("mô tả", "(không rõ): trả lời"))

    def test_comments_of_unknown_issues_are_ignored(self):
        _, _, _, comments = data()
        rep = build(comments=comments + [fake_comment(99, 12345, "của task khác")])
        self.assertNotIn("của task khác", " ".join(r.message + r.replies for r in rep.rows))

    def test_missing_comment_is_an_error(self):
        _, _, _, comments = data()
        with self.assertRaises(CvatError) as cm:
            build(comments=[c for c in comments if c["id"] != 7])                    # issue 4 báo 2 bình luận, chỉ ghép được 1
        self.assertEqual(str(cm.exception), "Bình luận của issue #4 trên CVAT vừa thay đổi trong lúc lấy. Hãy bấm Làm mới.")

    def test_issue_without_comment_summary_is_accepted(self):
        issues = [dict(fake_issue(1, 7, 3), comments=None)]
        self.assertEqual(build(issues=issues, comments=[]).rows[0].message, "(không có mô tả)")


class TestWarnings(unittest.TestCase):
    def test_job_reports_more_issues_than_fetched(self):
        task, jobs, _, _ = data()
        jobs[1]["issues"] = 5
        rep = build(jobs=jobs)
        self.assertEqual(rep.warnings, (COUNT_WARNING,))
        self.assertEqual(rep.flagged, frozenset({7}))

    def test_fetched_more_than_reported_is_not_a_warning(self):
        task, jobs, _, _ = data()
        jobs[1]["issues"] = 1
        self.assertEqual(build(jobs=jobs).warnings, ())

    def test_issue_in_job_missing_from_job_list_stays_in_report(self):
        _, _, issues, comments = data()
        rep = build(issues=issues + [fake_issue(6, 11, 2, comments=1)], comments=comments + [fake_comment(12, 6, "ở job ẩn")])
        self.assertEqual([r.issue_id for r in rep.rows], [2, 4, 5, 6])
        self.assertEqual((rep.rows[3].job, rep.rows[3].assignee), (11, ""))
        self.assertEqual([(j.id, j.listed, j.reported) for j in rep.jobs], [(7, True, 3), (8, True, 0), (11, False, None)])
        self.assertEqual(rep.warnings, ("Job 11: tài khoản này không xem được job, nhưng có 1 issue của nó trong báo cáo.",))
        self.assertEqual(rep.flagged, frozenset({11}))

    def test_task_has_more_jobs_than_listed(self):
        rep = build(task={"id": 3, "name": "clip", "size": 10, "jobs": 6})
        self.assertEqual(rep.warnings, ("Task có 6 job, tài khoản này chỉ xem được 2; issue ở các job còn lại có thể không có trong báo cáo.",))
        self.assertEqual(rep.flagged, frozenset())

    def test_unknown_job_total_gives_no_task_warning(self):
        self.assertEqual(build(task={"id": 3, "name": "clip", "size": 10, "jobs": None}).warnings, ())


class TestSelectAndSummary(unittest.TestCase):
    def test_select(self):
        rep = build()
        self.assertEqual([r.issue_id for r in ir.select(rep)], [2, 4, 5])
        self.assertEqual(ir.select(rep, excluded={7}), [])
        self.assertEqual([r.issue_id for r in ir.select(rep, resolved=False)], [2, 5])
        self.assertEqual([r.issue_id for r in ir.select(rep, resolved=True)], [4])
        self.assertEqual([r.issue_id for r in ir.select(rep, owner="hv_03")], [2])
        self.assertEqual(ir.owners(rep), ["hv_03", "qa_01"])

    def test_summary_lists_every_job_and_ignores_status_filter(self):
        rep = build()
        self.assertEqual(ir.summary(rep, excluded={8}), [ir.SummaryLine(7, "hv_03", 3, 2, 1, ""),
                                                         ir.SummaryLine(8, "", 0, 0, 0, "loại ground_truth; không đưa vào báo cáo")])
        self.assertEqual(ir.summary(rep, owner="hv_03")[0], ir.SummaryLine(7, "hv_03", 1, 1, 0, ""))

    def test_summary_note_for_unlisted_job(self):
        _, _, issues, comments = data()
        rep = build(issues=issues + [fake_issue(6, 11, 2, comments=0)], comments=comments)
        self.assertEqual(ir.summary(rep)[2], ir.SummaryLine(11, "", 1, 1, 0, "tài khoản không xem được job này"))


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.srv = FakeCvat([FakeJob(7, task_id=3, task_name="clip", n_frames=5, assignee="hv_03"),
                             FakeJob(8, task_id=3, task_name="clip", n_frames=5), FakeJob(9, task_id=4, task_name="khac", n_frames=3)])
        self.srv.issues = [fake_issue(1, 7, 87), fake_issue(2, 7, 0, resolved=True), fake_issue(3, 9, 5)]
        self.srv.comments = [fake_comment(1, 1, "mô tả 1"), fake_comment(2, 2, "mô tả 2"), fake_comment(3, 3, "mô tả 3")]
        self.srv.start()
        self.addCleanup(self.srv.stop)
        self.cl = CvatClient(self.srv.url, timeout=5)
        self.addCleanup(self.cl.close)
        self.cl.login("minh", "pw")

    def test_load_reads_one_task_with_get_only(self):
        tasks, rep = ir.load(self.cl, 3, now=NOW, tz=TZ)
        self.assertEqual([t["id"] for t in tasks], [3, 4])
        self.assertEqual((rep.user, rep.task_id, rep.task_name, rep.url), ("minh", 3, "clip", self.srv.url))
        self.assertEqual([(r.issue_id, r.message) for r in rep.rows], [(2, "mô tả 2"), (1, "mô tả 1")])
        self.assertEqual(rep.rows[0].link, self.srv.url + "/tasks/3/jobs/7?frame=0")
        self.assertEqual(self.srv.calls["GET /api/comments"], 1)                     # chỉ job 7 có issue
        self.assertTrue(all("task_id" not in r["query"] for r in self.srv.requests if r["path"] == "/api/comments"))
        self.assertEqual({r["method"] for r in self.srv.requests if r["path"] != "/api/auth/login"}, {"GET"})

    def test_no_task_or_unknown_task_reads_only_the_task_list(self):
        for task_id in (None, 999):
            with self.subTest(task_id):
                tasks, rep = ir.load(self.cl, task_id)
                self.assertEqual(len(tasks), 2)
                self.assertIsNone(rep)
        self.assertEqual(self.srv.calls["GET /api/issues"], 0)

    def test_hidden_issue_becomes_a_warning(self):
        self.srv.hidden_issues = {1}
        _, rep = ir.load(self.cl, 3)
        self.assertEqual([r.issue_id for r in rep.rows], [2])
        self.assertIn("Job 7: CVAT báo 2 issue, báo cáo lấy được 1.", rep.warnings[0])

    def test_any_failing_call_fails_the_whole_load(self):
        self.srv.tamper = {"/api/comments": lambda d: dict(d, count=d["count"] + 1)}
        with self.assertRaises(CvatError):
            ir.load(self.cl, 3)


if __name__ == "__main__":
    unittest.main()
