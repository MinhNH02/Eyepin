#!/usr/bin/env python3
"""SPIKE (dùng một lần, 2026-11-16). Đo một model landmark có sẵn (MediaPipe FaceLandmarker) trên case 01, cùng thước đo
với spike/headturn_spike.py, để trả lời câu hỏi "có cần model mới đạt độ chính xác cao không".

  python spike\\model_spike.py

CHỈ ĐO, không ghi nhãn, không sửa gói eyepin. Ảnh công khai PhysDrive, chỉ đọc vào RAM, model chạy trên máy (không gửi ảnh đi đâu).
Quy tắc "không dùng model học máy" trong CLAUDE.md vẫn còn hiệu lực cho sản phẩm; file này không thay đổi điều đó.
"""
import math
import os
import statistics as st
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, r"C:\Users\minhf\Documents\VinAI\Task\week2\tools")
from eyepin.geometry import EYES                       # noqa: E402
from eye_prelabel import DEFAULT_MODEL, suggest        # noqa: E402
from headturn_spike import CASE01, compare, load       # noqa: E402


def run_model(frames_dir):
    """{chỉ số frame: ({id điểm: (x, y)}, yaw độ)} cho các frame model tìm được mặt."""
    import mediapipe as mp
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision
    lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=mpp.BaseOptions(model_asset_path=DEFAULT_MODEL), running_mode=vision.RunningMode.IMAGE,
        num_faces=1, output_facial_transformation_matrixes=True))
    names = sorted(n for n in os.listdir(frames_dir) if n.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")))
    out = {}
    for f, n in enumerate(names):
        bgr = cv2.imdecode(np.fromfile(os.path.join(frames_dir, n), dtype=np.uint8), cv2.IMREAD_COLOR)
        h, w = bgr.shape[:2]
        res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
        if not res.face_landmarks:
            continue
        P = np.array([[p.x * w, p.y * h] for p in res.face_landmarks[0]])
        M = np.array(res.facial_transformation_matrixes[0])[:3, :3]
        out[f] = (suggest(P)[0], math.degrees(math.atan2(M[0, 2], M[2, 2])))
    return out, len(names)


def stats(name, errs, widths):
    pct = [100 * e / w for e, w in zip(errs, widths)]
    n = len(errs)
    print(f"    {name:38s} tb {st.mean(errs):5.1f} px, trung vị {st.median(errs):4.1f}, "
          f"đạt <=5% {sum(p <= 5 for p in pct):2d}/{n}, <=10% {sum(p <= 10 for p in pct):2d}/{n}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    gt, far_hidden = load(os.path.join(HERE, "out", "pins_case01_ai.json"))
    frames = sorted(gt)
    model, total = run_model(CASE01)
    missing = [f for f in range(total) if f not in model]
    print(f"(A) Model tìm được mặt ở {len(model)}/{total} frame; mất ở: {missing if len(missing) <= 40 else str(missing[:40]) + '...'}")
    yaws = {f: model[f][1] for f in frames if f in model}
    print("    yaw model tại frame ghim: " + ", ".join(f"{f}:{y:+.0f}" for f, y in yaws.items()))

    def err(pred, g, sp):
        return st.mean(math.dist(pred[i], gt[g][i]) for i in sp.pins)

    print("(B) Model dùng trực tiếp (không ghim), sai số so với ghim thô tại 24 frame ghim, trung bình 4 điểm ghim mỗi mắt")
    for name, pick in (("mọi frame ghim", lambda f: True), ("frame quay đầu", lambda f: f in far_hidden),
                       ("frame không quay", lambda f: f not in far_hidden)):
        errs, widths = [], []
        for g in frames:
            if g in model and pick(g):
                for sp in EYES.values():
                    errs.append(err(model[g][0], g, sp))
                    widths.append(math.dist(gt[g][sp.first], gt[g][sp.last]))
        if errs:
            stats(name, errs, widths)
    for label, sp in EYES.items():
        for tag, sel in (("quay đầu", True), ("không quay", False)):
            e = [err(model[g][0], g, sp) for g in frames if g in model and (g in far_hidden) == sel]
            print(f"    {label} / {tag:10s}: tb {st.mean(e):5.1f} px, lớn nhất {max(e):5.1f}")

    print("(C) Tại frame ghim bị giấu: model chỉ cấp ĐỘ DỊCH so với frame ghim (ghim + model(g) - model(ghim))")
    for step in (30, 20):
        train = sorted(set(range(0, 210, step)) & set(frames) | {frames[-1]})
        base = compare(CASE01, gt, far_hidden, train)
        print(f"  ghim mỗi {step} frame, {len(base)} mắt:")
        for k in ("đường thẳng CVAT", "bám tiến (tool)", "hai chiều, chọn theo độ khớp"):
            stats(k, [r[2][k] for r in base], [r[1] for r in base])
        rows = {"model trực tiếp": [], "model dịch từ ghim trước": [], "model dịch, trộn hai ghim": []}
        widths, skipped = [], 0
        for g in [f for f in frames if f not in train]:
            a, b = max(f for f in train if f < g), min(f for f in train if f > g)
            if not all(f in model for f in (a, g, b)):
                skipped += 1
                continue
            w = (g - a) / (b - a)
            mg, ma, mb = model[g][0], model[a][0], model[b][0]
            for sp in EYES.values():
                fa = {i: (gt[a][i][0] + mg[i][0] - ma[i][0], gt[a][i][1] + mg[i][1] - ma[i][1]) for i in sp.pins}
                fb = {i: (gt[b][i][0] + mg[i][0] - mb[i][0], gt[b][i][1] + mg[i][1] - mb[i][1]) for i in sp.pins}
                mix = {i: ((1 - w) * fa[i][0] + w * fb[i][0], (1 - w) * fa[i][1] + w * fb[i][1]) for i in sp.pins}
                rows["model trực tiếp"].append(err(mg, g, sp))
                rows["model dịch từ ghim trước"].append(err(fa, g, sp))
                rows["model dịch, trộn hai ghim"].append(err(mix, g, sp))
                widths.append(math.dist(gt[g][sp.first], gt[g][sp.last]))
        for k, e in rows.items():
            stats(k, e, widths)
        if skipped:
            print(f"    (bỏ {skipped} frame giấu vì model mất mặt ở frame đó hoặc ở ghim kề)")


if __name__ == "__main__":
    main()
