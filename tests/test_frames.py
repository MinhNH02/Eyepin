import hashlib
import math
import os
import shutil
import sys
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.frames import DirSource  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_tracking as T  # noqa: E402


class FakeSource:
    """Nguồn ảnh giả trong RAM: không có thư mục, không có tệp."""
    key = "fake:60"
    title = "nguồn giả"

    def __init__(self):
        self.names = [f"f{t:03d}" for t in range(T.N)]
        self.width, self.height = T.W, T.H
        self.deleted = {7}
        self._imgs = [cv2.cvtColor(T.render(t), cv2.COLOR_GRAY2BGR) for t in range(T.N)]   # nguồn luôn trả BGR

    def read(self, i):
        return self._imgs[i]


class FramesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_frames_src_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_dir_source_matches_old_reading(self):
        src = DirSource(self.dir)
        self.assertEqual(src.names, sorted(os.listdir(self.dir)))
        self.assertEqual((src.width, src.height), (T.W, T.H))
        self.assertEqual(src.deleted, set())
        want = cv2.imread(os.path.join(self.dir, src.names[3]))
        self.assertTrue(np.array_equal(src.read(3), want))
        self.assertEqual(src.key, os.path.abspath(self.dir).lower())
        self.assertEqual(src.title, os.path.basename(os.path.abspath(self.dir)))

    def test_dir_source_without_images_raises(self):
        empty = tempfile.mkdtemp(prefix="eyepin_empty_")
        self.addCleanup(shutil.rmtree, empty, True)
        with self.assertRaises(ValueError):
            DirSource(empty)

    def test_session_accepts_any_source(self):
        fake = FakeSource()
        s = Session(source=fake)
        self.assertIsNone(s.frames_dir)
        self.assertEqual((s.n_frames, s.width, s.height), (T.N, T.W, T.H))
        self.assertEqual((s.source_key, s.title), ("fake:60", "nguồn giả"))
        self.assertEqual(s.deleted, {7})
        self.assertIsNot(s.deleted, fake.deleted)
        truth = T.pins_at(0)
        for label, spec in EYES.items():
            s.add_pin(0, label, {i: truth[i] for i in spec.pins})
        worst = max(math.dist(s.labels[10].points[i], T.pins_at(10)[i]) for i in s.labels[10].points)
        self.assertLess(worst, 1.0)

    def test_folder_session_exposes_key_and_title(self):
        s = Session(self.dir)
        self.assertEqual(s.frames_dir, self.dir)
        self.assertEqual(s.source_key, os.path.abspath(self.dir).lower())
        self.assertEqual(s.title, os.path.basename(os.path.abspath(self.dir)))

    def test_state_key_for_folder_unchanged(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("không có màn hình để mở cửa sổ Tkinter")
        root.withdraw()
        self.addCleanup(root.destroy)
        from eyepin.gui import App
        home = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, home, True)
        old = os.environ.get("EYEPIN_HOME")
        os.environ["EYEPIN_HOME"] = home
        self.addCleanup(lambda: os.environ.__setitem__("EYEPIN_HOME", old) if old else os.environ.pop("EYEPIN_HOME", None))
        app = App(root)
        app.ask_restore = lambda n: False
        app.load(self.dir, None)
        key = hashlib.sha1(os.path.abspath(self.dir).lower().encode("utf-8")).hexdigest()[:12]
        self.assertEqual(os.path.basename(app.state_path()), f"{key}.json")


if __name__ == "__main__":
    unittest.main()
