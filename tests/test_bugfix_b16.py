"""B16 (buglist.md, nhóm CVAT/IO thấp): bốn chỗ báo lỗi hoặc sắp xếp sai ở lớp đọc ghi.

Đã tái hiện trước khi sửa (ảnh giả, không dùng dữ liệu công ty):
1. `CvatClient.login` gặp phản hồi 200 không phải JSON (trang HTML của proxy/đăng nhập) ném `ValueError: Expecting value` (tiếng Anh) ra giao diện;
   phản hồi 200 là JSON nhưng không phải đối tượng ném `AttributeError`. Các lệnh khác đi qua `_json` đã đổi thành `CvatError` (có test giữ nguyên).
2. Ảnh đầu không đọc được làm `AttributeError` ('NoneType' has no 'shape'). (Lúc đó còn sắp tên "tự nhiên" cho `DirSource`; B25 đã bỏ vì CVAT sắp
   theo CHUỖI, nên các test thứ tự dưới đây khẳng định thứ tự chuỗi như CVAT. Xem `test_bugfix_b25.py`.)
3. `python -m eyepin preview ... thư_mục_không_có/out.png`: `cv2.imwrite` trả False nhưng lệnh vẫn in trạng thái và thoát 0.
4. `cvatxml._remap_frames`: KHÔNG tái hiện. Track mất hết thẻ con vì frame ngoài phạm vi vẫn tính từng thẻ con vào `dropped`; chỉ track rỗng
   từ đầu (không mang nhãn nào) bị bỏ mà không tính, và đó không phải mất nhãn. `TrackKhongThe` chỉ giữ nguyên hành vi đó (không sửa mã).
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml  # noqa: E402
from eyepin.__main__ import main  # noqa: E402
from eyepin.cvatapi import CvatClient, CvatError  # noqa: E402
from eyepin.frames import DirSource  # noqa: E402


class OddServer:
    """Server giả chỉ trả một phản hồi 200 cố định cho mọi yêu cầu."""

    def __init__(self, body: bytes, ctype: str):
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _go(self):
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _go

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        self.t = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.t.start()
        outer.body = body

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.t.join(5)


class CvatNonJson(unittest.TestCase):
    def _client(self, body, ctype):
        srv = OddServer(body, ctype)
        self.addCleanup(srv.stop)
        cl = CvatClient(srv.url, timeout=5)
        self.addCleanup(cl.close)
        return cl

    def test_login_200_html_is_cvat_error_in_vietnamese(self):
        cl = self._client(b"<html><body>Dang nhap qua proxy</body></html>", "text/html")
        with self.assertRaises(CvatError) as cm:
            cl.login("minh", "pw")
        self.assertNotIn("Expecting value", str(cm.exception))
        self.assertIn("CVAT", str(cm.exception))

    def test_login_200_empty_body_is_cvat_error(self):
        cl = self._client(b"", "text/plain")
        with self.assertRaises(CvatError):
            cl.login("minh", "pw")

    def test_login_200_json_but_not_an_object_is_cvat_error(self):
        cl = self._client(b"[1, 2]", "application/json")
        with self.assertRaises(CvatError):
            cl.login("minh", "pw")

    def test_login_failure_leaves_no_token(self):
        cl = self._client(b"<html></html>", "text/html")
        with self.assertRaises(CvatError):
            cl.login("minh", "pw")
        self.assertNotIn("Authorization", cl._s.headers)

    def test_other_commands_200_html_are_cvat_error(self):
        cl = self._client(b"<html></html>", "text/html")
        for call in (cl.tasks, lambda: cl.jobs(3), lambda: cl.job(3), lambda: cl.meta(3), lambda: cl.annotations(3), lambda: cl.labels(3)):
            with self.subTest(call=call):
                with self.assertRaises(CvatError):
                    call()


class FramesOrder(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="eyepin_b16_frames_")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _write(self, names, size=(8, 6)):
        for n in names:
            cv2.imwrite(os.path.join(self.dir, n), np.full((size[1], size[0], 3), 90, np.uint8))

    # Thứ tự CHUỖI như CVAT (`sorting_method: lexicographical`, mặc định của CVAT và của script tạo task): số frame trong file XML / import tính theo
    # thứ tự đó. Bản sửa B16 từng sắp "tự nhiên" (`2.png` trước `10.png`) làm `--xml` ghép nhãn sai ảnh khi tên không đệm số 0 (B25).
    def test_string_order_numbers_like_cvat(self):
        self._write(["10.png", "2.png", "1.png", "11.png", "3.png"])
        self.assertEqual(DirSource(self.dir).names, ["1.png", "10.png", "11.png", "2.png", "3.png"])

    def test_string_order_with_prefix_like_cvat(self):
        self._write(["frame10.png", "frame2.png", "frame1.png", "frame100.png"])
        self.assertEqual(DirSource(self.dir).names, ["frame1.png", "frame10.png", "frame100.png", "frame2.png"])

    def test_zero_padded_names_keep_their_order(self):
        names = [f"f{t:03d}.png" for t in range(12)] + ["f100.png"]
        self._write(names)
        self.assertEqual(DirSource(self.dir).names, sorted(names))

    def test_mixed_names_do_not_raise(self):
        self._write(["a.png", "10.png", "b3.png", "b20.png", "2.png", "A1.png"])
        got = DirSource(self.dir).names
        self.assertEqual(sorted(got), sorted(["a.png", "10.png", "b3.png", "b20.png", "2.png", "A1.png"]))
        self.assertEqual(got, sorted(got))                                # đúng thứ tự chuỗi của CVAT
        self.assertLess(got.index("10.png"), got.index("2.png"))
        self.assertLess(got.index("b20.png"), got.index("b3.png"))

    def test_unreadable_first_image_is_value_error_in_vietnamese(self):
        self._write(["2.png", "10.png"])
        with open(os.path.join(self.dir, "1.png"), "wb") as fh:          # tên đứng đầu nhưng không phải ảnh
            fh.write(b"khong phai anh")
        with self.assertRaises(ValueError) as cm:
            DirSource(self.dir)
        self.assertIn("1.png", str(cm.exception))
        self.assertIn("Không đọc được ảnh", str(cm.exception))

    def test_empty_folder_message_unchanged(self):
        with self.assertRaises(ValueError) as cm:
            DirSource(self.dir)
        self.assertIn("Không có ảnh", str(cm.exception))


class PreviewWriteFailure(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="eyepin_b16_prev_")
        self.addCleanup(shutil.rmtree, self.dir, True)
        for t in range(3):
            cv2.imwrite(os.path.join(self.dir, f"f{t:03d}.png"), np.full((60, 80, 3), 100 + t, np.uint8))

    def _run(self, out):
        buf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")            # `main` gọi sys.stdout.reconfigure: StringIO không có
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = main(["preview", self.dir, out, "--frame", "0"])
        buf.flush()
        return code, buf.buffer.getvalue().decode("utf-8")

    def test_writing_into_missing_folder_fails_with_message(self):
        out = os.path.join(self.dir, "khong_co_thu_muc", "out.png")
        code, text = self._run(out)
        self.assertNotEqual(code, 0)
        self.assertIn("Lỗi", text)
        self.assertFalse(os.path.exists(out))

    def test_unsupported_extension_fails_with_message(self):
        out = os.path.join(self.dir, "out.khongbiet")
        code, text = self._run(out)
        self.assertNotEqual(code, 0)
        self.assertIn("Lỗi", text)

    def test_normal_write_still_exits_zero(self):
        out = os.path.join(self.dir, "out.png")
        code, text = self._run(out)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(out))
        self.assertNotIn("Lỗi", text)

    def _run_pins(self, pins_path):
        buf = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = main(["preview", self.dir, os.path.join(self.dir, "out.png"), "--frame", "0", "--pins", pins_path])
        buf.flush()
        return code, buf.buffer.getvalue().decode("utf-8")

    def test_corrupt_pins_file_reports_error_without_traceback(self):
        # B23: file --pins hỏng (không phải JSON, hoặc toạ độ NaN) phải ra một dòng "Lỗi" và mã 2, không Traceback
        bad = os.path.join(self.dir, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{ không phải json")
        code, text = self._run_pins(bad)
        self.assertEqual(code, 2)
        self.assertIn("Lỗi", text)

    def test_missing_pins_file_reports_error(self):
        code, text = self._run_pins(os.path.join(self.dir, "khong_co.json"))
        self.assertEqual(code, 2)
        self.assertIn("Lỗi", text)


XML_TRACKS = b"""<?xml version="1.0"?><annotations><version>1.1</version>
<track id="0" label="mattrai"><skeleton frame="1" keyframe="1" outside="0" occluded="0"><points label="14" points="1,1" outside="0" occluded="0" keyframe="1"/></skeleton></track>
<track id="1" label="hop"><box frame="5" keyframe="1" outside="0" occluded="0" xtl="1" ytl="1" xbr="2" ybr="2"/><box frame="9" keyframe="1" outside="0" occluded="0" xtl="1" ytl="1" xbr="2" ybr="2"/></track>
<track id="2" label="hop"/>
<track id="3" label="hop"><box frame="40" keyframe="1" outside="0" occluded="0" xtl="1" ytl="1" xbr="2" ybr="2"/></track>
</annotations>"""


class TrackKhongThe(unittest.TestCase):
    def test_every_label_carrying_element_removed_is_counted(self):
        """Frame ngoài `frame_numbers` bị bỏ thì mọi phần tử mang nhãn bị bỏ đều nằm trong `dropped` (track hộp 5, 9 trong; 40 ngoài)."""
        ann = cvatxml.parse_bytes(XML_TRACKS, frame_numbers=[1, 5, 9])
        self.assertEqual(ann.dropped, 1)                                  # chỉ box frame 40
        labels = [t.get("label") for t in ann.tree.getroot().findall("track")]
        self.assertEqual(labels.count("mattrai"), 1)
        self.assertEqual(labels.count("hop"), 1)                          # track 1 còn; track 3 mất hết thẻ con; track 2 rỗng không mang nhãn

    def test_track_with_all_children_outside_counts_every_child(self):
        data = (b'<?xml version="1.0"?><annotations><track id="0" label="hop">'
                b'<box frame="40" keyframe="1" outside="0" occluded="0" xtl="1" ytl="1" xbr="2" ybr="2"/>'
                b'<box frame="41" keyframe="1" outside="0" occluded="0" xtl="1" ytl="1" xbr="2" ybr="2"/></track></annotations>')
        ann = cvatxml.parse_bytes(data, frame_numbers=[1, 2])
        self.assertEqual(ann.dropped, 2)
        self.assertEqual(ann.tree.getroot().findall("track"), [])


if __name__ == "__main__":
    unittest.main()
