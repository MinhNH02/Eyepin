"""SPIKE: so sanh hinh thoi voi parabol de suy 4 diem con lai, va thu cong thuc doan khoe bi che."""
import sys, math, os, xml.etree.ElementTree as ET
sys.path.insert(0, r"C:\Users\minhf\Documents\VinAI\Task\week2\tools")
from eye_interp import derive
sys.stdout.reconfigure(encoding="utf-8")
ref = ET.parse(os.path.expanduser("~/Downloads/dms_build/eye_prelabel_out/prelabel.xml")).getroot()
frames = []
for im in ref.iter("image"):
    sk = {s.get("label"): {int(p.get("label")): tuple(map(float, p.get("points").split(","))) for p in s.findall("points")} for s in im.findall("skeleton")}
    if "mattrai" in sk and "matphai" in sk: frames.append(sk)
print("frames:", len(frames))
SPEC = {"mattrai": dict(f=14, l=18, up=16, lo=20, a=0.21, b=0.76, c=0.76, d=0.24, um=0.48, lm=0.50, ids=(15, 17, 19, 21)),
        "matphai": dict(f=22, l=26, up=24, lo=28, a=0.23, b=0.79, c=0.78, d=0.25, um=0.51, lm=0.52, ids=(23, 25, 27, 29))}
mix = lambda a, b, t: (a[0] + t*(b[0]-a[0]), a[1] + t*(b[1]-a[1]))
def diamond(P, s):
    f, l, up, lo = P[s["f"]], P[s["l"]], P[s["up"]], P[s["lo"]]
    i1, i2, i3, i4 = s["ids"]
    return {i1: mix(f, up, s["a"]/s["um"]), i2: mix(up, l, (s["b"]-s["um"])/(1-s["um"])),
            i3: mix(lo, l, (s["c"]-s["lm"])/(1-s["lm"])), i4: mix(f, lo, s["d"]/s["lm"])}
def stats(v): v = sorted(v); n = len(v); return f"trung vi {v[n//2]:.2f} | 90% duoi {v[int(n*.9)]:.2f} | lon nhat {v[-1]:.2f}"
err = {"parabol": [], "hinh thoi": []}; rel = {"parabol": [], "hinh thoi": []}
for sk in frames:
    for lab, s in SPEC.items():
        P = sk[lab]; w = math.dist(P[s["f"]], P[s["l"]])
        if w < 20: continue
        par = derive(lab, {i: P[i] for i in (s["f"], s["up"], s["l"], s["lo"])}); dia = diamond(P, s)
        for name, D in (("parabol", par), ("hinh thoi", dia)):
            for i in s["ids"]:
                e = math.dist(D[i], P[i]); err[name].append(e); rel[name].append(100*e/w)
print("\n== 4 diem suy ra (15,17,19,21 / 23,25,27,29), px ==")
for k in err: print(f"{k:10s}", stats(err[k]), "| % be rong mat:", stats(rel[k]))
ce = {"khoe trong 18/26 (an)": [], "khoe ngoai 14/22 (an)": []}; cr = {k: [] for k in ce}
for sk in frames:
    for lab, s in SPEC.items():
        P = sk[lab]; w = math.dist(P[s["f"]], P[s["l"]])
        if w < 20: continue
        u = (s["um"] + s["lm"]) / 2
        M = ((P[s["up"]][0] + P[s["lo"]][0]) / 2, (P[s["up"]][1] + P[s["lo"]][1]) / 2)
        f, l = P[s["f"]], P[s["l"]]
        est_l = (f[0] + (M[0]-f[0])/u, f[1] + (M[1]-f[1])/u)
        est_f = ((M[0] - u*l[0])/(1-u), (M[1] - u*l[1])/(1-u))
        for k, est, true in (("khoe trong 18/26 (an)", est_l, l), ("khoe ngoai 14/22 (an)", est_f, f)):
            e = math.dist(est, true); ce[k].append(e); cr[k].append(100*e/w)
print("\n== khoe bi che, doan tu 3 diem ghim con lai, px ==")
for k in ce: print(f"{k:24s}", stats(ce[k]), "| % be rong mat:", stats(cr[k]))
