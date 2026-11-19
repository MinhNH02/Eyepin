"""Đối chiếu việc sửa job prelabel với CVAT local thật (cần container cvat_server chạy; job đích phải TRỐNG; dữ liệu công khai).

Quy trình (thiết kế design/2026-11-19-qc-edit-design.md mục 6.10): dựng một job "prelabel" giả bằng 20 frame đầu của prelabel.xml (khớp ảnh job theo `name`, có
vài điểm Occluded, một điểm Outside, và hai frame thiếu shape mattrai), cho CVAT import; tạo một issue thử; đọc JSON annotations và nhãn đúng như
`CvatClient` đọc; nạp bằng `adopt` vào một Session (thư mục ảnh case 01); dời một điểm, chép shape vào một frame thiếu, đặt Occluded cả một đoạn;
đếm thay đổi như `cvatsync.prepare`; dựng file gửi như `cvatsync.send` (nền là bản xuất images đã bỏ nhãn mắt) và import; rồi đọc lại và so:

  Q1  `adopt.check` rỗng với dữ liệu thật; số shape nạp và toạ độ, cờ khớp file đã nhập
  Q2  shape chưa ai đụng trùng JSON trước khi gửi (không quá 0,01 px, cờ), `count_changes` đếm đúng "giữ" cả job
  Q3  shape sửa và thêm đúng, tổng số shape đúng, shape giữ nguyên còn nguyên, cờ Occluded cả đoạn đúng (điểm Outside không đổi), không có track;
      Q3b bản xuất "CVAT for video" thật: `cvatsync._compare` không báo lệch (đúng phép kiểm `cvatsync.send` chạy sau khi gửi);
      Q3c `adopt.check` trên JSON thật SAU khi gửi rỗng (mở lại job thì EyePin lại nạp được, không rơi vào chế độ chỉ xem)
  Q4  issue đã tạo còn sau import (đếm theo mã issue), cả sau khi gửi lẫn sau khi khôi phục
  Q5  (thông tin) tạo issue có đổi `updated_date` của job không (ảnh hưởng cảnh báo "job đã bị sửa" của `cvatsync.prepare`)
  Q6  bản chụp khôi phục (`cvatsync.adopted_snapshot`) import lại thì JSON về đúng shape mắt lúc trước khi gửi, kể cả điểm Outside, không có track
  Q7  dọn: xoá nhãn của job và đúng issue đã tạo; job về 0 shape, 0 track, 0 tag, issue y như trước

AN TOÀN: job có bất kỳ shape, track hay tag nào thì từ chối chạy và KHÔNG xoá gì (cờ `cleanup` chỉ bật sau khi kiểm job trống); chỉ xoá đúng các issue
script vừa tạo (mã ghi lại ngay khi tạo, xoá trong `finally`). Tên tài khoản CVAT local là địa chỉ email riêng tư: script không in phản hồi thô,
tên đăng nhập hay email, chỉ in dòng kết luận và số đếm. Đường vào CVAT là `docker exec` + `APIClient.force_login` (như tests/verify_issue_report.py),
không đăng nhập HTTP từ ngoài.

Chạy:  python tests\\verify_qc_edit.py [job_id=5] [thư_mục_ảnh] [prelabel.xml]    Thoát mã 0 khi mọi mục (trừ Q5, thông tin) đạt, 1 khi có mục lệch.
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from eyepin import adopt, cvatxml, qc  # noqa: E402
from eyepin.cvatsource import IMAGES, VIDEO, _eye_label_ids, base_format  # noqa: E402
from eyepin.cvatsync import (_compare, _compare_shapes, _expected, _expected_shapes, _json_eye_shapes, _kept_changed,  # noqa: E402
                             adopted_snapshot, count_changes)
from eyepin.cvatxml import EyeShape  # noqa: E402
from eyepin.geometry import EYES  # noqa: E402
from eyepin.session import Session  # noqa: E402

CONTAINER = "cvat_server"
JOB = int(sys.argv[1]) if len(sys.argv) > 1 else 5
FRAMES = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/Downloads/dms_build/cases/01_quay_dau_mat_xa_bi_che")
PRELABEL = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/Downloads/dms_build/prelabel_sample/prelabel.xml")
HOST = "localhost:8080"
MARK = "EYEPIN-VERIFY-QC"
TMP = "qc_edit"                              # tiền tố file tạm trong container (/tmp/qc_edit_*; `docker cp` tạo file của root nên không xoá lại được, như verify_vs_cvat)
TOL = 0.01                                   # px: CVAT chỉ giữ hai chữ số thập phân

N_FRAMES = 20                                # số frame đầu của prelabel.xml đưa vào job
NO_MATTRAI = (5, 12)                         # frame bỏ shape mattrai (thiếu nhãn)
OCCLUDED = {("mattrai", 2): (16,), ("matphai", 10): (24,), ("mattrai", 16): (20,)}     # điểm Occluded trong file nhập
OUT_FRAME, OUT_POINT = 15, 18                # điểm Outside trong file nhập (nằm trong đoạn Occluded cả đoạn)
OUTSIDE = {("mattrai", OUT_FRAME): (OUT_POINT,)}
MOVE_FRAME, MOVE_POINT, MOVE_BY = 8, 14, (1.0, 0.5)    # dời một điểm của một shape mattrai
COPY_FRAME = 5                               # chép shape gần nhất của mattrai vào frame thiếu này
RANGE = (14, 17)                             # Occluded cả đoạn cho cả 8 điểm của mattrai (điểm 18 ở frame 15 là Outside nên không đổi)
ISSUE_FRAME = 3
ISSUE_POSITION = [10.0, 10.0, 50.0, 50.0]

# Chạy trong container (chuỗi đưa vào bằng json.dumps nên đoạn mã chỉ có ký tự ASCII): các yêu cầu API qua APIClient đã đăng nhập tài khoản local đầu tiên.
CONTAINER_CODE = r'''
import json
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

REQS = json.loads(__REQS__)
client = APIClient()
client.force_login(get_user_model().objects.order_by("id").first(), backend="django.contrib.auth.backends.ModelBackend")
out = []
for method, path, data in REQS:
    kw = {"HTTP_HOST": __HOST__}
    if data is not None:
        kw["format"] = "json"
        r = getattr(client, method)(path, data, **kw)
    else:
        r = getattr(client, method)(path, **kw)
    out.append([r.status_code, json.loads(r.content) if r.content else None])
print("EYEPIN_OUT " + json.dumps(out))
'''

results, printed = [], set()


class Failed(Exception):
    """Lỗi của chính script (thông điệp chỉ gồm chữ của script, không kèm dữ liệu CVAT)."""


def verdict(code, ok, text):
    results.append(bool(ok))
    printed.add(code)
    print("%s  %s  %s" % (code, "ĐẠT" if ok else "LỆCH", text))


def scrub(text):
    """Che mọi thứ giống địa chỉ email trước khi in thông báo lỗi của tiến trình ngoài."""
    return re.sub(r"\S+@\S+", "<đã ẩn>", text)


def sh(*args):
    """Chạy một lệnh, trả stdout. Lỗi thì chỉ nêu tên lệnh con và dòng cuối của stderr đã che email (không in stdout: có thể kèm dữ liệu CVAT)."""
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    if r.returncode:
        tail = scrub(r.stderr.strip().splitlines()[-1]) if r.stderr.strip() else ""
        raise Failed("lệnh %s lỗi (mã %d). %s" % (args[1] if len(args) > 1 else args[0], r.returncode, tail))
    return r.stdout


def django(code):
    out = sh("docker", "exec", CONTAINER, "python", "manage.py", "shell", "-c", code)
    return [l for l in out.splitlines() if l and "imported automatically" not in l]


def api(reqs):
    """Gửi một loạt yêu cầu (phương thức, đường dẫn, dữ liệu hoặc None) qua APIClient trong container; trả danh sách (mã trạng thái, nội dung)."""
    code = CONTAINER_CODE.replace("__REQS__", json.dumps(json.dumps(reqs))).replace("__HOST__", json.dumps(HOST))
    r = subprocess.run(["docker", "exec", "-i", CONTAINER, "python", "manage.py", "shell", "-c", "import sys; exec(sys.stdin.read())"],
                       input=code, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    for line in r.stdout.splitlines():
        if line.startswith("EYEPIN_OUT "):
            return [tuple(x) for x in json.loads(line[len("EYEPIN_OUT "):])]
    tail = scrub(r.stderr.strip().splitlines()[-1]) if r.stderr.strip() else ""
    raise Failed("không chạy được đoạn mã API trong container (mã thoát %d). %s" % (r.returncode, tail))


def need(reqs, wants):
    """Như `api` nhưng mỗi mã trạng thái phải đúng `wants` (cùng độ dài); trả danh sách nội dung."""
    out = api(reqs)
    for (method, path, _), (status, _body), want in zip(reqs, out, wants):
        if status != want:
            raise Failed("%s %s trả %s, cần %s" % (method.upper(), path.split("?")[0], status, want))
    return [body for _status, body in out]


def job_counts():
    """(shape, track, tag) của job trong cơ sở dữ liệu CVAT."""
    lines = django("from cvat.apps.engine.models import LabeledShape, LabeledTrack, LabeledImage; "
                   f"print('EYEPIN_N', LabeledShape.objects.filter(job_id={JOB}).count(), LabeledTrack.objects.filter(job_id={JOB}).count(), "
                   f"LabeledImage.objects.filter(job_id={JOB}).count())")
    line = next(l for l in lines if l.startswith("EYEPIN_N "))
    return tuple(int(v) for v in line.split()[1:])


def export(fmt, name, wd):
    """Bản xuất `fmt` của job: nội dung annotations.xml (bytes)."""
    django(f"from cvat.apps.dataset_manager.task import export_job; export_job({JOB}, '/tmp/{TMP}_{name}.zip', format_name='{fmt}')")
    local = os.path.join(wd, name + ".zip")
    sh("docker", "cp", f"{CONTAINER}:/tmp/{TMP}_{name}.zip", local)
    with zipfile.ZipFile(local) as z:
        return z.read("annotations.xml")


def import_file(path, name):
    """Nạp file XML (import thay TOÀN BỘ nhãn của job)."""
    sh("docker", "cp", path, f"{CONTAINER}:/tmp/{TMP}_{name}.xml")
    django(f"from cvat.apps.dataset_manager.task import import_job_annotations; import_job_annotations('/tmp/{TMP}_{name}.xml', {JOB}, 'CVAT 1.1', False)")


def read_job():
    """Đúng những gì `cvatsource.open_job` / `cvatsync.prepare` đọc: job, JSON annotations, nhãn, meta, và danh sách mã issue của job."""
    job, aj, labels, meta, issues = need([("get", f"/api/jobs/{JOB}", None), ("get", f"/api/jobs/{JOB}/annotations", None),
                                          ("get", f"/api/labels?job_id={JOB}&page_size=100", None), ("get", f"/api/jobs/{JOB}/data/meta", None),
                                          ("get", f"/api/issues?job_id={JOB}&page_size=all", None)], [200] * 5)
    return {"job": job, "aj": aj, "labels": labels["results"], "meta": meta, "issues": sorted(i["id"] for i in issues["results"])}


def pts_of(sh):
    """EyeShape -> {điểm: ((x, y), occluded, outside)}, dạng của `cvatsync._json_eye_shapes`."""
    return {p: (tuple(ps.xy), ps.occluded, ps.outside) for p, ps in sh.key.points.items()}


def flag(occ, out):
    return "outside" if out else ("occluded" if occ else None)


def diff(a, b):
    """(độ lệch lớn nhất px, số điểm khác cờ) giữa hai bộ điểm dạng `_json_eye_shapes`; khác tập điểm thì (inf, 8)."""
    if set(a) != set(b):
        return math.inf, len(EYES["mattrai"].ids)
    return (max(math.dist(a[p][0], b[p][0]) for p in a),
            sum(1 for p in a if flag(a[p][1], a[p][2]) != flag(b[p][1], b[p][2])))


def adopted_pts(sh):
    """AdoptedShape -> bộ điểm dạng `_json_eye_shapes`."""
    return {p: (xy, sh.flags.get(p) == "occluded", sh.flags.get(p) == "outside") for p, xy in sh.points.items()}


def same(a, b):
    d, f = diff(a, b)
    return d <= TOL and f == 0


def keyed(aj, labels):
    """{(tên mắt, số frame của job): bộ điểm} của shape mắt trong JSON; hai shape cùng khoá là lỗi dữ liệu thử."""
    out = {}
    for name, jf, pts in _json_eye_shapes(aj, labels):
        if (name, jf) in out:
            raise Failed(f"hai shape {name} cùng ở frame {jf}")
        out[(name, jf)] = pts
    return out


def eye_tracks(aj, labels):
    eye = _eye_label_ids(labels)
    return [t for t in aj.get("tracks") or [] if t.get("label_id") in eye]


def build_import(base_ann, wd):
    """File import "prelabel" giả: 20 frame đầu của prelabel.xml trên nền là bản xuất images (rỗng) của job. Trả (đường dẫn, {(nhãn, frame): bộ điểm})."""
    pre = cvatxml.parse(PRELABEL)
    for f in range(N_FRAMES):
        if pre.frame_names.get(f) != base_ann.frame_names.get(f):
            raise Failed(f"tên ảnh frame {f} của prelabel.xml không khớp ảnh của job (khớp theo name)")
    shapes = []
    for label in EYES:
        for f in range(N_FRAMES):
            if label == "mattrai" and f in NO_MATTRAI:
                continue
            key = pre.shapes[label][f]
            for pid in OCCLUDED.get((label, f), ()):
                key.points[pid].occluded = True
            for pid in OUTSIDE.get((label, f), ()):
                key.points[pid].outside = True
            shapes.append(EyeShape(label, key))
    path = os.path.join(wd, "prelabel_import.xml")
    cvatxml.write_eyes(base_ann, path, new_shapes=shapes)
    return path, {(sh.label, sh.key.frame): pts_of(sh) for sh in shapes}


def main():
    if shutil.which("docker") is None:
        raise SystemExit("Không thấy lệnh docker.")
    wd = tempfile.mkdtemp(prefix="eyepin_qc_edit_")
    state = {"cleanup": False, "created": [], "existing": None}
    try:
        counts = job_counts()
        if any(counts):
            raise SystemExit(f"Job {JOB} không trống ({counts[0]} shape, {counts[1]} track, {counts[2]} tag); chọn job trống để khỏi mất nhãn. Không xoá gì.")
        state["cleanup"] = True                 # chỉ từ đây mới dọn job: chạy nhầm vào job có nhãn thì từ chối và KHÔNG xoá gì
        try:
            run(wd, state)
        except Failed as exc:
            print("Lỗi: %s" % exc)
            results.append(False)
        except Exception as exc:                # không in nội dung lỗi: có thể kèm dữ liệu CVAT
            tb = exc.__traceback__
            while tb.tb_next:
                tb = tb.tb_next
            print("Lỗi không mong đợi: %s ở dòng %d" % (type(exc).__name__, tb.tb_lineno))
            results.append(False)
        for code in ("Q1", "Q2", "Q3", "Q3b", "Q3c", "Q4", "Q6"):
            if code not in printed:
                verdict(code, False, "không kiểm được (dừng trước đó)")
    finally:
        if state["cleanup"]:
            clean(wd, state)
        shutil.rmtree(wd, ignore_errors=True)


def clean(wd, state):
    """Q7: xoá nhãn của job và đúng các issue đã tạo, rồi kiểm job về trống và issue như trước. Không ném lỗi."""
    problems = []
    try:
        django(f"from cvat.apps.dataset_manager.task import JobAnnotation; JobAnnotation({JOB}).delete()")
    except Exception as exc:
        problems.append("xoá nhãn lỗi " + type(exc).__name__)
    undeleted = []
    for iid in state["created"]:
        try:
            need([("delete", f"/api/issues/{iid}", None)], [204])
        except Exception:
            undeleted.append(iid)
    counts, issues = None, None
    try:
        counts = job_counts()
        issues = read_job()["issues"]
    except Exception as exc:
        problems.append("đọc lại lỗi " + type(exc).__name__)
    existing = state["existing"]
    ok = (not problems and not undeleted and counts == (0, 0, 0) and (existing is None or issues == existing))
    verdict("Q7", ok, "job còn %s shape, track, tag; issue còn %s (ban đầu %s); issue chưa xoá được %d%s"
            % ("/".join(map(str, counts)) if counts else "?", len(issues) if issues is not None else "?",
               len(existing) if existing is not None else "?", len(undeleted), ("; " + ", ".join(problems)) if problems else ""))


def run(wd, state):
    # ---- nhập job prelabel giả ----
    first = read_job()
    state["existing"] = first["issues"]
    job = first["job"]
    nums = list(range(int(job["start_frame"]), int(job["stop_frame"]) + 1))
    base_ann = cvatxml.parse_bytes(export("CVAT for images 1.1", "empty", wd), nums)      # job trống: chỉ có <image> của từng frame
    path, imported = build_import(base_ann, wd)
    import_file(path, "prelabel")

    # ---- tạo một issue thử, ghi updated_date trước và sau ----
    before_job, created, after_job = api([("get", f"/api/jobs/{JOB}", None),
                                          ("post", "/api/issues", {"job": JOB, "frame": ISSUE_FRAME, "position": ISSUE_POSITION, "message": MARK + " issue thử"}),
                                          ("get", f"/api/jobs/{JOB}", None)])
    if created[0] == 201:
        state["created"].append(created[1]["id"])        # ghi mã ngay khi tạo: `finally` xoá đúng issue này
    if before_job[0] != 200 or created[0] != 201 or after_job[0] != 200:
        raise Failed("không tạo được issue thử (%s)" % [before_job[0], created[0], after_job[0]])
    issue_id = created[1]["id"]
    moved = before_job[1].get("updated_date") != after_job[1].get("updated_date")
    q5 = "Q5  (thông tin)  tạo issue %s updated_date của job%s" % (
        "ĐỔI" if moved else "không đổi", ": cvatsync.prepare sẽ hiện cảnh báo 'job đã bị sửa' nếu issue được thêm sau khi mở job" if moved else "")

    # ---- mở job như cvatsource.open_job: JSON, nhãn, bản xuất nền, adopt.check, nạp ----
    opened = read_job()
    aj, labels = opened["aj"], opened["labels"]
    eye_ids = _eye_label_ids(labels)
    deleted = {int(f) for f in opened["meta"].get("deleted_frames") or []}
    base, _display = base_format(aj, eye_ids)
    s = Session(FRAMES)
    s.ann = cvatxml.parse_bytes(export(base, "open", wd), nums)
    reasons = adopt.check(aj, labels, nums, deleted)
    adopted = adopt.eye_shapes(aj, labels, nums) if not reasons else []
    exp_keys = {(label, nums[f]) for label, f in imported}
    got_keys = {(sh.label, nums[sh.frame]) for sh in adopted}
    dev_flag = [diff(adopted_pts(sh), imported[(sh.label, sh.frame)]) for sh in adopted if (sh.label, sh.frame) in imported]
    q1 = (not reasons and base == IMAGES and len(adopted) == len(imported) and got_keys == exp_keys
          and len(dev_flag) == len(imported) and all(d <= TOL and f == 0 for d, f in dev_flag))
    verdict("Q1", q1, "adopt.check %s lý do, nạp %d/%d shape (nền %s), lệch lớn nhất so với file đã nhập %.4f px, %d điểm khác cờ"
            % (len(reasons), len(adopted), len(imported), "images" if base == IMAGES else "KHÁC images",
               max((d for d, _ in dev_flag), default=math.nan), sum(f for _, f in dev_flag)))
    if reasons:
        raise Failed("adopt.check không rỗng: %d lý do" % len(reasons))
    s.adopt(adopted)

    # ---- Q2: shape chưa ai đụng trùng JSON ----
    server = _json_eye_shapes(aj, labels)
    sent0 = s.build_shapes()
    c0, _kept0 = count_changes(sent0, server, nums)
    before = keyed(aj, labels)
    per = [diff(pts_of(sh), before[(sh.label, nums[sh.key.frame])]) for sh in sent0 if (sh.label, nums[sh.key.frame]) in before]
    n = len(imported)
    verdict("Q2", s.adopted and not s.qc and len(per) == len(sent0) == n and all(d <= TOL and f == 0 for d, f in per)
            and c0 == {"server": n, "kept": n, "edited": 0, "added": 0, "removed": 0},
            "%d/%d shape của phiên trùng JSON (lệch lớn nhất %.4f px, %d điểm khác cờ); count_changes %s"
            % (len(per), n, max((d for d, _ in per), default=math.nan), sum(f for _, f in per), c0))

    # ---- sửa: dời một điểm, chép vào frame thiếu, Occluded cả đoạn ----
    x, y = s.pins[MOVE_FRAME][MOVE_POINT]
    new_xy = (x + MOVE_BY[0], y + MOVE_BY[1])
    s.move_point(MOVE_FRAME, MOVE_POINT, new_xy)
    src = s.copy_nearest_shape("mattrai", COPY_FRAME)
    changed, skipped = s.set_occluded_range("mattrai", None, RANGE[0], RANGE[1], True)

    # ---- chuẩn bị gửi (như cvatsync.prepare, không qua CvatClient) ----
    ann_plan = qc.without_eyes(cvatxml.parse_bytes(export(base, "prepare", wd), nums))
    sent = s.build_shapes()
    counts, kept = count_changes(sent, server, nums)
    snapshot = adopted_snapshot(ann_plan, aj, labels, nums, s.names, (s.width, s.height))
    want_shapes = _expected_shapes(s)
    want_tracks = _expected(s)
    saved, s.ann = s.ann, ann_plan                       # như cvatsync.send: nền đã bỏ nhãn mắt
    try:
        send_path = os.path.join(wd, "to_send.xml")
        s.export(send_path)
    finally:
        s.ann = saved

    # ---- gửi, đọc lại ----
    import_file(send_path, "send")
    sent_state = read_job()
    aj2 = sent_state["aj"]
    after = keyed(aj2, labels)
    video = cvatxml.parse_bytes(export(VIDEO, "video", wd), nums)

    edited_keys = {("mattrai", nums[MOVE_FRAME])} | {("mattrai", nums[f]) for f in range(RANGE[0], RANGE[1] + 1)}
    in_range = [("mattrai", nums[f]) for f in range(RANGE[0], RANGE[1] + 1)]
    moved_ok = (("mattrai", nums[MOVE_FRAME]) in after
                and math.dist(after[("mattrai", nums[MOVE_FRAME])][MOVE_POINT][0], new_xy) <= TOL
                and all(math.dist(after[("mattrai", nums[MOVE_FRAME])][p][0], before[("mattrai", nums[MOVE_FRAME])][p][0]) <= TOL
                        for p in EYES["mattrai"].ids if p != MOVE_POINT)
                and all(flag(after[("mattrai", nums[MOVE_FRAME])][p][1], after[("mattrai", nums[MOVE_FRAME])][p][2])
                        == flag(before[("mattrai", nums[MOVE_FRAME])][p][1], before[("mattrai", nums[MOVE_FRAME])][p][2]) for p in EYES["mattrai"].ids))
    copied_ok = (("mattrai", nums[COPY_FRAME]) in after and ("mattrai", nums[src]) in before
                 and same(after[("mattrai", nums[COPY_FRAME])], before[("mattrai", nums[src])]))
    occluded_ok = all(k in after and k in before and all(
        (flag(after[k][p][1], after[k][p][2]) == ("outside" if before[k][p][2] else "occluded")
         and math.dist(after[k][p][0], before[k][p][0]) <= TOL) for p in EYES["mattrai"].ids) for k in in_range)
    out_after = after[("mattrai", nums[OUT_FRAME])][OUT_POINT]
    outside_kept = flag(out_after[1], out_after[2]) == "outside"
    msgs = _compare_shapes(aj2, labels, want_shapes, set(), nums, cap=False)
    kept_bad = _kept_changed(aj2, labels, kept)
    expect_counts = {"server": n, "kept": n - len(edited_keys), "edited": len(edited_keys), "added": 1, "removed": 0}
    facts = {
        "tổng shape": len(after) == n + 1 and len(_json_eye_shapes(aj2, labels)) == n + 1,
        "không track": not aj2.get("tracks") and not eye_tracks(aj2, labels),
        "đếm": counts == expect_counts,
        "dời điểm": moved_ok,
        "chép": copied_ok and src == COPY_FRAME - 1,
        "Occluded cả đoạn": occluded_ok and (changed, skipped) == (RANGE[1] - RANGE[0] + 1, 1) and outside_kept,
        "so với file gửi": not msgs,
        "shape giữ nguyên": not kept_bad,
    }
    verdict("Q3", all(facts.values()), "%s; count_changes %s; CVAT có %d shape; _compare_shapes %d chỗ lệch, shape giữ nguyên lệch %d"
            % (", ".join("%s %s" % (k, "đúng" if v else "SAI") for k, v in facts.items()), counts, len(after), len(msgs), len(kept_bad)))
    cmp_video = _compare(video, want_tracks, set(), nums, want_shapes, cap=False)
    verdict("Q3b", not cmp_video, "bản xuất video có %d track (CVAT đổi mỗi shape thành một track một frame, %d shape đã gửi); _compare %d chỗ lệch"
            % (sum(len(video.tracks[l]) for l in EYES), n + 1, len(cmp_video)))
    deleted_after = {int(f) for f in sent_state["meta"].get("deleted_frames") or []}
    reopen = adopt.check(aj2, labels, nums, deleted_after)          # mở lại job sau khi gửi: phải nạp lại được (không rơi vào chế độ chỉ xem)
    verdict("Q3c", not reopen, "sau khi gửi, adopt.check trên JSON thật còn %d lý do: mở lại job %s%s"
            % (len(reopen), "nạp lại được" if not reopen else "sẽ ở chế độ chỉ xem", "" if not reopen else " (" + " ".join(reopen) + ")"))

    # ---- khôi phục bằng bản chụp ----
    restore_path = os.path.join(wd, "snapshot.xml")
    with open(restore_path, "wb") as fh:
        fh.write(snapshot)
    import_file(restore_path, "restore")
    restored = read_job()
    back = keyed(restored["aj"], labels)
    pairs = [diff(back[k], before[k]) for k in before if k in back]
    outside_before = sum(1 for pts in before.values() for p in pts.values() if p[2])
    outside_back = sum(1 for pts in back.values() for p in pts.values() if p[2])
    verdict("Q6", set(back) == set(before) and len(pairs) == len(before) and all(d <= TOL and f == 0 for d, f in pairs)
            and not restored["aj"].get("tracks") and outside_before == outside_back >= 1,
            "khôi phục: %d/%d shape về đúng (lệch lớn nhất %.4f px, %d điểm khác cờ), điểm Outside %d/%d, %d track"
            % (len(pairs), len(before), max((d for d, _ in pairs), default=math.nan), sum(f for _, f in pairs), outside_back, outside_before,
               len(restored["aj"].get("tracks") or [])))

    # ---- Q4: issue còn sau import ----
    keep = [issue_id in sent_state["issues"], issue_id in restored["issues"]]
    others = [sorted(set(x["issues"]) - {issue_id}) == state["existing"] for x in (sent_state, restored)]
    verdict("Q4", all(keep) and all(others), "issue %s còn sau khi gửi: %s, sau khi khôi phục: %s; các issue có sẵn còn nguyên: %s"
            % ("thử", "có" if keep[0] else "KHÔNG", "có" if keep[1] else "KHÔNG", "có" if all(others) else "KHÔNG"))
    print(q5)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Failed as exc:
        print("Lỗi: %s" % exc)
        sys.exit(1)
    print("KẾT QUẢ:", "ĐẠT" if all(results) else "KHÔNG ĐẠT", "(%d/%d)" % (sum(results), len(results)))
    sys.exit(0 if all(results) else 1)
