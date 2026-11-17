"""B25 (buglist.md, hồi quy do B16): sắp tên ảnh "tự nhiên" lệch với CVAT, và file phiên cũ khôi phục lên ảnh khác mà không báo.

CVAT (mặc định, và `create_cvat_tasks.py` đặt `sorting_method: "lexicographical"`) sắp ảnh theo CHUỖI: `10.png` đứng trước `2.png`. Số frame trong
file XML / file import là chỉ số theo thứ tự đó, nên `DirSource` phải sắp đúng như vậy; sắp tự nhiên (B16) làm `--xml` ghép nhãn sai ảnh và file xuất
rơi vào frame khác khi tên không đệm số 0. Vì vậy test này khẳng định thứ tự CHUỖI (kiểu CVAT), không phải thứ tự tự nhiên của test B16 cũ.

`Session.load_state` còn phải đối chiếu `names` (tên ảnh đầu, cuối) đã lưu với thư mục hiện tại: file phiên ghi từ trước khi sửa (thứ tự tự nhiên)
hay thư mục đã đổi tên ảnh thì không được nạp lên ảnh khác. Ảnh giả, không dùng dữ liệu công ty."""
import os
import shutil
import sys
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.frames import DirSource  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_gui as _tg  # noqa: E402

Ev = _tg.Ev


class _Dir:
    def make_dir(self):
        d = tempfile.mkdtemp(prefix="eyepin_b25_")
        self.addCleanup(shutil.rmtree, d, True)
        return d

    @staticmethod
    def write(folder, names, size=(8, 6)):
        for n in names:
            cv2.imwrite(os.path.join(folder, n), np.full((size[1], size[0], 3), 90, np.uint8))


class FramesOrderLikeCvat(_Dir, unittest.TestCase):
    def setUp(self):
        self.dir = self.make_dir()

    def test_unpadded_numbers_sort_as_strings_like_cvat(self):
        self.write(self.dir, ["10.png", "2.png", "1.png", "11.png", "3.png"])
        self.assertEqual(DirSource(self.dir).names, ["1.png", "10.png", "11.png", "2.png", "3.png"])

    def test_unpadded_names_with_prefix_sort_as_strings_like_cvat(self):
        self.write(self.dir, ["img_10.png", "img_2.png", "img_1.png", "img_100.png"])
        self.assertEqual(DirSource(self.dir).names, ["img_1.png", "img_10.png", "img_100.png", "img_2.png"])

    def test_order_equals_plain_sorted_for_any_names(self):
        names = ["a.png", "10.png", "b3.png", "b20.png", "2.png", "A1.png"]
        self.write(self.dir, names)
        self.assertEqual(DirSource(self.dir).names, sorted(names))

    def test_zero_padded_names_keep_their_order(self):
        names = [f"f{t:03d}.png" for t in range(12)] + ["f100.png"]
        self.write(self.dir, names)
        self.assertEqual(DirSource(self.dir).names, sorted(names))

    def test_unreadable_first_image_is_still_value_error_in_vietnamese(self):
        self.write(self.dir, ["2.png", "10.png"])
        with open(os.path.join(self.dir, "1.png"), "wb") as fh:          # đứng đầu theo thứ tự chuỗi nhưng không phải ảnh
            fh.write(b"khong phai anh")
        with self.assertRaises(ValueError) as cm:
            DirSource(self.dir)
        self.assertIn("1.png", str(cm.exception))
        self.assertIn("Không đọc được ảnh", str(cm.exception))

    def test_empty_folder_message_unchanged(self):
        with self.assertRaises(ValueError) as cm:
            DirSource(self.dir)
        self.assertIn("Không có ảnh", str(cm.exception))


class LoadStateChecksNames(_Dir, unittest.TestCase):
    NAMES = ["img_1.png", "img_2.png", "img_10.png"]

    def setUp(self):
        self.dir = self.make_dir()
        self.write(self.dir, self.NAMES)
        self.s = Session(self.dir)
        self.assertEqual(self.s.names, ["img_1.png", "img_10.png", "img_2.png"])      # thứ tự chuỗi: đầu img_1, cuối img_2

    def test_state_roundtrip_on_same_folder_loads(self):
        d = self.s.state()
        self.assertEqual(d["names"], ["img_1.png", "img_2.png"])
        again = Session(self.dir)
        again.load_state(d)                                              # không ném lỗi

    def test_state_saved_in_old_natural_order_is_refused(self):
        d = self.s.state()
        d["names"] = ["img_1.png", "img_10.png"]                         # file phiên ghi lúc còn sắp tự nhiên: đầu img_1, cuối img_10
        with self.assertRaises(ValueError) as cm:
            Session(self.dir).load_state(d)
        self.assertIn("ảnh", str(cm.exception))
        self.assertIn("img_10.png", str(cm.exception))

    def test_first_name_differs_is_refused(self):
        d = self.s.state()
        d["names"] = ["khac.png", "img_2.png"]
        with self.assertRaises(ValueError):
            Session(self.dir).load_state(d)

    def test_other_folder_with_same_frame_count_is_refused(self):
        other = self.make_dir()
        self.write(other, ["x1.png", "x2.png", "x3.png"])
        with self.assertRaises(ValueError) as cm:
            Session(other).load_state(self.s.state())
        self.assertIn("ảnh", str(cm.exception))

    def test_refused_state_leaves_session_untouched(self):
        s = Session(self.dir)
        s.pins[0] = {i: (float(i), float(i)) for i in range(14, 30)}
        d = self.s.state()
        d["names"] = ["khac.png", "img_2.png"]
        with self.assertRaises(ValueError):
            s.load_state(d)
        self.assertIn(0, s.pins)
        self.assertEqual(s.pins[0][14], (14.0, 14.0))

    def test_old_state_without_names_still_loads(self):
        d = self.s.state()
        del d["names"]
        Session(self.dir).load_state(d)
        Session(self.dir).load_state({"version": 1, "frames": 3, "pins": {}})


class TryRestoreReportsMismatch(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins

    def test_mismatched_saved_session_is_not_restored_and_user_is_told(self):
        import json
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        self.assertTrue(app.save_work())
        path = app.state_path()
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["names"] = ["f000.png", "f_cu.png"]                         # file phiên của dãy ảnh khác (cùng số frame)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        app.s.pins.clear()
        asked = []
        app.ask_restore = lambda n: asked.append(n) or True
        self.assertFalse(app.try_restore())
        self.assertTrue(asked)
        self.assertEqual(app.s.pins, {})                                 # không nạp gì
        self.assertIn("Không khôi phục được phiên đã lưu", app.notice)
        self.assertIn("ảnh", app.notice)

    def test_matching_saved_session_is_restored(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        self.assertTrue(app.save_work())
        app.s.pins.clear()
        app.ask_restore = lambda n: True
        self.assertTrue(app.try_restore())
        self.assertIn(0, app.s.pins)


if __name__ == "__main__":
    unittest.main()
