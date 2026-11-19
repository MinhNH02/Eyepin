"""Tab Issues nhiều nhóm và lệnh tạo shape trên giao diện (`gui_objects.ObjectsMixin`, `gui.App`; design/2026-11-19-qc-edit-design.md mục 6.3, 6.4).

Job toàn shape 8 frame dựng trên server giả `FakeCvat` (JSON của `test_adopt`, XML của `test_cvatsource`, ảnh giả của `test_tracking`: ảnh frame 0–7
giống hệt nhau nên bám luôn khớp 1,0). Bỏ qua nếu máy không mở được cửa sổ Tk."""
import os
import sys
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin import shortcuts as sc  # noqa: E402
from eyepin.cvatapi import CvatError  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import QC_MSG, RANGE_MSG, SHAPE_ONLY_MSG  # noqa: E402
import test_adopt as A  # noqa: E402
import test_adopt_open as AO  # noqa: E402
import test_gui_cvat as G  # noqa: E402
import test_tracking as T  # noqa: E402
from test_cvatsource import pts, xml_of  # noqa: E402

N = G.N
ALL = tuple(range(N))
FILLED = "Điền tự động, chưa xem mattrai · frame 5–6 (2 frame)"
GAP_56 = "Thiếu nhãn mattrai · frame 5–6 (2 frame)"


def shapes_xml(frames):
    """Bản xuất XML của job: mỗi frame một thẻ <image> chứa skeleton của các mắt có shape ở đó. `frames`: {nhãn: các frame có shape}."""
    images = ""
    for f in range(N):
        skel = "".join(f'<skeleton label="{l}" outside="0">{pts(l)}</skeleton>' for l in EYES if f in frames[l])
        if skel:
            images += f'<image id="{f}" name="frame_{f:06d}.jpg" width="{T.W}" height="{T.H}">{skel}</image>'
    return xml_of(images=images, job_size=N)


def eyes_job(mattrai, matphai):
    """Job 7: mattrai có shape ở các frame `mattrai`, matphai ở các frame `matphai`."""
    shapes = [A.skeleton(l, f, id=200 + 2 * f + (l == "matphai")) for l, frames in (("mattrai", mattrai), ("matphai", matphai)) for f in frames]
    return AO.fake_job(shapes=shapes, xml=shapes_xml({"mattrai": mattrai, "matphai": matphai}))


class QcEditCase(G.CvatGuiCase):
    def open_eyes(self, mattrai=(0, 1, 2, 3, 4, 7), matphai=ALL, extra=()):
        """Mở job 7 toàn shape; mặc định mattrai thiếu frame 5–6, matphai đủ. `extra`: các job khác dựng thêm trên cùng server giả."""
        self.serve(eyes_job(mattrai, matphai), *extra)
        app = self.make_app()
        app.adopt_asked, app.adopt_answer = [], True
        app.ask_restore_adopted = lambda text: True
        s = self.open_job(app)
        self.assertTrue(s.adopted)
        return app

    @staticmethod
    def texts(app):
        """Chữ cột "Vấn đề" của các dòng thật trong bảng Issues (bỏ dòng "Không có frame nào cần chú ý.")."""
        t = app.issue_table
        return [t.item(iid, "values")[2] for iid in t.get_children() if iid.isdigit()]

    @staticmethod
    def kinds(app):
        return [kind for kind, _ in app.issue_rows]

    @staticmethod
    def pick(app, i):
        app.issue_table.selection_set(str(i))


class TestRows(QcEditCase):
    def test_gap_rows_listed_and_jump(self):
        app = self.open_eyes()
        self.assertEqual(self.texts(app), [GAP_56])
        self.assertEqual(self.kinds(app), ["gap"])
        self.assertEqual(app.issues_var.get(), "Items: 1")
        self.assertEqual(app.items, [5])
        self.pick(app, 0)
        app.on_list(None)                                                      # bấm đúp
        self.assertEqual(app.f, 5)

    def test_resolve_on_gap_row_refused(self):
        app = self.open_eyes()
        self.pick(app, 0)
        app.issue_resolve()
        self.assertEqual(app.notice, "Dòng này không bỏ được bằng Đã xử lý.")
        self.assertEqual(self.texts(app), [GAP_56])

    def test_fill_from_menu_updates_rows(self):
        app = self.open_eyes()
        app.go(5)
        app.fill_gap_here()
        self.assertEqual(app.notice, "Đã điền đủ 2 frame.")
        self.assertEqual(self.texts(app), [FILLED])
        self.assertEqual(self.kinds(app), ["auto"])
        self.assertTrue(all(app.s.has_shape("mattrai", f) for f in (5, 6)))
        self.assertEqual(app.items, [5])

    def test_mark_reviewed_from_issue_row(self):
        app = self.open_eyes()
        app.go(5)
        app.fill_gap_here()
        self.pick(app, 0)
        app.issue_resolve()
        self.assertEqual(app.notice, "Đã đánh dấu đã xem 2 shape điền tự động.")
        self.assertEqual(self.texts(app), [])
        self.assertEqual(app.issues_var.get(), "Items: 0")
        self.assertEqual(app.s.unreviewed("mattrai"), [])
        self.assertTrue(all(app.s.has_shape("mattrai", f) for f in (5, 6)))      # chỉ đánh dấu đã xem, shape vẫn còn

    def test_auto_row_splits_runs_and_skips_deleted_frames(self):
        app = self.open_eyes(mattrai=(0, 1, 2, 3, 4))                            # thiếu 5–7
        app.go(5)
        app.fill_gap_here()
        self.assertEqual(self.texts(app), ["Điền tự động, chưa xem mattrai · frame 5–7 (3 frame)"])
        app.s.delete_frame(6)                                                    # frame đã xoá thì không còn trong nhóm "chưa xem"
        app.refresh()
        self.assertEqual(self.texts(app), ["Điền tự động, chưa xem mattrai · frame 5 (1 frame)",
                                           "Điền tự động, chưa xem mattrai · frame 7 (1 frame)"])
        self.pick(app, 1)
        app.issue_resolve()
        self.assertEqual(app.notice, "Đã đánh dấu đã xem 1 shape điền tự động.")
        self.assertEqual(self.texts(app), ["Điền tự động, chưa xem mattrai · frame 5 (1 frame)"])
        self.assertEqual(app.s.unreviewed("mattrai"), [5, 6])                    # frame 6 đã xoá vẫn chưa xem, chỉ không hiện

    def test_gap_row_of_eye_without_any_shape_does_not_jump(self):
        app = self.open_eyes(mattrai=ALL, matphai=())
        self.assertEqual(self.texts(app), ["matphai chưa có nhãn nào"])
        self.assertEqual(app.items, [None])
        app.go(3)
        self.pick(app, 0)
        app.on_list(None)
        self.assertEqual(app.f, 3)
        app.issue_step(1)
        self.assertEqual(app.f, 3)
        self.assertIn("Không còn vấn đề nào", app.notice)

    def test_step_visits_gap_and_auto_rows(self):
        app = self.open_eyes(mattrai=(0, 1, 2, 3, 4, 7), matphai=(0, 1, 2, 3, 4, 5, 6))   # mattrai thiếu 5–6, matphai thiếu 7
        self.assertEqual(self.texts(app), [GAP_56, "Thiếu nhãn matphai · frame 7 (1 frame)"])
        app.go(0)
        app.issue_step(1)
        self.assertEqual(app.f, 5)
        self.assertEqual(app.notice, GAP_56)
        app.issue_step(1)
        self.assertEqual(app.f, 7)
        app.issue_step(-1)
        self.assertEqual(app.f, 5)

    def test_level_of_gap_and_auto_rows_is_yellow_and_filter_ignores_them(self):
        app = self.open_eyes()
        t = app.issue_table
        self.assertIn(str(app._issue_dots["yellow"]), str(t.item("0", "image")))        # chấm vàng
        self.assertIn("Mức: Vàng", app.issue_info[0])
        s = app.s
        self.assertEqual(s.findings, [])
        for f in (4, 5, 6, 7):
            self.assertFalse(s.matches(f, "yellow"), f)                          # bộ lọc "Cảnh báo vàng/đỏ" chỉ tính Finding
            self.assertFalse(s.matches(f, "red"), f)
        self.assertIsNone(s.next_match(0, 1, "yellow"))
        self.assertTrue(s.matches(5, "missing"))                                 # còn bộ lọc riêng "Frame thiếu nhãn"

    def test_selection_survives_frame_change(self):
        app = self.open_eyes()
        self.pick(app, 0)
        with mock.patch.object(app, "_fill_issues", wraps=app._fill_issues) as fill:
            app.go(3)
            app.go(4)
            fill.assert_not_called()                                              # đổi frame không sửa nhãn thì không dựng lại bảng
        self.assertEqual(app.issue_table.selection(), ("0",))
        self.assertEqual(app._issue_selected(), 0)

    def test_rows_rebuilt_when_labels_change_and_back_on_undo(self):
        app = self.open_eyes()
        app.go(5)
        app.copy_nearest_shape()
        self.assertEqual(self.texts(app), ["Thiếu nhãn mattrai · frame 6 (1 frame)"])
        app.undo()
        self.assertEqual(self.texts(app), [GAP_56])

    def test_show_session_rebuilds_rows_and_clears_selection(self):
        app = self.open_eyes()
        self.pick(app, 0)
        app._show_session()
        self.assertEqual(self.texts(app), [GAP_56])                               # dựng lại từ đầu theo phiên hiện tại
        self.assertIsNone(app._issue_selected())


class TestTwoPeople(QcEditCase):
    def open_two(self):
        """Người 1: mattrai thiếu frame 5–6, matphai đủ. Người 2 (thêm bằng tay): mattrai chỉ có frame 0–1, matphai chưa có shape nào."""
        app = self.open_eyes()
        s = app.s
        s.add_layer()
        for f in (0, 1):
            s.pin_eye(f, "mattrai", {i: T.pins_at(f)[i] for i in EYES["mattrai"].pins})
        s.select_layer(0)
        app.refresh()
        return app

    def test_rows_of_other_person_are_prefixed(self):
        app = self.open_two()
        self.assertEqual(self.texts(app), ["người 2 · matphai chưa có nhãn nào", "người 2 · Thiếu nhãn mattrai · frame 2–7 (6 frame)", "người 1 · " + GAP_56])
        self.assertEqual(app.items, [None, 2, 5])

    def test_fill_selected_row_of_other_person_selects_that_person(self):
        app = self.open_two()
        self.pick(app, 1)                                                         # dòng của người 2, đang chọn người 1
        app.go(0)
        app.fill_gap_here()
        self.assertEqual(app.notice, "Đã điền đủ 6 frame.")
        self.assertEqual(app.s.cur, 1)
        self.assertTrue(all(app.s.has_shape("mattrai", f) for f in range(N)))
        self.assertEqual(self.texts(app), ["người 2 · matphai chưa có nhãn nào", "người 1 · " + GAP_56,
                                           "người 2 · Điền tự động, chưa xem mattrai · frame 2–7 (6 frame)"])
        app.s.select_layer(0)                                                     # Đã xử lý của dòng người 2 đánh dấu đúng người 2 dù đang chọn người 1
        self.pick(app, 2)
        app.issue_resolve()
        self.assertEqual(app.notice, "Đã đánh dấu đã xem 6 shape điền tự động.")
        self.assertEqual(self.texts(app), ["người 2 · matphai chưa có nhãn nào", "người 1 · " + GAP_56])
        self.assertEqual(app.s.cur, 1)


class TestCommands(QcEditCase):
    def test_copy_nearest_from_menu(self):
        app = self.open_eyes()
        app.go(5)
        app.copy_nearest_shape()
        self.assertEqual(app.notice, "Đã chép shape mattrai từ frame 4 sang frame 5.")
        self.assertTrue(app.s.has_shape("mattrai", 5))
        self.assertFalse(app.s.has_shape("mattrai", 6))

    def test_fill_outside_gap_notice(self):
        app = self.open_eyes()
        app.go(2)                                                                 # frame có shape của cả hai mắt
        app.fill_gap_here()
        self.assertEqual(app.notice, "Đứng trong một đoạn thiếu nhãn (hoặc chọn dòng Thiếu nhãn) rồi điền.")
        self.assertEqual(self.texts(app), [GAP_56])

    def test_copy_when_both_eyes_present_notice(self):
        app = self.open_eyes()
        app.go(2)
        app.copy_nearest_shape()
        self.assertEqual(app.notice, "Frame này đã có shape của cả hai mắt.")

    def test_copy_picks_the_missing_eye(self):
        app = self.open_eyes(mattrai=ALL, matphai=tuple(f for f in ALL if f != 5))
        app.go(5)
        app.select_eye("mattrai", quiet=True)                                     # thẻ đang chọn là mắt đã có shape ở frame này
        self.assertEqual(app._selected()[0], "mattrai")
        app.copy_nearest_shape()
        self.assertEqual(app.notice, "Đã chép shape matphai từ frame 4 sang frame 5.")
        self.assertTrue(app.s.has_shape("matphai", 5))

    def test_copy_takes_mattrai_when_both_eyes_are_missing(self):
        app = self.open_eyes(mattrai=(0, 1, 2, 3, 4, 6, 7), matphai=(0, 1, 2, 3, 4, 6, 7))
        app.go(5)
        app.s.delete_shape("mattrai", 4)                                          # mattrai thiếu 4–5, matphai thiếu 5: ở frame 5 cả hai cùng thiếu
        app.copy_nearest_shape()
        self.assertEqual(app.notice, "Đã chép shape mattrai từ frame 6 sang frame 5.")
        self.assertFalse(app.s.has_shape("matphai", 5))

    def test_fill_uses_selected_gap_row_over_current_frame(self):
        app = self.open_eyes(mattrai=(0, 1, 2, 3, 4, 7), matphai=(0, 1, 2, 3, 4, 5, 6))
        self.pick(app, 1)                                                         # dòng "Thiếu nhãn matphai · frame 7"
        app.go(0)
        app.fill_gap_here()
        self.assertEqual(app.notice, "Đã điền đủ 1 frame.")
        self.assertTrue(app.s.has_shape("matphai", 7))
        self.assertFalse(app.s.has_shape("mattrai", 5))

    def test_fill_on_row_of_eye_without_shape_says_why(self):
        app = self.open_eyes(mattrai=ALL, matphai=())
        self.pick(app, 0)
        app.fill_gap_here()
        self.assertEqual(app.notice, "matphai chưa có nhãn nào: vẽ một shape của mắt đó trước rồi mới điền được.")

    def test_fill_stops_on_bad_match_and_says_where(self):
        app = self.open_eyes(mattrai=(0, 1, 2, 3, 4), matphai=ALL)                # thiếu 5–7
        app.go(5)
        real = app.s.gray
        app.s.gray = lambda f: np.zeros_like(real(f)) if f == 6 else real(f)      # frame 6 bị che hẳn
        app.fill_gap_here()
        self.assertRegex(app.notice, r"^Đã tạo 1 shape \(frame 5\); dừng ở frame 6 vì khớp kém \(-?\d\.\d\d\)\.$")
        self.assertTrue(app.s.has_shape("mattrai", 5))
        self.assertFalse(app.s.has_shape("mattrai", 6))
        self.assertEqual(self.texts(app), ["Thiếu nhãn mattrai · frame 6–7 (2 frame)", "Điền tự động, chưa xem mattrai · frame 5 (1 frame)"])

    def test_fill_creating_nothing_says_so(self):
        app = self.open_eyes(mattrai=(0, 1, 2, 3, 4), matphai=ALL)
        app.go(5)
        real = app.s.gray
        app.s.gray = lambda f: np.zeros_like(real(f)) if f == 5 else real(f)
        depth = len(app.s._undo)
        app.fill_gap_here()
        self.assertRegex(app.notice, r"^Không tạo được shape nào: khớp kém ở frame 5 \(-?\d\.\d\d\)\.$")
        self.assertEqual(len(app.s._undo), depth)
        self.assertEqual(self.texts(app), ["Thiếu nhãn mattrai · frame 5–7 (3 frame)"])

    def test_fill_read_error_notice(self):
        app = self.open_eyes()
        app.go(5)
        with mock.patch.object(app.s, "gray", side_effect=CvatError("mất kết nối.")):
            app.fill_gap_here()
        self.assertTrue(app.notice.startswith("Không điền được:"), app.notice)
        self.assertEqual(app.notice, "Không điền được: mất kết nối. Chưa tạo shape nào.")
        self.assertFalse(app.s.has_shape("mattrai", 5))
        self.assertEqual(self.texts(app), [GAP_56])

    def test_fill_recompute_error_after_write_is_reported_as_written(self):
        app = self.open_eyes()
        app.go(5)

        def failing_recompute():
            app.s.stale = True
            raise CvatError("mất kết nối.")

        with mock.patch.object(app.s, "recompute", side_effect=failing_recompute):
            app.fill_gap_here()
        self.assertIn("Thao tác đã được ghi", app.notice)                         # shape đã ghi: không được nói "Chưa tạo shape nào"
        self.assertNotIn("Chưa tạo shape nào", app.notice)

    def test_copy_refuses_deleted_frame(self):
        app = self.open_eyes()
        app.s.delete_frame(5)
        app.go(5)
        app.copy_nearest_shape()
        self.assertEqual(app.notice, "Frame này đã bị xoá.")
        self.assertFalse(app.s.has_shape("mattrai", 5))

    def test_fill_refuses_deleted_frame(self):
        app = self.open_eyes()
        app.s.delete_frame(5)
        app.go(5)
        app.fill_gap_here()
        self.assertEqual(app.notice, "Frame này đã bị xoá.")
        self.assertFalse(app.s.has_shape("mattrai", 6))

    def test_commands_on_plain_job_say_shapes_only(self):
        self.serve()                                                              # job trống: phiên thường, mắt chưa có kiểu shape
        app = self.make_app()
        self.open_job(app)
        for command in (app.copy_nearest_shape, app.fill_gap_here):
            command()
            self.assertEqual(app.notice, SHAPE_ONLY_MSG)

    def test_actions_registered(self):
        app = self.open_eyes()
        for aid in ("copy_nearest_shape", "fill_gap"):
            self.assertIn(aid, sc.BY_ID)
            self.assertEqual(sc.BY_ID[aid].keys, ())
            self.assertEqual(sc.BY_ID[aid].group, sc.G_OBJ)
            self.assertIn(aid, app.handlers)

    def test_menu_has_the_two_commands_after_scan(self):
        app = self.open_eyes()
        menu = app._menu
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
        i = next(n for n, l in enumerate(labels) if l.startswith("Quét nhãn có sẵn"))
        self.assertEqual(labels[i + 1:i + 3], ["Chép shape gần nhất vào frame này", "Điền đoạn thiếu nhãn"])


class TestOccludedRange(QcEditCase):
    @staticmethod
    def values(app):
        """(người, mắt, điểm, từ frame, tới frame) trong hộp "Occluded cho cả đoạn" đang mở."""
        ui = app._occl_ui
        return tuple(ui[k].get() for k in ("layer", "label", "point", "first", "last"))

    def test_defaults_from_current_run(self):
        app = self.open_eyes()                                                   # mattrai có shape 0–4 và 7, matphai 0–7
        app.go(3)
        app.show_occluded_range()
        self.assertIn("occluded_range", app._dialogs)
        self.assertEqual(self.values(app), ("Người 1", "mattrai", "Cả mắt", "3", "4"))        # tới cuối đoạn 0–4 chứa frame 3
        self.assertEqual(app._occl_ui["status"].get(), "")
        app.select_eye("matphai", quiet=True)
        app.go(2)
        app.show_occluded_range()                                                 # mở lại: dựng lại theo frame và mắt hiện tại
        self.assertEqual(self.values(app), ("Người 1", "matphai", "Cả mắt", "2", "7"))

    def test_defaults_when_frame_has_no_shape(self):
        app = self.open_eyes()
        app.go(5)                                                                 # mattrai không có shape ở frame 5
        app.show_occluded_range()
        self.assertEqual(self.values(app), ("Người 1", "mattrai", "Cả mắt", "5", "5"))

    def test_changing_eye_resets_point_and_range(self):
        app = self.open_eyes()
        app.go(3)
        app.show_occluded_range()
        ui = app._occl_ui
        ui["point"].set("14")
        ui["label"].set("matphai")
        app._occluded_range_changed()                                             # như chọn trong ô Mắt
        self.assertEqual(self.values(app), ("Người 1", "matphai", "Cả mắt", "3", "7"))
        box = next(w for w in app._dialogs["occluded_range"].winfo_children() if str(w.cget("textvariable")) == str(ui["point"]))
        box.tk.call(box.cget("postcommand"))                                      # như mở danh sách điểm: chỉ điểm của mắt đang chọn
        self.assertEqual(tuple(str(v) for v in box.cget("values")), ("Cả mắt",) + tuple(str(i) for i in EYES["matphai"].ids))

    def test_apply_sets_and_reports(self):
        app = self.open_eyes()
        app.go(1)
        app.show_occluded_range()
        ui = app._occl_ui
        ui["point"].set("14")
        depth = len(app.s._undo)
        app.occluded_range_apply(True)
        want = "Đã đặt Occluded cho điểm 14 ở 4 shape (frame 1–4)."
        self.assertEqual(app.notice, want)
        self.assertEqual(ui["status"].get(), want)
        s = app.s
        self.assertEqual([s.flags_at(f).get(14) for f in range(N)], [None, "occluded", "occluded", "occluded", "occluded", None, None, None])
        self.assertEqual(s.flags_at(2).get(16), None)                              # chỉ điểm 14
        self.assertEqual(len(s._undo), depth + 1)                                  # một bước hoàn tác cho cả đoạn
        app.undo()
        self.assertTrue(all(s.flags_at(f).get(14) is None for f in range(N)))

    def test_apply_whole_eye_and_clear(self):
        app = self.open_eyes()
        app.go(0)
        app.show_occluded_range()
        app.occluded_range_apply(True)
        self.assertEqual(app.notice, "Đã đặt Occluded cho cả mắt ở 5 shape (frame 0–4).")
        self.assertTrue(all(app.s.flags_at(3).get(i) == "occluded" for i in EYES["mattrai"].ids))
        self.assertIsNone(app.s.flags_at(3).get(22))                               # mắt kia không đổi
        app._occl_ui["first"].set("2")
        app.occluded_range_apply(False)
        self.assertEqual(app.notice, "Đã bỏ Occluded cho cả mắt ở 3 shape (frame 2–4).")
        self.assertEqual([app.s.flags_at(f).get(14) for f in range(5)], ["occluded", "occluded", None, None, None])

    def test_clear_and_outside_skip(self):
        app = self.open_eyes()
        s = app.s
        s.toggle_flag(2, 14, "outside")                                            # điểm 14 ở frame 2 đang Outside
        app.go(0)
        app.show_occluded_range()
        app._occl_ui["point"].set("14")
        app.occluded_range_apply(True)
        self.assertEqual(app.notice, "Đã đặt Occluded cho điểm 14 ở 4 shape (frame 0–4); bỏ qua 1 điểm đang Outside.")
        self.assertEqual(s.flags_at(2), {14: "outside"})
        app.occluded_range_apply(False)
        self.assertEqual(app.notice, "Đã bỏ Occluded cho điểm 14 ở 4 shape (frame 0–4); bỏ qua 1 điểm đang Outside.")
        self.assertEqual(s.flags_at(2), {14: "outside"})

    def test_bad_input(self):
        app = self.open_eyes()
        app.go(0)
        app.show_occluded_range()
        ui = app._occl_ui
        depth, notice = len(app.s._undo), app.notice
        ui["first"].set("x")
        app.occluded_range_apply(True)
        self.assertEqual(ui["status"].get(), "Từ frame và Tới frame phải là số nguyên.")
        self.assertEqual(len(app.s._undo), depth)
        self.assertEqual(app.s.flags_at(0), {})
        ui["first"].set("4")
        ui["last"].set("1")                                                        # từ > tới: Session từ chối
        app.occluded_range_apply(True)
        self.assertEqual(ui["status"].get(), RANGE_MSG)
        self.assertEqual(len(app.s._undo), depth)
        ui["first"].set("0")
        ui["last"].set("99")                                                       # ngoài phạm vi
        app.occluded_range_apply(True)
        self.assertEqual(ui["status"].get(), f"frame ngoài phạm vi 0–{N - 1}")
        self.assertEqual(len(app.s._undo), depth)
        self.assertEqual(app.s.flags_at(0), {})

    def test_other_person_is_chosen_in_the_box(self):
        app = self.open_eyes()
        s = app.s
        s.add_layer()
        for f in (0, 1, 2):
            s.pin_eye(f, "mattrai", {i: T.pins_at(f)[i] for i in EYES["mattrai"].pins})
        s.select_layer(0)
        app.refresh()
        app.go(0)
        app.show_occluded_range()
        ui = app._occl_ui
        self.assertEqual(ui["layer"].get(), "Người 1")
        ui["layer"].set("Người 2")
        app._occluded_range_changed()
        self.assertEqual(self.values(app), ("Người 2", "mattrai", "Cả mắt", "0", "2"))
        app.occluded_range_apply(True)
        self.assertEqual(app.notice, "Đã đặt Occluded cho cả mắt ở 3 shape (frame 0–2).")
        self.assertEqual(s.cur, 1)
        self.assertEqual(s.flags_at(1).get(14), "occluded")
        s.select_layer(0)
        self.assertIsNone(s.flags_at(1).get(14))                                   # người 1 không đổi

    def test_error_keeps_the_selected_person(self):
        app = self.open_eyes()
        s = app.s
        s.add_layer()
        for f in (0, 1, 2):
            s.pin_eye(f, "mattrai", {i: T.pins_at(f)[i] for i in EYES["mattrai"].pins})
        s.select_layer(0)
        app.refresh()
        app.go(0)
        app.show_occluded_range()
        ui = app._occl_ui
        ui["layer"].set("Người 2")
        app._occluded_range_changed()
        depth, flags = len(s._undo), {f: dict(v) for f, v in s.flags.items()}
        for first, last, want in (("4", "1", RANGE_MSG), ("0", "99", f"frame ngoài phạm vi 0–{N - 1}")):
            ui["first"].set(first)
            ui["last"].set(last)
            app.occluded_range_apply(True)
            self.assertEqual(ui["status"].get(), want)
            self.assertEqual(s.cur, 0)                                             # lỗi: người đang chọn không đổi
            self.assertEqual(len(s._undo), depth)
            self.assertEqual({f: dict(v) for f, v in s.flags.items()}, flags)
        s.layers.pop()                                                             # hộp còn mở mà người 2 không còn
        app.occluded_range_apply(True)
        self.assertEqual(ui["status"].get(), "Không có người này trong job đang mở.")
        self.assertEqual((s.cur, len(s._undo)), (0, depth))

    def test_menu_and_action(self):
        app = self.open_eyes()
        top = app._menu
        labels = [top.entrycget(i, "label") for i in range(top.index("end") + 1) if top.type(i) == "command"]
        i = next(n for n, l in enumerate(labels) if l.startswith("Chép shape gần nhất"))
        self.assertEqual(labels[i + 1:i + 3], ["Điền đoạn thiếu nhãn", "Occluded cho cả đoạn…"])
        card = app.obj_menu
        self.assertIn("Occluded cho cả đoạn…", [card.entrycget(i, "label") for i in range(card.index("end") + 1) if card.type(i) == "command"])
        self.assertIn("occluded_range", sc.BY_ID)
        self.assertEqual(sc.BY_ID["occluded_range"].keys, ())
        self.assertEqual(sc.BY_ID["occluded_range"].group, sc.G_OBJ)
        self.assertIn("occluded_range", app.handlers)

    def test_action_handler_opens_the_box(self):
        app = self.open_eyes()
        app.handlers["occluded_range"](None)
        self.assertIn("occluded_range", app._dialogs)

    def test_blocked_in_qc(self):
        self.serve(self.qc_job())
        app = self.make_app()
        s = self.open_job(app)
        self.assertTrue(s.qc)
        app.notice = ""
        app.show_occluded_range()
        self.assertEqual(app.notice, QC_MSG)
        self.assertNotIn("occluded_range", app._dialogs)

    def test_apply_blocked_in_qc_and_while_busy(self):
        app = self.open_eyes()
        app.go(0)
        app.show_occluded_range()
        depth = len(app.s._undo)
        app.busy = "Đang gửi lên CVAT."
        app.occluded_range_apply(True)
        self.assertEqual(app.notice, "Đang gửi lên CVAT. Chờ xong rồi mới sửa nhãn được.")
        self.assertEqual(len(app.s._undo), depth)
        app.busy = None
        app.s.qc = True                                                            # phiên chuyển sang QC khi hộp còn mở
        app.occluded_range_apply(True)
        self.assertEqual(app.notice, QC_MSG)
        self.assertEqual(len(app.s._undo), depth)

    def test_plain_job_says_shapes_only(self):
        self.serve()                                                               # job trống: mắt chưa có kiểu shape
        app = self.make_app()
        self.open_job(app)
        app.show_occluded_range()
        self.assertEqual(app.notice, SHAPE_ONLY_MSG)
        self.assertNotIn("occluded_range", app._dialogs)

    def test_box_closed_when_session_replaced(self):
        app = self.open_eyes(extra=[self.empty_job(8)])
        app.show_occluded_range()
        box = app._dialogs["occluded_range"]
        self.assertTrue(box.winfo_exists())
        self.assertTrue(app._occl_ui)
        self.open_job(app, 8)                                                      # mở job khác: phiên cũ bị thay
        self.assertFalse(box.winfo_exists())
        self.assertNotIn("occluded_range", app._dialogs)
        self.assertEqual(app._occl_ui, {})

    def test_stale_person_choice_does_not_raise(self):
        app = self.open_eyes()
        s = app.s
        s.add_layer()
        s.select_layer(0)
        app.go(0)
        app.show_occluded_range()
        ui = app._occl_ui
        ui["layer"].set("Người 2")
        s.layers.pop()                                                             # người 2 không còn mà hộp còn mở
        s.select_layer(0)
        ui["label"].set("matphai")
        app._occluded_range_changed()                                              # như chọn mắt khác trong hộp: không được ném lỗi
        self.assertEqual(ui["status"].get(), "Không có người này trong job đang mở.")
        self.assertEqual(s.cur, 0)

    def test_logout_teardown_closes_the_box(self):
        app = self.open_eyes()
        app.show_occluded_range()
        box = app._dialogs["occluded_range"]
        self.assertTrue(box.winfo_exists())
        app.teardown()                                                             # đăng xuất: gỡ App khỏi root, huỷ mọi hộp
        self.assertFalse(box.winfo_exists())


if __name__ == "__main__":
    unittest.main()
