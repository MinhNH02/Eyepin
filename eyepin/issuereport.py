"""Lõi báo cáo issue CVAT: biến các danh sách thô CVAT trả (task, job, issue, bình luận) thành một `Report` tự mô tả.

Không biết gì về Tkinter hay Excel: cửa sổ và file Excel chỉ đọc từ `Report`, không bao giờ từ ô chọn task trên màn. Đường lấy dữ liệu chỉ GET
(xem `CvatClient.report_*`, `issues`, `comments`); bất kỳ lệnh nào lỗi thì cả lần `load` thất bại, không dựng báo cáo dở. Thông điệp lỗi và
cảnh báo là tiếng Việt, hiện thẳng cho người dùng.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from typing import NamedTuple

from .cvatapi import CvatError, username

STATUS_OPEN, STATUS_RESOLVED = "Chưa sửa", "Đã sửa"
NO_MESSAGE, UNKNOWN_USER = "(không có mô tả)", "(không rõ)"
NOTE_EXCLUDED, NOTE_UNLISTED = "không đưa vào báo cáo", "tài khoản không xem được job này"
DEFAULT_JOB_TYPE = "annotation"


@dataclass(frozen=True)
class Row:
    """Một issue. `message` là lời của bình luận đầu tiên; `replies` là các bình luận sau, mỗi cái một dòng; `assignee` là người được giao job lúc lấy."""
    issue_id: int
    job: int
    frame: int
    link: str
    message: str
    resolved: bool
    owner: str
    created: datetime | None
    assignee: str
    replies: str

    @property
    def status(self) -> str:
        return STATUS_RESOLVED if self.resolved else STATUS_OPEN


@dataclass(frozen=True)
class JobInfo:
    """Một job trong báo cáo. `reported` là số issue CVAT đếm sẵn (None nếu không biết, hoặc job chỉ thấy qua issue); `listed` sai nghĩa là job
    không có trong danh sách job của tài khoản."""
    id: int
    type: str = DEFAULT_JOB_TYPE
    assignee: str = ""
    reported: int | None = None
    listed: bool = True


@dataclass(frozen=True)
class Report:
    """Bộ dữ liệu báo cáo của MỘT task. `fetched` là giờ máy, không kèm múi giờ; `flagged` là mã các job có cảnh báo số issue."""
    url: str
    user: str
    task_id: int
    task_name: str
    fetched: datetime
    jobs: tuple[JobInfo, ...]
    rows: tuple[Row, ...]
    warnings: tuple[str, ...]
    flagged: frozenset[int]


class SummaryLine(NamedTuple):
    job: int
    assignee: str
    total: int
    open: int
    resolved: int
    note: str


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def frame_link(url: str, task_id: int, job_id: int, frame: int) -> str:
    """Đường dẫn mở thẳng một frame của job trên giao diện CVAT."""
    return "%s/tasks/%d/jobs/%d?frame=%d" % (url.rstrip("/"), task_id, job_id, frame)


def local_time(text: str | None, tz: tzinfo | None = None) -> datetime | None:
    """Đổi chuỗi ISO của CVAT (UTC, đuôi `Z`) sang giờ địa phương KHÔNG kèm múi giờ. `tz` chỉ để test cố định múi giờ (None = múi giờ máy).
    Chuỗi rỗng, None hoặc hỏng thì `None`. Chuỗi không ghi múi giờ được coi là UTC."""
    if not isinstance(text, str) or not text.strip():
        return None
    s = text.strip()
    if s[-1] in "Zz":
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(tz).replace(tzinfo=None)
    except (ValueError, OverflowError, OSError):
        return None


def _stamp(when: datetime | None) -> str:
    return when.strftime("%Y-%m-%d %H:%M") if when else ""


def _text(comment: dict) -> str:
    message = comment.get("message")
    return message if isinstance(message, str) else ""


def _reply(comment: dict, tz: tzinfo | None) -> str:
    name = username(comment.get("owner")) or UNKNOWN_USER
    stamp = _stamp(local_time(comment.get("created_date"), tz))
    return "%s (%s): %s" % (name, stamp, _text(comment)) if stamp else "%s: %s" % (name, _text(comment))


def _comments_by_issue(issues: list[dict], comments: list[dict]) -> dict[int, list[dict]]:
    """Ghép bình luận vào issue theo mã issue, mỗi nhóm theo `id` tăng dần. Bình luận của issue không có trong `issues` bị bỏ. Một issue có
    `comments.count` lớn hơn số bình luận ghép được là dữ liệu đổi giữa hai lệnh gọi: ném `CvatError`."""
    grouped = {i["id"]: [] for i in issues}
    for c in comments:
        mine = grouped.get(c.get("issue"))
        if mine is not None:
            mine.append(c)
    for i in issues:
        grouped[i["id"]].sort(key=lambda c: c["id"])
        summary = i.get("comments")
        count = summary.get("count") if isinstance(summary, dict) else None
        if _is_int(count) and count > len(grouped[i["id"]]):
            raise CvatError("Bình luận của issue #%d trên CVAT vừa thay đổi trong lúc lấy. Hãy bấm Làm mới." % i["id"])
    return grouped


def build(url: str, user: str, task: dict, jobs: list[dict], issues: list[dict], comments: list[dict], *,
          now: datetime | None = None, tz: tzinfo | None = None) -> Report:
    """Dựng báo cáo từ dữ liệu đã lấy. `task` là một `cvatapi.task_row`, `jobs` là các `cvatapi.job_row`; `issues`, `comments` là dict nguyên dạng CVAT.
    Mọi job đều vào `Report.jobs`, kể cả job chỉ thấy qua issue (`listed=False`). Thiếu dữ liệu (không xem được hết) là cảnh báo chứ không phải lỗi."""
    listed = {j["id"]: j for j in jobs}
    by_issue = _comments_by_issue(issues, comments)
    rows = []
    for i in issues:
        mine = by_issue[i["id"]]
        job = listed.get(i["job"])
        rows.append(Row(
            issue_id=i["id"], job=i["job"], frame=i["frame"], link=frame_link(url, task["id"], i["job"], i["frame"]),
            message=_text(mine[0]) if mine else NO_MESSAGE, resolved=bool(i.get("resolved")),
            owner=username(i.get("owner")) or UNKNOWN_USER, created=local_time(i.get("created_date"), tz),
            assignee=(job.get("assignee") or "") if job else "", replies="\n".join(_reply(c, tz) for c in mine[1:])))
    rows.sort(key=lambda r: (r.job, r.frame, r.issue_id))

    infos = {j["id"]: JobInfo(j["id"], j.get("type") or DEFAULT_JOB_TYPE, j.get("assignee") or "",
                              j["issues"] if _is_int(j.get("issues")) else None) for j in jobs}
    for r in rows:
        infos.setdefault(r.job, JobInfo(r.job, listed=False))
    ordered = tuple(infos[k] for k in sorted(infos))

    warnings, flagged = [], set()
    total = task.get("jobs")
    if _is_int(total) and total > len(jobs):
        warnings.append("Task có %d job, tài khoản này chỉ xem được %d; issue ở các job còn lại có thể không có trong báo cáo." % (total, len(jobs)))
    for j in ordered:
        got = sum(1 for r in rows if r.job == j.id)
        if not j.listed:
            warnings.append("Job %d: tài khoản này không xem được job, nhưng có %d issue của nó trong báo cáo." % (j.id, got))
            flagged.add(j.id)
        elif j.reported is not None and j.reported > got:
            warnings.append("Job %d: CVAT báo %d issue, báo cáo lấy được %d. Có thể tài khoản này không xem được hết, hoặc issue vừa thay đổi; "
                            "bấm Làm mới để kiểm lại." % (j.id, j.reported, got))
            flagged.add(j.id)
    return Report(url=url, user=user, task_id=task["id"], task_name=task.get("name") or "", fetched=now if now is not None else datetime.now(),
                  jobs=ordered, rows=tuple(rows), warnings=tuple(warnings), flagged=frozenset(flagged))


def load(client, task_id: int | None, *, now: datetime | None = None, tz: tzinfo | None = None) -> tuple[list[dict], Report | None]:
    """Lấy từ CVAT (chỉ GET), theo thứ tự: tên tài khoản, danh sách task, rồi (nếu `task_id` có trong danh sách) job, issue của task và bình luận của
    từng job có mặt trong issue. Trả `(danh sách task, báo cáo)`; `task_id` là None hoặc không có trong danh sách thì báo cáo là None và không đọc thêm gì.
    Lệnh nào lỗi thì cả lần lấy thất bại (`CvatError`)."""
    user = client.whoami()
    tasks = client.report_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if task is None:
        return tasks, None
    jobs = client.report_jobs(task_id)
    issues = client.issues(task_id)
    comments = []
    for job_id in sorted({i["job"] for i in issues}):
        comments.extend(client.comments(job_id))
    return tasks, build(client.url, user, task, jobs, issues, comments, now=now, tz=tz)


def select(report: Report, excluded=frozenset(), resolved: bool | None = None, owner: str | None = None) -> list[Row]:
    """Các dòng sau khi bỏ job `excluded`, lọc theo trạng thái (`resolved` None = mọi trạng thái) và người báo (`owner` None = mọi người); giữ thứ tự của báo cáo."""
    return [r for r in report.rows
            if r.job not in excluded and (resolved is None or r.resolved == resolved) and (owner is None or r.owner == owner)]


def owners(report: Report) -> list[str]:
    """Các người báo khác nhau trong báo cáo (kể cả `UNKNOWN_USER`), đã sắp xếp."""
    return sorted({r.owner for r in report.rows})


def summary(report: Report, excluded=frozenset(), owner: str | None = None) -> list[SummaryLine]:
    """Một dòng cho MỖI job của báo cáo (kể cả job bị `excluded`, để người đọc thấy nó bị bỏ): số issue, chưa sửa, đã sửa, theo `owner` nếu có."""
    lines = []
    for j in report.jobs:
        mine = [r for r in report.rows if r.job == j.id and (owner is None or r.owner == owner)]
        done = sum(1 for r in mine if r.resolved)
        notes = []
        if j.type != DEFAULT_JOB_TYPE:
            notes.append("loại %s" % j.type)
        if not j.listed:
            notes.append(NOTE_UNLISTED)
        if j.id in excluded:
            notes.append(NOTE_EXCLUDED)
        lines.append(SummaryLine(j.id, j.assignee, len(mine), len(mine) - done, done, "; ".join(notes)))
    return lines
