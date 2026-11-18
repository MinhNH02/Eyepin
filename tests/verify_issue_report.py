"""Đối chiếu lõi báo cáo issue và file Excel với CVAT local thật (cần container cvat_server chạy; dữ liệu công khai).

Quy trình: gửi một đoạn mã Python qua stdin cho `manage.py shell` trong container. Đoạn mã dùng `APIClient` của Django REST framework đã
`force_login` tài khoản local đầu tiên (không mật khẩu, không khoá, không đăng nhập HTTP từ ngoài), tạo ba issue thử trên một job, lấy các danh sách
đúng như `CvatClient` lấy (`page_size=all`, bình luận theo `job_id`), rồi xoá đúng ba issue đó. Ngoài container, script dựng báo cáo bằng
`issuereport.build`, ghi Excel bằng `issuexlsx.write`, mở lại bằng openpyxl và kiểm:

  V1  mỗi phản hồi danh sách có count, results, next rỗng, và len(results) == count
  V2  danh sách issue và bình luận xếp id giảm dần
  V3  ba dòng đúng (mô tả, trạng thái, frame, bình luận trả lời, nhiều dòng, link)
  V4  thứ tự dòng: frame 0 trước frame 3, cùng frame thì mã nhỏ trước; bộ lọc `select` đúng
  V5  số issue CVAT đếm sẵn của job khớp, báo cáo không cảnh báo job này
  V6  file Excel: mô tả bắt đầu bằng `=` là chuỗi chữ, link có siêu liên kết đúng, sheet "Tổng hợp" có dòng của job
  V7  (thông tin) bẫy `task_id` của /api/comments còn nguyên hay không
  V8  sau khi chạy, job có đúng các issue ban đầu và không còn bình luận nào chứa EYEPIN-VERIFY

AN TOÀN: chỉ xoá đúng các issue script vừa tạo (danh sách `created` khai báo trước `try`, xoá trong `finally` kể cả khi lỗi giữa chừng); không
đụng gì khác. Tên tài khoản CVAT local là địa chỉ email riêng tư: script không in phản hồi thô, tên đăng nhập hay email, chỉ in dòng kết luận và số đếm.

Chạy:  python tests\\verify_issue_report.py [job_id=5]    Thoát mã 0 khi V1-V6 và V8 đạt, 1 khi có mục lệch.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from eyepin import issuereport, issuexlsx  # noqa: E402
from eyepin.cvatapi import CvatError, job_row, task_row  # noqa: E402

CONTAINER = "cvat_server"
JOB = int(sys.argv[1]) if len(sys.argv) > 1 else 5
URL = "http://localhost:8080"
MARK = "EYEPIN-VERIFY"
MESSAGES = {
    "A": "=> EYEPIN-VERIFY mí trên lệch 3 px",
    "B": "EYEPIN-VERIFY khoé ngoài sai",
    "B_REPLY": "EYEPIN-VERIFY đã sửa",
    "C": "EYEPIN-VERIFY dòng 1\ndòng 2",
}

# Chạy trong container (mọi chuỗi đưa vào bằng json.dumps nên đoạn mã chỉ có ký tự ASCII). Khai báo `created` trước `try`, xoá trong `finally`.
CONTAINER_CODE = r'''
import json
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

JOB = __JOB__
MARK = __MARK__
M = __MESSAGES__
HOST = "localhost:8080"
POSITION = [10.0, 10.0, 50.0, 50.0]


class Failed(Exception):
    pass


client = APIClient()


def call(method, path, data=None):
    kw = {"HTTP_HOST": HOST}
    if data is not None:
        kw["format"] = "json"
        r = getattr(client, method)(path, data, **kw)
    else:
        r = getattr(client, method)(path, **kw)
    return r.status_code, (json.loads(r.content) if r.content else None)


def need(method, path, want, data=None):
    status, body = call(method, path, data)
    if status != want:
        raise Failed("%s %s tra %s, can %s" % (method.upper(), path.split("?")[0], status, want))
    return body


created, names, existing, error = [], {}, [], None
try:
    client.force_login(get_user_model().objects.order_by("id").first(), backend="django.contrib.auth.backends.ModelBackend")
    task_id = need("get", "/api/jobs/%d" % JOB, 200)["task_id"]
    existing = sorted(i["id"] for i in need("get", "/api/issues?job_id=%d&page_size=all" % JOB, 200)["results"])

    def make(name, frame, message):
        body = need("post", "/api/issues", 201, {"job": JOB, "frame": frame, "position": POSITION, "message": message})
        created.append(body["id"])
        names[name] = body["id"]
        return body["id"]

    make("A", 3, M["A"])
    b = make("B", 0, M["B"])
    need("post", "/api/comments", 201, {"issue": b, "message": M["B_REPLY"]})
    need("patch", "/api/issues/%d" % b, 200, {"resolved": True})
    make("C", 3, M["C"])

    tasks = need("get", "/api/tasks?page_size=all", 200)
    jobs = need("get", "/api/jobs?task_id=%d&page_size=all" % task_id, 200)
    issues = need("get", "/api/issues?task_id=%d&page_size=all" % task_id, 200)
    comments = {}
    for j in sorted({i["job"] for i in issues["results"]}):
        comments[str(j)] = need("get", "/api/comments?job_id=%d&page_size=all" % j, 200)
    others = [t["id"] for t in tasks["results"] if t["id"] != task_id]
    trap = None
    if others:
        trap = {"task": others[0], "count": len(need("get", "/api/comments?task_id=%d&page_size=all" % others[0], 200)["results"])}
    print("EYEPIN_JSON " + json.dumps({"task_id": task_id, "created": created, "names": names, "existing": existing, "tasks": tasks,
                                       "jobs": jobs, "issues": issues, "comments": comments, "trap": trap}))
except Exception as exc:
    error = type(exc).__name__ + (": " + str(exc) if isinstance(exc, Failed) else "")
finally:
    undeleted = []
    for iid in created:
        try:
            if call("delete", "/api/issues/%d" % iid)[0] != 204:
                undeleted.append(iid)
        except Exception:
            undeleted.append(iid)
    left = {"undeleted": undeleted}
    try:
        left["issues"] = sorted(i["id"] for i in need("get", "/api/issues?job_id=%d&page_size=all" % JOB, 200)["results"])
        left["comments"] = sum(1 for c in need("get", "/api/comments?page_size=all", 200)["results"] if MARK in (c.get("message") or ""))
    except Exception as exc2:
        left["error"] = type(exc2).__name__
    print("EYEPIN_LEFT " + json.dumps(left))
    if error:
        print("EYEPIN_ERROR " + error)
'''

results = []


def verdict(code, ok, text):
    results.append(ok)
    print("%s  %s  %s" % (code, "ĐẠT" if ok else "LỆCH", text))


def scrub(text):
    """Che mọi thứ giống địa chỉ email trước khi in thông báo lỗi của tiến trình ngoài."""
    return re.sub(r"\S+@\S+", "<đã ẩn>", text)


def run_in_container():
    code = (CONTAINER_CODE.replace("__JOB__", str(JOB)).replace("__MARK__", json.dumps(MARK))
            .replace("__MESSAGES__", json.dumps(MESSAGES)))
    r = subprocess.run(["docker", "exec", "-i", CONTAINER, "python", "manage.py", "shell", "-c", "import sys; exec(sys.stdin.read())"],
                       input=code, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    found = {}
    for line in r.stdout.splitlines():
        for tag in ("EYEPIN_JSON", "EYEPIN_LEFT", "EYEPIN_ERROR"):
            if line.startswith(tag + " "):
                found[tag] = line[len(tag) + 1:]
    if not found:
        last = scrub(r.stderr.strip().splitlines()[-1]) if r.stderr.strip() else ""
        raise SystemExit("Không chạy được đoạn mã trong container (mã thoát %d). %s" % (r.returncode, last))
    return found


def complete(d):
    return (isinstance(d, dict) and isinstance(d.get("results"), list) and isinstance(d.get("count"), int) and not d.get("next")
            and len(d["results"]) == d["count"])


def descending(d):
    ids = [r["id"] for r in d["results"]]
    return ids == sorted(ids, reverse=True)


def check_excel(report, link):
    """V6: ghi Excel vào thư mục tạm, mở lại, kiểm ba điều, rồi xoá thư mục tạm."""
    import openpyxl
    folder = tempfile.mkdtemp(prefix="eyepin-verify-")
    try:
        path = os.path.join(folder, "bao-cao.xlsx")
        issuexlsx.write(path, report, issuereport.select(report))
        wb = openpyxl.load_workbook(path)
        try:
            issues = wb[issuexlsx.SHEET_ISSUES]
            row = next((r for r in issues.iter_rows(min_row=2) if r[1].value == JOB and r[4].value == MESSAGES["A"]), None)
            text_ok = row is not None and row[4].data_type == "s" and isinstance(row[4].value, str)
            link_ok = row is not None and row[3].hyperlink is not None and row[3].hyperlink.target == link and row[3].value == link
            summary = wb[issuexlsx.SHEET_SUMMARY]
            line = next((r for r in summary.iter_rows() if r[0].value == JOB), None)
            expect = sum(1 for r in report.rows if r.job == JOB)
            line_ok = line is not None and line[2].value == expect
            return text_ok, link_ok, line_ok
        finally:
            wb.close()
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def main():
    if shutil.which("docker") is None:
        raise SystemExit("Không thấy lệnh docker.")
    found = run_in_container()
    if "EYEPIN_ERROR" in found:
        print("Lỗi trong container: %s" % found["EYEPIN_ERROR"])
    data = json.loads(found["EYEPIN_JSON"]) if "EYEPIN_JSON" in found else None
    if data is not None:
        check_data(data)
    else:
        results.append(False)
    left = json.loads(found["EYEPIN_LEFT"]) if "EYEPIN_LEFT" in found else {}
    existing = data["existing"] if data is not None else None
    clean = (not left.get("error") and not left.get("undeleted") and left.get("comments") == 0
             and (existing is None or left.get("issues") == existing))
    detail = "issue còn lại của job: %s, bình luận còn chứa %s: %s, issue chưa xoá được: %s" % (
        len(left["issues"]) if "issues" in left else "?", MARK, left.get("comments", "?"), len(left.get("undeleted", [])))
    verdict("V8", bool(clean), detail + (", ban đầu: %d" % len(existing) if existing is not None else ""))


def check_data(p):
    task_id, created, names, existing = p["task_id"], p["created"], p["names"], p["existing"]
    lists = [p["tasks"], p["jobs"], p["issues"]] + list(p["comments"].values())
    verdict("V1", all(complete(d) for d in lists), "%d phản hồi danh sách đủ count, results, next rỗng" % len(lists))
    verdict("V2", descending(p["issues"]) and all(descending(d) for d in p["comments"].values()),
            "issue (%d) và bình luận (%d) xếp id giảm dần" % (len(p["issues"]["results"]), sum(len(d["results"]) for d in p["comments"].values())))

    task = task_row(next(t for t in p["tasks"]["results"] if t["id"] == task_id))
    jobs = [job_row(j) for j in p["jobs"]["results"]]
    comments = [c for d in p["comments"].values() for c in d["results"]]
    try:
        report = issuereport.build(URL, "verify", task, jobs, p["issues"]["results"], comments)
    except CvatError as exc:
        verdict("V3", False, "build ném CvatError: %s" % exc)
        return
    by_id = {r.issue_id: r for r in report.rows}
    rows = {k: by_id.get(names.get(k)) for k in "ABC"}
    a, b, c = rows["A"], rows["B"], rows["C"]
    link = "%s/tasks/%d/jobs/%d?frame=3" % (URL, task_id, JOB)
    facts = {
        "A": a is not None and (a.message, a.resolved, a.frame, a.job, a.link) == (MESSAGES["A"], False, 3, JOB, link),
        "B": b is not None and (b.message, b.resolved, b.frame, b.job) == (MESSAGES["B"], True, 0, JOB) and b.replies.endswith(": " + MESSAGES["B_REPLY"]),
        "C": c is not None and (c.message, c.resolved, c.frame) == (MESSAGES["C"], False, 3) and len(c.message.splitlines()) == 2,
        "chủ và ngày": all(r is not None and r.owner not in ("", issuereport.UNKNOWN_USER) and r.created is not None for r in (a, b, c)),
    }
    verdict("V3", all(facts.values()) and len(created) == 3, "dòng A, B, C: " + ", ".join("%s %s" % (k, "đúng" if v else "sai") for k, v in facts.items()))
    if not all((a, b, c)):
        return

    order = [r.issue_id for r in issuereport.select(report) if r.issue_id in created]
    resolved_only = [r.issue_id for r in issuereport.select(report, resolved=True) if r.issue_id in created]
    verdict("V4", order == [b.issue_id, a.issue_id, c.issue_id] and a.issue_id < c.issue_id and resolved_only == [b.issue_id],
            "thứ tự B (frame 0), A, C (frame 3); lọc Đã sửa chỉ còn B")

    mine = next((j for j in jobs if j["id"] == JOB), None)
    job_warnings = [w for w in report.warnings if w.startswith("Job %d:" % JOB)]
    verdict("V5", mine is not None and mine["issues"] == len(existing) + 3 and JOB not in report.flagged and not job_warnings,
            "CVAT đếm %s issue cho job (có sẵn %d cộng 3), %d cảnh báo cho job, %d cảnh báo cả báo cáo"
            % (mine["issues"] if mine else "?", len(existing), len(job_warnings), len(report.warnings)))

    try:
        text_ok, link_ok, line_ok = check_excel(report, link)
        ok, detail = text_ok and link_ok and line_ok, "mô tả dạng chữ: %s, siêu liên kết: %s, dòng job ở Tổng hợp: %s" % (
            "đúng" if text_ok else "sai", "đúng" if link_ok else "sai", "đúng" if line_ok else "sai")
    except ImportError:
        ok, detail = False, "máy thiếu openpyxl"
    verdict("V6", ok, detail)

    trap = p["trap"]
    if trap is None:
        print("V7  (thông tin)  không có task khác để thử bẫy task_id")
    else:
        print("V7  (thông tin)  /api/comments?task_id=<task khác> trả %d mục%s" % (trap["count"], ": bẫy task_id còn nguyên" if trap["count"] > 0 else ""))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:                       # không in nội dung lỗi: có thể kèm dữ liệu CVAT
        tb = exc.__traceback__
        while tb.tb_next:
            tb = tb.tb_next
        print("Lỗi không mong đợi: %s ở dòng %d" % (type(exc).__name__, tb.tb_lineno))
        sys.exit(1)
    sys.exit(0 if all(results) else 1)
