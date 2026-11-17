"""B24 (buglist.md): hộp Thông tin, dòng "Keyframe khi xuất" chỉ đếm track ĐẦU (một mắt) của người đang chọn.
Nay hiện số keyframe của từng mắt. Ảnh giả của `test_tracking` (không dùng dữ liệu công ty)."""
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from eyepin.gui import App  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402


class InfoKeyframeRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b24_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def row(self, s):
        rows = dict(App._stat_rows(SimpleNamespace(s=s)))
        return rows.get("Keyframe khi xuất")

    def test_row_lists_keyframes_of_each_eye(self):
        s = Session(self.dir)
        truth = T.pins_at(0)
        for label, spec in EYES.items():
            s.add_pin(0, label, {i: truth[i] for i in spec.pins})
        truth = T.pins_at(30)
        for label, spec in EYES.items():
            s.add_pin(30, label, {i: truth[i] for i in spec.pins})
        text = self.row(s)
        self.assertIsNotNone(text)
        for label, track in s.build_tracks().items():
            self.assertIn(f"{label} {len(track.keys)}", text)
        self.assertNotIn("tiết kiệm", text)

    def test_no_pins_has_no_keyframe_row(self):
        self.assertIsNone(self.row(Session(self.dir)))


if __name__ == "__main__":
    unittest.main()
