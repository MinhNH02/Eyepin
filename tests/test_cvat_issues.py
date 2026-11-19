import os
import sys
import unittest

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatapi  # noqa: E402
from eyepin.cvatapi import CvatClient, CvatError, LoginNeeded  # noqa: E402
from fake_cvat import FakeCvat, FakeJob, fake_comment, fake_issue  # noqa: E402


class IssueApiCase(unittest.TestCase):
    def setUp(self):
        self.srv = FakeCvat([FakeJob(7, task_id=3, task_name="clip", n_frames=5, assignee="hv_03"),
                             FakeJob(8, task_id=3, task_name="clip", n_frames=5, type="ground_truth"),
                             FakeJob(9, task_id=4, task_name="khac", n_frames=3)])
        self.srv.issues = [fake_issue(1, 7, 87), fake_issue(2, 7, 0, resolved=True), fake_issue(3, 9, 5)]
        self.srv.comments = [fake_comment(1, 1, "=> Mí trên mắt trái lệch 3 px"), fake_comment(2, 2, "Khoé ngoài mắt phải sai"),
                             fake_comment(3, 2, "Đã sửa lại khoé", owner="hv_03"), fake_comment(4, 3, "Thiếu điểm 16")]
        self.srv.start()
        self.addCleanup(self.srv.stop)
        self.cl = CvatClient(self.srv.url, timeout=5)
        self.addCleanup(self.cl.close)
        self.cl.login("minh", "pw")

    def last(self):
        return self.srv.requests[-1]


class TestReading(IssueApiCase):
    def test_issues_of_task_come_in_one_request_newest_first(self):
        got = self.cl.issues(3)
        self.assertEqual([i["id"] for i in got], [2, 1])
        self.assertEqual(got[0]["comments"]["count"], 2)
        self.assertEqual(self.last()["query"], {"task_id": "3", "page_size": "all"})
        self.assertEqual(self.srv.calls["GET /api/issues"], 1)

    def test_more_than_100_issues_arrive_in_one_request(self):
        self.srv.issues = [fake_issue(i, 7, i % 5) for i in range(1, 251)]
        self.assertEqual(len(self.cl.issues(3)), 250)
        self.assertEqual(self.srv.calls["GET /api/issues"], 1)

    def test_comments_are_filtered_by_job_never_by_task(self):
        got = self.cl.comments(7)
        self.assertEqual([c["id"] for c in got], [3, 2, 1])
        self.assertEqual(self.last()["query"], {"job_id": "7", "page_size": "all"})

    def test_report_jobs(self):
        self.assertEqual(self.cl.report_jobs(3), [{"id": 7, "type": "annotation", "assignee": "hv_03", "issues": 2},
                                                  {"id": 8, "type": "ground_truth", "assignee": "", "issues": 0}])
        self.assertEqual(self.last()["query"], {"task_id": "3", "page_size": "all"})

    def test_report_tasks(self):
        self.assertEqual(self.cl.report_tasks(), [{"id": 3, "name": "clip", "size": 10, "jobs": 2},
                                                  {"id": 4, "name": "khac", "size": 3, "jobs": 1}])

    def test_rows_tolerate_missing_fields(self):
        self.assertEqual(cvatapi.job_row({"id": 5}), {"id": 5, "type": "annotation", "assignee": "", "issues": None})
        self.assertEqual(cvatapi.task_row({"id": 2}), {"id": 2, "name": "", "size": 0, "jobs": None})
        self.assertEqual(cvatapi.username(None), "")
        self.assertEqual(cvatapi.username({"username": "qa_01"}), "qa_01")

    def test_incomplete_list_is_an_error(self):
        broken = {"đếm lệch": lambda d: dict(d, count=d["count"] + 1),
                  "còn trang sau": lambda d: dict(d, next="http://127.0.0.1:1/api/issues?page=2"),
                  "thiếu results": lambda d: {k: v for k, v in d.items() if k != "results"},
                  "thiếu count": lambda d: {k: v for k, v in d.items() if k != "count"},
                  "id trùng": lambda d: dict(d, results=d["results"] + d["results"][:1], count=d["count"] + 1),
                  "mục không phải dict": lambda d: dict(d, results=d["results"][:1] + ["không phải dict"]),
                  "id là chuỗi": lambda d: dict(d, results=d["results"][:1] + [dict(d["results"][1], id="1")]),
                  "id là True": lambda d: dict(d, results=d["results"][:1] + [dict(d["results"][1], id=True)]),   # thay mục id 1 (không thì True == 1 làm id trùng)
                  "results không phải list": lambda d: dict(d, results={"id": 1}, count=1)}
        for name, fn in broken.items():
            with self.subTest(name):
                self.srv.tamper = {"/api/issues": fn}
                with self.assertRaises(CvatError) as cm:
                    self.cl.issues(3)
                self.assertIn("không trọn vẹn", str(cm.exception))
                self.assertIn("issue", str(cm.exception))

    def test_expired_login_is_login_needed(self):
        self.srv.fail_401 = True
        with self.assertRaises(LoginNeeded):
            self.cl.issues(3)

    def test_reading_sends_only_get(self):
        self.cl.report_tasks(), self.cl.report_jobs(3), self.cl.issues(3), self.cl.comments(7)
        methods = {r["method"] for r in self.srv.requests if r["path"] != "/api/auth/login"}
        self.assertEqual(methods, {"GET"})


class TestFakeBehavesLikeCvat(IssueApiCase):
    def raw(self, method, path, **params):
        s = requests.Session()
        s.trust_env = False                                      # như CvatClient: không đi qua proxy hệ thống
        self.addCleanup(s.close)
        return s.request(method, self.srv.url + path, params=params, headers={"Authorization": "Token " + self.srv.token}, timeout=5)

    def test_comments_ignore_task_id(self):
        body = self.raw("GET", "/api/comments", task_id=4, page_size="all").json()
        self.assertEqual(body["count"], 4)                       # bẫy của CVAT thật: tham số lạ bị bỏ qua, trả mọi bình luận

    def test_other_methods_are_logged_and_refused(self):
        r = self.raw("DELETE", "/api/issues/1")
        self.assertEqual(r.status_code, 405)
        self.assertEqual(self.last()["method"], "DELETE")

    def test_hidden_issue_is_missing_from_list_but_counted_on_job(self):
        self.srv.hidden_issues = {1}
        self.assertEqual([i["id"] for i in self.cl.issues(3)], [2])
        self.assertEqual(self.cl.report_jobs(3)[0]["issues"], 2)

    def test_unlisted_job_is_counted_on_task_only(self):
        self.srv.jobs[8].listed = False
        self.assertEqual([j["id"] for j in self.cl.report_jobs(3)], [7])
        self.assertEqual(self.cl.report_tasks()[0]["jobs"], 2)


if __name__ == "__main__":
    unittest.main()
