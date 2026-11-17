import io
import os
import socket
import sys
import unittest
import zipfile
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.cvatapi import CvatClient, CvatError, LoginNeeded  # noqa: E402
from fake_cvat import FakeCvat, FakeJob, XML_EMPTY  # noqa: E402

XML_A = b'<?xml version="1.0"?><annotations><version>1.1</version><image id="0"><skeleton label="mattrai"><points label="14" points="10.0,20.0"/></skeleton></image></annotations>'


class CvatApiBase(unittest.TestCase):
    def setUp(self):
        self.srv = FakeCvat([FakeJob(7, task_id=3, task_name="clip", n_frames=5, start_frame=10, xml=XML_A,
                                     deleted_frames=[12])])
        self.srv.start()
        self.addCleanup(self.srv.stop)
        self.cl = CvatClient(self.srv.url, timeout=5)
        self.cl.poll_interval = 0.01

    def login(self):
        self.cl.login("minh", "pw")


class TestCvatApi(CvatApiBase):
    def test_refuses_non_local_host(self):
        with self.assertRaises(CvatError) as cm:
            CvatClient("https://cvat-dc.vantixapps.net")
        self.assertIn("localhost", str(cm.exception))
        for ok in ("http://localhost:8080", "http://127.0.0.1:8080/", "http://[::1]:8080"):
            CvatClient(ok)

    def test_login_sends_token_header_and_no_accept_json(self):
        self.login()
        self.cl.tasks()
        last = self.srv.requests[-1]
        self.assertEqual(last["headers"]["Authorization"], "Token k1")
        self.assertNotEqual(last["headers"].get("Accept"), "application/json")
        # kể cả lúc đăng nhập
        self.assertNotEqual(self.srv.requests[0]["headers"].get("Accept"), "application/json")

    def test_login_wrong_password(self):
        self.srv.password = "khac"
        with self.assertRaises(CvatError) as cm:
            self.login()
        self.assertIn("mật khẩu", str(cm.exception))

    def test_401_raises_login_needed(self):
        self.login()
        self.srv.fail_401 = True
        with self.assertRaises(LoginNeeded):
            self.cl.tasks()
        self.assertTrue(issubclass(LoginNeeded, CvatError))

    def test_relogin_after_expired_token_does_not_send_stale_authorization(self):
        self.login()
        self.srv.reject_login_with_auth = True
        self.srv.token = "k2"
        self.cl.login("minh", "pw")
        self.assertNotIn("Authorization", self.srv.requests[-1]["headers"])
        self.srv.token = "k2"
        self.cl.tasks()
        self.assertEqual(self.srv.requests[-1]["headers"]["Authorization"], "Token k2")

    def test_second_login_on_same_client_is_not_refused_by_csrf(self):
        """Log CVAT 2.75 ngày 2026-11-16: đăng nhập lần đầu 200, đăng nhập lại trên cùng client bị 403 "CSRF Failed: CSRF token missing."
        vì client bỏ khoá nhưng vẫn gửi cookie phiên của lần đăng nhập trước."""
        self.login()
        self.cl.tasks()
        self.cl.login("minh", "pw")                          # trước khi sửa: CvatError 403 CSRF
        self.cl.export_xml(7, "CVAT for images 1.1")         # POST sau khi đăng nhập lại vẫn qua

    def test_client_never_sends_the_session_cookie(self):
        """EyePin xác thực bằng khoá; cookie phiên làm yêu cầu đi đường Session của CVAT (POST cần CSRF), nên không bao giờ được gửi."""
        self.login()
        self.cl.tasks()
        self.cl.export_xml(7, "CVAT for images 1.1")
        self.assertTrue(all("Cookie" not in r["headers"] for r in self.srv.requests))

    def test_failed_relogin_does_not_leave_a_half_logged_in_client(self):
        """Đăng nhập lại sai mật khẩu: khoá cũ đã bỏ. Client phải báo cần đăng nhập ở mọi lệnh, không được đọc còn qua (nhờ cookie) mà ghi bị 403."""
        self.login()
        self.srv.password = "khac"
        with self.assertRaises(CvatError):
            self.cl.login("minh", "pw")
        with self.assertRaises(LoginNeeded):
            self.cl.tasks()
        with self.assertRaises(LoginNeeded):
            self.cl.export_xml(7, "CVAT for images 1.1")

    def test_session_ignores_proxy_env_and_never_follows_redirects(self):
        self.assertFalse(self.cl._s.trust_env)
        self.login()
        self.srv.redirect_job = True
        with self.assertRaises(CvatError) as cm:
            self.cl.job(7)
        self.assertEqual(cm.exception.status, 302)
        self.assertNotIn("example.com", [r["headers"].get("Host") for r in self.srv.requests])

    def test_error_carries_status_code(self):
        self.srv.password = "khac"
        with self.assertRaises(CvatError) as cm:
            self.login()
        self.assertEqual(cm.exception.status, 400)

    def test_500_raises_cvat_error(self):
        self.login()
        self.srv.fail_500 = True
        with self.assertRaises(CvatError) as cm:
            self.cl.job(7)
        self.assertIn("500", str(cm.exception))

    def test_tasks_and_jobs_follow_pagination(self):
        self.srv.page_size = 1
        self.srv.jobs[8] = FakeJob(8, task_id=3, task_name="clip", n_frames=2, start_frame=15)
        self.srv.jobs[9] = FakeJob(9, task_id=4, task_name="khac", n_frames=3)
        self.login()
        tasks = self.cl.tasks()
        self.assertEqual({t["id"] for t in tasks}, {3, 4})
        self.assertEqual({t["name"] for t in tasks}, {"clip", "khac"})
        self.assertEqual(next(t for t in tasks if t["id"] == 4)["size"], 3)
        jobs = self.cl.jobs(3)
        self.assertEqual([j["id"] for j in jobs], [7, 8])
        self.assertEqual(jobs[0]["start_frame"], 10)
        self.assertEqual(jobs[0]["stop_frame"], 14)
        self.assertIn("state", jobs[0])
        self.assertIn("stage", jobs[0])

    def test_job_and_meta(self):
        self.login()
        job = self.cl.job(7)
        self.assertEqual(job["task_id"], 3)
        self.assertTrue(job["updated_date"])
        meta = self.cl.meta(7)
        self.assertEqual(meta["start_frame"], 10)
        self.assertEqual(meta["deleted_frames"], [12])
        self.assertEqual(len(meta["frames"]), 5)

    def test_export_waits_for_the_request_and_unzips_in_memory(self):
        self.login()
        xml = self.cl.export_xml(7, "CVAT for images 1.1")
        self.assertEqual(xml, XML_A)
        self.assertGreaterEqual(self.srv.calls["GET /api/requests/rq1"], 2)
        self.assertEqual(self.srv.export_formats, ["CVAT for images 1.1"])
        self.assertEqual(self.srv.export_query[-1].get("save_images"), "False")

    def test_import_replaces_and_reports_server_failure(self):
        self.login()
        before = self.cl.job(7)["updated_date"]
        new = b'<annotations><version>1.1</version></annotations>'
        self.cl.import_xml(7, new)
        self.assertEqual(self.srv.jobs[7].xml, new)
        self.assertEqual(self.srv.import_formats, ["CVAT 1.1"])
        self.assertNotEqual(self.cl.job(7)["updated_date"], before)
        self.assertGreaterEqual(self.srv.calls["GET /api/requests/rq1"], 2)

        self.srv.fail_import = "Thiếu nhãn mattrai"
        with self.assertRaises(CvatError) as cm:
            self.cl.import_xml(7, XML_A)
        self.assertIn("Thiếu nhãn mattrai", str(cm.exception))
        self.assertEqual(self.srv.jobs[7].xml, new)

    def test_import_sends_no_filename_query(self):
        self.login()
        self.cl.import_xml(7, XML_A)  # fake trả 400 nếu URL có `filename`
        q = next(r for r in self.srv.requests if r["method"] == "POST" and r["path"].endswith("/annotations"))["query"]
        self.assertEqual(q, {"format": "CVAT 1.1"})

    def test_annotations_returns_server_json(self):
        self.login()
        self.assertEqual(self.cl.annotations(7), {"version": 0, "tags": [], "shapes": [], "tracks": []})
        data = {"version": 3, "tags": [], "shapes": [{"label_id": 1, "type": "skeleton", "frame": 30}],
                "tracks": [{"label_id": 2, "frame": 0, "shapes": [{"frame": 0}]}]}
        self.srv.jobs[7].annotations_json = data
        self.assertEqual(self.cl.annotations(7), data)
        self.srv.fail_401 = True
        with self.assertRaises(LoginNeeded):
            self.cl.annotations(7)

    def test_export_returns_a_different_payload_per_format(self):
        self.login()
        job = self.srv.jobs[7]
        job.export_xml_by_format = {"CVAT for images 1.1": b"<images/>", "CVAT for video 1.1": b"<video/>"}
        self.assertEqual(self.cl.export_xml(7, "CVAT for images 1.1"), b"<images/>")
        self.assertEqual(self.cl.export_xml(7, "CVAT for video 1.1"), b"<video/>")
        self.assertEqual(self.cl.export_xml(7, "CVAT 1.1"), XML_A)  # định dạng vắng: dùng XML đang lưu
        self.assertEqual(self.srv.export_formats, ["CVAT for images 1.1", "CVAT for video 1.1", "CVAT 1.1"])

    def test_shift_on_import_switch_changes_stored_xml(self):
        self.login()
        self.srv.shift_on_import = 5.0
        self.cl.import_xml(7, XML_A)
        self.assertIn(b'points="15.0,20.0"', self.srv.jobs[7].xml)

    def test_frame_bytes_never_touch_disk(self):
        self.login()
        real_open = open

        def guard(file, mode="r", *a, **k):
            if any(c in mode for c in "wax+"):
                raise AssertionError("ghi file khi lấy frame: %r" % (file,))
            return real_open(file, mode, *a, **k)

        with mock.patch("builtins.open", guard):
            data = self.cl.frame(7, 10)
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
        self.assertEqual(img.shape[:2], (160, 320))
        q = self.srv.frame_query[-1]
        self.assertEqual(q["quality"], "original")
        self.assertEqual(q["number"], "10")
        self.assertEqual(q["type"], "frame")

    def test_connection_refused_gives_a_helpful_message(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        cl = CvatClient("http://127.0.0.1:%d" % port, timeout=2)
        with self.assertRaises(CvatError) as cm:
            cl.login("a", "b")
        self.assertIn("Docker Desktop", str(cm.exception))
        self.assertIn("docker restart traefik", str(cm.exception))

    def test_connection_dropped_while_polling_is_a_cvat_error(self):
        self.login()
        self.srv.drop_on_poll = True
        with self.assertRaises(CvatError):
            self.cl.export_xml(7, "CVAT for images 1.1")

    def test_polling_gives_up_after_max_wait(self):
        self.login()
        self.srv.polls_before_finish = 10 ** 6
        self.cl.max_wait = 0.1
        with self.assertRaises(CvatError) as cm:
            self.cl.export_xml(7, "CVAT for images 1.1")
        self.assertIn("quá lâu", str(cm.exception))

    def test_eye_labels_ok(self):
        self.login()
        self.assertIsNone(self.cl.eye_labels_ok(7))
        self.srv.jobs[7].labels = [lb for lb in self.srv.jobs[7].labels if lb["name"] != "matphai"]
        self.assertIn("matphai", self.cl.eye_labels_ok(7))
        self.srv.jobs[7].labels = FakeJob.default_labels()
        self.srv.jobs[7].labels[0]["sublabels"] = self.srv.jobs[7].labels[0]["sublabels"][:5]
        self.assertIn("mattrai", self.cl.eye_labels_ok(7))
        self.srv.jobs[7].labels = FakeJob.default_labels()
        self.srv.jobs[7].labels[1]["type"] = "rectangle"
        self.assertIn("matphai", self.cl.eye_labels_ok(7))

    def test_server_state_is_inspectable(self):
        self.login()
        self.cl.job(7)
        self.cl.job(7)
        self.assertEqual(self.srv.calls["GET /api/jobs/7"], 2)
        self.assertEqual(self.srv.calls["POST /api/auth/login"], 1)


class TestToken(CvatApiBase):
    """Khoá đăng nhập để nhớ qua lần mở tool (eyepin.cvatlogin): đọc ra sau đăng nhập, nạp lại, và thử xem còn dùng được không."""

    def test_token_is_none_before_login_and_the_key_after(self):
        self.assertIsNone(self.cl.token)
        self.login()
        self.assertEqual(self.cl.token, "k1")

    def test_use_token_sets_the_header_and_needs_no_login(self):
        self.cl.use_token("k1")
        self.assertEqual(self.cl.token, "k1")
        self.cl.tasks()
        self.assertEqual(self.srv.requests[-1]["headers"]["Authorization"], "Token k1")
        self.assertEqual(self.srv.calls["POST /api/auth/login"], 0)

    def test_use_token_refuses_empty_or_spaced_keys(self):
        for bad in ("", "   ", "a b", "a\nb", None, 5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.cl.use_token(bad)
        self.assertIsNone(self.cl.token)

    def test_use_token_replaces_the_key_of_an_earlier_login(self):
        self.login()
        self.srv.token = "k9"
        self.cl.use_token("k9")
        self.assertEqual(self.cl.token, "k9")
        self.cl.tasks()

    def test_whoami_returns_the_username_with_a_login_or_a_loaded_token(self):
        self.login()
        self.assertEqual(self.cl.whoami(), "minh")
        other = CvatClient(self.srv.url, timeout=5)
        self.addCleanup(other.close)
        other.use_token(self.cl.token)
        self.assertEqual(other.whoami(), "minh")

    def test_whoami_with_a_revoked_or_missing_token_raises_login_needed(self):
        with self.assertRaises(LoginNeeded):
            self.cl.whoami()
        self.cl.use_token("khoa-da-huy")
        with self.assertRaises(LoginNeeded):
            self.cl.whoami()

    def test_whoami_with_an_unreadable_answer_raises_cvat_error(self):
        self.login()
        self.srv.username = ""
        with self.assertRaises(CvatError) as cm:
            self.cl.whoami()
        self.assertNotIsInstance(cm.exception, LoginNeeded)

    def test_server_down_is_a_cvat_error_not_login_needed(self):
        self.login()
        self.srv.stop()
        with self.assertRaises(CvatError) as cm:
            self.cl.whoami()
        self.assertNotIsInstance(cm.exception, LoginNeeded)


if __name__ == "__main__":
    unittest.main()
