"""B02 (buglist.md): điểm vắng trong file CVAT bị điền thành (0, 0) Outside, nên `scan` báo nhảy giả và `preview.position_at` trả toạ độ (0, 0).

Phân biệt hai loại (đọc từ mã CVAT 2.75, `cvat/apps/dataset_manager/bindings.py` `_export_track` và `annotation.py`
`get_interpolated_shapes`, include_outside=False):
  - Điểm Outside THẬT: keyframe riêng của điểm có outside="1". CVAT luôn xuất thẻ <points> của keyframe, kèm toạ độ đã lưu.
  - Điểm VẮNG: ở frame không phải keyframe của điểm mà keyframe bên trái của điểm đang Outside, CVAT for video bỏ hẳn thẻ <points>.
    Trong CVAT điểm đó vẫn có toạ độ: nội suy đường thẳng giữa keyframe trái (Outside) và keyframe phải của chính điểm đó.
    Nếu cả 8 điểm đều vắng thì CVAT không ghi cả thẻ <skeleton> của frame đó.
XML ở đây tự dựng (mắt giả hình thấu kính), không dùng dữ liệu công ty.
"""
import math
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatxml  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.preview import position_at  # noqa: E402
from eyepin.scan import scan  # noqa: E402
from test_geometry import lens_eye  # noqa: E402

MATTRAI, MATPHAI = EYES["mattrai"], EYES["matphai"]
W, H, N = 640, 360, 12


def eye(spec, f):
    """Mắt giả trôi 1 px/frame theo x; toạ độ làm tròn 2 chữ số như file CVAT."""
    cx = (200.0 if spec is MATTRAI else 300.0) + 1.0 * f
    return {i: (round(x, 2), round(y, 2)) for i, (x, y) in lens_eye(spec, cx, 180.0, 24, 7).items()}


def pt(pid, xy, keyframe, outside=False):
    return (f'<points label="{pid}" keyframe="{int(keyframe)}" outside="{int(outside)}" occluded="0" '
            f'points="{xy[0]:.2f},{xy[1]:.2f}"/>')


def skel(f, keyframe, points):
    return f'<skeleton frame="{f}" keyframe="{int(keyframe)}" z_order="0">' + "".join(points) + "</skeleton>"


def video_xml():
    """Bản xuất kiểu "CVAT for video 1.1" (mọi frame từ keyframe đầu tới hết job).
    mattrai: keyframe 0, 4, 8; điểm 20 có keyframe Outside thật ở frame 4, vắng ở 5, 6, 7, hiện lại (keyframe) ở 8.
    matphai: keyframe 0, 3 (cả 8 điểm Outside thật), 6; frame 4, 5 không có thẻ <skeleton> (mọi điểm đều vắng)."""
    left = []
    for f in range(N):
        kf = f in (0, 4, 8)
        g = min(f, 8)                                      # sau keyframe cuối CVAT giữ nguyên vị trí
        pts = []
        for i in MATTRAI.ids:
            if i == 20 and 5 <= f <= 7:
                continue                                   # CVAT bỏ thẻ: keyframe trái của điểm 20 (frame 4) đang Outside
            pts.append(pt(i, eye(MATTRAI, g)[i], kf, outside=(i == 20 and f == 4)))
        left.append(skel(f, kf, pts))
    right = []
    for f in range(N):
        if f in (4, 5):
            continue                                       # cả 8 điểm vắng: CVAT không ghi thẻ <skeleton>
        kf = f in (0, 3, 6)
        g = min(f, 6)
        right.append(skel(f, kf, [pt(i, eye(MATPHAI, g)[i], kf, outside=(f == 3)) for i in MATPHAI.ids]))
    return ("<?xml version='1.0' encoding='utf-8'?>\n<annotations><version>1.1</version><meta><job><size>12</size></job>"
            f"<task><original_size><width>{W}</width><height>{H}</height></original_size></task></meta>"
            '<track id="0" label="mattrai" source="manual">' + "".join(left) + "</track>"
            '<track id="1" label="matphai" source="manual">' + "".join(right) + "</track>"
            '<track id="2" label="mui" source="manual"><box frame="0" keyframe="1" outside="0" occluded="0" '
            'xtl="10.00" ytl="10.00" xbr="20.00" ybr="20.00" z_order="0"/></track>'
            "</annotations>")


def parse_text(text):
    fd, path = tempfile.mkstemp(suffix=".xml")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        return cvatxml.parse(path)
    finally:
        os.unlink(path)


def lerp(a, b, w):
    return a[0] + w * (b[0] - a[0]), a[1] + w * (b[1] - a[1])


class AbsentPointTests(unittest.TestCase):
    def setUp(self):
        self.ann = parse_text(video_xml())
        self.left = self.ann.tracks["mattrai"][0].keys
        self.right = self.ann.tracks["matphai"][0].keys

    def test_scan_reports_no_false_jump(self):
        """Trước khi sửa: điểm 20 vắng ở frame 5–7 bị đặt ở (0, 0) nên quét báo hai lần nhảy (frame 5 và frame 8)."""
        found = scan(self.ann, N, width=W, height=H)
        self.assertEqual([(f.code, f.label, f.frame) for f in found if f.code == "jump"], [])
        self.assertEqual(found, [])                        # mắt trôi đều 1 px/frame, hai mí đúng: không có gì đáng báo

    def test_absent_point_gets_cvat_coordinate_and_stays_outside(self):
        for f in (5, 6, 7):
            p = self.left[f].points[20]
            self.assertTrue(p.outside)                     # vẫn Outside như CVAT (cờ lấy từ keyframe trái)
            self.assertFalse(p.keyframe)
            want = lerp(eye(MATTRAI, 4)[20], eye(MATTRAI, 8)[20], (f - 4) / 4)   # CVAT nội suy giữa keyframe 4 (Outside) và 8
            self.assertAlmostEqual(p.xy[0], want[0], places=6)
            self.assertAlmostEqual(p.xy[1], want[1], places=6)

    def test_position_at_is_near_the_eye(self):
        k = position_at(self.left, 6, MATTRAI.ids)
        self.assertTrue(k.points[20].outside)
        self.assertLess(math.dist(k.points[20].xy, eye(MATTRAI, 6)[20]), 0.05)    # trước khi sửa: (0, 0)
        # matphai frame 4, 5 không có thẻ <skeleton>: nội suy giữa keyframe 3 (Outside thật) và 6, cờ Outside lấy từ bên trái
        for f in (4, 5):
            k = position_at(self.right, f, MATPHAI.ids)
            self.assertTrue(all(k.points[i].outside for i in MATPHAI.ids))
            self.assertLess(max(math.dist(k.points[i].xy, eye(MATPHAI, f)[i]) for i in MATPHAI.ids), 0.05)

    def test_true_outside_points_keep_their_coordinates(self):
        p = self.left[4].points[20]
        self.assertTrue(p.outside and p.keyframe)
        self.assertEqual(p.xy, eye(MATTRAI, 4)[20])
        for i in MATPHAI.ids:
            self.assertTrue(self.right[3].points[i].outside)
            self.assertEqual(self.right[3].points[i].xy, eye(MATPHAI, 3)[i])

    def test_parse_does_not_touch_the_xml_tree(self):
        """Điền điểm vắng chỉ ở dữ liệu đọc ra; cây XML (nền của write_eyes) giữ nguyên, nên file ghi ra không đổi."""
        root = self.ann.tree.getroot()
        sk5 = root.find("track[@label='mattrai']/skeleton[@frame='5']")
        self.assertEqual(sorted(int(p.get("label")) for p in sk5.findall("points")), [i for i in MATTRAI.ids if i != 20])
        self.assertIsNone(root.find("track[@label='matphai']/skeleton[@frame='4']"))

    def test_write_eyes_round_trip_keeps_true_outside_points(self):
        fd, out = tempfile.mkstemp(suffix=".xml")
        os.close(fd)
        try:
            cvatxml.write_eyes(self.ann, out, new_tracks=[t for l in EYES for t in self.ann.tracks[l]])
            again = cvatxml.parse(out)
            root = ET.parse(out).getroot()
        finally:
            os.unlink(out)
        p = again.tracks["mattrai"][0].keys[4].points[20]
        self.assertTrue(p.outside)
        self.assertEqual(p.xy, eye(MATTRAI, 4)[20])
        for i in MATPHAI.ids:
            q = again.tracks["matphai"][0].keys[3].points[i]
            self.assertTrue(q.outside)
            self.assertEqual(q.xy, eye(MATPHAI, 3)[i])
        el = root.find("track[@label='mattrai']/skeleton[@frame='4']/points[@label='20']")
        x, y = eye(MATTRAI, 4)[20]
        self.assertEqual((el.get("outside"), el.get("points")), ("1", f"{x:.2f},{y:.2f}"))
        self.assertEqual(len(root.findall("track[@label='mui']")), 1)                  # nhãn không phải mắt giữ nguyên
        # mọi điểm có mặt trong file gốc giữ nguyên toạ độ và cờ
        for label in EYES:
            before, after = self.ann.tracks[label][0].keys, again.tracks[label][0].keys
            for f, k in before.items():
                for i, ps in k.points.items():
                    self.assertEqual((after[f].points[i].xy, after[f].points[i].outside), (ps.xy, ps.outside))
        self.assertEqual(scan(again, N, width=W, height=H), [])


class AbsentEdgeCaseTests(unittest.TestCase):
    def test_point_absent_before_its_first_keyframe_takes_the_next_coordinate(self):
        """Track con của một điểm bắt đầu muộn hơn skeleton: CVAT không xuất điểm đó ở các frame trước keyframe đầu của nó."""
        sks = []
        for f in range(4):
            sks.append(skel(f, f in (0, 2), [pt(i, eye(MATTRAI, f)[i], f in (0, 2)) for i in MATTRAI.ids if not (i == 21 and f < 2)]))
        ann = parse_text("<annotations><version>1.1</version><meta><job><size>4</size></job></meta>"
                         '<track id="0" label="mattrai" source="manual">' + "".join(sks) + "</track></annotations>")
        keys = ann.tracks["mattrai"][0].keys
        for f in (0, 1):
            self.assertTrue(keys[f].points[21].outside)
            self.assertEqual(keys[f].points[21].xy, eye(MATTRAI, 2)[21])
        self.assertEqual([f for f in scan(ann, 4) if f.code == "jump"], [])

    def test_absent_point_in_image_shapes(self):
        """Dạng "CVAT for images": điểm vắng của một shape lấy toạ độ từ shape cùng nhãn ở frame gần nhất có điểm đó."""
        ims = []
        for f in range(3):
            pts = "".join(f'<points label="{i}" source="manual" outside="0" occluded="0" points="{x:.2f},{y:.2f}"/>'
                          for i, (x, y) in eye(MATTRAI, f).items() if not (i == 20 and f == 1))
            ims.append(f'<image id="{f}" name="f{f}.jpg" width="{W}" height="{H}">'
                       f'<skeleton label="mattrai" source="manual" z_order="0">{pts}</skeleton></image>')
        ann = parse_text("<annotations><version>1.1</version>" + "".join(ims) + "</annotations>")
        p = ann.shapes["mattrai"][1].points[20]
        self.assertTrue(p.outside)
        want = lerp(eye(MATTRAI, 0)[20], eye(MATTRAI, 2)[20], 0.5)
        self.assertAlmostEqual(p.xy[0], want[0], places=6)
        self.assertAlmostEqual(p.xy[1], want[1], places=6)
        self.assertEqual([f for f in scan(ann, 3, width=W, height=H) if f.code == "jump"], [])

    def test_lone_absent_point_without_any_neighbour_uses_its_own_skeleton(self):
        """Không frame nào có điểm này: lấy trọng tâm các điểm có mặt của chính skeleton đó, không còn (0, 0)."""
        e = eye(MATTRAI, 0)
        pts = "".join(f'<points label="{i}" source="manual" outside="0" occluded="0" points="{x:.2f},{y:.2f}"/>'
                      for i, (x, y) in e.items() if i != 20)
        ann = parse_text('<annotations><version>1.1</version><image id="0" name="a.jpg" width="640" height="360">'
                         f'<skeleton label="mattrai" source="manual" z_order="0">{pts}</skeleton></image></annotations>')
        p = ann.shapes["mattrai"][0].points[20]
        self.assertTrue(p.outside)
        cx = sum(e[i][0] for i in e if i != 20) / 7
        cy = sum(e[i][1] for i in e if i != 20) / 7
        self.assertAlmostEqual(p.xy[0], cx, places=6)
        self.assertAlmostEqual(p.xy[1], cy, places=6)


if __name__ == "__main__":
    unittest.main()
