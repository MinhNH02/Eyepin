import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.cvatxml import Annotations, EyeKey, EyeTrack, PointState  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.scan import eye_ear, scan  # noqa: E402
from test_geometry import lens_eye  # noqa: E402

MATTRAI, MATPHAI = EYES["mattrai"], EYES["matphai"]
W, H = 640, 360


def key(spec, frame, cx=200, cy=180, tilt=0, mutate=None, per_point_keyframe=None):
    pts = lens_eye(spec, cx, cy, 24, 7, tilt_deg=tilt)
    if mutate:
        pts = mutate(pts)
    return EyeKey(frame, {i: PointState(pts[i], keyframe=True if per_point_keyframe is None else (i in per_point_keyframe))
                          for i in spec.ids})


def ann(tracks=None, shapes=None):
    return Annotations(None, {}, tracks or {"mattrai": [], "matphai": []}, shapes or {"mattrai": {}, "matphai": {}}, 0)


def track(label, keys):
    return {label: [EyeTrack(label, keys={k.frame: k for k in keys})], "matphai" if label == "mattrai" else "mattrai": []}


def codes(findings):
    return sorted({(f.level, f.code, f.label) for f in findings})


class ScanTests(unittest.TestCase):
    def test_clean_track_has_no_findings(self):
        a = ann(track("mattrai", [key(MATTRAI, 0), key(MATTRAI, 40, cx=215)]))
        self.assertEqual(scan(a, 41, width=W, height=H), [])

    def test_swapped_corners_is_red(self):
        def swap(p):
            p[14], p[18] = p[18], p[14]
            return p
        a = ann(track("mattrai", [key(MATTRAI, 0, mutate=swap)]))
        c = codes(scan(a, 1, width=W, height=H))
        self.assertIn(("red", "corner_order", "mattrai"), c)

    def test_flipped_lids_is_red_and_reports_pair(self):
        def flip(p):
            p[16], p[20] = (p[16][0], p[20][1]), (p[20][0], p[16][1])
            return p
        a = ann(track("mattrai", [key(MATTRAI, 0, mutate=flip)]))
        f = [x for x in scan(a, 1) if x.code == "lid_order"]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].points, (16, 20))

    def test_crossing_is_red(self):
        def cross(p):
            p[24], p[28] = p[28], p[24]
            return p
        a = ann(track("matphai", [key(MATPHAI, 0, cx=300, mutate=cross)]))
        self.assertIn(("red", "crossing", "matphai"), codes(scan(a, 1)))

    def test_closed_eye_is_not_a_crossing(self):
        def close(p):                       # mắt nhắm: mí trên trùng mí dưới, các điểm gần thẳng hàng (có sai số làm tròn)
            for up, lo in ((15, 21), (16, 20), (17, 19)):
                y = 180.0
                p[up] = (p[up][0], y + 1e-7)
                p[lo] = (p[lo][0], y - 1e-7)
            p[14], p[18] = (p[14][0], 180.0), (p[18][0], 180.0)
            return p
        a = ann(track("mattrai", [key(MATTRAI, 0, mutate=close)]))
        self.assertEqual([f for f in scan(a, 1, width=W, height=H) if f.level == "red"], [])

    def test_point_outside_frame_is_red(self):
        a = ann(track("mattrai", [key(MATTRAI, 0, cx=W - 5)]))
        self.assertIn(("red", "out_of_frame", "mattrai"), codes(scan(a, 1, width=W, height=H)))

    def test_outside_flag_silences_out_of_frame(self):
        k = key(MATTRAI, 0, cx=W - 5)
        for i in MATTRAI.ids:
            k.points[i].outside = True
        self.assertEqual(scan(ann(track("mattrai", [k])), 1, width=W, height=H), [])

    def test_jump_between_frames_is_yellow_and_reported_at_the_frame_after(self):
        a = ann(shapes={"mattrai": {0: key(MATTRAI, 0), 1: key(MATTRAI, 1, cx=230)}, "matphai": {}})
        f = [x for x in scan(a, 2) if x.code == "jump"]
        self.assertEqual([(x.frame, x.level) for x in f], [(1, "yellow")])
        self.assertAlmostEqual(f[0].value, 30.0, delta=0.5)

    def test_partial_keyframe_is_yellow(self):
        a = ann(track("mattrai", [key(MATTRAI, 0), key(MATTRAI, 10, per_point_keyframe={14, 15, 16})]))
        f = [x for x in scan(a, 11) if x.code == "partial_keyframe"]
        self.assertEqual([(x.frame, x.value) for x in f], [(10, 3.0)])

    def test_still_label_over_many_frames_is_yellow(self):
        a = ann(shapes={"mattrai": {t: key(MATTRAI, t) for t in range(40)}, "matphai": {}})
        f = [x for x in scan(a, 40, still_frames=30) if x.code == "still"]
        self.assertEqual(len(f), 1)
        self.assertEqual((f[0].frame, f[0].last), (0, 39))

    def test_consecutive_bad_frames_merge_into_one_range(self):
        def swap(p):
            p[14], p[18] = p[18], p[14]
            return p
        a = ann(shapes={"mattrai": {t: key(MATTRAI, t, cx=200 + 3 * t, mutate=swap) for t in range(5, 12)}, "matphai": {}})
        f = [x for x in scan(a, 20) if x.code == "corner_order"]
        self.assertEqual([(x.frame, x.last) for x in f], [(5, 11)])

    def test_ear_value_and_missing_points(self):
        p = lens_eye(MATTRAI, 200, 180, 24, 7)
        self.assertAlmostEqual(eye_ear(MATTRAI, p), 0.237, delta=0.01)
        q = dict(p)
        del q[16]
        self.assertIsNone(eye_ear(MATTRAI, q))
        self.assertGreater(eye_ear(MATTRAI, lens_eye(MATTRAI, 200, 180, 24, 12)), eye_ear(MATTRAI, p))

    def test_closed_wide_and_jump_ear_rules_are_yellow(self):
        def lids(h):
            return lambda p: lens_eye(MATTRAI, 200, 180, 24, h)
        a = ann(track("mattrai", [key(MATTRAI, 0, mutate=lids(7)), key(MATTRAI, 1, mutate=lids(0.5)), key(MATTRAI, 2, mutate=lids(7)),
                                  key(MATTRAI, 3, mutate=lids(26))]))
        f = scan(a, 4, width=W, height=H)
        c = {(x.level, x.code) for x in f}
        self.assertIn(("yellow", "ear_closed"), c)
        self.assertIn(("yellow", "ear_jump"), c)
        self.assertIn(("yellow", "ear_wide"), c)
        self.assertEqual([x.frame for x in f if x.code == "ear_closed"], [1])
        self.assertEqual(sorted(x.frame for x in f if x.code == "ear_jump"), [1, 2, 3])      # mỗi lần nhảy báo một dòng
        self.assertTrue(all(x.level == "yellow" for x in f if x.code.startswith("ear_")))

    def test_steady_open_eye_has_no_ear_findings(self):
        a = ann(track("mattrai", [key(MATTRAI, 0), key(MATTRAI, 40, cx=215)]))
        self.assertEqual([x for x in scan(a, 41, width=W, height=H) if x.code.startswith("ear_")], [])

    def test_cvat_export_that_omits_outside_points_does_not_crash(self):
        """CVAT 2.75 bỏ thẻ của điểm Outside khi xuất; parse phải điền lại để quét không lỗi (lỗi thật tìm được khi đối chiếu CVAT)."""
        import tempfile
        xml = """<annotations><version>1.1</version><meta><job><size>3</size></job></meta>
<track id="1" label="mattrai" source="manual">
 <skeleton frame="0" keyframe="1" outside="0" occluded="0">""" + "".join(
            f'<points label="{i}" keyframe="1" outside="{1 if i == 20 else 0}" occluded="0" points="{100 + i},{50 + i}"/>' for i in MATTRAI.ids if i != 99) + """</skeleton>
 <skeleton frame="1" keyframe="0" outside="0" occluded="0">""" + "".join(
            f'<points label="{i}" keyframe="0" outside="0" occluded="0" points="{100 + i},{50 + i}"/>' for i in MATTRAI.ids if i != 20) + """</skeleton>
</track></annotations>"""
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as fh:
            fh.write(xml)
        from eyepin import cvatxml
        ann = cvatxml.parse(fh.name)
        os.unlink(fh.name)
        keys = ann.tracks["mattrai"][0].keys
        self.assertEqual(set(keys[1].points), set(MATTRAI.ids))              # điểm 20 vắng trong file nhưng vẫn đủ 8 điểm
        self.assertTrue(keys[1].points[20].outside)
        scan(ann, 3, width=W, height=H)                                      # không còn KeyError

    def test_red_listed_before_yellow(self):
        def swap(p):
            p[14], p[18] = p[18], p[14]
            return p
        a = ann(shapes={"mattrai": {0: key(MATTRAI, 0), 1: key(MATTRAI, 1, cx=240, mutate=swap)}, "matphai": {}})
        levels = [x.level for x in scan(a, 2)]
        self.assertEqual(levels, sorted(levels, key=lambda v: v != "red"))


if __name__ == "__main__":
    unittest.main()
