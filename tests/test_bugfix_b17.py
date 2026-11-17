"""B17 (buglist.md): ba chỗ báo cáo sai.

1. `Session.export` trả `keyframes` = số keyframe của track ĐẦU, không phải của mọi track mắt (thông báo "Đã ghi N keyframe").
2. `App.finish_job` luôn nói "Đã lưu phiên" kể cả khi lưu lỗi (OSError) hoặc đang chạy `--pins` (App.scratch, không ghi file phiên).
3. `scan.scan` bỏ lỡ "nhãn đứng yên" khi mắt vắng giữa chừng: chuỗi đứng yên bị đặt về 0 mà không được báo.

Ảnh giả của `test_tracking` (không dùng dữ liệu công ty)."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from eyepin.scan import scan  # noqa: E402
from eyepin.session import Session  # noqa: E402
import test_gui as _tg  # noqa: E402
import test_scan as _ts  # noqa: E402
import test_tracking as T  # noqa: E402

MATTRAI = EYES["mattrai"]


class ExportKeyframeCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="eyepin_b17_")
        for t in range(T.N):
            cv2.imwrite(os.path.join(cls.dir, f"f{t:03d}.png"), T.render(t))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    @staticmethod
    def pin_both(s, frame):
        truth = T.pins_at(frame)
        for label, spec in EYES.items():
            s.add_pin(frame, label, {i: truth[i] for i in spec.pins})

    def test_export_counts_keyframes_of_every_track(self):
        s = Session(self.dir)
        self.pin_both(s, 0)
        self.pin_both(s, 30)
        tracks = s.build_all_tracks()
        self.assertEqual(len(tracks), 2)
        want = sum(len(t.keys) for t in tracks)
        self.assertGreater(want, len(tracks[0].keys))           # hai mắt đều có keyframe: đếm track đầu là thiếu
        info = s.export(os.path.join(self.dir, "out.xml"))
        self.assertEqual(info["keyframes"], want)

    def test_export_counts_tracks_of_all_people(self):
        s = Session(self.dir)
        self.pin_both(s, 0)
        s.add_layer()
        self.pin_both(s, 0)
        tracks = s.build_all_tracks()
        self.assertEqual(len(tracks), 4)
        info = s.export(os.path.join(self.dir, "out2.xml"))
        self.assertEqual(info["keyframes"], sum(len(t.keys) for t in tracks))


class FinishJobMessageTests(unittest.TestCase):
    setUpClass = classmethod(_tg.GuiTests.setUpClass.__func__)
    tearDownClass = classmethod(_tg.GuiTests.tearDownClass.__func__)
    make_app = _tg.GuiTests.make_app
    click_pins = _tg.GuiTests.click_pins

    def pinned_app(self):
        app, seq = self.make_app()
        self.click_pins(app, seq, 0)
        return app

    def asked(self, app):
        """Gọi finish_job (người dùng bấm Không ở câu hỏi xuất file) và trả về nội dung hộp hỏi."""
        with mock.patch("eyepin.gui_frames.messagebox.askyesno", return_value=False) as ask:
            app.finish_job()
        self.assertEqual(ask.call_count, 1)
        return ask.call_args[0][1]

    def test_saved_ok_says_saved(self):
        app = self.pinned_app()
        text = self.asked(app)
        self.assertIn("Đã lưu phiên", text)
        self.assertTrue(os.path.exists(app.state_path()))

    def test_save_failure_does_not_claim_saved(self):
        app = self.pinned_app()
        with mock.patch.object(app.s, "save_state", side_effect=OSError("đĩa đầy")):
            text = self.asked(app)
        self.assertNotIn("Đã lưu phiên", text)
        self.assertIn("Không lưu được", text)
        self.assertIn("Xuất file import", text)                    # vẫn mời xuất file: đó là cách giữ việc khi lưu phiên lỗi

    def test_pins_mode_does_not_claim_saved(self):
        from eyepin.gui import App
        pins = {str(f): {str(i): list(p) for i, p in T.pins_at(f).items()} for f in (0, 20, 40)}
        app = App(self.root)
        app.ask_restore = lambda n: False
        os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_home_")
        self.addCleanup(shutil.rmtree, os.environ["EYEPIN_HOME"], True)
        app.load(self.dir, None, pins=pins)
        self.assertTrue(app.scratch)
        text = self.asked(app)
        self.assertNotIn("Đã lưu phiên", text)
        self.assertIn("--pins", text)
        self.assertFalse(os.path.exists(app.state_path()))


class StillRunBrokenByMissingEyeTests(unittest.TestCase):
    def still(self, shapes, n, still_frames):
        a = _ts.ann(shapes={"mattrai": shapes, "matphai": {}})
        return sorted((x.frame, x.last) for x in scan(a, n, still_frames=still_frames) if x.code == "still")

    def test_still_run_before_a_gap_is_reported(self):
        shapes = {t: _ts.key(MATTRAI, t) for t in list(range(0, 25)) + list(range(30, 55))}      # vắng ở frame 25–29
        self.assertEqual(self.still(shapes, 55, 20), [(0, 24), (30, 54)])

    def test_still_run_ending_the_clip_after_a_gap_is_still_reported(self):
        shapes = {t: _ts.key(MATTRAI, t) for t in range(0, 25)}                                  # mắt vắng từ frame 25 tới hết clip
        self.assertEqual(self.still(shapes, 40, 20), [(0, 24)])

    def test_short_run_before_a_gap_is_not_reported(self):
        shapes = {t: _ts.key(MATTRAI, t) for t in list(range(0, 10)) + list(range(15, 20))}
        self.assertEqual(self.still(shapes, 20, 20), [])


if __name__ == "__main__":
    unittest.main()
