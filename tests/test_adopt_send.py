"""Gửi lại job đã nạp shape mắt (`cvatsync.prepare`/`send`/`count_changes`/`adopted_snapshot`, khôi phục trong `gui_cvat`; design/2026-11-19-qc-edit-design.md).

Server giả `FakeCvat` không tự cập nhật JSON annotations sau import, nên các test gửi đặt `FakeCvat.on_import`: móc đó dựng JSON từ chính file
đã gửi (như CVAT thật sẽ lưu), có thể cấy lệch vào để thử phép kiểm sau khi gửi. JSON và nhãn dựng tay bằng các hàm của `test_adopt`; ảnh giả
của `test_tracking`. Phần giao diện bỏ qua nếu máy không mở được cửa sổ Tk."""
import copy
import os
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import cvatsync, cvatxml, gui_cvat  # noqa: E402
from eyepin.cvatapi import CvatError  # noqa: E402
from eyepin.cvatsource import open_job  # noqa: E402
from eyepin.cvatxml import EyeKey, EyeShape, PointState  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
import test_adopt as A  # noqa: E402
import test_adopt_open as O  # noqa: E402
import test_gui_cvat as G  # noqa: E402
import test_tracking as T  # noqa: E402
from test_cvatsource import VIDEO, Base, box_image, eye_shape_image, xml_of  # noqa: E402

N = G.N
ID = {lb["name"]: lb["id"] for lb in A.LABELS}
MOVE = 0.5                                                    # px: dời đủ xa để chắc chắn là "sửa"


def four_shapes():
    """Bốn shape mắt trên CVAT: mattrai ở frame 1 và 3, matphai ở frame 2 và 5."""
    return [A.skeleton("mattrai", 1), A.skeleton("mattrai", 3), A.skeleton("matphai", 2), A.skeleton("matphai", 5)]


def images_xml(shapes, extra=""):
    """XML "CVAT for images" của job: mỗi shape mắt là một `<image>` (toạ độ trong XML khác JSON, để thấy bản chụp dựng từ JSON)."""
    eyes = "".join(eye_shape_image(sh["frame"], next(n for n, i in ID.items() if i == sh["label_id"])) for sh in shapes)
    return xml_of(images=extra + eyes, job_size=N)


def stored_json(xml, nums):
    """JSON annotations mà CVAT lưu sau khi nạp file `xml` (số frame của job `nums`): các shape mắt trong `<image>` của file."""
    ann = cvatxml.parse_bytes(xml, nums)
    shapes = []
    for label, per_frame in sorted(ann.shapes.items()):
        for f, key in sorted(per_frame.items()):
            pts = {i: ps.xy for i, ps in key.points.items()}
            flags = {i: "outside" if ps.outside else "occluded" for i, ps in key.points.items() if ps.outside or ps.occluded}
            shapes.append(A.skeleton(label, nums[f], pts, flags=flags))
    return A.job(shapes=shapes)


def shift_point(aj, label, frame, pid, dx):
    """Dời điểm `pid` của shape `label` ở số frame `frame` trong JSON một đoạn `dx` theo x."""
    for o in aj["shapes"]:
        if o["label_id"] == ID[label] and o["frame"] == frame:
            for el in o["elements"]:
                if el["label_id"] == A.SUB[label][pid]:
                    el["points"][0] += dx
                    return
    raise AssertionError(f"không có shape {label} ở frame {frame}")


def drop_shape(aj, label, frame):
    aj["shapes"].remove(next(o for o in aj["shapes"] if o["label_id"] == ID[label] and o["frame"] == frame))


def server_of(aj):
    return cvatsync._json_eye_shapes(aj, A.LABELS)


def eye_images(job):
    """([(id của <image>, nhãn)] của skeleton mắt, [track mắt]) trong XML đang lưu ở job."""
    root = ET.fromstring(job.xml)
    return (sorted((int(im.get("id")), sk.get("label")) for im in root.findall("image") for sk in im.findall("skeleton") if sk.get("label") in EYES),
            [tr for tr in root.findall("track") if tr.get("label") in EYES])


def image_skeletons(xml):
    root = ET.fromstring(xml)
    return sorted((int(im.get("id")), sk.get("label")) for im in root.findall("image") for sk in im.findall("skeleton") if sk.get("label") in EYES)


class AdoptedJob(Base):
    """Job 7 (8 frame, nhãn của `test_adopt`) trên server giả, mở thành phiên đã nạp."""

    def open(self, shapes=None, xml=None, tracks=(), video=None, **kw):
        shapes = four_shapes() if shapes is None else shapes
        self.job = self.serve(n_frames=N, labels=A.LABELS, xml=xml or images_xml(shapes), **kw)
        self.job.annotations_json = A.job(shapes=shapes, tracks=tracks)
        if video is not None:
            self.job.export_xml_by_format[VIDEO] = video
        s = open_job(self.cl, 7)
        self.assertTrue(s.adopted)
        self.nums = s.source.frame_numbers
        return s

    def cvat_stores(self, tamper=None):
        """Sau mỗi import, JSON của job là điều CVAT lưu từ file vừa nhận; `tamper(aj)` cấy lệch vào (CVAT lưu sai)."""
        def on_import(job, xml):
            aj = stored_json(xml, self.nums)
            if tamper:
                tamper(aj)
            job.annotations_json = aj
        self.srv.on_import = on_import

    @staticmethod
    def edit_one_and_add_one(s):
        """Dời điểm 14 của mattrai ở frame 3 và vẽ thêm shape mattrai ở frame 6; các shape khác giữ nguyên. Có công chưa gửi."""
        x, y = s.pins[3][14]
        s.move_point(3, 14, (x + MOVE, y))
        s.pin_eye(6, "mattrai", {i: T.pins_at(6)[i] for i in EYES["mattrai"].pins})


class TestCountChanges(AdoptedJob):
    def test_count_changes_basic(self):
        s = self.open()
        x, y = s.pins[3][14]
        s.move_point(3, 14, (x + MOVE, y))                          # sửa: dời một điểm 0,5 px
        s.toggle_flag(2, 24, "occluded")                            # sửa: đổi cờ
        s.delete_shape("matphai", 5)                                # bỏ
        s.pin_eye(6, "mattrai", {i: T.pins_at(6)[i] for i in EYES["mattrai"].pins})      # thêm
        plan = cvatsync.prepare(s, self.cl)
        self.assertTrue(plan.adopted)
        self.assertEqual(plan.counts, {"server": 4, "kept": 1, "edited": 2, "added": 1, "removed": 1})
        self.assertEqual([(name, jf) for name, jf, _ in plan.kept], [("mattrai", 1)])

    def test_count_changes_tolerance(self):
        s = self.open()
        server = server_of(self.job.annotations_json)
        sent = s.build_shapes()

        def counts(dx):
            moved = copy.deepcopy(sent)
            x, y = moved[0].key.points[14].xy
            moved[0].key.points[14].xy = (x + dx, y)
            return cvatsync.count_changes(moved, server, self.nums)[0]

        self.assertEqual(counts(0.0)["kept"], 4)
        self.assertEqual(counts(0.004)["kept"], 4)
        self.assertEqual((counts(0.006)["kept"], counts(0.006)["edited"]), (3, 1))

    def test_tolerance_has_float_slack(self):
        """210.485 - 210.48 là 0,005000000000024 (lớn hơn 0,005 một chút do dấu phẩy động): vẫn là "giữ"."""
        self.assertGreater(210.485 - 210.48, cvatsync.TOL_KEPT)
        ids = EYES["mattrai"].ids
        server = [("mattrai", 4, {i: ((210.48, 50.0 + i), False, False) for i in ids})]
        sent = [EyeShape("mattrai", EyeKey(4, {i: PointState((210.485, 50.0 + i)) for i in ids}))]
        counts, kept = cvatsync.count_changes(sent, server, list(range(N)))
        self.assertEqual((counts["kept"], counts["edited"]), (1, 0))
        self.assertEqual(kept, server)

    def test_flags_decide_kept(self):
        ids = EYES["mattrai"].ids
        server = [("mattrai", 4, {i: ((100.0, 50.0 + i), i == 16, i == 18) for i in ids})]        # điểm 16 occluded, điểm 18 outside

        def sent():
            return [EyeShape("mattrai", EyeKey(4, {i: PointState((100.0, 50.0 + i), outside=(i == 18), occluded=(i == 16)) for i in ids}))]

        self.assertEqual(cvatsync.count_changes(sent(), server, list(range(N)))[0]["kept"], 1)
        other = sent()
        other[0].key.points[18].outside, other[0].key.points[18].occluded = False, True           # outside đổi thành occluded
        self.assertEqual(cvatsync.count_changes(other, server, list(range(N)))[0]["edited"], 1)

    def test_two_people_on_the_same_frame(self):
        s = self.open()
        server = server_of(self.job.annotations_json)
        sent = s.build_shapes()
        extra = copy.deepcopy(sent[0])
        extra.key.points[14].xy = (extra.key.points[14].xy[0] + 20, extra.key.points[14].xy[1])
        for order in (sent + [extra], [extra] + sent):                # shape giống bản cũ được ghép với bản cũ, không phụ thuộc thứ tự
            with self.subTest(first=order[0] is extra):
                counts, kept = cvatsync.count_changes(order, server, self.nums)
                self.assertEqual(counts, {"server": 4, "kept": 4, "edited": 0, "added": 1, "removed": 0})
                self.assertEqual(len(kept), 4)

    def test_swap_counts_two_edits(self):
        s = self.open([A.skeleton("mattrai", 2), A.skeleton("matphai", 2)])
        s.swap_shapes_at(2)
        plan = cvatsync.prepare(s, self.cl)
        self.assertEqual(plan.counts, {"server": 2, "kept": 0, "edited": 2, "added": 0, "removed": 0})
        self.assertFalse(plan.needs_warning())

    def test_plan_text_for_adopted(self):
        s = self.open()
        x, y = s.pins[3][14]
        s.move_point(3, 14, (x + MOVE, y))
        s.delete_shape("matphai", 5)
        plan = cvatsync.prepare(s, self.cl)
        self.assertTrue(plan.text().startswith("Job có 4 shape mắt trên CVAT. Sẽ gửi 3 shape: giữ nguyên 2, sửa 1, thêm 0, bỏ 1."), plan.text())
        self.assertNotIn("Việc gửi sẽ xoá nhãn mắt", plan.text())
        self.assertNotIn("EyePin sẽ thay toàn bộ nhãn", plan.text())

    def test_warning_only_when_removed(self):
        s = self.open()
        self.assertFalse(cvatsync.prepare(s, self.cl).needs_warning())            # chưa đổi gì
        self.edit_one_and_add_one(s)
        self.assertFalse(cvatsync.prepare(s, self.cl).needs_warning())            # sửa và thêm: không mất gì
        s.delete_shape("matphai", 5)
        plan = cvatsync.prepare(s, self.cl)
        self.assertEqual(plan.counts["removed"], 1)
        self.assertTrue(plan.needs_warning())                                     # bỏ một shape

    def test_warning_when_job_changed_on_server(self):
        s = self.open()
        self.job.version += 1                                                      # ai đó sửa job trên CVAT sau lúc mở
        plan = cvatsync.prepare(s, self.cl)
        self.assertEqual(plan.counts["removed"], 0)
        self.assertTrue(plan.needs_warning())
        self.assertIn("Job đã bị sửa trên CVAT kể từ lúc EyePin mở", plan.text())

    def test_not_adopted_unchanged(self):
        job = self.serve(n_frames=N)
        s = open_job(self.cl, 7)
        for f in (0, 4):
            t = s.source.frame_numbers[f]
            for label, spec in EYES.items():
                s.pin_eye(f, label, {i: T.pins_at(t)[i] for i in spec.pins})
        plan = cvatsync.prepare(s, self.cl)
        self.assertFalse(plan.adopted)
        self.assertIsNone(plan.counts)
        self.assertEqual(plan.kept, [])
        self.assertEqual(plan.base_xml, job.xml)                                   # bản chụp vẫn là bản xuất nền nguyên văn
        self.assertFalse(plan.needs_warning())
        self.assertEqual(plan.text(), f"EyePin sẽ thay toàn bộ nhãn của job #7 trên CVAT bằng nhãn nền hiện có cộng {plan.keyframes} keyframe mắt mới.")


class TestSendAdopted(AdoptedJob):
    def test_send_adopted_roundtrip_ok(self):
        s = self.open()
        self.edit_one_and_add_one(s)
        s.delete_shape("matphai", 5)
        self.assertTrue(s.unsent)
        self.cvat_stores()
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertTrue(res.ok, (res.message, res.mismatches))
        self.assertEqual(res.mismatches, [])
        self.assertIs(s.unsent, False)
        images, tracks = eye_images(self.job)
        self.assertEqual(images, [(1, "mattrai"), (2, "matphai"), (3, "mattrai"), (6, "mattrai")])      # shape vẫn là shape
        self.assertEqual(tracks, [])

    def test_kept_shape_changed_on_server_is_caught(self):
        s = self.open()
        self.edit_one_and_add_one(s)
        self.cvat_stores(lambda aj: shift_point(aj, "matphai", 2, 24, 0.5))        # shape matphai ở frame 2 không ai sửa
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertIn("Shape matphai frame 2 không ai sửa nhưng CVAT lưu khác bản trước khi gửi", res.mismatches)
        self.assertTrue(s.unsent)

    def test_kept_shape_missing_after_import_is_caught(self):
        s = self.open()
        self.edit_one_and_add_one(s)
        self.cvat_stores(lambda aj: drop_shape(aj, "mattrai", 1))
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertIn("Shape mattrai frame 1 không ai sửa nhưng CVAT lưu khác bản trước khi gửi", res.mismatches)
        self.assertTrue(s.unsent)

    def test_small_drift_of_kept_shape_is_caught_by_its_own_check(self):
        """Lệch 0,015 px nằm trong dung sai đối chiếu chung (0,02) nhưng quá dung sai của shape "giữ nguyên" (0,01)."""
        exact = [A.skeleton(l, f, {i: (round(x, 2), round(y, 2)) for i, (x, y) in T.pins_at(f).items() if i in EYES[l].ids})
                 for l, f in (("mattrai", 1), ("matphai", 2))]
        s = self.open(exact)
        s.pin_eye(5, "mattrai", {i: T.pins_at(5)[i] for i in EYES["mattrai"].pins})
        self.cvat_stores(lambda aj: shift_point(aj, "mattrai", 1, 14, 0.015))
        res = cvatsync.send(s, self.cl, cvatsync.prepare(s, self.cl))
        self.assertFalse(res.ok)
        self.assertEqual(res.mismatches, ["Shape mattrai frame 1 không ai sửa nhưng CVAT lưu khác bản trước khi gửi"])

    def test_edited_shape_is_not_in_the_kept_check(self):
        """Shape đã sửa không bị kiểm "giữ nguyên": CVAT lưu đúng điều tool gửi thì khớp dù khác bản cũ."""
        s = self.open()
        self.edit_one_and_add_one(s)
        self.cvat_stores()
        plan = cvatsync.prepare(s, self.cl)
        self.assertNotIn(("mattrai", 3), [(n, jf) for n, jf, _ in plan.kept])
        self.assertTrue(cvatsync.send(s, self.cl, plan).ok)

    def test_prepare_refuses_when_snapshot_cannot_be_built(self):
        s = self.open()
        self.job.annotations_json["shapes"][0]["elements"].pop()                   # ai đó đổi shape trên CVAT: còn 7 điểm
        with self.assertRaises(CvatError) as ctx:
            cvatsync.prepare(s, self.cl)
        self.assertIn("không đủ 8 điểm", str(ctx.exception))


class TestAdoptedSnapshot(AdoptedJob):
    def test_snapshot_keeps_eye_shapes(self):
        shapes = [A.skeleton("mattrai", 1, flags={16: "outside", 18: "occluded"}), A.skeleton("matphai", 2), A.box(4)]
        s = self.open(shapes, xml=images_xml(shapes[:2], extra=box_image(4)))
        plan = cvatsync.prepare(s, self.cl)
        root = ET.fromstring(plan.base_xml)
        self.assertEqual([tr.get("label") for tr in root.findall("track")], [])                  # không có track mắt
        sks = {(int(im.get("id")), sk.get("label")): sk for im in root.findall("image") for sk in im.findall("skeleton")}
        self.assertEqual(sorted(sks), [(1, "mattrai"), (2, "matphai")])
        for (f, label), sk in sks.items():
            self.assertEqual(sorted(int(p.get("label")) for p in sk.findall("points")), list(EYES[label].ids))
        flags = {int(p.get("label")): (p.get("outside"), p.get("occluded")) for p in sks[(1, "mattrai")].findall("points")}
        self.assertEqual((flags[16], flags[18], flags[14]), (("1", "0"), ("0", "1"), ("0", "0")))   # điểm Outside vẫn đủ trong file
        boxes = [(im.get("id"), b.get("label")) for im in root.findall("image") for b in im.findall("box")]
        self.assertEqual(boxes, [("4", "face")])                                                # nhãn không phải mắt còn nguyên
        back = cvatxml.parse_bytes(plan.base_xml, self.nums)                                      # toạ độ lấy từ JSON, không từ XML của job
        for (f, label), sk in sks.items():
            for i, ps in back.shapes[label][f].points.items():
                self.assertEqual(ps.xy, tuple(round(v, 2) for v in T.pins_at(f)[i]))

    def test_snapshot_with_non_eye_tracks(self):
        face = ('<track id="9" label="face" source="manual">'
                '<box frame="0" keyframe="1" outside="0" occluded="0" xtl="10" ytl="10" xbr="50" ybr="50" z_order="0"/>'
                '<box frame="1" keyframe="1" outside="0" occluded="0" xtl="12" ytl="10" xbr="52" ybr="50" z_order="0"/></track>')
        shapes = [A.skeleton("mattrai", 2), A.skeleton("matphai", 5)]
        s = self.open(shapes, tracks=[A.box_track([0, 1])], video=xml_of(tracks=face, job_size=N))      # nền video: có track không phải mắt
        plan = cvatsync.prepare(s, self.cl)
        self.assertEqual(plan.base_format, VIDEO)
        root = ET.fromstring(plan.base_xml)
        self.assertEqual([tr.get("label") for tr in root.findall("track")], ["face"])
        self.assertEqual(image_skeletons(plan.base_xml), [(2, "mattrai"), (5, "matphai")])
        self.assertEqual(plan.counts, {"server": 2, "kept": 2, "edited": 0, "added": 0, "removed": 0})

    def test_snapshot_job_numbers(self):
        shapes = [A.skeleton("mattrai", 11), A.skeleton("matphai", 13)]
        s = self.open(shapes, xml=xml_of(job_size=N), start_frame=10)
        self.assertEqual(self.nums, list(range(10, 10 + N)))
        plan = cvatsync.prepare(s, self.cl)
        root = ET.fromstring(plan.base_xml)
        self.assertEqual(sorted((im.get("id"), im.get("name"), sk.get("label")) for im in root.findall("image") for sk in im.findall("skeleton")),
                         [("11", "frame_000011.jpg", "mattrai"), ("13", "frame_000013.jpg", "matphai")])
        self.assertEqual(plan.counts, {"server": 2, "kept": 2, "edited": 0, "added": 0, "removed": 0})   # đổi số frame trước khi so

    def test_adopted_snapshot_function(self):
        """Hàm dùng chung với nơi khác (Task 9): bản chụp dựng từ JSON, số frame của job, tên ảnh của phiên."""
        s = self.open([A.skeleton("mattrai", 1, flags={20: "outside"})], xml=xml_of(job_size=N))
        ann = cvatxml.parse_bytes(xml_of(job_size=N), self.nums)
        data = cvatsync.adopted_snapshot(ann, self.job.annotations_json, A.LABELS, self.nums, s.names, (s.width, s.height))
        back = cvatxml.parse_bytes(data, self.nums)
        self.assertEqual(sorted(back.shapes["mattrai"]), [1])
        self.assertTrue(back.shapes["mattrai"][1].points[20].outside)
        self.assertFalse(back.shapes["mattrai"][1].points[14].outside)
        self.assertEqual(back.shapes["matphai"], {})


class TestAdoptedRestoreText(O.AdoptGuiCase):
    def send_failing(self):
        """Mở job toàn shape, xoá một shape rồi gửi; import báo lỗi nên hiện hộp lỗi có nút khôi phục."""
        self.serve_shapes()
        app = self.make_app()
        s = self.open_job(app)
        s.delete_shape("mattrai", 2)
        self.srv.fail_import = "file không hợp lệ"
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        return app, app._dialogs["send_failed"]

    def test_restore_limit_text(self):
        app, d = self.send_failing()
        self.assertEqual(gui_cvat.RESTORE_LIMIT_ADOPTED,
                         "Khôi phục đưa job về đúng nhãn trên CVAT ngay trước lần gửi này (shape mắt và nhãn khác).")
        shown = G.texts(d)
        self.assertIn(gui_cvat.RESTORE_LIMIT_ADOPTED, shown)
        self.assertNotIn(gui_cvat.RESTORE_LIMIT, shown)
        self.srv.fail_import = None
        G.buttons(d, "Khôi phục job về bản trước khi gửi")[0].invoke()
        self.wait(app)
        asked = [text for kind, text, _ in app.asked if kind == "restore"]
        self.assertEqual(len(asked), 1)
        self.assertIn(gui_cvat.RESTORE_LIMIT_ADOPTED, asked[0])
        self.assertNotIn(gui_cvat.RESTORE_LIMIT, asked[0])

    def test_restore_brings_back_shapes_as_shapes(self):
        app, d = self.send_failing()
        before = self.srv.jobs[7].xml
        self.srv.fail_import = None
        G.buttons(d, "Khôi phục job về bản trước khi gửi")[0].invoke()
        self.wait(app)
        job = self.srv.jobs[7]
        self.assertNotEqual(job.xml, before)                                        # bản chụp đã được nạp lại
        self.assertEqual(image_skeletons(job.xml), [(2, "mattrai"), (5, "matphai")])              # shape mắt vẫn là shape, đủ như trước khi gửi
        self.assertEqual([tr for tr in ET.fromstring(job.xml).findall("track") if tr.get("label") in EYES], [])

    def test_plain_session_keeps_the_old_limit_text(self):
        self.serve_plain()
        app = self.make_app()
        self.open_job(app)
        self.draw(app)
        self.srv.fail_import = "file không hợp lệ"
        app.send_cvat()
        self.wait(app)
        self.wait(app)
        shown = G.texts(app._dialogs["send_failed"])
        self.assertIn(gui_cvat.RESTORE_LIMIT, shown)
        self.assertNotIn(gui_cvat.RESTORE_LIMIT_ADOPTED, shown)


if __name__ == "__main__":
    unittest.main()
