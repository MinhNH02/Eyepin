#!/usr/bin/env python3
"""SPIKE (dùng một lần, 2026-11-16). Đo trên case 01 để làm căn cứ cho design/2026-11-15-headturn-mvp-design.md.

  python spike\\headturn_spike.py

Đọc điểm ghim thô `spike/out/pins_case01_ai.json` (AI đọc trên ảnh phóng to, ±2 px, KHÔNG phải nhãn chuẩn) và ảnh công khai
PhysDrive ở Downloads\\dms_build. In ra: (1) chỉ số quay đầu tại từng frame ghim, (2) đoạn quay đầu phát hiện được khi ghim
thưa dần và trên đoạn mặt thẳng đối chứng, (3) sai số tại frame ghim bị giấu của sáu cách dự đoán.
Không sửa gì trong gói eyepin. Ảnh chỉ đọc vào RAM.
"""
import json
import math
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from eyepin.geometry import EYES, derive          # noqa: E402
from eyepin.session import Session                # noqa: E402
from eyepin.tracking import track_forward         # noqa: E402

CASE01 = r"C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che"
FRONTAL = r"C:\Users\minhf\Downloads\dms_build\physdrive_seg"
TAU = 0.85                      # độ khớp tối thiểu để tin một frame do tool bám (bằng MATCH_FLAG của session)
ENTER, LEAVE, MIN_LEN = 0.86, 0.90, 5
L, R = EYES["mattrai"], EYES["matphai"]


def load(path):
    raw = json.load(open(path, encoding="utf-8"))
    pins = {int(f): {int(i): tuple(p) for i, p in d.items()} for f, d in raw.items() if not f.startswith("_")}
    return pins, set(raw.get("_far_hidden", []))


def build(frames_dir, gt, train):
    s = Session(frames_dir)
    for f in train:
        for label, sp in EYES.items():
            s.add_pin(f, label, {i: gt[f][i] for i in sp.pins})
    return s


def eight(gt, f):
    out = {}
    for sp in EYES.values():
        out.update(derive(sp, {i: gt[f][i] for i in sp.pins}))
    return out


def centre(p, sp, ids=None):
    ids = ids or sp.ids
    return tuple(sum(p[i][k] for i in ids) / len(ids) for k in (0, 1))


def detect(s):
    """Đoạn quay đầu: khoảng cách hai mắt / mốc <= ENTER thì vào, >= LEAVE thì ra; chỉ xét frame ghim và frame cả hai mắt khớp >= TAU."""
    d = {f: math.dist(centre(s.labels[f].points, L), centre(s.labels[f].points, R)) for f in s.labels}
    at_pins = sorted(d[f] for f in s.pins)
    ref = at_pins[min(len(at_pins) - 1, int(0.9 * len(at_pins)))]
    trusted = {f for f in s.labels if f in s.pins or min(s.labels[f].scores.values()) >= TAU}
    segs, state, start, low, unsure = [], False, None, 1.0, 0
    for f in sorted(s.labels):
        if f in trusted:
            r = d[f] / ref
            if not state and r <= ENTER:
                state, start, low, unsure = True, f, r, 0
            elif state and r >= LEAVE:
                if f - start >= MIN_LEN:
                    segs.append((start, f - 1, low, unsure))
                state = False
            elif state:
                low = min(low, r)
        elif state:
            unsure += 1
    if state and max(s.labels) - start + 1 >= MIN_LEN:
        segs.append((start, max(s.labels), low, unsure))
    return ref, segs, len(s.labels) - len(trusted)


def compare(frames_dir, gt, far_hidden, train):
    """Sai số trung bình trên 4 điểm ghim của từng mắt tại các frame ghim không nằm trong `train`."""
    s = build(frames_dir, gt, train)
    rows = []
    for g in [f for f in sorted(gt) if f not in train]:
        a, b = max(f for f in train if f < g), min(f for f in train if f > g)
        w = (g - a) / (b - a)
        pa, pb = eight(gt, a), eight(gt, b)
        fwd = s.labels[g]
        back = track_forward(lambda k, b=b: s.gray(b - k), 0, b - g + 1, pb)[-1]        # bám lùi từ ghim b về g
        for label, sp in EYES.items():
            cf, cb = fwd.scores[label], back.scores[label]
            mix = {i: ((1 - w) * fwd.points[i][0] + w * back.points[i][0], (1 - w) * fwd.points[i][1] + w * back.points[i][1]) for i in sp.pins}
            pred = {"đường thẳng CVAT": {i: (pa[i][0] + w * (pb[i][0] - pa[i][0]), pa[i][1] + w * (pb[i][1] - pa[i][1])) for i in sp.pins},
                    "bám tiến (tool)": {i: fwd.points[i] for i in sp.pins},
                    "bám lùi": {i: back.points[i] for i in sp.pins},
                    "hai chiều, trộn theo thời gian": mix,
                    "hai chiều, chọn theo độ khớp": ({i: fwd.points[i] for i in sp.pins} if cf >= TAU > cb
                                                     else {i: back.points[i] for i in sp.pins} if cb >= TAU > cf else mix)}
            width = math.dist(gt[g][sp.first], gt[g][sp.last])
            rows.append((g in far_hidden, width, {k: st.mean(math.dist(v[i], gt[g][i]) for i in sp.pins) for k, v in pred.items()}))
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    gt, far_hidden = load(os.path.join(HERE, "out", "pins_case01_ai.json"))
    frames = sorted(gt)

    print("(1) Chỉ số tại frame ghim (case 01)")
    rows = []
    for f in frames:
        p = gt[f]
        wl, wr = math.dist(p[L.first], p[L.last]), math.dist(p[R.first], p[R.last])
        rows.append((f, wl / wr, math.dist(centre(p, L, L.pins), centre(p, R, R.pins))))
    ref = sorted(r[2] for r in rows)[int(0.9 * len(rows))]
    for name, pick in (("bề rộng mắt xa / mắt gần", lambda r: r[1]), ("khoảng cách hai mắt / mốc", lambda r: r[2] / ref)):
        t = [pick(r) for r in rows if r[0] in far_hidden]
        n = [pick(r) for r in rows if r[0] not in far_hidden]
        print(f"  {name:28s} quay đầu {min(t):.2f}..{max(t):.2f} | không quay {min(n):.2f}..{max(n):.2f}")

    print("(2) Phát hiện đoạn quay đầu (mắt thường: khoảng frame 20-70 và 100-150)")
    for step in (10, 20, 30, 50):
        train = sorted(set(range(0, 210, step)) & set(frames) | {frames[-1]})
        ref, segs, untrusted = detect(build(CASE01, gt, train))
        text = "; ".join(f"{a}-{b} co {100 * (1 - m):.0f}% ({u} frame không chắc)" for a, b, m, u in segs) or "không có"
        print(f"  ghim mỗi {step:2d} frame: {text} | {untrusted}/210 frame không tin được")
    spike_pins, _ = load(os.path.join(HERE, "out", "pins_ai.json"))
    ref, segs, untrusted = detect(build(FRONTAL, spike_pins, sorted(spike_pins)))
    print(f"  đối chứng mặt thẳng (5 ghim): {len(segs)} đoạn | {untrusted}/200 frame không tin được")

    print("(3) Sai số tại frame ghim bị giấu (trung bình 4 điểm ghim mỗi mắt)")
    for step in (30, 20):
        train = sorted(set(range(0, 210, step)) & set(frames) | {frames[-1]})
        rows = compare(CASE01, gt, far_hidden, train)
        print(f"  ghim mỗi {step} frame, {len(rows)} mắt:")
        for k in rows[0][2]:
            e = [r[2][k] for r in rows]
            pct = [100 * r[2][k] / r[1] for r in rows]
            print(f"    {k:32s} tb {st.mean(e):5.1f} px, trung vị {st.median(e):4.1f}, đạt <=5% {sum(p <= 5 for p in pct):2d}/{len(e)}, <=10% {sum(p <= 10 for p in pct):2d}/{len(e)}")


if __name__ == "__main__":
    main()
