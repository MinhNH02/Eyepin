"""Kiểm hành vi Shape mắt trên CVAT local (không cần khoá API: đi qua `docker exec cvat_server python manage.py shell`).

Trả lời năm câu hỏi của Task 1 (design/2026-11-18-shape-plan), và đối chiếu hai giả định về dạng dữ liệu CVAT mà
`eyepin/cvatsync.py` dựa vào (`_json_eye_shapes`, `_shape_tracks`):

  1. file "CVAT for video" (có <meta>, không có <image>) thêm một <image id name width height> chứa skeleton mắt: import được không,
     shape nằm đúng frame không
  2. <image> có name sai / id sai: CVAT đặt shape ở frame nào
  3. outside / occluded ở từng <points> có giữ không; thuộc tính outside trên thẻ <skeleton> của shape có gây lỗi không
  4. JSON của một shape skeleton (nguyên `shapes[0]`)
  5. bản xuất "CVAT for video" của job có 1 track mắt + 2 shape mắt cùng nhãn

AN TOÀN: chỉ làm việc với MỘT job (mặc định 5, CVAT local, dữ liệu công khai). Từ chối chạy nếu job có bất kỳ shape, track hay tag nào;
mỗi phép thử xong và trong `finally` đều xoá sạch job bằng cách import file rỗng rồi kiểm lại về 0.

Chạy:  python spike\\cvat_shape_check.py [job_id=5]      Thoát mã 2 khi job không trống, mã 1 khi có giả định sai.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from eyepin import cvatsync, cvatxml  # noqa: E402
from eyepin.cvatxml import EyeKey, EyeShape, EyeTrack, PointState  # noqa: E402
from eyepin.geometry import EYES, derive  # noqa: E402

CONTAINER = "cvat_server"
JOB = int(sys.argv[1]) if len(sys.argv) > 1 else 5
EMPTY_XML = "<annotations><version>1.1</version></annotations>"
MARK = "@@"                      # tiền tố dòng kết quả, để lọc khỏi dòng thông báo của Django

wrong: list[str] = []            # các giả định bị sai


def sh(*args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(f"Lệnh lỗi: {' '.join(args[:6])}...\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r.stdout


def django(code):
    out = sh("docker", "exec", CONTAINER, "python", "manage.py", "shell", "-c", code)
    return [l for l in out.splitlines() if l and "imported automatically" not in l]


def django_json(code):
    """Chạy `code` (phải gọi `emit(obj)` đúng một lần) và trả đối tượng JSON."""
    pre = f"import json\ndef emit(o): print('{MARK}' + json.dumps(o, default=str))\n"
    lines = [l for l in django(pre + code) if l.startswith(MARK)]
    return json.loads(lines[-1][len(MARK):])


def counts():
    return django_json(
        "from cvat.apps.engine.models import LabeledShape, LabeledTrack, LabeledImage\n"
        f"emit([LabeledShape.objects.filter(job_id={JOB}).count(), LabeledTrack.objects.filter(job_id={JOB}).count(), "
        f"LabeledImage.objects.filter(job_id={JOB}).count()])")


def job_info():
    """Tên ảnh, cỡ ảnh, nhãn (đúng dạng `GET /api/labels`, có sublabels) và số frame của job."""
    return django_json(
        "from cvat.apps.engine.models import Job\n"
        "from cvat.apps.engine.serializers import LabelSerializer\n"
        f"j = Job.objects.get(pk={JOB}); t = j.segment.task\n"
        "imgs = list(t.data.images.all().order_by('frame'))\n"
        "emit({'start': j.segment.start_frame, 'stop': j.segment.stop_frame, 'task': t.id,\n"
        " 'names': [i.path for i in imgs], 'size': [imgs[0].width, imgs[0].height],\n"
        " 'labels': [LabelSerializer(l).data for l in t.get_labels()]})")


def annotations_json():
    """Đúng dữ liệu `GET /api/jobs/{id}/annotations` trả (`JobViewSet.annotations`: Response(dm.task.get_job_data(pk)))."""
    return django_json(f"from cvat.apps.dataset_manager.task import get_job_data\nemit(get_job_data({JOB}))")


def import_xml(path, name):
    sh("docker", "cp", path, f"{CONTAINER}:/tmp/{name}.xml")
    django(f"from cvat.apps.dataset_manager.task import import_job_annotations; import_job_annotations('/tmp/{name}.xml', {JOB}, 'CVAT 1.1', False)")


def export(fmt, name, wd):
    django(f"from cvat.apps.dataset_manager.task import export_job; export_job({JOB}, '/tmp/{name}.zip', format_name='{fmt}')")
    local = os.path.join(wd, name + ".zip")
    sh("docker", "cp", f"{CONTAINER}:/tmp/{name}.zip", local)
    with zipfile.ZipFile(local) as z:
        z.extract("annotations.xml", os.path.join(wd, name))
    return os.path.join(wd, name, "annotations.xml")


def clear(wd, why=""):
    empty = os.path.join(wd, "empty.xml")
    with open(empty, "w", encoding="utf-8") as fh:
        fh.write(EMPTY_XML)
    import_xml(empty, "empty")
    c = counts()
    if c != [0, 0, 0]:
        raise SystemExit(f"Job {JOB} CHƯA sạch sau khi dọn{why}: shape/track/tag = {c}. Dọn tay: delete_job_data({JOB}).")


def heading(n, text):
    print(f"\n=== {n}. {text}")


def verdict(name, ok, detail):
    print(f"[{'ĐÚNG' if ok else 'SAI'}] {name}: {detail}")
    if not ok:
        wrong.append(name)


# ---- dựng dữ liệu thử ----

def eye(label, cx, cy, w=36.0, h=9.0):
    """8 điểm của một mắt thẳng (lấy 4 điểm ghim rồi suy phần còn lại như EyePin)."""
    spec = EYES[label]
    pins = {spec.first: (cx - w / 2, cy), spec.last: (cx + w / 2, cy),
            spec.up: (cx - w * 0.02, cy - h), spec.lo: (cx + w * 0.0, cy + h * 0.7)}
    return derive(spec, pins)


def key(label, frame, cx, cy, flags=None, outside=False):
    pts = eye(label, cx, cy)
    flags = flags or {}
    return EyeKey(frame, {i: PointState(pts[i], flags.get(i) == "outside", flags.get(i) == "occluded") for i in EYES[label].ids}, True, outside)


def sk_xml(label, frame_pts, sk_attrs="", flags=None):
    """Thẻ <skeleton> của shape, viết tay: `flags` {điểm: (outside, occluded)}."""
    flags = flags or {}
    spec = EYES[label]
    rows = []
    for i in spec.ids:
        o, c = flags.get(i, (0, 0))
        x, y = frame_pts[i]
        rows.append(f'      <points label="{i}" source="manual" outside="{o}" occluded="{c}" points="{x:.2f},{y:.2f}"/>')
    return (f'    <skeleton label="{label}" source="manual" {sk_attrs} occluded="0" z_order="0">\n' + "\n".join(rows) + "\n    </skeleton>")


def image_xml(img_id, name, size, body):
    return f'  <image id="{img_id}" name="{name}" width="{size[0]}" height="{size[1]}">\n{body}\n  </image>'


def write_text(wd, name, images):
    p = os.path.join(wd, name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("<annotations>\n  <version>1.1</version>\n" + "\n".join(images) + "\n</annotations>\n")
    return p


def all_outside(k):
    """Bản xuất video của CVAT không ghi `outside` trên thẻ <skeleton>: skeleton "Outside" là khi cả 8 điểm Outside."""
    return k.outside or all(p.outside for p in k.points.values())


def proposed_shape_tracks(tracks, sent):
    """`cvatsync._shape_tracks` sau khi sửa: nhận Outside bằng `all_outside` (cả 8 điểm), không dùng `EyeKey.outside` của thẻ skeleton."""
    cands = {}
    for t in tracks:
        real = [f for f, k in t.keys.items() if not all_outside(k)]
        if len(real) == 1 and t.keys[real[0]].keyframe:
            cands.setdefault(real[0], []).append(t)
    drop = []
    for sh in sent:
        pool = cands.get(sh.key.frame)
        if pool:
            best = min(pool, key=lambda t: cvatsync._key_dist(sh.key, t.keys[sh.key.frame]))
            pool.remove(best)
            drop.append(best)
    return drop


def shape_frames(aj, label_ids):
    """[(frame, tên nhãn)] của các shape skeleton trong JSON."""
    return sorted((s["frame"], label_ids.get(s["label_id"], s["label_id"])) for s in aj.get("shapes", []))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    c = counts()
    if c != [0, 0, 0]:
        print(f"Job {JOB} không trống (shape/track/tag = {c}); từ chối chạy để khỏi mất nhãn. Chọn job trống.")
        raise SystemExit(2)
    info = job_info()
    names, size, labels = info["names"], info["size"], info["labels"]
    label_ids = {lb["id"]: lb["name"] for lb in labels}
    print(f"Job {JOB}: task {info['task']}, frame {info['start']}..{info['stop']}, {len(names)} ảnh {size[0]}x{size[1]}, "
          f"ảnh đầu {names[0]}; nhãn {label_ids}")
    wd = tempfile.mkdtemp(prefix="eyepin_shape_check_")
    try:
        # ---------- 1 ----------
        heading(1, 'Bản xuất "CVAT for video" (có <meta>, không <image>) + <image> mới chứa shape mắt')
        base = export("CVAT for video 1.1", "base_video", wd)
        ann = cvatxml.parse(base)
        root = ET.parse(base).getroot()
        print(f"Bản xuất rỗng: meta={'có' if root.find('meta') is not None else 'KHÔNG'}, <image>={len(root.findall('image'))}, "
              f"<track>={len(root.findall('track'))}; original_size={ann.width}x{ann.height}")
        sent = [EyeShape("mattrai", key("mattrai", 3, 300, 250), {"id": "1"}),
                EyeShape("matphai", key("matphai", 7, 400, 250), {"id": "10"})]
        f1 = os.path.join(wd, "shape_from_video.xml")
        cvatxml.write_eyes(ann, f1, new_shapes=sent, frame_names=names, size=tuple(size))
        print("Phần <image> đã tạo trong file gửi:")
        print(ET.tostring(ET.parse(f1).getroot().find("image"), encoding="unicode")[:700], "...")
        import_xml(f1, "t1")
        aj = annotations_json()
        got = shape_frames(aj, label_ids)
        verdict("1. shape ở đúng frame sau import", got == [(3, "mattrai"), (7, "matphai")] and not aj["tracks"],
                f"JSON: shapes (frame, nhãn) = {got}; tracks={len(aj['tracks'])}")
        shape0 = aj["shapes"][0]
        print("JSON shapes[0] (nguyên):")
        print(json.dumps(shape0, indent=1, ensure_ascii=False))
        # 4 + giả định 1: dạng JSON mà cvatsync đọc
        parsed = cvatsync._json_eye_shapes(aj, labels)
        ok = sorted((n, f) for n, f, _ in parsed) == [("matphai", 7), ("mattrai", 3)] and all(len(p) == 8 for _, _, p in parsed)
        okpts = True
        for n, f, p in parsed:
            want = next(sh for sh in sent if sh.label == n).key.points
            okpts &= all(abs(p[i][0][0] - want[i].xy[0]) < 0.01 and abs(p[i][0][1] - want[i].xy[1]) < 0.01 for i in p)
        verdict("giả định 1 (JSON, _json_eye_shapes)", ok and okpts,
                f"_json_eye_shapes đọc ra {[(n, f, len(p)) for n, f, p in parsed]}; toạ độ khớp gửi={okpts}; "
                f"khoá element = {sorted(shape0['elements'][0])}; "
                f"frame là số tương đối của job={'có' if shape0['frame'] == 3 else 'KHÔNG'}")
        # bản xuất video của đúng hai shape này (câu 5 phần shape, giả định 2)
        vid = export("CVAT for video 1.1", "video_two_shapes", wd)
        vroot = ET.parse(vid).getroot()
        print('Bản xuất "CVAT for video" của job chỉ có hai shape: '
              f"<track>={len(vroot.findall('track'))}, <image>={len(vroot.findall('image'))}")
        tr0 = next(t for t in vroot.findall("track") if t.get("label") == "mattrai")
        print("Một shape mattrai (frame 3) trong bản xuất video (nguyên thẻ <track>):")
        print(ET.tostring(tr0, encoding="unicode").rstrip())
        vp = cvatxml.parse(vid)
        mine = [t for t in vp.tracks["mattrai"]]
        shape_like = {l: cvatsync._shape_tracks(vp.tracks[l], [s for s in sent if s.label == l]) for l in EYES}
        verdict("giả định 2 (_shape_tracks nhận ra track sinh từ shape)",
                all(len(shape_like[l]) == 1 for l in EYES) and len(vp.tracks["mattrai"]) == 1,
                f"mattrai: {[(f, k.outside, k.keyframe) for f, k in sorted(mine[0].keys.items())]}; "
                f"_shape_tracks nhận {[len(v) for v in shape_like.values()]} track")
        prop = {l: proposed_shape_tracks(vp.tracks[l], [s for s in sent if s.label == l]) for l in EYES}
        verdict("giả định 2 sau khi sửa (all_outside)", all(len(prop[l]) == 1 for l in EYES),
                f"proposed_shape_tracks nhận {[len(v) for v in prop.values()]} track")
        print(f"  (EyeKey.outside của track sinh từ shape ở frame kế = {mine[0].keys[4].outside}; "
              f"điểm Outside = {sum(p.outside for p in mine[0].keys[4].points.values())}/8)")
        clear(wd)

        # ---------- 2 ----------
        heading(2, "<image> có name/id lệch nhau: CVAT đặt shape ở frame nào")
        pts = eye("mattrai", 300, 250)
        cases = [("name đúng (frame 20), id sai (11)", 11, names[20], 20),
                 ("name SAI (không có trong task), id đúng (12)", 12, "khong_co_anh_nay.jpg", 12),
                 ("name frame 30, id frame 31 (hai bên mâu thuẫn)", 31, names[30], 30)]
        for desc, img_id, nm, expect in cases:
            p = write_text(wd, "t2.xml", [image_xml(img_id, nm, size, sk_xml("mattrai", pts, 'outside="0"'))])
            try:
                import_xml(p, "t2")
                where = [f for f, _ in shape_frames(annotations_json(), label_ids)]
                print(f"  {desc}: shape ở frame {where} (mong theo mã nguồn: {expect})")
                r = f"frame {where}"
            except SystemExit as e:
                print(f"  {desc}: import LỖI: {str(e)[-300:].strip()}")
                r = "lỗi import"
            finally:
                clear(wd)
            print(f"  -> kết luận: {r}")

        # ---------- 3 ----------
        heading(3, "Cờ outside / occluded ở từng <points>; outside trên thẻ <skeleton>")
        flags = {14: (0, 1), 16: (1, 0), 18: (1, 1), 20: (0, 0)}
        for desc, attrs in (("outside=\"0\" trên <skeleton>", 'outside="0"'), ("outside=\"1\" trên <skeleton>", 'outside="1"')):
            p = write_text(wd, "t3.xml", [image_xml(5, names[5], size, sk_xml("mattrai", pts, attrs, flags))])
            try:
                import_xml(p, "t3")
                aj = annotations_json()
                shp = aj["shapes"]
                els = {}
                for el in (shp[0]["elements"] if shp else []):
                    els[el["label_id"]] = (el["occluded"], el["outside"])
                sub = cvatsync._sublabel_points(labels)
                byp = {sub[k][1]: v for k, v in els.items() if k in sub}
                keep = {i: (bool(o), bool(c)) for i, (o, c) in flags.items()}
                got = {i: (byp[i][1], byp[i][0]) for i in flags if i in byp}        # (outside, occluded)
                print(f"  {desc}: import OK, {len(shp)} shape; thuộc tính shape: occluded={shp[0].get('occluded')}, outside={shp[0].get('outside')}")
                print(f"    cờ gửi (outside,occluded) {{điểm: ...}} = {keep}")
                print(f"    cờ CVAT giữ                          = {got}")
                same = {i: (bool(o), bool(c)) for i, (o, c) in flags.items()} == {i: (bool(o), bool(c)) for i, (o, c) in got.items()}
                pt = {i: byp[i] for i in byp}
                verdict(f"3. cờ từng điểm giữ nguyên ({desc})", same, f"{'khớp' if same else 'LỆCH'}")
                p14 = [el["points"] for el in shp[0]["elements"] if el["label_id"] == next(k for k, v in sub.items() if v[1] == 16)]
                print(f"    toạ độ điểm 16 (outside=1) vẫn lưu: {p14}")
            except SystemExit as e:
                print(f"  {desc}: import LỖI: {str(e)[-300:].strip()}")
                verdict(f"3. {desc} không gây lỗi", False, "import lỗi")
            finally:
                clear(wd)

        # ---------- 5 ----------
        heading(5, 'Job có 1 track mắt + 2 shape mắt cùng nhãn: bản xuất "CVAT for video"')
        track = EyeTrack("mattrai", {0: key("mattrai", 0, 300, 250), 20: key("mattrai", 20, 320, 255)}, {"id": "1"})
        shapes5 = [EyeShape("mattrai", key("mattrai", 3, 500, 300), {"id": "10"}),
                   EyeShape("mattrai", key("mattrai", 7, 510, 305), {"id": "19"})]
        f5 = os.path.join(wd, "mixed.xml")
        cvatxml.write_eyes(ann, f5, new_tracks=[track], new_shapes=shapes5, frame_names=names, size=tuple(size))
        import_xml(f5, "t5")
        aj = annotations_json()
        print(f"  JSON: {len(aj['tracks'])} track ({[[s['frame'] for s in t['shapes']] for t in aj['tracks']]}), "
              f"shape ở frame {[s['frame'] for s in aj['shapes']]}")
        vid = export("CVAT for video 1.1", "video_mixed", wd)
        vp = cvatxml.parse(vid)
        print(f"  Bản xuất video: {len(vp.tracks['mattrai'])} track mattrai")
        for t in sorted(vp.tracks["mattrai"], key=lambda t: min(t.keys)):
            nonout = [f for f, k in sorted(t.keys.items()) if not all_outside(k)]
            kfs = [f for f, k in sorted(t.keys.items()) if k.keyframe]
            outs = [f for f, k in sorted(t.keys.items()) if all_outside(k)]
            print(f"    track id={t.attrs.get('id')}: {len(t.keys)} skeleton; keyframe ở {kfs}; không-Outside ở "
                  f"{nonout[0]}..{nonout[-1]} ({len(nonout)} frame); Outside ở {outs[:3]}{'...' if len(outs) > 3 else ''}")
        drop = cvatsync._shape_tracks(vp.tracks["mattrai"], shapes5)
        print(f"  _shape_tracks nhận {len(drop)} track là sinh từ shape, ở frame "
              f"{sorted(min(f for f, k in t.keys.items() if not k.outside) for t in drop)}")
        remain = [t for t in vp.tracks["mattrai"] if all(t is not d for d in drop)]
        verdict("giả định 2 (hỗn hợp track + 2 shape)",
                len(drop) == 2 and len(remain) == 1 and sorted(remain[0].keys)[0] == 0 and sorted(f for f, k in remain[0].keys.items() if k.keyframe) == [0, 20],
                f"{len(vp.tracks['mattrai'])} track trong bản xuất, bỏ {len(drop)} track sinh từ shape, còn {len(remain)} track thật")
        drop2 = proposed_shape_tracks(vp.tracks["mattrai"], shapes5)
        remain2 = [t for t in vp.tracks["mattrai"] if all(t is not d for d in drop2)]
        verdict("giả định 2 hỗn hợp sau khi sửa (all_outside)",
                len(drop2) == 2 and len(remain2) == 1 and sorted(f for f, k in remain2[0].keys.items() if k.keyframe) == [0, 20],
                f"bỏ {len(drop2)} track sinh từ shape (frame {sorted(min(f for f, k in t.keys.items() if not all_outside(k)) for t in drop2)}), "
                f"còn {len(remain2)} track thật")
        # chạy cả phép đối chiếu của cvatsync trên dữ liệu thật
        msgs = cvatsync._compare_shapes(aj, labels, {"mattrai": shapes5, "matphai": []}, set(), list(range(info["start"], info["stop"] + 1)))
        verdict("_compare_shapes trên JSON thật", msgs == [], f"{msgs or 'không lệch'}")
        clear(wd)

        # ---------- 6 ----------
        heading(6, "Phụ: shape ở frame CUỐI của job (frame kế không tồn tại) trong bản xuất video")
        last = len(names) - 1
        last_shape = [EyeShape("mattrai", key("mattrai", last, 300, 250), {"id": "1"})]
        f6 = os.path.join(wd, "last.xml")
        cvatxml.write_eyes(ann, f6, new_shapes=last_shape, frame_names=names, size=tuple(size))
        import_xml(f6, "t6")
        vroot = ET.parse(export("CVAT for video 1.1", "video_last", wd)).getroot()
        for t in vroot.findall("track"):
            fr = [(int(s.get("frame")), s.find("points").get("outside")) for s in t.findall("skeleton")]
            print(f"  track mattrai: skeleton (frame, outside của điểm đầu) = {fr}")
        vp6 = cvatxml.parse(os.path.join(wd, "video_last", "annotations.xml"))
        drop6 = proposed_shape_tracks(vp6.tracks["mattrai"], last_shape)
        verdict("shape ở frame cuối, proposed_shape_tracks", len(drop6) == 1, f"nhận {len(drop6)} track")
        print("  Bước 3 (giao diện web): script không điều khiển trình duyệt; xem ghi chú trong design/cvat-api-notes.md (nút thẻ shape đã kiểm tay qua Chrome; phím N chưa kiểm).")
    finally:
        clear(wd, " (finally)")
        shutil.rmtree(wd, ignore_errors=True)
        print(f"\nJob {JOB} sau khi dọn: shape/track/tag = {counts()}")
    print("\n" + ("TẤT CẢ giả định đúng." if not wrong else "GIẢ ĐỊNH SAI: " + "; ".join(wrong)))
    raise SystemExit(1 if wrong else 0)


if __name__ == "__main__":
    main()
