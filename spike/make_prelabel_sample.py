"""Dựng dữ liệu prelabel MẪU (giả lập) để thử phần mổ lỗi prelabel: 200 frame đầu của case 01 (PhysDrive, dữ liệu công khai).

Spike dùng một lần. KHÔNG phải prelabel thật của công ty, KHÔNG phải nhãn chuẩn.

- Đáp án tạm (`reference.xml`): ghim thô do AI đọc (`spike/out/pins_case01_ai.json`, ±2 px) rồi EyePin điền mọi frame bằng bám hai
  chiều chọn theo độ khớp (MVP 3, `evaluate.choose`). Mắt xa (mattrai) có điểm 14 Occluded ở frame 20–70 và 100–150 (ghi chú `_far_hidden`
  của file ghim: ở đó điểm 14 là đầu nhìn thấy của mắt, không phải khoé thật).
- Prelabel giả lập (`prelabel.xml`): đáp án tạm + lỗi cấy giống một bộ dò chạy riêng từng frame:
    rung           nhiễu Gauss JITTER px mỗi điểm mỗi frame (mọi frame, không ghi vào answer_key)
    sot            mắt xa không có nhãn ở N_MISS frame mắt xa hẹp nhất
    lac_cho        một mắt bị đặt lên lông mày (dời lên nửa bề rộng mắt) ở N_BROW frame ngẫu nhiên
    sai_dang_chop  frame chớp 86–94 vẽ dáng mắt mở (của frame OPEN_REF) tại vị trí mắt
    doi_ben        mattrai và matphai đổi nhãn cho nhau ở N_SWAP frame
    thieu_co       prelabel không có cờ Occluded nào (đáp án có ở mắt xa frame 20–70, 100–150)
  Lỗi từng frame: `answer_key.json`.
- Ảnh cho task CVAT: `prelabel_200.zip` (200 ảnh đầu của case 01, giữ nguyên tên).

Chạy:  python spike\\make_prelabel_sample.py      (khoảng 1 phút; ghi vào OUT)
"""
from __future__ import annotations

import json
import math
import os
import random
import statistics
import sys
import zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from eyepin import cvatxml, overlap                    # noqa: E402
from eyepin.cvatxml import Annotations, EyeKey, PointState   # noqa: E402
from eyepin.evaluate import choose                     # noqa: E402
from eyepin.geometry import EYES                       # noqa: E402
from eyepin.session import Session                     # noqa: E402
from eyepin.tracking import track_backward             # noqa: E402

CASE01 = r"C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che"
PINS = os.path.join(HERE, "out", "pins_case01_ai.json")
OUT = r"C:\Users\minhf\Downloads\dms_build\prelabel_sample"
N = 200
SEED = 7
JITTER = 1.0
FAR = "mattrai"
FAR_RANGES = [(20, 70), (100, 150)]
BLINK = range(86, 95)
OPEN_REF = 85
N_MISS, N_BROW, N_SWAP = 20, 6, 2


def mid(spec, p):
    (x0, y0), (x1, y1) = p[spec.first], p[spec.last]
    return (x0 + x1) / 2, (y0 + y1) / 2


def width(spec, p):
    return math.dist(p[spec.first], p[spec.last])


def reference(s: Session) -> dict[str, dict[int, dict[int, tuple]]]:
    ref = {l: {} for l in EYES}
    for label, spec in EYES.items():
        keys = s.eye_keyframes(label)
        for f in keys:
            if f < N:
                ref[label][f] = {i: s.pins[f][i] for i in spec.ids}
        for a, b in zip(keys, keys[1:]):
            if a + 1 >= N:
                break
            back = {r.frame: r for r in track_backward(s.gray, b, a + 1, {i: s.pins[b][i] for i in spec.ids})}
            for g in range(a + 1, min(b, N)):
                fwd = {i: s.labels[g].points[i] for i in spec.ids}
                bk = back[g]
                ref[label][g] = choose(fwd, s.labels[g].scores[label], {i: bk.points[i] for i in spec.ids},
                                       bk.scores[label], (g - a) / (b - a))
    missing = [(l, f) for l in EYES for f in range(N) if f not in ref[l]]
    if missing:
        raise SystemExit(f"đáp án tạm thiếu frame: {missing[:10]}")
    return ref


def inject(ref):
    rng = random.Random(SEED)
    pre = {l: {f: {i: (x + rng.gauss(0, JITTER), y + rng.gauss(0, JITTER)) for i, (x, y) in p.items()} for f, p in per.items()}
           for l, per in ref.items()}
    key = {f: {l: [] for l in EYES} for f in range(N)}
    for g in BLINK:                                                   # vẽ mắt mở trong lúc chớp
        for l, spec in EYES.items():
            src, (cx, cy) = ref[l][OPEN_REF], mid(spec, ref[l][OPEN_REF])
            dx, dy = mid(spec, ref[l][g])
            pre[l][g] = {i: (x - cx + dx + rng.gauss(0, JITTER), y - cy + dy + rng.gauss(0, JITTER)) for i, (x, y) in src.items()}
            key[g][l].append("sai_dang_chop")
    spec_far = EYES[FAR]
    cands = sorted((f for a, b in FAR_RANGES for f in range(a, b + 1)), key=lambda f: width(spec_far, ref[FAR][f]))
    miss = sorted(cands[:N_MISS])
    for f in miss:                                                    # bộ dò không thấy mắt xa
        del pre[FAR][f]
        key[f][FAR] = ["sot"]
    pool = [f for f in range(N) if f not in BLINK and f not in miss]
    brow = sorted(rng.sample(pool, N_BROW))
    for f in brow:                                                    # nhận nhầm lông mày là mắt
        l = rng.choice(list(EYES))
        up = 0.5 * width(EYES[l], ref[l][f])
        pre[l][f] = {i: (x, y - up) for i, (x, y) in pre[l][f].items()}
        key[f][l].append("lac_cho")
    swap = sorted(rng.sample([f for f in pool if f not in brow], N_SWAP))
    pairs = list(zip(EYES["mattrai"].ids, EYES["matphai"].ids))
    for f in swap:                                                    # nhầm trái phải
        lt, rt = pre["mattrai"][f], pre["matphai"][f]
        pre["mattrai"][f] = {a: rt[b] for a, b in pairs}
        pre["matphai"][f] = {b: lt[a] for a, b in pairs}
        for l in EYES:
            key[f][l].append("doi_ben")
    occluded = {(f, FAR, spec_far.first) for a, b in FAR_RANGES for f in range(a, b + 1)}
    for f, l, _ in occluded:
        if "sot" not in key[f][l]:
            key[f][l].append("thieu_co")
    return pre, key, occluded, {"miss": miss, "brow": brow, "swap": swap}


def base_ann(names, w, h) -> Annotations:
    root = ET.Element("annotations")
    ET.SubElement(root, "version").text = "1.1"
    for i, n in enumerate(names):
        ET.SubElement(root, "image", {"id": str(i), "name": n, "width": str(w), "height": str(h)})
    return Annotations(ET.ElementTree(root), dict(enumerate(names)), {l: [] for l in EYES}, {l: {} for l in EYES}, 0, len(names), w, h)


def shapes(data, occluded=frozenset()):
    return {l: {f: EyeKey(f, {i: PointState(p[i], False, (f, l, i) in occluded) for i in EYES[l].ids}, False)
                for f, p in sorted(per.items())} for l, per in data.items()}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    s = Session(CASE01)
    pins = json.load(open(PINS, encoding="utf-8"))
    s.load_pins(pins)
    names = s.names[:N]
    ref = reference(s)
    pre, key, occluded, picks = inject(ref)

    ann = base_ann(names, s.width, s.height)
    cvatxml.write_eyes(ann, os.path.join(OUT, "reference.xml"), new_shapes=shapes(ref, occluded))
    cvatxml.write_eyes(ann, os.path.join(OUT, "prelabel.xml"), new_shapes=shapes(pre))
    with zipfile.ZipFile(os.path.join(OUT, "prelabel_200.zip"), "w", zipfile.ZIP_STORED) as z:
        for n in names:
            z.write(os.path.join(CASE01, n), n)
    errors = {str(f): {l: tags for l, tags in d.items() if tags} for f, d in key.items() if any(d.values())}
    json.dump({"_note": "Lỗi cấy vào prelabel giả lập; xem docstring của spike/make_prelabel_sample.py",
               "params": {"seed": SEED, "jitter_px": JITTER, "far_eye": FAR, "far_ranges": FAR_RANGES,
                          "blink": [BLINK.start, BLINK.stop - 1], "open_ref": OPEN_REF, **picks},
               "frames": errors}, open(os.path.join(OUT, "answer_key.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # kiểm lại: đọc hai file vừa ghi, đo IoU prelabel so với đáp án theo từng loại lỗi
    r, p = cvatxml.parse(os.path.join(OUT, "reference.xml")), cvatxml.parse(os.path.join(OUT, "prelabel.xml"))
    print("đáp án tạm:", {l: len(v) for l, v in r.shapes.items()}, "| prelabel:", {l: len(v) for l, v in p.shapes.items()})
    groups: dict[str, list[float]] = {}
    for l, spec in EYES.items():
        for f in range(N):
            tags = key[f][l] or ["chi_rung"]
            if f not in p.shapes[l]:
                groups.setdefault("sot", []).append(0.0)
                continue
            ov = overlap.compare(spec, {i: ps.xy for i, ps in p.shapes[l][f].points.items()},
                                 {i: ps.xy for i, ps in r.shapes[l][f].points.items()})
            if ov is not None:
                for t in tags:
                    groups.setdefault(t, []).append(ov.iou)
    for t, v in sorted(groups.items()):
        print(f"  {t:14s} {len(v):4d} mẫu  IoU tb {statistics.fmean(v):.2f}")
    print("ghi vào", OUT)


if __name__ == "__main__":
    main()
