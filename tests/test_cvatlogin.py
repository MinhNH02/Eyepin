"""Khoá đăng nhập CVAT nhớ trên máy (eyepin.cvatlogin): mã hoá DPAPI, có hạn, không bao giờ lưu mật khẩu."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatlogin as L  # noqa: E402
from eyepin import shortcuts as sc  # noqa: E402

URL, USER, TOKEN = "http://localhost:8080", "minh.nguyen", "9f3c2a77d1e04b5c8a6e1f0b2d4c7a99"
HOUR = 3600.0


class HoursTests(unittest.TestCase):
    def settings(self, value):
        return {"workspace": {"remember_login_hours": value}}

    def test_default_is_eight_hours_and_missing_key_uses_it(self):
        self.assertEqual(L.DEFAULT_HOURS, 8)
        self.assertEqual(L.remember_hours({}), 8)
        self.assertEqual(L.remember_hours({"workspace": {}}), 8)
        self.assertEqual(L.remember_hours(sc.load_settings(Path(tempfile.gettempdir()) / "khong_co_settings.json")), 8)

    def test_numbers_are_clamped_and_zero_means_do_not_remember(self):
        self.assertEqual(L.remember_hours(self.settings(0)), 0)
        self.assertEqual(L.remember_hours(self.settings(-3)), 0)
        self.assertEqual(L.remember_hours(self.settings(2.5)), 2.5)
        self.assertEqual(L.remember_hours(self.settings("12")), 12)
        self.assertEqual(L.remember_hours(self.settings(500)), L.MAX_HOURS)

    def test_garbage_falls_back_to_the_default(self):
        for bad in (None, "abc", float("nan"), float("inf"), True, [], {}):
            self.assertEqual(L.remember_hours(self.settings(bad)), 8, repr(bad))


@unittest.skipUnless(sys.platform == "win32", "Windows DPAPI chỉ có trên Windows")
class LoginFileTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="eyepin_login_")
        self.old = os.environ.get("EYEPIN_HOME")
        os.environ["EYEPIN_HOME"] = self.home
        self.addCleanup(shutil.rmtree, self.home, True)
        self.addCleanup(self.restore_env)

    def restore_env(self):
        if self.old is None:
            os.environ.pop("EYEPIN_HOME", None)
        else:
            os.environ["EYEPIN_HOME"] = self.old

    def test_file_sits_beside_settings(self):
        self.assertEqual(L.login_path(), sc.settings_path().parent / "cvat_login.bin")

    def test_protect_roundtrip_and_is_not_plain(self):
        blob = L.protect(b"bi mat cua minh")
        self.assertNotIn(b"bi mat", blob)
        self.assertEqual(L.unprotect(blob), b"bi mat cua minh")

    def test_unprotect_rejects_garbage(self):
        for junk in (b"", b"khong phai blob DPAPI", os.urandom(200)):
            with self.assertRaises(ValueError):
                L.unprotect(junk)

    def test_roundtrip(self):
        self.assertTrue(L.save_login(URL, USER, TOKEN, 8, now=1000.0))
        self.assertTrue(L.login_path().exists())
        self.assertEqual(L.load_login(URL, now=1000.0 + HOUR), (USER, TOKEN))
        self.assertTrue(L.login_path().exists())                      # đọc không làm mất file

    def test_file_does_not_contain_token_user_or_url_in_plain(self):
        L.save_login(URL, USER, TOKEN, 8, now=1000.0)
        raw = L.login_path().read_bytes()
        for secret in (TOKEN, USER, URL, "localhost"):
            for enc in ("utf-8", "utf-16-le"):
                self.assertNotIn(secret.encode(enc), raw, f"{secret!r} ({enc}) lộ trong file khoá")

    def test_expiry_is_exact_and_deletes_the_file(self):
        L.save_login(URL, USER, TOKEN, 8, now=1000.0)
        self.assertEqual(L.load_login(URL, now=1000.0 + 8 * HOUR - 1), (USER, TOKEN))
        self.assertIsNone(L.load_login(URL, now=1000.0 + 8 * HOUR + 1))
        self.assertFalse(L.login_path().exists())

    def test_other_address_returns_none_and_deletes(self):
        L.save_login(URL, USER, TOKEN, 8, now=1000.0)
        self.assertIsNone(L.load_login("http://127.0.0.1:8080", now=1001.0))
        self.assertFalse(L.login_path().exists())

    def test_address_spelling_does_not_matter(self):
        L.save_login(URL, USER, TOKEN, 8, now=1000.0)
        self.assertEqual(L.load_login("localhost:8080/", now=1001.0), (USER, TOKEN))
        self.assertEqual(L.load_login("HTTP://LocalHost:8080", now=1001.0), (USER, TOKEN))

    def test_corrupt_file_returns_none_and_deletes(self):
        L.login_path().write_bytes(b"\x01\x00\x00\x00 khong phai blob")
        self.assertIsNone(L.load_login(URL, now=1.0))
        self.assertFalse(L.login_path().exists())

    def test_blob_with_wrong_payload_returns_none_and_deletes(self):
        for payload in (b"khong phai json", b'{"url": "http://localhost:8080"}', b'[1, 2, 3]',
                        b'{"url": "http://localhost:8080", "user": "a", "token": "", "expires_at": 9e9}',
                        b'{"url": "http://localhost:8080", "user": "a", "token": "t", "expires_at": "mai"}'):
            L.login_path().write_bytes(L.protect(payload))
            self.assertIsNone(L.load_login(URL, now=1.0), payload)
            self.assertFalse(L.login_path().exists(), payload)

    def test_missing_file_is_none(self):
        self.assertIsNone(L.load_login(URL))

    def test_zero_or_negative_hours_does_not_save_and_removes_the_old_one(self):
        L.save_login(URL, USER, TOKEN, 8, now=1000.0)
        self.assertFalse(L.save_login(URL, USER, "khoa-moi", 0, now=1001.0))
        self.assertFalse(L.login_path().exists())
        self.assertFalse(L.save_login(URL, USER, TOKEN, -1, now=1001.0))
        self.assertFalse(L.login_path().exists())

    def test_save_overwrites_the_previous_login(self):
        L.save_login(URL, USER, TOKEN, 8, now=1000.0)
        L.save_login(URL, "nguoi.khac", "khoa-khac", 8, now=1000.0)
        self.assertEqual(L.load_login(URL, now=1001.0), ("nguoi.khac", "khoa-khac"))
        self.assertEqual([p.name for p in Path(self.home).iterdir()], ["cvat_login.bin"])      # không để lại file tạm

    def test_save_that_cannot_write_returns_false_and_never_raises(self):
        blocker = Path(self.home) / "la_mot_file"
        blocker.write_text("x")
        os.environ["EYEPIN_HOME"] = str(blocker)                   # thư mục cài đặt không tạo được
        self.assertFalse(L.save_login(URL, USER, TOKEN, 8))

    def test_forget_removes_the_file_and_is_quiet_when_there_is_none(self):
        L.save_login(URL, USER, TOKEN, 8)
        self.assertIsNone(L.forget_login())
        self.assertFalse(L.login_path().exists())
        self.assertIsNone(L.forget_login())

    def test_forget_names_the_file_it_could_not_delete(self):
        L.save_login(URL, USER, TOKEN, 8)
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("đang bị khoá")):
            failed = L.forget_login()
        self.assertEqual(failed, str(L.login_path()))
        self.assertTrue(L.login_path().exists())

    def test_token_default_clock_is_used_when_now_is_omitted(self):
        L.save_login(URL, USER, TOKEN, 1)
        self.assertEqual(L.load_login(URL), (USER, TOKEN))


def pins_of(*frames):
    return {str(f): {"14": [1.0, 2.0]} for f in frames}


def cvat_state(job=7, unsent=None, frames=(0, 5), layers=1):
    """File phiên của job CVAT như `Session.state()` ghi: có khoá `cvat`; `unsent` thiếu = file lưu trước khi có cờ này."""
    d = {"version": 2, "frames": 8, "cur": 0, "layers": [{"pins": pins_of(*frames)} for _ in range(layers)], "cvat": {"job": job, "updated": "t"}}
    if unsent is not None:
        d["unsent"] = unsent
    return d


def folder_state(frames=(0, 1, 2)):
    return {"version": 2, "frames": 8, "cur": 0, "layers": [{"pins": pins_of(*frames)}]}


class SessionFilesTests(unittest.TestCase):
    """Phiên làm việc của job CVAT trên máy: nhận ra bằng nội dung, biết cái nào có thể chưa gửi, và xoá khi Đăng xuất."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="eyepin_sess_")
        self.old = os.environ.get("EYEPIN_HOME")
        os.environ["EYEPIN_HOME"] = self.home
        self.addCleanup(shutil.rmtree, self.home, True)
        self.addCleanup(self.restore_env)
        self.dir = Path(self.home) / "sessions"

    def restore_env(self):
        if self.old is None:
            os.environ.pop("EYEPIN_HOME", None)
        else:
            os.environ["EYEPIN_HOME"] = self.old

    def write(self, name, data):
        self.dir.mkdir(parents=True, exist_ok=True)
        text = data if isinstance(data, str) else json.dumps(data)
        (self.dir / name).write_text(text, encoding="utf-8")
        return self.dir / name

    def test_sessions_folder_is_beside_settings(self):
        self.assertEqual(L.sessions_dir(), sc.settings_path().parent / "sessions")

    def test_cvat_sessions_are_found_by_content_not_by_name(self):
        a = self.write("aaa.json", cvat_state(7))
        self.write("folder.json", folder_state())
        self.write("corrupt.json", "{{ không phải json")
        self.write("alist.json", "[1, 2, 3]")
        self.write("null.json", {"cvat": None, "layers": []})
        self.write("text.json", {"cvat": "job 7"})
        self.write("notes.txt", "không phải file phiên")
        self.assertEqual(L.cvat_session_files(), [a])

    def test_no_sessions_folder_is_fine(self):
        self.assertEqual(L.cvat_session_files(), [])
        self.assertEqual(L.unsent_sessions(), [])
        self.assertEqual(L.wipe_local(sc.load_settings()), [])

    def test_unsent_lists_only_what_may_not_have_been_sent(self):
        a = self.write("a.json", cvat_state(5, unsent=True, frames=(0, 3)))
        self.write("b.json", cvat_state(6, unsent=False))
        c = self.write("c.json", cvat_state(8, frames=(1, 2, 3)))                 # file cũ, chưa có cờ: chưa rõ
        self.write("d.json", cvat_state(9, frames=()))                            # file cũ không có ghim: không có gì để mất
        self.write("e.json", cvat_state(10, unsent=True, frames=()))
        f = folder_state()
        f["unsent"] = True
        self.write("f.json", f)                                                   # không phải job CVAT: không thuộc việc này
        got = L.unsent_sessions()
        self.assertEqual([(u.path, u.job, u.pins, u.known) for u in got], [(a, 5, 2, True), (c, 8, 3, False)])

    def test_pins_are_counted_over_every_person(self):
        self.write("a.json", cvat_state(5, unsent=True, frames=(0, 3), layers=2))
        self.assertEqual(L.unsent_sessions()[0].pins, 4)

    def test_folder_sessions_are_every_other_session_file(self):
        self.write("aaa.json", cvat_state(7))
        f = self.write("folder.json", folder_state())
        bad = self.write("corrupt.json", "{{ không phải json")
        self.write("notes.txt", "không phải file phiên")
        self.assertEqual(L.folder_session_files(), [bad, f])

    def test_wipe_removes_every_session_and_the_user_name_but_keeps_settings(self):
        """Người dùng chốt 2026-11-17: Đăng xuất xoá cả phiên thư mục ảnh; giữ settings.json; chỉ đụng thư mục EyePin."""
        a = self.write("a.json", cvat_state(5, unsent=True))
        b = self.write("b.json", cvat_state(6, unsent=False))
        folder = self.write("folder.json", folder_state())
        tmp = self.write("folder.json.tmp", "{")                                  # bản ghi dở của lần lưu bị ngắt
        other = self.write("notes.txt", "không phải file phiên")
        st = sc.load_settings()
        st["cvat"] = {"url": "http://localhost:8080", "user": "minh"}
        st["workspace"]["autosave"] = False
        self.assertEqual(L.wipe_local(st), [])
        self.assertFalse(a.exists() or b.exists() or folder.exists() or tmp.exists())
        self.assertTrue(other.exists())                                           # chỉ xoá file phiên
        self.assertIs(json.loads(sc.settings_path().read_text(encoding="utf-8"))["workspace"]["autosave"], False)
        self.assertEqual(st["cvat"], {"url": "http://localhost:8080", "user": ""})
        self.assertEqual(json.loads(sc.settings_path().read_text(encoding="utf-8"))["cvat"], {"url": "http://localhost:8080", "user": ""})

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI chỉ có trên Windows")
    def test_wipe_also_forgets_the_remembered_key(self):
        self.assertTrue(L.save_login(URL, USER, TOKEN, 8))
        self.assertEqual(L.wipe_local(sc.load_settings()), [])
        self.assertFalse(L.login_path().exists())

    def test_wipe_names_the_file_it_could_not_delete_and_still_does_the_rest(self):
        a = self.write("a.json", cvat_state(5))
        b = self.write("b.json", cvat_state(6))
        real = Path.unlink

        def locked(path, *args, **kw):
            if path.name == "b.json":
                raise PermissionError("đang bị khoá")
            return real(path, *args, **kw)
        st = sc.load_settings()
        st["cvat"]["user"] = "minh"
        with mock.patch.object(Path, "unlink", locked):
            failed = L.wipe_local(st)
        self.assertEqual(failed, [str(b)])
        self.assertFalse(a.exists())
        self.assertTrue(b.exists())
        self.assertEqual(st["cvat"]["user"], "")

    @unittest.skipUnless(sys.platform == "win32", "Windows DPAPI chỉ có trên Windows")
    def test_a_locked_session_does_not_stop_the_key_from_being_forgotten(self):
        self.write("a.json", cvat_state(5))
        L.save_login(URL, USER, TOKEN, 8)
        real = Path.unlink

        def locked(path, *args, **kw):
            if path.suffix == ".json":
                raise PermissionError("đang bị khoá")
            return real(path, *args, **kw)
        with mock.patch.object(Path, "unlink", locked):
            failed = L.wipe_local(sc.load_settings())
        self.assertEqual(len(failed), 1)
        self.assertFalse(L.login_path().exists())

    def test_wipe_reports_settings_it_could_not_save(self):
        st = sc.load_settings()
        st["cvat"]["user"] = "minh"
        with mock.patch.object(sc, "save_settings", side_effect=OSError("đĩa đầy")):
            failed = L.wipe_local(st)
        self.assertEqual(failed, [str(sc.settings_path())])
        self.assertEqual(st["cvat"]["user"], "")


if __name__ == "__main__":
    unittest.main()
