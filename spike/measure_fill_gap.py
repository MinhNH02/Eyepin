"""SPIKE (đo một lần, kế hoạch "Sửa job prelabel" Task 5; design/2026-11-19-qc-edit-design.md mục 6.4.3): điền đoạn thiếu nhãn bằng bám tiến
(`Session.fill_gap`) tốt tới đâu trên dữ liệu thử.

Dữ liệu (DỮ LIỆU THỬ, công khai, nằm ngoài kho mã, KHÔNG sao chép vào đâu, chỉ đọc):
- ảnh: case 01 PhysDrive (210 ảnh; prelabel và reference chỉ có 200 frame đầu nên frame 200–209 được đánh dấu đã xoá);
- `prelabel.xml`: prelabel GIẢ LẬP có lỗi cấy (rung, mất nhãn mắt xa ở 20 frame, nhãn sai, đổi bên...), nạp bằng `adopt.shapes_from_ann`;
- `reference.xml`: đáp án tạm (không phải nhãn người gán), dùng để so IoU vùng mắt (`overlap.compare`).

Với mỗi đoạn thiếu của `gaps.find_gaps` gọi `Session.fill_gap`; mỗi frame tạo được thì so với `reference.xml`. Frame mà `reference.xml` không có mắt
đó (hay hai vùng đều rỗng) bị bỏ khỏi IoU và được đếm riêng.

Chạy:  python spike\\measure_fill_gap.py     (vài giây; chỉ in số liệu, không ghi file nào)
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from eyepin import adopt, cvatxml, gaps, overlap          # noqa: E402
from eyepin.geometry import EYES                           # noqa: E402
from eyepin.session import FILL_NO_SOURCE_MSG, Session     # noqa: E402

CASE = r"C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che"
PRELABEL = r"C:\Users\minhf\Downloads\dms_build\prelabel_sample\prelabel.xml"
REFERENCE = r"C:\Users\minhf\Downloads\dms_build\prelabel_sample\reference.xml"
LABELLED = 200                       # prelabel và reference chỉ có 200 frame đầu


def mean(values: list[float]) -> str:
    return f"{sum(values) / len(values):.3f}" if values else "-"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    prelabel, reference = cvatxml.parse(PRELABEL), cvatxml.parse(REFERENCE)
    s = Session(CASE)
    s.deleted.update(range(LABELLED, s.n_frames))
    for f in range(LABELLED):
        if prelabel.frame_names.get(f) != s.names[f]:
            raise SystemExit(f"Tên ảnh của frame {f} không khớp prelabel.xml: {prelabel.frame_names.get(f)} và {s.names[f]}")
    shapes = adopt.shapes_from_ann(prelabel)
    s.adopt(shapes)
    todo = gaps.find_gaps(s)
    print(f"Ảnh: {s.n_frames} frame, đã xoá {len(s.deleted)} (frame {LABELLED}–{s.n_frames - 1}). Shape nạp từ prelabel: {len(shapes)}.")
    print(f"Đoạn thiếu: {len([g for g in todo if g.first >= 0])}, tổng {sum(g.count for g in todo)} frame thiếu.")
    for g in todo:
        if g.first < 0:
            print(f"  (bỏ qua) {g.label} chưa có nhãn nào")

    total = made = n_gaps = 0
    ious: list[float] = []
    worst = (2.0, "", -1)
    no_reference = no_area = 0
    began = time.perf_counter()
    for g in todo:
        if g.first < 0:
            continue
        n_gaps += 1
        total += g.count
        t0 = time.perf_counter()
        try:
            res = s.fill_gap(g.label, g.first, g.last)
        except ValueError as err:
            note = "không có nguồn ngay trước đoạn" if str(err) == FILL_NO_SOURCE_MSG else str(err)
            print(f"{g.label} frame {g.first}–{g.last} ({g.count} frame): {note}")
            continue
        seconds = time.perf_counter() - t0
        made += len(res.created)
        here: list[float] = []
        for f in res.created:
            key = reference.shapes[g.label].get(f)
            if key is None:
                no_reference += 1
                continue
            got = overlap.compare(EYES[g.label], {i: s.pins[f][i] for i in EYES[g.label].ids}, {i: key.points[i].xy for i in EYES[g.label].ids})
            if got is None:
                no_area += 1
                continue
            here.append(got.iou)
            if got.iou < worst[0]:
                worst = (got.iou, g.label, f)
        ious += here
        stop = f"; dừng ở frame {res.stopped_at} (khớp {res.score:.3f})" if res.stopped_at is not None else ""
        low = f", thấp nhất {min(here):.3f}" if here else ""
        print(f"{g.label} frame {g.first}–{g.last}: tạo {len(res.created)}/{g.count}{stop}; IoU trung bình {mean(here)}{low}; {seconds:.2f} s")
    elapsed = time.perf_counter() - began

    pct = 100 * made / total if total else 0.0
    low = f", thấp nhất {worst[0]:.3f} ({worst[1]} frame {worst[2]})" if ious else ""
    print(f"Tổng: {n_gaps} đoạn, điền được {made}/{total} frame thiếu ({pct:.0f}%); IoU trung bình {mean(ious)}{low} trên {len(ious)} frame; "
          f"bỏ khỏi IoU {no_reference + no_area} frame (reference không có mắt đó: {no_reference}, hai vùng rỗng: {no_area}); {elapsed:.1f} s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
