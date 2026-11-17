#!/usr/bin/env python3
"""SPIKE (dùng một lần, 2026-11-17). Đo chất lượng nội suy giữa hai frame ghim bằng chỉ số vùng (IoU chính; Dice, Boundary IoU,
Precision/Recall) trên case 01, làm căn cứ cho design/2026-11-17-interp-iou-research.md.

  python spike\\interp_iou_spike.py

(A) Trần IoU do nhiễu của chính điểm ghim: so mắt ghim với chính nó khi dời 1–2 px, hoặc khi hai người ghim cùng một mắt lệch ±2 px.
(B) Bảy cách đoán tại frame ghim bị giấu (cách đo như spike/headturn_spike.py: ghim mỗi `step` frame, kiểm ở các ghim còn lại).

Đọc điểm ghim thô `spike/out/pins_case01_ai.json` (AI đọc, ±2 px, KHÔNG phải nhãn chuẩn) và ảnh công khai PhysDrive. Không sửa gì
trong gói eyepin, không ghi nhãn. Ảnh chỉ đọc vào RAM.
"""
import json
import math
import os
import random
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from eyepin import overlap                         # noqa: E402
from eyepin.geometry import EYES, derive          # noqa: E402
from eyepin.scan import EAR_CLOSED, eye_ear       # noqa: E402
from eyepin.session import Session                # noqa: E402
from eyepin.tracking import track_forward         # noqa: E402

CASE01 = r"C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che"
TAU = 0.85


def load(path):
    raw = json.load(open(path, encoding="utf-8"))
    pins = {int(f): {int(i): tuple(p) for i, p in d.items()} for f, d in raw.items() if not f.startswith("_")}
    return pins, set(raw.get("_far_hidden", []))


def eight(four, spec):
    return derive(spec, {i: four[i] for i in spec.pins})


def centroid(p, spec):
    return (sum(p[i][0] for i in spec.ids) / 8, sum(p[i][1] for i in spec.ids) / 8)


def lerp(pa, pb, w, ids):
    return {i: (pa[i][0] + w * (pb[i][0] - pa[i][0]), pa[i][1] + w * (pb[i][1] - pa[i][1])) for i in ids}


def with_shape(pos, pa, pb, w, spec):
    """Giữ vị trí (tâm) của `pos`, thay dáng mắt bằng dáng nội suy thẳng giữa ghim a và ghim b."""
    c, ca, cb = centroid(pos, spec), centroid(pa, spec), centroid(pb, spec)
    return {i: (c[0] + (1 - w) * (pa[i][0] - ca[0]) + w * (pb[i][0] - cb[0]),
                c[1] + (1 - w) * (pa[i][1] - ca[1]) + w * (pb[i][1] - cb[1])) for i in spec.ids}


def pin_err(pred, truth, spec):
    return st.fmean(math.dist(pred[i], truth[i]) for i in spec.pins)


def noise_floor(gt):
    """(A) IoU của một mắt ghim với chính nó khi dời đều, và giữa hai lần ghim độc lập lệch ngẫu nhiên tới 2 px mỗi điểm ghim."""
    rnd = random.Random(1)
    rows = {k: [] for k in ("dời ngang 1 px", "dời dọc 1 px", "dời ngang 2 px", "dời dọc 2 px",
                            "hai lần ghim, mỗi điểm lệch ≤1 px", "hai lần ghim, mỗi điểm lệch ≤2 px")}
    heights = []
    for f, four in gt.items():
        for spec in EYES.values():
            truth = eight(four, spec)
            if (eye_ear(spec, truth) or 0) < EAR_CLOSED:
                continue
            heights.append(math.dist(truth[spec.up], truth[spec.lo]))
            for name, (dx, dy) in (("dời ngang 1 px", (1, 0)), ("dời dọc 1 px", (0, 1)), ("dời ngang 2 px", (2, 0)), ("dời dọc 2 px", (0, 2))):
                rows[name].append(overlap.compare(spec, {i: (x + dx, y + dy) for i, (x, y) in truth.items()}, truth))
            for r, name in ((1.0, "hai lần ghim, mỗi điểm lệch ≤1 px"), (2.0, "hai lần ghim, mỗi điểm lệch ≤2 px")):
                for _ in range(20):
                    def jitter():
                        out = {}
                        for i in spec.pins:
                            a, d = rnd.uniform(0, 2 * math.pi), r * math.sqrt(rnd.random())   # đều trong hình tròn bán kính r
                            out[i] = (four[i][0] + d * math.cos(a), four[i][1] + d * math.sin(a))
                        return eight(out, spec)
                    rows[name].append(overlap.compare(spec, jitter(), jitter()))
    widths = [math.dist(eight(four, s)[s.first], eight(four, s)[s.last]) for four in gt.values() for s in EYES.values()]
    print(f"(A) Trần IoU do nhiễu điểm ghim (mắt mở của case 01: rộng {min(widths):.0f}–{max(widths):.0f} px, "
          f"cao giữa mí {min(heights):.0f}–{max(heights):.0f} px)")
    for name, rs in rows.items():
        print(f"    {name:34s} IoU tb {st.fmean(r.iou for r in rs):.3f} (thấp nhất {min(r.iou for r in rs):.3f})  "
              f"Dice {st.fmean(r.dice for r in rs):.3f}  Boundary IoU {st.fmean(r.boundary_iou for r in rs):.3f}")


VARIANTS = False                # True: thêm (C) các biến thể của luật chọn hai chiều


def methods_at(s, gt, a, b, g, w):
    """Mỗi cách đoán: {tên: {mắt: 8 điểm}} tại frame g, chỉ dùng ghim a và b."""
    fwd = s.labels[g]
    path = track_forward(lambda k: s.gray(b - k), 0, b - g + 1, {**eight(gt[b], EYES["mattrai"]), **eight(gt[b], EYES["matphai"])})
    back = path[-1]
    out = {}
    for label, spec in EYES.items():
        pa, pb = eight(gt[a], spec), eight(gt[b], spec)
        f_pts = {i: fwd.points[i] for i in spec.ids}
        b_pts = {i: back.points[i] for i in spec.ids}
        mix = lerp(f_pts, b_pts, w, spec.ids)
        cf, cb = fwd.scores[label], back.scores[label]
        pick = f_pts if cf >= TAU > cb else b_pts if cb >= TAU > cf else mix
        out[label] = {
            "1 đường thẳng CVAT": lerp(pa, pb, w, spec.ids),
            "2 bám tiến (tool hiện tại)": f_pts,
            "3 bám lùi": b_pts,
            "4 hai chiều, trộn theo thời gian": mix,
            "5 hai chiều, chọn theo độ khớp": pick,
            "6 bám tiến + dáng nội suy": with_shape(f_pts, pa, pb, w, spec),
            "7 hai chiều chọn + dáng nội suy": with_shape(pick, pa, pb, w, spec),
        }
        if VARIANTS:
            best = f_pts if cf >= cb else b_pts
            mf = min(s.labels[f].scores[label] for f in range(a, g + 1))           # độ khớp thấp nhất trên cả đường đi, không chỉ tại g
            mb = min(r.scores[label] for r in path)
            out[label].update({
                "8 luôn lấy phía khớp hơn": best,
                "9 cả hai đủ khớp thì trộn, còn lại lấy phía khớp hơn": mix if min(cf, cb) >= TAU else best,
                "10 như 5, độ khớp thấp nhất trên đường đi": f_pts if mf >= TAU > mb else b_pts if mb >= TAU > mf else mix,
                "11 như 9, độ khớp thấp nhất trên đường đi": mix if min(mf, mb) >= TAU else (f_pts if mf >= mb else b_pts),
            })
    return out


def compare_methods(gt, far_hidden, step):
    frames = sorted(gt)
    train = sorted(set(range(0, 210, step)) & set(frames) | {frames[-1]})
    s = Session(CASE01)
    for f in train:
        for label, spec in EYES.items():
            s.add_pin(f, label, {i: gt[f][i] for i in spec.pins})
    rows = []
    for g in [f for f in frames if f not in train]:
        a, b = max(f for f in train if f < g), min(f for f in train if f > g)
        w = (g - a) / (b - a)
        for label, preds in methods_at(s, gt, a, b, g, w).items():
            spec = EYES[label]
            truth = eight(gt[g], spec)
            closed = (eye_ear(spec, truth) or 0) < EAR_CLOSED
            rows.append({"g": g, "label": label, "turn": g in far_hidden, "closed": closed,
                         "width": math.dist(truth[spec.first], truth[spec.last]),
                         "m": {k: (overlap.compare(spec, p, truth), pin_err(p, truth, spec)) for k, p in preds.items()}})
    return train, rows


def table(rows, title):
    print(f"    {title}: {len(rows)} mẫu")
    if not rows:
        return
    for k in rows[0]["m"]:
        ov = [r["m"][k][0] for r in rows]
        ious = sorted(o.iou for o in ov)
        n = len(ious)
        px = [r["m"][k][1] for r in rows]
        p10 = ious[max(0, math.ceil(0.1 * n) - 1)]
        print(f"      {k:34s} IoU tb {st.fmean(ious):.2f} trung vị {st.median(ious):.2f} p10 {p10:.2f} "
              f"≥0,5 {sum(i >= 0.5 for i in ious):2d}/{n} ≥0,75 {sum(i >= 0.75 for i in ious):2d}/{n} | "
              f"Dice {st.fmean(o.dice for o in ov):.2f} BIoU {st.fmean(o.boundary_iou for o in ov):.2f} "
              f"P {st.fmean(o.precision for o in ov):.2f} R {st.fmean(o.recall for o in ov):.2f} | sai số {st.fmean(px):5.1f} px")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    gt, far_hidden = load(os.path.join(HERE, "out", "pins_case01_ai.json"))
    print(f"Frame ghim thô: {sorted(gt)}")
    noise_floor(gt)
    print("(B) Bảy cách đoán tại frame ghim bị giấu (frame kiểm nằm giữa hai ghim, chỗ xấu nhất)")
    for step in (20, 30):
        train, rows = compare_methods(gt, far_hidden, step)
        print(f"  ghim mỗi {step} frame ({len(train)} ghim: {train})")
        open_rows = [r for r in rows if not r["closed"]]
        table(open_rows, "mắt mở, mọi frame")
        table([r for r in open_rows if r["turn"]], "mắt mở, frame quay đầu (_far_hidden)")
        table([r for r in open_rows if not r["turn"]], "mắt mở, frame không quay đầu")
        table([r for r in rows if r["closed"]], "mắt nhắm (EAR < EAR_CLOSED)")
        worst = sorted(open_rows, key=lambda r: r["m"]["2 bám tiến (tool hiện tại)"][0].iou)[:4]
        print("    mẫu tệ nhất của bám tiến: " + "; ".join(
            f"frame {r['g']} {r['label']}: IoU tiến {r['m']['2 bám tiến (tool hiện tại)'][0].iou:.2f}, "
            f"hai chiều chọn {r['m']['5 hai chiều, chọn theo độ khớp'][0].iou:.2f}, "
            f"+dáng {r['m']['7 hai chiều chọn + dáng nội suy'][0].iou:.2f}" for r in worst))


if __name__ == "__main__":
    main()
