"""Task 2 (shape): `cvatxml.write_eyes` ghi shape mắt vào file chưa có thẻ <image> (danh sách `EyeShape`).
Dữ liệu giả của `test_tracking`, không dùng ảnh công ty."""
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml  # noqa: E402
from eyepin.cvatxml import EyeKey, EyeShape, PointState  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import empty_annotations  # noqa: E402
import test_tracking as T  # noqa: E402

NAMES = [f"f{i:03d}.png" for i in range(5)]


def make_key(frame, dx=0.0, label="mattrai"):
    pts = T.pins_at(0)
    return EyeKey(frame, {i: PointState((pts[i][0] + dx, pts[i][1])) for i in EYES[label].ids})


class ShapeXmlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="eyepin_shape_")
        self.out = os.path.join(self.tmp.name, "out.xml")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, ann, shapes, **kw):
        cvatxml.write_eyes(ann, self.out, new_shapes=shapes, **kw)
        return ET.parse(self.out).getroot()

    def test_creates_image_when_base_has_none(self):
        key = make_key(3)
        root = self.write(empty_annotations(), [EyeShape("mattrai", key)], frame_names=NAMES, size=(T.W, T.H))
        images = root.findall("image")
        self.assertEqual(len(images), 1)
        im = images[0]
        self.assertEqual((im.get("id"), im.get("name"), im.get("width"), im.get("height")), ("3", "f003.png", str(T.W), str(T.H)))
        sks = im.findall("skeleton")
        self.assertEqual(len(sks), 1)
        self.assertEqual(sks[0].get("label"), "mattrai")
        self.assertEqual(len(sks[0].findall("points")), 8)
        self.assertIsNone(sks[0].get("frame"))
        self.assertIsNone(sks[0].get("keyframe"))
        back = cvatxml.parse(self.out)
        self.assertEqual(set(back.shapes["mattrai"]), {3})
        for pid, ps in key.points.items():
            got = back.shapes["mattrai"][3].points[pid].xy
            self.assertLess(abs(got[0] - ps.xy[0]), 0.01)
            self.assertLess(abs(got[1] - ps.xy[1]), 0.01)

    def test_two_people_same_label_same_frame(self):
        root = self.write(empty_annotations(), [EyeShape("mattrai", make_key(3)), EyeShape("mattrai", make_key(3, dx=40.0))],
                          frame_names=NAMES, size=(T.W, T.H))
        images = root.findall("image")
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].get("id"), "3")
        sks = images[0].findall("skeleton")
        self.assertEqual([s.get("label") for s in sks], ["mattrai", "mattrai"])

    def test_point_flags_are_written(self):
        key = make_key(3)
        key.points[14].outside = True
        key.points[16].occluded = True
        root = self.write(empty_annotations(), [EyeShape("mattrai", key)], frame_names=NAMES, size=(T.W, T.H))
        pts = {p.get("label"): p for p in root.find("image/skeleton").findall("points")}
        self.assertEqual(pts["14"].get("outside"), "1")
        self.assertEqual(pts["16"].get("occluded"), "1")
        self.assertEqual(pts["18"].get("outside"), "0")

    def test_frame_numbers_are_remapped(self):
        ann = empty_annotations()
        ann.frame_numbers = [10, 11, 12, 13, 14]
        root = self.write(ann, [EyeShape("mattrai", make_key(3))], frame_names=NAMES, size=(T.W, T.H))
        im = root.find("image")
        self.assertEqual((im.get("id"), im.get("name")), ("13", NAMES[3]))

    def test_images_come_before_tracks_and_sorted(self):
        ann = empty_annotations()
        tr = ET.SubElement(ann.tree.getroot(), "track", {"id": "5", "label": "khac"})
        ET.SubElement(tr, "box", {"frame": "0"})
        root = self.write(ann, [EyeShape("mattrai", make_key(4)), EyeShape("matphai", make_key(1, label="matphai"))],
                          frame_names=NAMES, size=(T.W, T.H))
        tags = [el.tag for el in root]
        self.assertLess(max(i for i, t in enumerate(tags) if t == "image"), tags.index("track"))
        self.assertEqual([im.get("id") for im in root.findall("image")], ["1", "4"])

    def test_missing_image_without_names_still_raises(self):
        with self.assertRaises(KeyError):
            self.write(empty_annotations(), [EyeShape("mattrai", make_key(3))])
        with self.assertRaises(KeyError):
            self.write(empty_annotations(), {"mattrai": {3: make_key(3)}})

    def test_existing_image_is_reused_and_old_eye_removed(self):
        ann = empty_annotations()
        im = ET.SubElement(ann.tree.getroot(), "image", {"id": "3", "name": "f003.png", "width": "320", "height": "160"})
        ET.SubElement(im, "box", {"label": "mat", "xtl": "0", "ytl": "0", "xbr": "5", "ybr": "5"})
        old = ET.SubElement(im, "skeleton", {"label": "mattrai"})
        ET.SubElement(old, "points", {"label": "14", "points": "1.00,1.00"})
        root = self.write(ann, [EyeShape("mattrai", make_key(3, dx=7.0))], frame_names=NAMES, size=(T.W, T.H))
        images = root.findall("image")
        self.assertEqual(len(images), 1)
        self.assertEqual(len(images[0].findall("box")), 1)
        sks = images[0].findall("skeleton")
        self.assertEqual(len(sks), 1)
        self.assertEqual(len(sks[0].findall("points")), 8)

    def test_old_dict_form_still_works(self):
        ann = empty_annotations()
        ET.SubElement(ann.tree.getroot(), "image", {"id": "3", "name": "f003.png"})
        root = self.write(ann, {"mattrai": {3: make_key(3)}})
        self.assertEqual(len(root.find("image").findall("skeleton")), 1)

    def test_dict_form_names_image_by_dict_key(self):
        """M5: dạng dict {nhãn: {frame: EyeKey}}: id và tên của <image> mới đều theo khoá dict (không lấy tên theo `key.frame`)."""
        root = self.write(empty_annotations(), {"mattrai": {3: make_key(1)}}, frame_names=NAMES, size=(T.W, T.H))
        im = root.find("image")
        self.assertEqual((im.get("id"), im.get("name")), ("3", "f003.png"))


if __name__ == "__main__":
    unittest.main()
