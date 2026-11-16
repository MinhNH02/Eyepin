#!/usr/bin/env python3
"""SPIKE: ban demo dung mot lan, khong phai ma san pham.

Chay hai huong tren 200 frame lien tiep cong khai (PhysDrive, frame 2352-2551):

  Huong 1 (logic backend): ghim 4 diem moi mat O FRAME DAU, suy ra 8 diem, roi bam theo mat qua cac frame bang
      so khop vung anh (khong dung model). Dang mat giu nguyen nhu frame dau, chi dich chuyen.
  Huong 2 (co tro ly AI):  tro ly ghim 4 diem moi mat o NAM FRAME (0, 50, 100, 150, 199), suy ra 8 diem, noi suy
      duong thang giua cac frame ghim nhu CVAT. Kem bang do (toa do, chieu cao, ti le, pixel) va bao cao QC.

Ket qua trong thu muc out/: d1_track.csv, d2_metrics.csv, qc_report.md, file XML de import vao CVAT, viewer.html.
"""
import csv
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, r"C:\Users\minhf\Documents\VinAI\Task\week2\tools")
from eye_interp import EYES, derive  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SEG = os.path.expanduser("~/Downloads/dms_build/physdrive_seg")
NAMES = sorted(f for f in os.listdir(SEG) if f.endswith(".jpg"))
N = len(NAMES)
IDS = {label: list(range(spec["first"], spec["first"] + 8)) for label, spec in EYES.items()}
PAIRS = {"mattrai": [(15, 21), (16, 20), (17, 19)], "matphai": [(23, 29), (24, 28), (25, 27)]}


def full16(pins):
    """8 diem ghim {id: (x, y)} -> du 16 diem cua hai mat."""
    out = {}
    for label, spec in EYES.items():
        need = [spec["first"], spec["up"], spec["last"], spec["lo"]]
        out.update(derive(label, {i: tuple(pins[i]) for i in need}))
    return out


def interpolate(keyframes):
    """{frame: 16 diem} -> danh sach N frame, noi suy duong thang, giu vi tri sau frame ghim cuoi (nhu CVAT)."""
    ks = sorted(keyframes)
    res = []
    for t in range(N):
        left = max((k for k in ks if k <= t), default=ks[0])
        right = min((k for k in ks if k >= t), default=ks[-1])
        if left == right:
            res.append(dict(keyframes[left]))
            continue
        a = (t - left) / (right - left)
        res.append({i: (keyframes[left][i][0] + a * (keyframes[right][i][0] - keyframes[left][i][0]),
                        keyframes[left][i][1] + a * (keyframes[right][i][1] - keyframes[left][i][1]))
                    for i in keyframes[left]})
    return res


def track(gray, base, margin=(12, 10), search=14):
    """Bam tung mat tu frame 0 bang so khop mau voi vung anh quanh mat o frame 0. Tra ve {label: [(dx, dy, diem)]}."""
    res = {}
    for label, ids in IDS.items():
        xs = [base[i][0] for i in ids]
        ys = [base[i][1] for i in ids]
        x0, y0 = int(min(xs) - margin[0]), int(min(ys) - margin[1])
        x1, y1 = int(max(xs) + margin[0]), int(max(ys) + margin[1])
        tmpl = gray[0][y0:y1, x0:x1]
        th, tw = tmpl.shape
        px, py = x0, y0
        shifts = [(0, 0, 1.0)]
        for t in range(1, N):
            wx0, wy0 = max(0, px - search), max(0, py - search)
            wx1, wy1 = min(gray[t].shape[1] - tw, px + search), min(gray[t].shape[0] - th, py + search)
            r = cv2.matchTemplate(gray[t][wy0:wy1 + th, wx0:wx1 + tw], tmpl, cv2.TM_CCOEFF_NORMED)
            _, score, _, loc = cv2.minMaxLoc(r)
            px, py = wx0 + loc[0], wy0 + loc[1]
            shifts.append((px - x0, py - y0, float(score)))
        res[label] = shifts
    return res


def reduce_keyframes(positions, tol):
    """Chon it frame ghim nhat sao cho noi suy duong thang giua chung lech khong qua tol px (tham lam)."""
    keys = [0]
    while keys[-1] < len(positions) - 1:
        a, best = keys[-1], keys[-1] + 1
        for b in range(a + 1, len(positions)):
            ok = True
            for t in range(a + 1, b):
                w = (t - a) / (b - a)
                for i in positions[a]:
                    x = positions[a][i][0] + w * (positions[b][i][0] - positions[a][i][0])
                    y = positions[a][i][1] + w * (positions[b][i][1] - positions[a][i][1])
                    if math.hypot(x - positions[t][i][0], y - positions[t][i][1]) > tol:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                best = b
            else:
                break
        keys.append(best)
    return keys


def measure(pts, grad):
    """Bang do cho mot frame: toa do, chieu cao, ti le, pixel."""
    row = {}
    centers = {}
    for label, spec in EYES.items():
        p0, p1 = pts[spec["first"]], pts[spec["last"]]
        w = math.dist(p0, p1)
        opens = [math.dist(pts[a], pts[b]) for a, b in PAIRS[label]]
        cx = sum(pts[i][0] for i in IDS[label]) / 8
        cy = sum(pts[i][1] for i in IDS[label]) / 8
        centers[label] = (cx, cy)
        h, wd = grad.shape
        edge = [float(grad[min(h - 1, max(0, round(pts[i][1]))), min(wd - 1, max(0, round(pts[i][0])))]) for i in IDS[label]]
        k = label[3:]   # "trai" / "phai"
        row.update({f"rong_{k}": round(w, 1), f"mo_giua_{k}": round(opens[1], 1),
                    f"mo_tb_{k}": round(sum(opens) / 3, 1), f"ti_le_mo_{k}": round(opens[1] / w, 3),
                    f"goc_{k}": round(math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])), 1),
                    f"tam_x_{k}": round(cx, 1), f"tam_y_{k}": round(cy, 1),
                    f"bien_{k}": round(sum(edge) / 8, 3)})
    row["kc_hai_mat"] = round(math.dist(centers["mattrai"], centers["matphai"]), 1)
    return row, centers


def write_xml(path, keyframes, offset, count):
    """File 'CVAT 1.1' dang video: moi mat mot track, keyframe du 8 diem. Frame trong file = frame doan - offset."""
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<annotations>", "<version>1.1</version>"]
    kfs = sorted(k for k in keyframes if offset <= k < offset + count)
    for tid, (label, ids) in enumerate(IDS.items()):
        lines.append(f'<track id="{tid}" label="{label}" source="manual">')
        for k in kfs:
            lines.append(f'<skeleton frame="{k - offset}" keyframe="1" outside="0" occluded="0" z_order="0">')
            for i in ids:
                x, y = keyframes[k][i]
                lines.append(f'<points label="{i}" keyframe="1" outside="0" occluded="0" points="{x:.2f},{y:.2f}"></points>')
            lines.append("</skeleton>")
        lines.append("</track>")
    lines.append("</annotations>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(kfs)


def ranges(frames):
    out, start, prev = [], None, None
    for f in frames:
        if start is None:
            start = prev = f
        elif f == prev + 1:
            prev = f
        else:
            out.append((start, prev)); start = prev = f
    if start is not None:
        out.append((start, prev))
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in out) or "không có"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    raw = json.load(open(os.path.join(OUT, "pins_ai.json"), encoding="utf-8"))
    pins = {int(k): {int(i): tuple(v) for i, v in d.items()} for k, d in raw.items() if not k.startswith("_")}
    gray = [cv2.cvtColor(cv2.imread(os.path.join(SEG, n)), cv2.COLOR_BGR2GRAY) for n in NAMES]

    # ---------- Huong 1: ghim frame 0 + bam theo vung anh ----------
    base = full16(pins[0])
    shifts = track(gray, base)
    d1 = [{i: (base[i][0] + shifts[label][t][0], base[i][1] + shifts[label][t][1])
           for label, ids in IDS.items() for i in ids} for t in range(N)]
    d1_score = [min(shifts["mattrai"][t][2], shifts["matphai"][t][2]) for t in range(N)]
    d1_keys = reduce_keyframes(d1, tol=2.0)
    d1_low = [t for t in range(N) if d1_score[t] < 0.6]

    # ---------- Huong 2: ghim 5 frame + noi suy ----------
    d2_keys = sorted(pins)
    d2 = interpolate({k: full16(pins[k]) for k in d2_keys})

    # ---------- Bang do va QC ----------
    rows, gaps = [], []
    for t in range(N):
        g = cv2.GaussianBlur(gray[t], (3, 3), 0).astype(np.float32)
        grad = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
        grad /= max(1.0, float(np.percentile(grad[200:400, 230:610], 99)))
        m2, c2 = measure(d2[t], grad)
        m1, c1 = measure(d1[t], grad)
        gap = max(math.dist(c1[label], c2[label]) for label in EYES)
        gaps.append(gap)
        step = 0.0 if t == 0 else max(math.dist(d2[t][i], d2[t - 1][i]) for i in d2[t])
        rows.append({"frame": t, "file": NAMES[t], "ghim": int(t in d2_keys), **m2,
                     "dich_max_so_frame_truoc": round(step, 1), "lech_tam_so_huong1": round(gap, 1),
                     "diem_khop_huong1": round(d1_score[t], 3),
                     "bien_huong1": round((m1["bien_trai"] + m1["bien_phai"]) / 2, 3)})
    with open(os.path.join(OUT, "d2_metrics.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, "d1_track.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["frame", "dx_trai", "dy_trai", "khop_trai", "dx_phai", "dy_phai", "khop_phai", "la_frame_ghim"])
        for t in range(N):
            a, b = shifts["mattrai"][t], shifts["matphai"][t]
            w.writerow([t, a[0], a[1], round(a[2], 3), b[0], b[1], round(b[2], 3), int(t in d1_keys)])

    # Huong 1 so voi diem ghim cua huong 2 tai cac frame ghim (khong phai nhan chuan, chi la hai nguon doc lap)
    cmp_lines = []
    for k in d2_keys[1:]:
        ref = full16(pins[k])
        pin_ids = [i for spec in EYES.values() for i in (spec["first"], spec["up"], spec["last"], spec["lo"])]
        d = [math.dist(d1[k][i], ref[i]) for i in pin_ids]
        cmp_lines.append(f"| {k} | {sum(d) / len(d):.1f} | {max(d):.1f} | {d1_score[k]:.2f} |")

    big_gap = [t for t in range(N) if gaps[t] > 5]
    ear = [r["ti_le_mo_trai"] for r in rows]
    edge2 = float(np.mean([(r["bien_trai"] + r["bien_phai"]) / 2 for r in rows]))
    edge1 = float(np.mean([r["bien_huong1"] for r in rows]))
    n3 = write_xml(os.path.join(OUT, "import_job3_huong1.xml"), {k: d1[k] for k in d1_keys}, 0, 100)
    n4 = write_xml(os.path.join(OUT, "import_job4_huong2.xml"), {k: d2[k] for k in d2_keys}, 100, 100)
    report = f"""# Báo cáo demo hai hướng (SPIKE, bản dùng một lần)

Dữ liệu: 200 frame liên tiếp công khai, PhysDrive frame 2352–2551, 1024×576, 30 fps.
Điểm ghim do Claude đọc trên ảnh phóng to có lưới (đóng vai trợ lý AI). Không có nhãn chuẩn để so.

## Hướng 1: ghim frame 0, bám theo vùng ảnh

- Số frame phải ghim tay: 1 (frame 0).
- Số keyframe cần ghi để nội suy của CVAT không lệch quá 2 px so với kết quả bám: {len(d1_keys)} trên {N} frame.
- Frame có điểm khớp dưới 0,6 (dáng mắt đã khác frame 0, kết quả bám không đáng tin): {len(d1_low)} frame — {ranges(d1_low)}.
- Dáng mắt luôn giữ như frame 0, nên mắt nhắm không được thể hiện.

So với điểm ghim của hướng 2 tại các frame ghim (hai nguồn độc lập, không nguồn nào là chuẩn):

| Frame | Lệch trung bình (px) | Lệch lớn nhất (px) | Điểm khớp |
| --- | --- | --- | --- |
{chr(10).join(cmp_lines)}

## Hướng 2: trợ lý ghim 5 frame, nội suy đường thẳng

- Số frame ghim: {len(d2_keys)} ({", ".join(map(str, d2_keys))}).
- Frame mà tâm mắt nội suy lệch hơn 5 px so với kết quả bám của hướng 1: {len(big_gap)} frame — {ranges(big_gap)}.
  Lệch lớn nhất: {max(gaps):.1f} px ở frame {int(np.argmax(gaps))}. Đây là chỗ đầu cử động không đều giữa hai frame ghim.
- Tỉ lệ mở mắt trái (độ mở giữa / bề rộng): nhỏ nhất {min(ear):.2f}, lớn nhất {max(ear):.2f}. Giữa frame ghim mắt mở và frame ghim
  mắt nhắm, nội suy cho mắt khép dần đều; chớp mắt thật thì nhanh hơn nhiều.

## Độ bám mép sáng tối (pixel)

Trung bình độ tương phản ngay dưới 16 điểm (0 = không có mép, 1 = mép rõ nhất vùng mặt):
hướng 1 = {edge1:.2f}, hướng 2 = {edge2:.2f}. Ảnh cháy sáng nên số này thấp ở cả hai hướng.

## File để import vào CVAT local

- `import_job3_huong1.xml`: job 3 (frame 0–99), {n3} keyframe mỗi mắt.
- `import_job4_huong2.xml`: job 4 (frame 100–199), {n4} keyframe mỗi mắt.
"""
    with open(os.path.join(OUT, "qc_report.md"), "w", encoding="utf-8") as fh:
        fh.write(report)

    data = {"names": NAMES, "d1": [[[round(p[i][0], 1), round(p[i][1], 1)] for i in range(14, 30)] for p in d1],
            "d2": [[[round(p[i][0], 1), round(p[i][1], 1)] for i in range(14, 30)] for p in d2],
            "score": [round(s, 2) for s in d1_score], "gap": [round(g, 1) for g in gaps],
            "k1": d1_keys, "k2": d2_keys, "rows": rows}
    with open(os.path.join(OUT, "viewer_data.js"), "w", encoding="utf-8") as fh:
        fh.write("const DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print(report)


if __name__ == "__main__":
    main()
