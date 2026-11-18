"""Đối chiếu EyePin với CVAT thật trong Docker (cần container cvat_server chạy; job đích phải TRỐNG; dữ liệu công khai).

Quy trình: dùng Session (không cửa sổ) trên đúng thư mục ảnh của job, ghim vài frame (có ghim khi che khoé, có xoay label và kéo điểm),
xuất file import, cho CVAT import vào job, xuất lại từ CVAT, rồi so từng điều tool tuyên bố với số CVAT trả về:

  V1  vị trí từng frame do CVAT nội suy khớp nhãn tool tính, trong ngưỡng keyframe (2 px) cộng sai số làm tròn
  V2  cờ Occluded / Outside từng điểm, từng frame khớp
  V3  keyframe CVAT ghi nhận đúng bằng keyframe tool xuất; mỗi keyframe đủ 8 điểm; frame ghim khớp đúng (< 0,02 px)
  V4  sau khi xoay label và kéo điểm, toạ độ ở frame ghim vẫn khớp đúng sau import
  V5  quét nhãn do CVAT trả về: không có lỗi đỏ
  V6  số liệu "Manually / Interpolated" tool báo trong hộp Thông tin khớp bảng thống kê của CVAT (đếm keyframe)
  V12 mắt kiểu shape: job có 1 track matphai + 3 shape mattrai (một có điểm Occluded, một có điểm Outside): đúng số, frame, toạ độ, cờ;
      V12b hai người cùng nhãn cùng frame thành hai shape. Đọc lại bằng JSON như `GET /api/jobs/{id}/annotations` (đi qua `get_job_data`)
      V12c cùng job của V12, bản xuất "CVAT for video" thật: `cvatsync._compare` (bỏ track CVAT sinh từ shape bằng `_shape_tracks`) không
      báo lệch nào, đúng phép đối chiếu `cvatsync.send` chạy sau khi gửi; V12d chế độ QC khi mở lại job đó (`cvatsource._shapes_from_video`):
      shape về đúng frame, không kéo dài sang frame sau

AN TOÀN: job có bất kỳ shape, track hay tag nào thì từ chối chạy và KHÔNG xoá gì (chỉ dọn job sau khi đã kiểm job trống).

Chạy:  python tests\\verify_vs_cvat.py [job_id=5] [thư_mục_ảnh]    Xoá nhãn trong job khi xong.
"""
import json
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
from eyepin.cvatsync import _compare, _compare_shapes, _expected, _expected_shapes, _json_eye_shapes, _sublabel_points  # noqa: E402
from eyepin.cvatsource import _shapes_from_video  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.scan import eye_at  # noqa: E402
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


MARK = "@@"                      # tiền tố dòng kết quả JSON, để lọc khỏi dòng thông báo của Django


def django_json(code):
    """Chạy `code` (phải gọi `emit(obj)` đúng một lần) và trả đối tượng JSON."""
    pre = f"import json\ndef emit(o): print('{MARK}' + json.dumps(o, default=str))\n"
    lines = [l for l in django(pre + code) if l.startswith(MARK)]
    return json.loads(lines[-1][len(MARK):])


def job_info():
    """Số frame đầu/cuối của job và nhãn đúng dạng `GET /api/labels` (có sublabels)."""
    return django_json(
        "from cvat.apps.engine.models import Job\n"
        "from cvat.apps.engine.serializers import LabelSerializer\n"
        f"j = Job.objects.get(pk={JOB}); t = j.segment.task\n"
        "emit({'start': j.segment.start_frame, 'stop': j.segment.stop_frame, 'labels': [LabelSerializer(l).data for l in t.get_labels()]})")


def annotations_json():
    """Đúng dữ liệu `GET /api/jobs/{id}/annotations` trả (`Response(dm.task.get_job_data(pk))`)."""
    return django_json(f"from cvat.apps.dataset_manager.task import get_job_data\nemit(get_job_data({JOB}))")


results = []


def check(name, ok, detail):
    results.append(ok)
    print(f"[{'ĐẠT' if ok else 'KHÔNG ĐẠT'}] {name}: {detail}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    wd = tempfile.mkdtemp(prefix="eyepin_vs_cvat_")
    cleanup = False                  # chỉ dọn job khi đã kiểm job trống: chạy nhầm vào job có nhãn thì từ chối và KHÔNG xoá gì
    try:
        count = django("from cvat.apps.engine.models import LabeledShape, LabeledTrack, LabeledImage; "
                       f"print(LabeledShape.objects.filter(job_id={JOB}).count() + LabeledTrack.objects.filter(job_id={JOB}).count() "
                       f"+ LabeledImage.objects.filter(job_id={JOB}).count())")[-1]
        if count != "0":
            raise SystemExit(f"Job {JOB} không trống ({count} đối tượng: shape, track, tag); chọn job trống để khỏi mất nhãn. Không xoá gì.")
        cleanup = True
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
        # ---- V12: mắt kiểu shape (ảnh rời) cùng mắt kia kiểu track trong một job ----
        info = job_info()
        labels, label_ids = info["labels"], {lb["id"]: lb["name"] for lb in info["labels"]}
        nums = list(range(info["start"], info["stop"] + 1))

        def roundtrip_json(sess, name):
            """Xoá job, nạp file xuất của `sess`, trả JSON như `GET /api/jobs/{id}/annotations`."""
            django(f"from cvat.apps.dataset_manager.task import JobAnnotation; JobAnnotation({JOB}).delete()")
            sess.ann = cvatxml.parse(base)
            o = os.path.join(wd, name + ".xml")
            sess.export(o)
            sh("docker", "cp", o, f"{CONTAINER}:/tmp/{name}.xml")
            django(f"from cvat.apps.dataset_manager.task import import_job_annotations; import_job_annotations('/tmp/{name}.xml', {JOB}, 'CVAT 1.1', False)")
            return annotations_json()

        def shape_flag(occ, out):
            return "occluded" if occ else ("outside" if out else None)

        s3 = Session(FRAMES)
        s3.pin_eye(0, "matphai", {i: b[i] for i in mr.pins}, kind="track")
        shape_frames = [10, 50, 150]
        for k, f in enumerate(shape_frames):
            e = lens_eye(ml, 380 + 6 * k, 312 + 2 * k, 36, 9, tilt_deg=2 * k)
            s3.pin_eye(f, "mattrai", {i: e[i] for i in ml.pins}, kind="shape")
        s3.toggle_flag(50, 20, "occluded")                  # một shape có điểm Occluded
        s3.toggle_flag(150, 16, "outside")                  # một shape có điểm Outside
        aj = roundtrip_json(s3, "shapes_mixed")
        sh_name = {l: [o for o in aj["shapes"] if label_ids.get(o["label_id"]) == l] for l in EYES}
        tr_name = {l: [t for t in aj["tracks"] if label_ids.get(t["label_id"]) == l] for l in EYES}
        got = _json_eye_shapes(aj, labels)
        got_by_frame = {nums.index(jf) if jf in nums else jf: pts for name, jf, pts in got if name == "mattrai"}
        bad = []
        for f in shape_frames:
            pts = got_by_frame.get(f)
            if pts is None:
                bad.append(("thiếu shape", f))
                continue
            fl = s3.flags_at(f)
            for i in ml.ids:
                xy, occ, out = pts[i]
                if not (fl.get(i) == "outside") and math.dist(xy, s3.pins[f][i]) > 0.01:
                    bad.append(("lệch", f, i, round(math.dist(xy, s3.pins[f][i]), 4)))
                if shape_flag(occ, out) != fl.get(i):
                    bad.append(("cờ", f, i, fl.get(i), shape_flag(occ, out)))
        # track matphai: một track, một keyframe ở frame 0, toạ độ đúng
        trk = tr_name["matphai"][0] if tr_name["matphai"] else None
        track_err = None
        if trk is not None:
            track_err = 0.0
            for el in trk.get("elements") or []:
                who = _sublabel_points(labels).get(el["label_id"])
                key0 = next((sp for sp in el["shapes"] if sp["frame"] == nums[0] and sp.get("keyframe", True)), None)
                if who is None or key0 is None:
                    track_err = math.inf
                    break
                track_err = max(track_err, math.dist(key0["points"][:2], s3.pins[0][who[1]]))
        msgs = _compare_shapes(aj, labels, {"mattrai": s3.build_shapes(), "matphai": []}, set(), nums)
        with open(export("CVAT for video 1.1", "shapes_mixed_video", wd), "rb") as fh:
            video12 = cvatxml.parse_bytes(fh.read(), nums)      # số frame của task -> chỉ số EyePin, như cvatsync.send
        cmp12 = _compare(video12, _expected(s3), set(), nums, _expected_shapes(s3))
        check("V12 shape: CVAT có 1 track matphai và 3 shape mattrai, đúng frame, toạ độ < 0,01 px, cờ đúng",
              len(tr_name["matphai"]) == 1 and not tr_name["mattrai"] and len(sh_name["mattrai"]) == 3 and not sh_name["matphai"]
              and sorted(got_by_frame) == shape_frames and not bad and track_err is not None and track_err < 0.01 and not msgs,
              f"JSON: track {len(aj['tracks'])} (matphai {len(tr_name['matphai'])}), shape {len(aj['shapes'])} ở frame {sorted(got_by_frame)}; "
              f"sai lệch {bad[:4]}; track matphai lệch {track_err}; _compare_shapes {msgs[:3] or 'khớp'}")
        check("V12c bản xuất video thật của job V12: cvatsync._compare (bỏ track sinh từ shape) không báo lệch",
              not cmp12 and len(video12.tracks["mattrai"]) == len(shape_frames) and len(video12.tracks["matphai"]) == 1,
              f"bản xuất video: mattrai {len(video12.tracks['mattrai'])} track (sinh từ {len(shape_frames)} shape), "
              f"matphai {len(video12.tracks['matphai'])} track; _compare {cmp12[:3] or 'khớp'}")
        with open(os.path.join(wd, "shapes_mixed_video", "annotations.xml"), "rb") as fh:
            qcv = cvatxml.parse_bytes(fh.read(), nums)
        _shapes_from_video(qcv, aj, labels, nums)
        smear = [f + 1 for f in shape_frames if f + 1 < n and eye_at(qcv, "mattrai", f + 1) is not None]
        check("V12d mở lại job V12 ở chế độ QC: shape mattrai về đúng frame, không kéo dài sang frame sau, track matphai giữ nguyên",
              sorted(qcv.shapes["mattrai"]) == shape_frames and not qcv.tracks["mattrai"] and len(qcv.tracks["matphai"]) == 1 and not smear,
              f"shape mattrai ở {sorted(qcv.shapes['mattrai'])}, track mattrai còn {len(qcv.tracks['mattrai'])}, "
              f"matphai {len(qcv.tracks['matphai'])} track; frame sau shape vẫn có nhãn: {smear or 'không'}")
        # hai người, cùng nhãn, cùng frame: hai shape
        s4 = Session(FRAMES)
        s4.pin_eye(20, "mattrai", {i: a[i] for i in ml.pins}, kind="shape")
        s4.add_layer()
        a4 = lens_eye(ml, 700, 330, 30, 8)
        s4.pin_eye(20, "mattrai", {i: a4[i] for i in ml.pins}, kind="shape")
        aj4 = roundtrip_json(s4, "shapes_twopeople")
        pairs = [(jf, pts) for name, jf, pts in _json_eye_shapes(aj4, labels) if name == "mattrai"]
        msgs4 = _compare_shapes(aj4, labels, {"mattrai": s4.build_shapes(), "matphai": []}, set(), nums)
        ids4 = sorted(sh.attrs["id"] for sh in s4.build_shapes())
        check("V12b hai người, cùng frame: CVAT có hai shape mattrai ở frame 20, khớp từng điểm",
              len(pairs) == 2 and {jf for jf, _ in pairs} == {nums[20]} and not aj4["tracks"] and not msgs4 and len(set(ids4)) == 2,
              f"JSON: {len(pairs)} shape, {len(aj4['tracks'])} track; ID tool {ids4}; _compare_shapes {msgs4[:3] or 'khớp'}")
        ok = all(results)
        print("KẾT QUẢ:", "ĐẠT" if ok else "KHÔNG ĐẠT", f"({sum(results)}/{len(results)})")
        return 0 if ok else 1
    finally:
        if cleanup and not os.environ.get("EYEPIN_KEEP"):
            django(f"from cvat.apps.dataset_manager.task import JobAnnotation; JobAnnotation({JOB}).delete()")
            print(f"Đã dọn nhãn trong job {JOB}")
        shutil.rmtree(wd, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
