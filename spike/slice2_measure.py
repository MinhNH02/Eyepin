"""SPIKE: do phep bam + chon keyframe tren 200 frame lien tiep (PhysDrive 2352-2551), dung 5 diem ghim cua lan demo."""
import json, math, os, sys
import cv2
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from eyepin.geometry import EYES, derive
from eyepin.tracking import propagate, pin_jump, reduce_keyframes
sys.stdout.reconfigure(encoding="utf-8")
SEG = os.path.expanduser("~/Downloads/dms_build/physdrive_seg")
names = sorted(f for f in os.listdir(SEG) if f.endswith(".jpg")); N = len(names)
cache = {}
def gray(f):
    if f not in cache: cache[f] = cv2.cvtColor(cv2.imread(os.path.join(SEG, names[f])), cv2.COLOR_BGR2GRAY)
    return cache[f]
raw = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "pins_ai.json"), encoding="utf-8"))
pins = {}
for k, d in raw.items():
    if k.startswith("_"): continue
    p = {int(i): tuple(v) for i, v in d.items()}; full = {}
    for spec in EYES.values(): full.update(derive(spec, {i: p[i] for i in spec.pins}))
    pins[int(k)] = full
print("frame ghim:", sorted(pins))
for use in ([0], sorted(pins)):
    labels, arrival = propagate(gray, N, {f: pins[f] for f in use})
    scores = [labels[f].score for f in sorted(labels)]
    if len(use) == 1:   # ghim 1 frame: so vị trí bám tại mỗi frame ghim còn lại với điểm ghim thật
        drift = {f: round(max(math.dist(labels[f].points[i], pins[f][i]) for i in pins[f]), 1) for f in sorted(pins) if f != 0}
    else:               # ghim cả 5: mỗi đoạn bám tới frame ghim kế tiếp, đo độ trôi của riêng đoạn đó
        drift = {f: round(pin_jump(arrival[f], pins[f]), 1) for f in sorted(arrival)}
    pos = [labels[f].points for f in range(N)]
    keys = reduce_keyframes(pos, 2.0, forced=use)
    print(f"\nghim tại {use}: nhãn {len(labels)}/{N} frame | độ khớp thấp nhất {min(scores):.2f}, trung vị {sorted(scores)[len(scores)//2]:.2f}")
    print("  độ trôi tại frame ghim (px, lớn nhất trên các điểm):", drift or "-")
    print(f"  số keyframe cần ghi để CVAT nội suy lệch ≤ 2 px: {len(keys)} / {N}")
