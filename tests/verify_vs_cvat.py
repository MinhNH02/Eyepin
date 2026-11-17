"""Đối chiếu EyePin với CVAT thật trong Docker (cần container cvat_server chạy; job đích phải TRỐNG; dữ liệu công khai).

Quy trình: dùng Session (không cửa sổ) trên đúng thư mục ảnh của job, ghim vài frame (có ghim khi che khoé, có xoay label và kéo điểm),
xuất file import, cho CVAT import vào job, xuất lại từ CVAT, rồi so từng điều tool tuyên bố với số CVAT trả về:

  V1  vị trí từng frame do CVAT nội suy khớp nhãn tool tính, trong ngưỡng keyframe (2 px) cộng sai số làm tròn
  V2  cờ Occluded / Outside từng điểm, từng frame khớp
  V3  keyframe CVAT ghi nhận đúng bằng keyframe tool xuất; mỗi keyframe đủ 8 điểm; frame ghim khớp đúng (< 0,02 px)
  V4  sau khi xoay label và kéo điểm, toạ độ ở frame ghim vẫn khớp đúng sau import
  V5  quét nhãn do CVAT trả về: không có lỗi đỏ
  V6  số liệu "Manually / Interpolated" tool báo trong hộp Thông tin khớp bảng thống kê của CVAT (đếm keyframe)

Chạy:  python tests\\verify_vs_cvat.py [job_id=5] [thư_mục_ảnh]    Xoá nhãn trong job khi xong.
"""
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eyepin import cvatxml  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.scan import scan  # noqa: E402
from eyepin.session import Session  # noqa: E402
from test_geometry import lens_eye  # noqa: E402

CONTAINER = "cvat_server"
JOB = int(sys.argv[1]) if len(sys.argv) > 1 else 5
FRAMES = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/Downloads/dms_build/cases/01_quay_dau_mat_xa_bi_che")
TOL = 2.0 + 0.02


def sh(*args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(f"Lệnh lỗi: {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def django(code):
    out = sh("docker", "exec", CONTAINER, "python", "manage.py", "shell", "-c", code)
    return [l for l in out.splitlines() if l and "imported automatically" not in l]


def export(fmt, name, wd):
    django(f"from cvat.apps.dataset_manager.task import export_job; export_job({JOB}, '/tmp/{name}.zip', format_name='{fmt}')")
    local = os.path.join(wd, name + ".zip")
    sh("docker", "cp", f"{CONTAINER}:/tmp/{name}.zip", local)
    with zipfile.ZipFile(local) as z:
        z.extract("annotations.xml", os.path.join(wd, name))
    return os.path.join(wd, name, "annotations.xml")


results = []


def check(name, ok, detail):
    results.append(ok)
    print(f"[{'ĐẠT' if ok else 'KHÔNG ĐẠT'}] {name}: {detail}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    wd = tempfile.mkdtemp(prefix="eyepin_vs_cvat_")
    try:
        count = django(f"from cvat.apps.engine.models import LabeledShape, LabeledTrack; print(LabeledShape.objects.filter(job_id={JOB}).count() + LabeledTrack.objects.filter(job_id={JOB}).count())")[-1]
        if count != "0":
            raise SystemExit(f"Job {JOB} không trống ({count} đối tượng); chọn job trống để khỏi mất nhãn.")
        s = Session(FRAMES)
        base = export("CVAT for images 1.1", "base_images", wd)
        s.ann = cvatxml.parse(base)
        n = s.n_frames
        print(f"Job {JOB}: {n} frame, ảnh {s.width}x{s.height}, thư mục {os.path.basename(FRAMES)}")

        # ---- dựng phiên: ghim đủ, ghim khi che khoé, keyframe từ frame tool tính, xoay, kéo điểm ----
        ml, mr = EYES["mattrai"], EYES["matphai"]
        a = lens_eye(ml, 385, 312, 36, 9)
        b = lens_eye(mr, 560, 305, 36, 9)
        s.add_pin_free(0, [a[i] for i in ml.pins] + [b[i] for i in mr.pins])
        a2 = lens_eye(ml, 388, 314, 36, 9, tilt_deg=3)
        b2 = lens_eye(mr, 562, 307, 36, 9, tilt_deg=3)
        hidden_clicks = [a2[i] for i in ml.pins if i != 18] + [b2[i] for i in mr.pins]
        random.Random(1).shuffle(hidden_clicks)
        info = s.add_pin_hidden(60, hidden_clicks)
        print(f"Frame 60 ghim khi che khoé: mắt {info['eye']}, khoé {info['hidden']}, Occluded {info['occluded']}")
        s.toggle_pin_here(120)
        c = 0.0
        pts = s.pins[120]
        cx = (min(pts[i][0] for i in ml.ids) + max(pts[i][0] for i in ml.ids)) / 2
        cy = (min(pts[i][1] for i in ml.ids) + max(pts[i][1] for i in ml.ids)) / 2
        ang = math.radians(12)
        rot = {i: (cx + (x - cx) * math.cos(ang) - (y - cy) * math.sin(ang), cy + (x - cx) * math.sin(ang) + (y - cy) * math.cos(ang))
               for i, (x, y) in ((i, pts[i]) for i in ml.ids)}
        s.drag_points(120, rot)                                        # xoay label 12 độ (tương đương kéo tay cầm)
        s.drag_points(120, {22: (pts[22][0] + 4, pts[22][1] - 2)})     # kéo một điểm của mắt kia
        s.toggle_flag(120, 29, "outside")
        s.toggle_pin_here(180)
        print(f"Frame ghim: {sorted(s.pins)}; keyframe sau khi giảm: ", end="")
        tracks = s.build_tracks()
        kf = sorted(tracks["mattrai"].keys)
        print(kf)

        # ---- xuất, import vào CVAT, xuất lại ----
        out = os.path.join(wd, "to_import.xml")
        s.export(out)
        sh("docker", "cp", out, f"{CONTAINER}:/tmp/to_import.xml")
        django(f"from cvat.apps.dataset_manager.task import import_job_annotations; import_job_annotations('/tmp/to_import.xml', {JOB}, 'CVAT 1.1', False)")
        video = cvatxml.parse(export("CVAT for video 1.1", "after_video", wd))

        first = min(s.pins)
        for label, spec in EYES.items():
            got = video.tracks[label]
            assert len(got) == 1, f"mong 1 track {label}, CVAT có {len(got)}"
        # V1, V2
        worst = {l: 0.0 for l in EYES}
        bad_flags, missing = [], []
        dropped = 0
        for label, spec in EYES.items():
            cv = video.tracks[label][0].keys          # CVAT xuất từng frame (kể cả frame nội suy): so thẳng, không tự nội suy lại
            for f in range(first, n):
                ours = s.labels[f].points
                theirs = cv.get(f)
                if theirs is None:
                    missing.append((label, f))
                    continue
                for i in spec.ids:
                    want = s.flags_at(f).get(i)
                    p = theirs.points.get(i)
                    if p is None or (p.outside and not p.keyframe):   # CVAT bỏ điểm Outside (không phải keyframe của điểm) khỏi file xuất; cvatxml điền lại
                        dropped += 1
                        have = "outside"
                    else:
                        if not p.outside:                  # điểm Outside không có toạ độ thật để so
                            worst[label] = max(worst[label], math.dist(ours[i], p.xy))
                        have = "occluded" if p.occluded else ("outside" if p.outside else None)
                    if want != have:
                        bad_flags.append((label, f, i, want, have))
        if dropped:
            print(f"Ghi chú: file xuất của CVAT bỏ {dropped} điểm Outside (không có thẻ cho điểm đó); tool coi là Outside khi so")
        if missing:
            print(f"Cảnh báo: CVAT không xuất {len(missing)} frame {missing[:3]}")
        check("V1 vị trí nội suy của CVAT khớp nhãn tool", all(w < TOL for w in worst.values()),
              "lệch lớn nhất " + ", ".join(f"{l} {w:.3f} px" for l, w in worst.items()) + f" trên {n - first} frame (ngưỡng {TOL})")
        check("V2 cờ Occluded/Outside khớp", not bad_flags, f"{len(bad_flags)} chỗ khác nhau {bad_flags[:4]}")
        # V3
        kf_cvat = {l: sorted(f for f, k in video.tracks[l][0].keys.items() if k.keyframe) for l in EYES}
        partial = [(l, f) for l in EYES for f in kf_cvat[l] if len(video.tracks[l][0].keys[f].points) != 8]
        exact = max(math.dist(video.tracks[l][0].keys[f].points[i].xy, s.pins[f][i])
                    for l, sp in EYES.items() for f in s.pins for i in sp.ids if f in video.tracks[l][0].keys)
        check("V3 keyframe CVAT ghi nhận khớp, đủ 8 điểm, frame ghim khớp đúng",
              all(kf_cvat[l] == sorted(tracks[l].keys) for l in EYES) and not partial and exact < 0.02,
              f"tool xuất mattrai {len(kf)} / matphai {len(tracks['matphai'].keys)} keyframe, CVAT {len(kf_cvat['mattrai'])} / {len(kf_cvat['matphai'])}; thiếu điểm {partial}; lệch tại frame ghim {exact:.4f} px")
        # V4
        v4 = max(math.dist(video.tracks["mattrai"][0].keys[120].points[i].xy, s.pins[120][i]) for i in ml.ids)
        v4b = math.dist(video.tracks["matphai"][0].keys[120].points[22].xy, s.pins[120][22])
        check("V4 sau xoay label và kéo điểm, CVAT giữ đúng toạ độ", v4 < 0.02 and v4b < 0.02,
              f"mattrai lệch {v4:.4f} px, điểm 22 mắt kia lệch {v4b:.4f} px; Outside điểm 29 = "
              f"{video.tracks['matphai'][0].keys[120].points[29].outside}")
        ids_cvat = {l: video.tracks[l][0].attrs.get("id") for l in EYES}
        check("V10 ID đối tượng: file xuất của CVAT đánh lại ID (0, 1), còn giao diện CVAT hiện 1 và 10; tool dùng 1 và 10 như giao diện",
              s.obj_ids == {"mattrai": 1, "matphai": 10} and len(set(ids_cvat.values())) == 2,
              f"tool {s.obj_ids}; file xuất của CVAT {ids_cvat}")
        # V5
        red = [f for f in scan(video, n, width=s.width, height=s.height) if f.level == "red"]
        check("V5 quét nhãn CVAT trả về: không có lỗi đỏ", not red, f"{len(red)} lỗi đỏ {[(f.code, f.label, f.frame) for f in red[:4]]}")
        # V6
        manual, total = len(s.pins), len(s.labels)
        cv_manual = len(kf_cvat["mattrai"])
        stats = django(f"from cvat.apps.engine.models import LabeledTrack, TrackedShape; "
                       f"print(TrackedShape.objects.filter(track__job_id={JOB}, track__label__name='mattrai').count())")[-1]
        check("V6 số keyframe: tool, CVAT export và cơ sở dữ liệu CVAT khớp", len(kf) == cv_manual == int(stats),
              f"tool {len(kf)}, CVAT export {cv_manual}, CVAT DB {stats} (tool báo Manually {manual} frame ghim → {len(kf)} keyframe khi xuất, "
              f"Interpolated {total - manual})")
        # ---- V7, V8: Propagate và hoán đổi label, qua một vòng import mới ----
        def roundtrip(sess, name):
            django(f"from cvat.apps.dataset_manager.task import JobAnnotation; JobAnnotation({JOB}).delete()")
            sess.ann = cvatxml.parse(base)
            o = os.path.join(wd, name + ".xml")
            sess.export(o)
            sh("docker", "cp", o, f"{CONTAINER}:/tmp/{name}.xml")
            django(f"from cvat.apps.dataset_manager.task import import_job_annotations; import_job_annotations('/tmp/{name}.xml', {JOB}, 'CVAT 1.1', False)")
            return cvatxml.parse(export("CVAT for video 1.1", name + "_video", wd))
        got = s.propagate(120, 3, direction=1)
        v7 = roundtrip(s, "propagated")
        kf7 = sorted(f for f, k in v7.tracks["mattrai"][0].keys.items() if k.keyframe)
        pos7 = max(math.dist(v7.tracks["mattrai"][0].keys[g].points[i].xy, s.pins[120][i]) for g in (121, 122, 123) for i in ml.ids
                   if not (v7.tracks["mattrai"][0].keys[g].points[i].outside and not v7.tracks["mattrai"][0].keys[g].points[i].keyframe))
        check("V7 Propagate: CVAT có keyframe ở các frame vừa nhân và vị trí bằng frame nguồn",
              got == 3 and {121, 122, 123} <= set(kf7) and pos7 < 0.02, f"nhân {got} frame; CVAT keyframe có 121-123: {{121, 122, 123}} <= {len(kf7)} keyframe; lệch {pos7:.4f} px")
        before = {f: dict(p) for f, p in s.pins.items()}
        s.swap_eyes()
        v8 = roundtrip(s, "swapped")
        k0 = v8.tracks["mattrai"][0].keys[0].points
        err8 = max(math.dist(k0[a].xy, before[0][b]) for a, b in zip(ml.ids, mr.ids))
        check("V8 hoán đổi label: CVAT nhận điểm mattrai đúng bằng điểm matphai cũ", err8 < 0.02, f"lệch {err8:.4f} px ở frame 0")
        # ---- V9: xoá một label (mắt) ----
        s.delete_eye("matphai")
        v9 = roundtrip(s, "deleted")
        kf9 = sorted(f for f, k in v9.tracks["mattrai"][0].keys.items() if k.keyframe)
        check("V9 xoá label: CVAT chỉ còn track mattrai, không có matphai", not v9.tracks["matphai"] and len(v9.tracks["mattrai"]) == 1 and bool(kf9),
              f"CVAT: matphai {len(v9.tracks['matphai'])} track, mattrai {len(v9.tracks['mattrai'])} track, {len(kf9)} keyframe")
        # ---- V11: hai người trong một job (nhiều đối tượng cùng label) ----
        s2 = Session(FRAMES)
        s2.add_pin_free(0, [a[i] for i in ml.pins] + [b[i] for i in mr.pins])
        s2.add_layer()
        a3 = lens_eye(ml, 700, 330, 30, 8)
        b3 = lens_eye(mr, 840, 330, 30, 8)
        s2.add_pin_free(40, [a3[i] for i in ml.pins] + [b3[i] for i in mr.pins])
        v11 = roundtrip(s2, "twopeople")
        counts = {l: len(v11.tracks[l]) for l in EYES}
        starts = sorted((l, min(t.keys)) for l in EYES for t in v11.tracks[l])
        ids_ui = [o[2] for o in s2.objects()]
        check("V11 hai người: CVAT có hai track mỗi label, track người 2 bắt đầu từ frame ghim của họ",
              counts == {"mattrai": 2, "matphai": 2} and starts == [("matphai", 0), ("matphai", 40), ("mattrai", 0), ("mattrai", 40)] and ids_ui == [1, 10, 19, 28],
              f"CVAT: {counts}, frame bắt đầu {starts}; ID trong tool {ids_ui} (giao diện CVAT hiện 1, 10, 19, 28 khi nạp bốn track)")
        ok = all(results)
        print("KẾT QUẢ:", "ĐẠT" if ok else "KHÔNG ĐẠT", f"({sum(results)}/{len(results)})")
        return 0 if ok else 1
    finally:
        if not os.environ.get("EYEPIN_KEEP"):
            django(f"from cvat.apps.dataset_manager.task import JobAnnotation; JobAnnotation({JOB}).delete()")
        shutil.rmtree(wd, ignore_errors=True)
        print(f"Đã dọn nhãn trong job {JOB}")


if __name__ == "__main__":
    sys.exit(main())
