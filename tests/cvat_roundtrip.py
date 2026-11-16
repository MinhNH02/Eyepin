"""Kiểm tích hợp với CVAT local (cần container cvat_server đang chạy, job đích phải trống).

Chứng minh bốn điều của spec v3 mục 8:
  1. File do tool ghi (track + shape) import được vào job.
  2. Sau import, vị trí từng frame CVAT xuất ra khớp bản xem trước của tool (eyepin.preview).
  3. Cờ Occluded của keyframe được chép đúng cho các frame giữa (từ keyframe bên trái).
  4. Mỗi keyframe trong job đều đủ 8 điểm.

Chạy: python tests\\cvat_roundtrip.py [job_id=9]
Xoá nhãn trong job khi xong để job trở lại trống.
"""
import math
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eyepin import cvatxml  # noqa: E402
from eyepin.cvatxml import EyeKey, EyeTrack, PointState  # noqa: E402
from eyepin.geometry import EYES, derive  # noqa: E402
from eyepin.preview import position_at  # noqa: E402
from test_geometry import lens_eye  # noqa: E402

CONTAINER = "cvat_server"
JOB = int(sys.argv[1]) if len(sys.argv) > 1 else 9


def sh(*args, check=True):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode:
        raise SystemExit(f"Lệnh lỗi: {' '.join(args)}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def django(code):
    out = sh("docker", "exec", CONTAINER, "python", "manage.py", "shell", "-c", code)
    return [l for l in out.splitlines() if l and "imported automatically" not in l]


def export(fmt, name, workdir):
    django(f"from cvat.apps.dataset_manager.task import export_job; export_job({JOB}, '/tmp/{name}.zip', format_name='{fmt}')")
    local = os.path.join(workdir, name + ".zip")
    sh("docker", "cp", f"{CONTAINER}:/tmp/{name}.zip", local)
    with zipfile.ZipFile(local) as z:
        z.extract("annotations.xml", os.path.join(workdir, name))
    return os.path.join(workdir, name, "annotations.xml")


def keyframe(spec, frame, cx, cy, rx, ry, tilt, scale_x=1.0, occluded=()):
    full = lens_eye(spec, cx, cy, rx, ry, tilt_deg=tilt, scale_x=scale_x)
    return EyeKey(frame, {i: PointState(full[i], False, i in occluded) for i in spec.ids})


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    wd = tempfile.mkdtemp(prefix="eyepin_rt_")
    try:
        count = django(f"from cvat.apps.engine.models import LabeledShape, LabeledTrack; print(LabeledShape.objects.filter(job_id={JOB}).count() + LabeledTrack.objects.filter(job_id={JOB}).count())")[-1]
        if count != "0":
            raise SystemExit(f"Job {JOB} không trống ({count} đối tượng); chọn job trống để khỏi mất nhãn.")
        base = export("CVAT for images 1.1", "base_images", wd)
        ann = cvatxml.parse(base)
        n_frames = len(ann.frame_names)
        print(f"Job {JOB}: {n_frames} frame, nền xuất từ CVAT for images")

        mattrai, matphai = EYES["mattrai"], EYES["matphai"]
        track = EyeTrack("mattrai", keys={
            0: keyframe(mattrai, 0, 300, 300, 22, 7, 0),
            30: keyframe(mattrai, 30, 320, 304, 18, 7, 4, scale_x=0.8, occluded=(18, 17, 19)),
            60: keyframe(mattrai, 60, 340, 298, 24, 6, -3),
            n_frames - 1: keyframe(mattrai, n_frames - 1, 345, 300, 24, 6, -3),
        })
        shapes = {"matphai": {5: keyframe(matphai, 5, 450, 300, 22, 7, 0), 6: keyframe(matphai, 6, 452, 301, 22, 7, 1)}}
        out = os.path.join(wd, "to_import.xml")
        cvatxml.write_eyes(ann, out, new_tracks={"mattrai": track}, new_shapes=shapes)

        sh("docker", "cp", out, f"{CONTAINER}:/tmp/to_import.xml")
        django(f"from cvat.apps.dataset_manager.task import import_job_annotations; import_job_annotations('/tmp/to_import.xml', {JOB}, 'CVAT 1.1', False)")
        print("Đã import file do tool ghi (1 track mattrai + 2 shape matphai)")

        video = cvatxml.parse(export("CVAT for video 1.1", "after_video", wd))
        images = cvatxml.parse(export("CVAT for images 1.1", "after_images", wd))
        got = video.tracks["mattrai"]
        assert len(got) == 1, f"mong 1 track mattrai, CVAT có {len(got)}"
        cv = got[0].keys

        worst, bad_occ, partial = 0.0, [], []
        for f in range(n_frames):
            ours = position_at(track.keys, f, mattrai.ids)
            theirs = cv.get(f)
            if ours is None or theirs is None:
                if (ours is None) != (theirs is None):
                    bad_occ.append((f, "tồn tại khác nhau"))
                continue
            for i in mattrai.ids:
                worst = max(worst, math.dist(ours.points[i].xy, theirs.points[i].xy))
                if ours.points[i].occluded != theirs.points[i].occluded:
                    bad_occ.append((f, i))
        kf_frames = sorted(f for f, k in cv.items() if k.keyframe)
        print(f"Track mattrai: lệch lớn nhất giữa bản xem trước và CVAT = {worst:.4f} px trên {n_frames} frame")
        print(f"Cờ Occluded khác nhau: {len(bad_occ)} (mong 0) {bad_occ[:5]}")
        print(f"Keyframe CVAT ghi nhận: {kf_frames} (đã ghi {sorted(track.keys)})")
        for f in kf_frames:
            if len(cv[f].points) != 8:
                partial.append(f)
        print(f"Keyframe không đủ 8 điểm: {partial} (mong rỗng)")

        shp = images.shapes["matphai"]
        sh_worst = max(math.dist(shapes["matphai"][f].points[i].xy, shp[f].points[i].xy)
                       for f in shapes["matphai"] for i in matphai.ids)
        print(f"Shape matphai: frame có shape {sorted(shp)} (đã ghi {sorted(shapes['matphai'])}); lệch lớn nhất {sh_worst:.4f} px")

        ok = worst < 0.02 and not bad_occ and not partial and sorted(shp) == sorted(shapes["matphai"]) and sh_worst < 0.02
        print("KẾT QUẢ:", "ĐẠT" if ok else "KHÔNG ĐẠT")
        return 0 if ok else 1
    finally:
        django(f"from cvat.apps.dataset_manager.task import JobAnnotation; JobAnnotation({JOB}).delete()")
        shutil.rmtree(wd, ignore_errors=True)
        print(f"Đã dọn nhãn trong job {JOB}")


if __name__ == "__main__":
    sys.exit(main())
