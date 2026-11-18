#!/usr/bin/env python3
"""SPIKE (dùng một lần, 2026-11-17). Hai phép đo nhỏ với MediaPipe FaceLandmarker (model offline, người dùng cho phép 2026-11-17):

  (A) Điểm chớp mắt "blendshape" (eyeBlinkLeft/Right) của model có thấy được lần chớp ở frame 76–104 của case 01 không,
      so với EAR của điểm ghim và với mốc nhìn ảnh trong design/2026-11-17-interp-iou-research.md mục 4
      (bắt đầu khép 87, nhắm 88–91, mở lại 92–94).
  (B) Cột "ghim + độ dịch của model" đo bằng IoU (chỉ số chính), cùng cách đo với spike/interp_iou_spike.py
      (ghim mỗi 20 / 30 frame, kiểm tại các frame ghim còn lại).

  python spike\\model_iou_spike.py

CHỈ ĐO: không ghi nhãn, không sửa gói eyepin. Ảnh công khai PhysDrive, chỉ đọc vào RAM. Model chạy trên máy; script chặn mọi kết nối
mạng ở tầng Python và báo nếu có lần thử nào (không chặn được tầng C++ của MediaPipe).
"""
import math
import os
import socket
import statistics as st
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:\Users\minhf\Documents\VinAI\Task\week2\tools")

NET_ATTEMPTS = []
_orig_connect = socket.socket.connect


def _no_net(self, addr):                         # chặn mạng ở tầng Python, ghi lại để báo
    NET_ATTEMPTS.append(addr)
    raise OSError(f"spike chặn kết nối mạng tới {addr}")


socket.socket.connect = _no_net
socket.socket.connect_ex = lambda self, addr: (NET_ATTEMPTS.append(addr), 1)[1]

from eye_prelabel import DEFAULT_MODEL, suggest        # noqa: E402
from eyepin import overlap                             # noqa: E402
from eyepin.geometry import EYES                       # noqa: E402
from eyepin.scan import eye_ear                        # noqa: E402
from interp_iou_spike import CASE01, compare_methods, eight, lerp, load   # noqa: E402

KEEP = ("1 đường thẳng CVAT", "2 bám tiến (tool hiện tại)", "5 hai chiều, chọn theo độ khớp")


def run_model(frames_dir):
    """{frame: (16 điểm theo id dự án, {tên blendshape: điểm})} cho mọi frame model tìm được mặt."""
    import mediapipe as mp
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision
    lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=mpp.BaseOptions(model_asset_path=DEFAULT_MODEL), running_mode=vision.RunningMode.IMAGE,
        num_faces=1, output_face_blendshapes=True))
    names = sorted(n for n in os.listdir(frames_dir) if n.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")))
    out = {}
    for f, n in enumerate(names):
        bgr = cv2.imdecode(np.fromfile(os.path.join(frames_dir, n), dtype=np.uint8), cv2.IMREAD_COLOR)
        h, w = bgr.shape[:2]
        res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
        if not res.face_landmarks:
            continue
        P = np.array([[p.x * w, p.y * h] for p in res.face_landmarks[0]])
        out[f] = (suggest(P)[0], {c.category_name: c.score for c in res.face_blendshapes[0]})
    return out, len(names)


def corr(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return float(np.corrcoef(a, b)[0, 1])


def part_a(model, total, gt):
    print(f"(A) Model tìm được mặt ở {len(model)}/{total} frame")
    fr = sorted(model)
    # Gán blendshape cho mắt theo tương quan với EAR do chính model vẽ (mattrai = mắt bên trái ảnh)
    ear = {lb: [eye_ear(sp, model[f][0]) or 0 for f in fr] for lb, sp in EYES.items()}
    blink = {k: [model[f][1][k] for f in fr] for k in ("eyeBlinkLeft", "eyeBlinkRight")}
    pairs = {lb: max(blink, key=lambda k: -corr(blink[k], ear[lb])) for lb in EYES}
    for lb, k in pairs.items():
        print(f"    {lb} ↔ {k}: tương quan với EAR của điểm model {corr(blink[k], ear[lb]):+.2f}")
    print("    frame | " + " | ".join(f"{lb}: blink  EAR(model)  EAR(ghim)" for lb in EYES))
    for f in range(76, 105):
        if f not in model:
            print(f"    {f:5d} | model mất mặt")
            continue
        cells = []
        for lb, sp in EYES.items():
            g = f"{eye_ear(sp, eight(gt[f], sp)):.2f}" if f in gt else "   "
            cells.append(f"{model[f][1][pairs[lb]]:.2f}   {eye_ear(sp, model[f][0]):.2f}        {g}")
        mark = " khép" if f == 87 else " NHẮM" if 88 <= f <= 91 else " mở lại" if 92 <= f <= 94 else ""
        print(f"    {f:5d} | " + " | ".join(cells) + mark)
    # Ngoài đoạn 76–104: những frame nào blink cao (chớp khác mà chưa ai ghim?)
    for lb in EYES:
        hi = [f for f in fr if model[f][1][pairs[lb]] >= 0.5]
        print(f"    {lb}: frame có blink ≥ 0,5: {hi}")
    print("    Tại 24 frame ghim: blink của model so với EAR ghim")
    for lb, sp in EYES.items():
        xs = [(f, model[f][1][pairs[lb]], eye_ear(sp, eight(gt[f], sp))) for f in sorted(gt) if f in model]
        print(f"      {lb}: tương quan blink–EAR ghim {corr([x[1] for x in xs], [x[2] for x in xs]):+.2f}; "
              + ", ".join(f"{f}:{b:.2f}/{e:.2f}" for f, b, e in xs))
    return pairs


def model_preds(model, gt, a, b, g, spec):
    w = (g - a) / (b - a)
    mg, ma, mb = (model[f][0] for f in (g, a, b))
    pa, pb = eight(gt[a], spec), eight(gt[b], spec)
    fa = {i: (pa[i][0] + mg[i][0] - ma[i][0], pa[i][1] + mg[i][1] - ma[i][1]) for i in spec.ids}
    fb = {i: (pb[i][0] + mg[i][0] - mb[i][0], pb[i][1] + mg[i][1] - mb[i][1]) for i in spec.ids}
    return {
        "M1 model trực tiếp (không ghim)": {i: mg[i] for i in spec.ids},
        "M2 ghim trước + độ dịch model": fa,
        "M3 hai ghim + độ dịch model, trộn": lerp(fa, fb, w, spec.ids),
    }


def table(rows, title, keys):
    print(f"    {title}: {len(rows)} mẫu")
    if not rows:
        return
    for k in keys:
        ious = sorted(r["m"][k][0].iou for r in rows)
        n = len(ious)
        p10 = ious[max(0, math.ceil(0.1 * n) - 1)]
        print(f"      {k:36s} IoU tb {st.fmean(ious):.2f} trung vị {st.median(ious):.2f} p10 {p10:.2f} "
              f"≥0,5 {sum(i >= .5 for i in ious):2d}/{n} ≥0,75 {sum(i >= .75 for i in ious):2d}/{n} | "
              f"P {st.fmean(r['m'][k][0].precision for r in rows):.2f} R {st.fmean(r['m'][k][0].recall for r in rows):.2f} | "
              f"sai số {st.fmean(r['m'][k][1] for r in rows):5.1f} px")


def part_b(model, gt, far_hidden):
    print("\n(B) IoU tại frame ghim bị giấu (ghim AI ±2 px, không phải nhãn chuẩn)")
    for step in (20, 30):
        train, rows = compare_methods(gt, far_hidden, step)
        skipped = 0
        for r in rows:
            g = r["g"]
            a, b = max(f for f in train if f < g), min(f for f in train if f > g)
            if not all(f in model for f in (a, g, b)):
                skipped += 1
                r["skip"] = True
                continue
            spec = EYES[r["label"]]
            truth = eight(gt[g], spec)
            for k, p in model_preds(model, gt, a, b, g, spec).items():
                r["m"][k] = (overlap.compare(spec, p, truth), st.fmean(math.dist(p[i], truth[i]) for i in spec.pins))
        rows = [r for r in rows if not r.get("skip")]
        keys = list(KEEP) + [k for k in rows[0]["m"] if k.startswith("M")]
        print(f"  ghim mỗi {step} frame ({len(train)} ghim)" + (f"; bỏ {skipped} mẫu vì model mất mặt" if skipped else ""))
        opened = [r for r in rows if not r["closed"]]
        table(opened, "mắt mở, mọi frame", keys)
        table([r for r in opened if r["turn"]], "mắt mở, trong đoạn quay đầu", keys)
        table([r for r in opened if not r["turn"]], "mắt mở, ngoài đoạn quay đầu", keys)
        table([r for r in rows if r["closed"]], "mắt nhắm", keys)
        base = "5 hai chiều, chọn theo độ khớp"
        for k in [k for k in keys if k.startswith("M")]:
            d = [r["m"][k][0].iou - r["m"][base][0].iou for r in opened]
            print(f"      so theo cặp {k} − hai chiều: {st.fmean(d):+.3f}, hơn >0,05 ở {sum(x > .05 for x in d)}, kém ở {sum(x < -.05 for x in d)} / {len(d)}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    gt, far_hidden = load(os.path.join(HERE, "out", "pins_case01_ai.json"))
    model, total = run_model(CASE01)
    part_a(model, total, gt)
    part_b(model, gt, far_hidden)
    print(f"\nKết nối mạng ở tầng Python trong lúc chạy: {NET_ATTEMPTS if NET_ATTEMPTS else 'không có'}")


if __name__ == "__main__":
    main()
