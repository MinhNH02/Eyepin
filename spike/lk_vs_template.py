"""Spike dùng một lần: so ba cách bám mắt qua các frame bằng độ trôi tại frame ghim kế tiếp.

  template   : so khớp vùng ảnh (cách đang dùng trong eyepin/tracking.py)
  lk_chain   : Lucas-Kanade (calcOpticalFlowPyrLK), bám từng cặp frame liền kề, dời mắt theo trung vị chuyển động các góc ảnh
  lk_anchor  : Lucas-Kanade, luôn bám từ frame ghim tới frame hiện tại (có ước lượng khởi đầu từ frame trước) nên không cộng dồn

Không dùng model học máy. Đo: bám từ frame ghim a tới frame ghim b, so với điểm ghim ở b (chỉ số pin_jump của EyePin).
Chạy:  python spike/lk_vs_template.py <thư_mục_frame> <pins.json> [--out kết_quả.csv]
pins.json có dạng {"0": {"14": [x, y], ...}, "50": {...}}  (8 điểm ghim mỗi frame; các điểm còn lại được suy ra)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402
from eyepin.tracking import track_forward  # noqa: E402

LK = dict(winSize=(21, 21), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
FB_TOL = 1.0          # px: sai lệch bám xuôi rồi bám ngược cho phép


def _box(pts, ids, margin=(0.3, 0.45)):
    xs, ys = [pts[i][0] for i in ids], [pts[i][1] for i in ids]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    w, h = x1 - x0, max(y1 - y0, 0.25 * (x1 - x0))
    return x0 - margin[0] * w, y0 - margin[1] * h, x1 + margin[0] * w, y1 + margin[1] * h


def _features(gray, box):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, gray.shape[1]), min(y1, gray.shape[0])
    mask = np.zeros_like(gray)
    mask[y0:y1, x0:x1] = 255
    p = cv2.goodFeaturesToTrack(gray, maxCorners=60, qualityLevel=0.01, minDistance=2, blockSize=5, mask=mask)
    return p if p is not None else np.zeros((0, 1, 2), np.float32)


def _flow(a, b, p, guess=None):
    """Vị trí mới của các điểm p (từ ảnh a sang ảnh b) chỉ giữ điểm qua kiểm tra xuôi-ngược; trả (p_cũ, p_mới)."""
    if len(p) == 0:
        return p, p
    kw = dict(LK)
    if guess is not None:
        q, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p, guess.copy(), flags=cv2.OPTFLOW_USE_INITIAL_FLOW, **kw)
    else:
        q, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p, None, **kw)
    r, st2, _ = cv2.calcOpticalFlowPyrLK(b, a, q, None, **kw)
    ok = (st.ravel() == 1) & (st2.ravel() == 1) & (np.linalg.norm((r - p).reshape(-1, 2), axis=1) < FB_TOL)
    return p[ok], q[ok]


def track_lk(get_gray, start, end, pins, *, anchored: bool):
    """Trả về danh sách {điểm: (x, y)} cho các frame start..end-1 (frame start là điểm ghim)."""
    out = [dict(pins)]
    base = get_gray(start)
    prev = base
    shift = {l: np.zeros(2) for l in EYES}
    feats = {l: _features(base, _box(pins, EYES[l].ids)) for l in EYES}
    for f in range(start + 1, end):
        g = get_gray(f)
        pts = {}
        for label, spec in EYES.items():
            cur = {i: (pins[i][0] + shift[label][0], pins[i][1] + shift[label][1]) for i in spec.ids}
            if anchored:
                p0 = feats[label]
                guess = (p0 + shift[label].astype(np.float32)).astype(np.float32) if len(p0) else None
                a, b = _flow(base, g, p0, guess)
            else:
                p0 = _features(prev, _box(cur, spec.ids))
                a, b = _flow(prev, g, p0)
            if len(a) >= 4:
                d = np.median((b - a).reshape(-1, 2), axis=0)
                shift[label] = d if anchored else shift[label] + d
            for i in spec.ids:
                pts[i] = (pins[i][0] + shift[label][0], pins[i][1] + shift[label][1])
        out.append(pts)
        prev = g
    return out


def track_template(get_gray, start, end, pins):
    return [r.points for r in track_forward(get_gray, start, end, pins)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("pins_json")
    ap.add_argument("--out")
    a = ap.parse_args()
    s = Session(a.frames_dir)
    raw = json.load(open(a.pins_json, encoding="utf-8"))
    for fk, d in raw.items():
        if fk.startswith("_"):
            continue
        pts = {int(i): tuple(v) for i, v in d.items()}
        for label, spec in EYES.items():
            s.add_pin(int(fk), label, {i: pts[i] for i in spec.pins})
    frames = sorted(s.pins)
    spans = [(frames[i], frames[j]) for i in range(len(frames)) for j in range(i + 1, len(frames)) if j - i <= 2]
    methods = {
        "template": lambda f0, f1: track_template(s.gray, f0, f1 + 1, s.pins[f0]),
        "lk_chain": lambda f0, f1: track_lk(s.gray, f0, f1 + 1, s.pins[f0], anchored=False),
        "lk_anchor": lambda f0, f1: track_lk(s.gray, f0, f1 + 1, s.pins[f0], anchored=True),
    }
    rows = []
    for f0, f1 in spans:
        for name, fn in methods.items():
            t0 = time.perf_counter()
            res = fn(f0, f1)
            dt = (time.perf_counter() - t0) / max(1, f1 - f0)
            end = res[-1]
            err = [math.dist(end[i], s.pins[f1][i]) for i in s.pins[f1]]
            rows.append({"from": f0, "to": f1, "frames": f1 - f0, "method": name, "max_px": round(max(err), 2),
                         "mean_px": round(sum(err) / len(err), 2), "ms_per_frame": round(dt * 1000, 1)})
    print(f"{'từ':>4} {'tới':>4} {'số frame':>8} {'cách':<10} {'lệch max':>9} {'lệch TB':>8} {'ms/frame':>9}")
    for r in rows:
        print(f"{r['from']:>4} {r['to']:>4} {r['frames']:>8} {r['method']:<10} {r['max_px']:>9} {r['mean_px']:>8} {r['ms_per_frame']:>9}")
    print("\nTrung bình theo cách (px):")
    for name in methods:
        sel = [r for r in rows if r["method"] == name]
        print(f"  {name:<10} lệch max {sum(r['max_px'] for r in sel) / len(sel):.2f}   lệch TB {sum(r['mean_px'] for r in sel) / len(sel):.2f}   "
              f"{sum(r['ms_per_frame'] for r in sel) / len(sel):.1f} ms/frame")
    if a.out:
        with open(a.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print("Đã ghi", a.out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
