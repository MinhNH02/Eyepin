"""Gửi nhãn mắt của phiên về job CVAT đã mở (xem design/2026-11-16-cvat-direct-design.md mục 7, design/cvat-api-notes.md).

Ghi vào CVAT chỉ bằng import ("CVAT 1.1"), mà import thay TOÀN BỘ nhãn của job, nên quy trình là:
  prepare  đọc lại job (đã bị sửa chưa), nhãn hiện có bằng JSON (đúng loại track/shape), chọn định dạng nền, xuất nền mới nhất bỏ nhãn mắt,
           giữ bản XML nền gốc làm bản chụp để khôi phục; trả SendPlan để người dùng xác nhận. Phiên đã nạp shape (`Session.adopted`, xem
           adopt.py) thì còn đếm shape mắt giữ nguyên / sửa / thêm / bỏ so với JSON của job (`count_changes`) và dựng bản chụp từ JSON
           (`adopted_snapshot`) vì bản xuất nền có thể trải hoặc đổi kiểu shape mắt.
  send     ghép nhãn mắt của phiên vào nền, import, rồi xuất lại "CVAT for video" và đối chiếu với điều tool tuyên bố (như tests/verify_vs_cvat.py:
           vị trí trong 2 px + làm tròn, cờ Occluded/Outside, keyframe). Shape mắt được đối chiếu bằng JSON annotations (chỉ JSON giữ đúng
           loại); track một frame mà bản xuất video sinh ra từ mỗi shape bị bỏ trước khi đếm track. Shape "giữ nguyên" của phiên đã nạp
           còn được kiểm riêng: CVAT phải lưu đúng như trước khi gửi (`TOL_KEPT_CHECK`).
  restore  import lại bản chụp.

Frame: mọi so sánh theo chỉ số EyePin (XML đọc về đã đổi sang chỉ số, xem cvatxml.parse_bytes); file gửi đi mang số frame của job. Frame bỏ qua khi
đối chiếu là frame CVAT đã xoá (`session.source.deleted`), không phải tập xoá của phiên.
Lưới an toàn: số đối tượng không phải mắt theo nhãn (JSON) trước và sau khi gửi phải bằng nhau.
"""
from __future__ import annotations

import math
import os
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from . import cvatxml, qc
from .cvatapi import EYES as EYE_NAMES, CvatClient, CvatError, LoginNeeded
from .cvatsource import VIDEO, _eye_label_ids, _is_eye, base_format
from .cvatxml import Annotations, EyeKey, EyeShape, PointState
from .geometry import EYES
from .qc import EyeLabels
from .session import KEYFRAME_TOL, Session

TOL_KEY = 0.02                       # px: tại keyframe CVAT phải giữ đúng toạ độ (chỉ chênh làm tròn hai chữ số)
TOL_INTERP = KEYFRAME_TOL + 0.02     # px: giữa hai keyframe, CVAT nội suy đường thẳng và tool cho phép lệch tới KEYFRAME_TOL
TOL_KEPT = 0.005                     # px: một shape của job đã nạp được đếm "giữ nguyên" khi mọi điểm lệch không quá chừng này (mỗi trục)
TOL_KEPT_CHECK = 0.01                # px: sau khi gửi, shape "giữ nguyên" phải còn đúng như trước khi gửi trong chừng này (làm tròn hai chữ số)
MAX_MISMATCHES = 40                  # liệt kê tối đa chừng này chỗ lệch; còn lại chỉ đếm
_CVAT_FAILED = "CVAT báo thất bại"   # đầu thông điệp của cvatapi khi CVAT trả status `failed` (khác với mất kết nối: kết quả chưa rõ)
_TWO_SHAPES_REASON = "Có hai shape cùng nhãn mắt ở cùng frame"        # đầu lý do 4 của `adopt.check` (adopt nhập module này nên không nhập được tên của nó)
UNREVIEWED_LINE = "Còn {n} shape điền tự động chưa xem; sau khi gửi và mở lại job, danh sách này không còn."
TWO_PEOPLE_LINE = "Có hai người cùng vẽ một mắt ở cùng frame: lần mở sau EyePin sẽ mở job ở chế độ chỉ xem."
JOB_CHANGED_MSG = "Job đã đổi trên CVAT nên không gửi kiểu sửa tại chỗ được: {reasons} Hãy mở lại job."


@dataclass
class SendPlan:
    changed_on_server: bool          # job.updated_date khác session.cvat["updated"] (có người sửa job trên CVAT kể từ lúc mở)
    replaced: EyeLabels              # nhãn mắt đang có trên CVAT (đếm từ JSON, frame theo số frame của job) sẽ bị thay
    mixed_types: bool                # job có cả shape lẫn track không phải mắt: shape sẽ thành track một frame (nền = video)
    keyframes: int                   # số keyframe EyePin sẽ gửi (cả hai mắt, mọi người)
    base_format: str
    job_id: int = 0
    opened_updated: str | None = None    # updated_date lúc mở job (session.cvat["updated"])
    server_updated: str | None = None    # updated_date lúc prepare; send từ chối nếu CVAT đã đổi sau đó
    ann: Annotations | None = field(default=None, repr=False)    # nền đã bỏ nhãn mắt (chỉ số EyePin)
    base_xml: bytes = field(default=b"", repr=False)             # bản chụp để khôi phục: bản xuất nền gốc nguyên văn; phiên đã nạp: dựng từ JSON (`adopted_snapshot`)
    non_eye: dict = field(default_factory=dict, repr=False)      # số đối tượng không phải mắt theo nhãn trước khi gửi (_count_non_eye)
    label_names: dict = field(default_factory=dict, repr=False)  # id nhãn -> tên (để báo)
    shapes: int = 0                                              # số shape mắt EyePin sẽ gửi (mọi người)
    labels: list = field(default_factory=list, repr=False)       # nhãn của job (`client.labels`, có `sublabels`): đọc JSON shape sau khi gửi
    adopted: bool = False                                        # phiên đã nạp shape mắt của job (`Session.adopted`): gửi là sửa các shape đó
    counts: dict | None = None                                   # chỉ khi `adopted`: {"server", "kept", "edited", "added", "removed"} (`count_changes`)
    kept: list = field(default_factory=list, repr=False)         # chỉ khi `adopted`: shape của job được đếm "giữ nguyên" (dạng `_json_eye_shapes`)
    unreviewed: int = 0                                          # chỉ khi `adopted`: số shape điền tự động chưa xem của mọi người (`Session.unreviewed`)
    two_people: bool = False                                     # chỉ khi `adopted`: hai shape cùng nhãn mắt ở cùng frame (hai người): lần mở sau job vào chế độ chỉ xem

    def needs_warning(self) -> bool:
        if self.adopted:                                         # gửi lại chỉ làm mất shape bị bỏ; sửa và thêm không phải điều đáng hỏi
            return (self.counts["removed"] > 0 or self.changed_on_server or self.mixed_types or self.unreviewed > 0 or self.two_people)
        return self.changed_on_server or not self.replaced.empty() or self.mixed_types

    def text(self) -> str:
        if self.adopted:
            c = self.counts
            lines = [f"Job có {c['server']} shape mắt trên CVAT. Sẽ gửi {self.shapes} shape: giữ nguyên {c['kept']}, sửa {c['edited']}, "
                     f"thêm {c['added']}, bỏ {c['removed']}."]
            if self.unreviewed:                                  # danh sách "chưa xem" chỉ sống trong phiên: gửi xong mở lại là mất
                lines.append(UNREVIEWED_LINE.format(n=self.unreviewed))
            if self.two_people:
                lines.append(TWO_PEOPLE_LINE)
        else:
            what = f"{self.keyframes} keyframe và {self.shapes} shape mắt mới" if self.shapes else f"{self.keyframes} keyframe mắt mới"
            lines = [f"EyePin sẽ thay toàn bộ nhãn của job #{self.job_id} trên CVAT bằng nhãn nền hiện có cộng {what}."]
            if not self.replaced.empty():
                lines.append(f"Việc gửi sẽ xoá nhãn mắt đang có trên CVAT: {self.replaced.message()}.")
        if self.mixed_types:
            lines.append("Job có cả shape lẫn track không phải mắt: khi gửi, shape sẽ thành track một frame (nhãn nền được gửi theo CVAT for video).")
        if self.changed_on_server:
            lines.append(f"Job đã bị sửa trên CVAT kể từ lúc EyePin mở (cập nhật lúc mở {self.opened_updated}, hiện tại {self.server_updated}); "
                         "gửi sẽ ghi đè mọi thay đổi đó.")
        return "\n".join(lines)


@dataclass
class SendResult:
    ok: bool
    message: str
    mismatches: list[str] = field(default_factory=list)
    snapshot: bytes | None = None    # bản XML nền trước khi gửi; đưa cho restore. None khi chưa gửi gì (lỗi trước lúc import): không có gì để khôi phục


def _require_cvat(session: Session) -> int:
    if not session.cvat or "job" not in session.cvat:
        raise CvatError("Phiên này không mở từ một job CVAT nên không gửi lên CVAT được.")
    return int(session.cvat["job"])


def _eye_labels_from_json(aj: dict, labels: list[dict]) -> EyeLabels:
    """Nhãn mắt đang có trên CVAT, đếm từ JSON (đúng loại track/shape); frame là số frame của job như CVAT ghi."""
    names = {lb["id"]: lb["name"] for lb in labels if lb.get("name") in EYE_NAMES}
    tracks, shapes = [], {}
    for t in aj.get("tracks") or []:
        name = names.get(t.get("label_id"))
        if name is None:
            continue
        frames = [int(s["frame"]) for s in t.get("shapes") or [] if "frame" in s] or [int(t.get("frame", 0))]
        tracks.append((name, int(t.get("id", -1)), min(frames), max(frames)))
    for s in aj.get("shapes") or []:
        name = names.get(s.get("label_id"))
        if name is not None:
            shapes[name] = shapes.get(name, 0) + 1
    return EyeLabels(tracks, shapes)


STALE_MSG = "Nhãn tool tính đang cũ vì lần bám gần nhất bị lỗi (mất kết nối CVAT?). Làm lại thao tác hoặc mở lại job rồi gửi."
DROPPED_MSG = "Nhãn không phải mắt nằm ngoài phạm vi frame của job: không gửi để khỏi xoá chúng"


def _count_non_eye(aj: dict, eye_ids: set[int]) -> dict:
    """Số đối tượng không phải mắt theo nhãn: shape và track cộng chung (nền "CVAT for video" đổi shape thành track một frame), tag đếm riêng.
    Khoá là ("obj", label_id) hoặc ("tag", label_id)."""
    out: dict = {}
    for kind in ("shapes", "tracks"):
        for o in aj.get(kind) or []:
            if not _is_eye(o, eye_ids):
                k = ("obj", o.get("label_id"))
                out[k] = out.get(k, 0) + 1
    for t in aj.get("tags") or []:
        k = ("tag", t.get("label_id"))
        out[k] = out.get(k, 0) + 1
    return out


def _non_eye_on_deleted(aj: dict, eye_ids: set[int], deleted: set[int], names: dict) -> list[str]:
    """Nhãn không phải mắt nằm trên frame CVAT đã xoá (số frame tương đối như JSON): "face frame 3" ... Shape, tag, và từng shape của track
    (kể cả phần tử của skeleton track)."""
    hits: dict[tuple, None] = {}

    def add(label_id, frame, kind):
        if frame is not None and int(frame) in deleted:
            hits[(names.get(label_id, f"#{label_id}"), int(frame), kind)] = None

    for o in aj.get("shapes") or []:
        if not _is_eye(o, eye_ids):
            add(o.get("label_id"), o.get("frame"), "shape")
    for t in aj.get("tags") or []:
        add(t.get("label_id"), t.get("frame"), "tag")
    for t in aj.get("tracks") or []:
        if _is_eye(t, eye_ids):
            continue
        for sh in t.get("shapes") or []:
            add(t.get("label_id"), sh.get("frame"), "track")
        for el in t.get("elements") or []:
            for sh in el.get("shapes") or []:
                add(t.get("label_id"), sh.get("frame"), "track")
    return [f"{kind} '{name}' ở frame {f}" for name, f, kind in sorted(hits, key=lambda h: (h[1], h[0], h[2]))]


def _count_diff(before: dict, after: dict, names: dict) -> list[str]:
    out = []
    for k in sorted(set(before) | set(after), key=lambda k: (k[0], str(k[1]))):
        b, a = before.get(k, 0), after.get(k, 0)
        if b != a:
            kind, lid = k
            what = "tag" if kind == "tag" else "đối tượng (shape + track)"
            out.append(f"Nhãn {names.get(lid, f'#{lid}')}: trước khi gửi có {b} {what}, sau khi gửi CVAT có {a}")
    return out


def prepare(session: Session, client: CvatClient) -> SendPlan:
    """Hỏi CVAT mọi điều cần biết trước khi gửi (không ghi gì). Ném CvatError/LoginNeeded nếu không hỏi được, nếu nhãn tool tính đang cũ
    (`session.stale`), hoặc khi gửi chắc chắn làm mất nhãn không phải mắt: nhãn trên frame CVAT đã xoá (bản xuất bỏ chúng), tag khi nền là
    "CVAT for video" (định dạng này không ghi tag), nhãn nằm ngoài phạm vi frame của job. Phiên đã nạp shape (`session.adopted`): thêm `counts`
    và `kept` (`count_changes`), bản chụp dựng từ JSON; `unreviewed` (shape điền tự động chưa xem, mọi người) và `two_people` (hai người cùng một mắt
    ở cùng frame); ném CvatError khi job đã đổi trên CVAT thành thứ `adopt.check` không cho nạp (trừ lý do hai người cùng frame: có `two_people` lo)
    hoặc khi một shape mắt của job không dựng lại được (không đủ 8 điểm, ngoài job)."""
    job_id = _require_cvat(session)
    if getattr(session, "stale", False):
        raise CvatError(STALE_MSG)
    job = client.job(job_id)
    labels = client.labels(job_id)
    aj = client.annotations(job_id)
    eye_ids = _eye_label_ids(labels)
    base, _display = base_format(aj, eye_ids)
    shapes, tracks = aj.get("shapes") or [], aj.get("tracks") or []
    mixed = any(not _is_eye(o, eye_ids) for o in shapes) and any(not _is_eye(o, eye_ids) for o in tracks)
    names = {lb["id"]: lb.get("name", "") for lb in labels if "id" in lb}
    deleted = {int(f) for f in client.meta(job_id).get("deleted_frames") or []}
    on_deleted = _non_eye_on_deleted(aj, eye_ids, deleted, names)
    if on_deleted:
        more = f" và {len(on_deleted) - 10} nhãn nữa" if len(on_deleted) > 10 else ""
        raise CvatError(f"Job #{job_id} có nhãn không phải mắt nằm trên frame đã xoá trong CVAT: {'; '.join(on_deleted[:10])}{more}. "
                        "CVAT không xuất các nhãn này nên gửi (import thay cả job) sẽ xoá chúng và bản chụp trước khi gửi cũng không có chúng. "
                        "Không gửi. Hãy khôi phục các frame đó hoặc chuyển/xoá các nhãn đó trên CVAT trước.")
    if session.adopted:                                       # job đã đổi trên CVAT thành thứ không sửa tại chỗ được: bản chụp không dựng lại được nên không hứa khôi phục
        from . import adopt                                   # adopt nhập module này: nhập muộn để khỏi vòng
        nums = session.source.frame_numbers
        reasons = [r for r in adopt.check(aj, labels, nums, {nums[i] for i in session.source.deleted}) if not r.startswith(_TWO_SHAPES_REASON)]
        if reasons:                                           # lý do hai người cùng frame bỏ qua: job hai người gửi lại trong cùng phiên do cảnh báo `two_people` lo
            raise CvatError(JOB_CHANGED_MSG.format(reasons=" ".join(reasons)))
    if base == VIDEO and aj.get("tags"):
        raise CvatError(f"Job #{job_id} có {len(aj['tags'])} tag (nhãn gắn cả frame) và có track không phải mắt nên nhãn nền phải gửi theo "
                        "CVAT for video, mà định dạng này không chứa tag: gửi sẽ xoá mọi tag và khôi phục cũng không lấy lại được. Không gửi.")
    base_xml = client.export_xml(job_id, base)
    try:
        parsed = cvatxml.parse_bytes(base_xml, session.source.frame_numbers)
    except ValueError as e:
        raise CvatError(str(e)) from e
    if parsed.dropped:
        raise CvatError(f"{DROPPED_MSG} ({parsed.dropped} nhãn trong bản xuất nền của job #{job_id} nằm ngoài frame "
                        f"{session.source.frame_numbers[0]}–{session.source.frame_numbers[-1]}).")
    ann = qc.without_eyes(parsed)
    try:
        keyframes = sum(len(t.keys) for t in session.build_all_tracks())
    except ValueError:
        keyframes = 0                                         # chưa ghim gì: send sẽ từ chối
    sent = session.build_shapes()
    counts, kept, snapshot = None, [], base_xml
    unreviewed, two_people = 0, False
    if session.adopted:                                       # shape mắt của job được sửa tại chỗ: đếm so với JSON lúc này, bản chụp giữ shape là shape
        nums = session.source.frame_numbers
        counts, kept = count_changes(sent, _json_eye_shapes(aj, labels), nums)
        try:
            snapshot = adopted_snapshot(ann, aj, labels, nums, session.names, (session.width, session.height))
        except ValueError as e:
            raise CvatError(f"{e} Không gửi.") from e
        for i in range(len(session.layers)):                  # shape điền tự động chưa xem của MỌI người (người đang chọn không đổi)
            with session.layer_ctx(i):
                unreviewed += sum(len(session.unreviewed(l)) for l in EYES)
        two_people = any(n > 1 for n in Counter((sh.label, sh.key.frame) for sh in sent).values())
    updated = job.get("updated_date")
    return SendPlan(changed_on_server=updated != session.cvat.get("updated"), replaced=_eye_labels_from_json(aj, labels), mixed_types=mixed,
                    keyframes=keyframes, base_format=base, job_id=job_id, opened_updated=session.cvat.get("updated"), server_updated=updated,
                    ann=ann, base_xml=snapshot, non_eye=_count_non_eye(aj, eye_ids), label_names=names,
                    shapes=len(sent), labels=labels, adopted=session.adopted, counts=counts, kept=kept, unreviewed=unreviewed, two_people=two_people)


@dataclass
class _Want:
    tid: int
    keys: dict[int, EyeKey]                                   # keyframe tool gửi (điểm đủ 8, kèm cờ)
    frames: dict[int, tuple[dict, dict]]                      # frame -> (nhãn do tool tính {điểm: xy}, cờ hiệu lực {điểm: 'occluded'|'outside'})


def _expected(session: Session) -> dict[str, list[_Want]]:
    """Track tool tuyên bố sẽ có trên CVAT, chụp trước khi gửi. Ném ValueError khi không có cả track lẫn shape mắt để gửi; job chỉ có shape
    thì trả danh sách track rỗng (shape: `_expected_shapes`)."""
    want: dict[str, list[_Want]] = {l: [] for l in EYES}
    for i, layer in enumerate(session.layers):
        if not layer.pins:
            continue
        with session.layer_ctx(i):
            for label, tr in session.build_tracks().items():
                ids = EYES[label].ids
                frames = {}
                for f in range(min(tr.keys), session.n_frames):
                    r = session.labels.get(f)
                    if r is not None:
                        flags = session.flags_at(f)
                        frames[f] = ({p: r.points[p] for p in ids if p in r.points}, {p: flags[p] for p in ids if p in flags})
                want[label].append(_Want(int(tr.attrs.get("id", 10 ** 9)), dict(tr.keys), frames))
    if not any(want.values()) and not session.build_shapes():
        raise ValueError("Chưa có nhãn mắt nào để gửi: hãy ghim ít nhất một frame.")
    return want


def _expected_shapes(session: Session) -> dict[str, list[EyeShape]]:
    """Shape mắt tool sẽ gửi, theo nhãn (chụp trước khi gửi; frame là chỉ số EyePin)."""
    out: dict[str, list[EyeShape]] = {l: [] for l in EYES}
    for sh in session.build_shapes():
        out[sh.label].append(sh)
    return out


def _at(f: int, nums: list[int]) -> str:
    """Chỉ số EyePin f trong câu báo, kèm số frame của job khi hai số khác nhau."""
    return f"frame {f}" + (f" (số {nums[f]} của job)" if nums[f] != f else "")


def _cap(out: list[str]) -> list[str]:
    if len(out) > MAX_MISMATCHES:
        out[MAX_MISMATCHES:] = [f"… và {len(out) - MAX_MISMATCHES} chỗ lệch nữa"]
    return out


# ---- dạng JSON của shape skeleton trong `GET /api/jobs/{id}/annotations` ----
# Đã kiểm trên CVAT 2.75 local (design/cvat-api-notes.md, "Shape mắt (2026-11-18)", câu 4): mỗi shape có "type": "skeleton", "frame" (số frame tương đối
# của job, như `session.source.frame_numbers`), "label_id" (id nhãn skeleton), "elements": mỗi điểm một phần tử có "label_id" (id nhãn
# con; tên nhãn con là số điểm "14".."29"), "points": [x, y], "occluded", "outside". Sai chỗ nào thì chỉ sửa hai hàm dưới.

def _sublabel_points(labels: list[dict]) -> dict[int, tuple[str, int]]:
    """id nhãn con của hai skeleton mắt -> (tên mắt, số điểm)."""
    out = {}
    for lb in labels:
        if lb.get("name") in EYE_NAMES:
            for sub in lb.get("sublabels") or []:
                if str(sub.get("name", "")).isdigit():
                    out[sub["id"]] = (lb["name"], int(sub["name"]))
    return out


def _json_eye_shapes(aj: dict, labels: list[dict]) -> list[tuple[str, int, dict[int, tuple[tuple[float, float], bool, bool]]]]:
    """Shape mắt trong JSON annotations: (tên mắt, số frame của job, {điểm: ((x, y), occluded, outside)})."""
    names = {lb["id"]: lb["name"] for lb in labels if lb.get("name") in EYE_NAMES}
    subs = _sublabel_points(labels)
    out = []
    for o in aj.get("shapes") or []:
        name = names.get(o.get("label_id"))
        if name is None or o.get("type") != "skeleton":
            continue
        pts = {}
        for el in o.get("elements") or []:
            who = subs.get(el.get("label_id"))
            xy = el.get("points") or []
            if who is None or who[0] != name or len(xy) < 2:
                continue
            pts[who[1]] = ((float(xy[0]), float(xy[1])), bool(el.get("occluded")), bool(el.get("outside")))
        out.append((name, int(o.get("frame", -1)), pts))
    return out


# ---- phiên đã nạp shape (adopt.py): đếm thay đổi, kiểm shape "giữ nguyên", bản chụp ----
# Dạng một shape của CVAT trong các hàm dưới: như một phần tử của `_json_eye_shapes`, (tên mắt, số frame của job, {điểm: ((x, y), occluded, outside)}).

def _flag(occluded: bool, outside: bool) -> str | None:
    return "outside" if outside else ("occluded" if occluded else None)


def _same_points(a: dict, b: dict, tol: float) -> bool:
    """Hai bộ điểm (dạng của `_json_eye_shapes`) giống nhau: cùng các điểm, mỗi điểm lệch không quá `tol` theo từng trục, cùng cờ. So với
    `tol + 1e-9` vì làm tròn hai chữ số có thể cho hiệu 0,005000000000109."""
    if set(a) != set(b):
        return False
    for pid, ((x, y), occ, out) in a.items():
        (x2, y2), occ2, out2 = b[pid]
        if _flag(occ, out) != _flag(occ2, out2) or abs(x - x2) > tol + 1e-9 or abs(y - y2) > tol + 1e-9:
            return False
    return True


def _mean_dist(a: dict, b: dict) -> float:
    d = [math.dist(a[p][0], b[p][0]) for p in a if p in b]
    return sum(d) / len(d) if d else math.inf


def count_changes(sent: list[EyeShape], server: list[tuple[str, int, dict]], frame_numbers: list[int]) -> tuple[dict, list[tuple]]:
    """So shape mắt tool sắp gửi (`sent`, frame là chỉ số EyePin) với shape mắt đang có trên CVAT (`server`, kết quả `_json_eye_shapes`, frame là số
    frame của job). Khoá là (tên mắt, frame): "giữ" khi có ở cả hai và mọi điểm lệch không quá `TOL_KEPT` theo từng trục, cờ trùng; "sửa" khi có ở
    cả hai mà không giữ; "thêm" chỉ có trong `sent`; "bỏ" chỉ có trên server. Đổi bên mắt ở một frame (label) là hai "sửa". Hai shape cùng khoá
    (hai người) được ghép theo khoảng cách điểm nhỏ nhất trước, nên kết quả không phụ thuộc thứ tự `sent`.
    Trả ({"server", "kept", "edited", "added", "removed"}, các mục `server` được đếm "giữ")."""
    mine: dict[tuple[str, int], list[dict]] = {}
    for sh in sent:
        mine.setdefault((sh.label, frame_numbers[sh.key.frame]), []).append({p: (ps.xy, ps.occluded, ps.outside) for p, ps in sh.key.points.items()})
    theirs: dict[tuple[str, int], list[tuple]] = {}
    for item in server:
        theirs.setdefault(item[:2], []).append(item)
    counts = {"server": len(server), "kept": 0, "edited": 0, "added": 0, "removed": 0}
    kept: list[tuple] = []
    for key in sorted(set(mine) | set(theirs)):
        ws, gs = mine.get(key, []), theirs.get(key, [])
        used_w: set[int] = set()
        used_g: set[int] = set()
        for _, i, j in sorted((_mean_dist(w, g[2]), i, j) for i, w in enumerate(ws) for j, g in enumerate(gs)):
            if i in used_w or j in used_g:
                continue
            used_w.add(i)
            used_g.add(j)
            if _same_points(ws[i], gs[j][2], TOL_KEPT):
                counts["kept"] += 1
                kept.append(gs[j])
            else:
                counts["edited"] += 1
        counts["added"] += len(ws) - len(used_w)
        counts["removed"] += len(gs) - len(used_g)
    return counts, kept


def _kept_changed(aj: dict, labels: list[dict], kept: list[tuple]) -> list[str]:
    """Shape "giữ nguyên" (`SendPlan.kept`, đã có trên CVAT trước khi gửi và không ai sửa) mà JSON sau import không còn y như trước: thiếu, hoặc có
    điểm lệch quá `TOL_KEPT_CHECK` hay cờ khác."""
    got: dict[tuple[str, int], list[dict]] = {}
    for name, jf, pts in _json_eye_shapes(aj, labels):
        got.setdefault((name, jf), []).append(pts)
    return [f"Shape {name} frame {jf} không ai sửa nhưng CVAT lưu khác bản trước khi gửi"
            for name, jf, pts in kept if not any(_same_points(pts, g, TOL_KEPT_CHECK) for g in got.get((name, jf), []))]


def adopted_snapshot(ann_no_eyes: Annotations, aj: dict, labels: list[dict], frame_numbers: list[int], names: Sequence[str],
                     size: tuple[int, int]) -> bytes:
    """Bản chụp để khôi phục job của phiên đã nạp: nhãn nền `ann_no_eyes` (bản xuất nền đã bỏ nhãn mắt, đọc bằng `parse_bytes(..., frame_numbers)`
    nên frame theo chỉ số EyePin và `write_eyes` đổi lại sang số frame của job) cộng shape mắt
    đọc từ JSON `aj` (toạ độ và cờ như CVAT đang lưu), ghi thành `<image>` theo số frame của job. Dựng từ JSON vì bản xuất nền có thể đổi shape mắt
    thành track hoặc trải ra mọi frame (xem design/cvat-api-notes.md), khôi phục từ đó sẽ đổi kiểu đối tượng. `names[i]`, `size`: tên ảnh và cỡ ảnh để
    `write_eyes` tạo `<image>` cho frame file nền chưa có. ValueError (tiếng Việt) khi một shape mắt không đủ 8 điểm hoặc nằm ngoài job: khôi phục
    không trả lại đúng được nên không dựng."""
    index = {n: i for i, n in enumerate(frame_numbers)}
    shapes = []
    for name, jf, pts in _json_eye_shapes(aj, labels):
        if jf not in index:
            raise ValueError(f"Shape mắt {name} ở frame {jf} nằm ngoài job nên không dựng được bản chụp để khôi phục.")
        if set(pts) != set(EYES[name].ids):
            raise ValueError(f"Shape mắt {name} ở frame {jf} của job không đủ 8 điểm nên không dựng được bản chụp để khôi phục.")
        key = EyeKey(index[jf], {pid: PointState(xy, outside, occluded) for pid, (xy, occluded, outside) in pts.items()})
        shapes.append(EyeShape(name, key))
    shapes.sort(key=lambda sh: (sh.key.frame, sh.label))
    with tempfile.TemporaryDirectory(prefix="eyepin_snap_") as d:
        path = os.path.join(d, "snapshot.xml")
        cvatxml.write_eyes(ann_no_eyes, path, new_shapes=shapes, frame_names=names, size=size)
        with open(path, "rb") as fh:
            return fh.read()


def _compare_shapes(aj: dict, labels: list[dict], want: dict[str, list[EyeShape]], skip: set[int], nums: list[int],
                    cap: bool = True) -> list[str]:
    """So shape mắt CVAT lưu (JSON sau import) với shape tool gửi: số shape mỗi nhãn, frame, toạ độ từng điểm (trong `TOL_KEY`), cờ từng
    điểm. Frame trong `skip` (đã xoá trong CVAT) bỏ qua. Hai shape cùng nhãn cùng frame (hai người) được ghép theo điểm gần nhau nhất.
    `cap=False`: không cắt danh sách (người gọi cắt sau khi gộp)."""
    index = {n: i for i, n in enumerate(nums)}
    got: dict[str, dict[int, list[dict]]] = {l: {} for l in EYES}
    outside_job: dict[str, list[int]] = {l: [] for l in EYES}
    for name, jf, pts in _json_eye_shapes(aj, labels):
        f = index.get(jf)
        if f is None:
            outside_job[name].append(jf)
        elif f not in skip:
            got[name].setdefault(f, []).append(pts)
    out: list[str] = []
    for label, spec in EYES.items():
        mine: dict[int, list[EyeShape]] = {}
        for sh in want[label]:
            if sh.key.frame not in skip:
                mine.setdefault(sh.key.frame, []).append(sh)
        n_mine = sum(map(len, mine.values()))
        n_got = sum(map(len, got[label].values())) + len(outside_job[label])
        if n_mine != n_got:
            out.append(f"{label}: tool gửi {n_mine} shape, CVAT có {n_got} shape")
        for jf in sorted(outside_job[label]):
            out.append(f"{label} frame số {jf} của job (ngoài phạm vi EyePin): CVAT có shape tool không gửi")
        for f in sorted(set(mine) | set(got[label])):
            ws, gs = list(mine.get(f, [])), list(got[label].get(f, []))
            for _ in range(len(ws) - len(gs)):
                out.append(f"{label} {_at(f, nums)}: CVAT thiếu shape tool đã gửi")
            for _ in range(len(gs) - len(ws)):
                out.append(f"{label} {_at(f, nums)}: CVAT có shape tool không gửi")
            for sh in ws:
                if not gs:
                    break

                def cost(g):
                    d = [math.dist(sh.key.points[p].xy, g[p][0]) for p in spec.ids if p in g]
                    return sum(d) / len(d) if d else math.inf
                g = min(gs, key=cost)
                gs.remove(g)
                for pid in spec.ids:
                    ps = sh.key.points[pid]
                    ours = "occluded" if ps.occluded else ("outside" if ps.outside else None)
                    if pid not in g:
                        out.append(f"{label} shape {_at(f, nums)}, điểm {pid}: CVAT không có điểm này")
                        continue
                    xy, occ, outside = g[pid]
                    have = "occluded" if occ else ("outside" if outside else None)
                    if ours != have:
                        out.append(f"{label} shape {_at(f, nums)}, điểm {pid}: cờ {ours or 'không'} ở tool, {have or 'không'} ở CVAT")
                    if ps.outside or outside:
                        continue                              # điểm Outside không có toạ độ thật để so
                    d = math.dist(ps.xy, xy)
                    if d > TOL_KEY:
                        out.append(f"{label} shape {_at(f, nums)}, điểm {pid}: lệch {d:.2f} px (tool {ps.xy[0]:.2f},{ps.xy[1]:.2f}; "
                                   f"CVAT {xy[0]:.2f},{xy[1]:.2f})")
    return _cap(out) if cap else out


def _key_dist(a: EyeKey, b: EyeKey) -> float:
    """Khoảng cách trung bình giữa các điểm không Outside có ở cả hai (không có điểm nào để so thì 0)."""
    d = [math.dist(p.xy, b.points[i].xy) for i, p in a.points.items() if not p.outside and i in b.points and not b.points[i].outside]
    return sum(d) / len(d) if d else 0.0


def _key_outside(k: EyeKey) -> bool:
    """Cả mắt Outside ở frame này: cờ trên thẻ <skeleton>, hoặc mọi điểm đều Outside. CVAT 2.75 xuất frame Outside của track sinh từ shape
    KHÔNG có `outside` trên thẻ <skeleton>, chỉ có ở từng <points> (design/cvat-api-notes.md, "Shape mắt (2026-11-18)", câu 5)."""
    return k.outside or (bool(k.points) and all(p.outside for p in k.points.values()))


def _shape_tracks(tracks: list, sent: list[EyeShape]) -> list:
    """Các track trong `tracks` (một nhãn, bản xuất "CVAT for video") được coi là track CVAT sinh ra từ các shape `sent` tool đã gửi.

    Dạng đã kiểm trên CVAT 2.75 (design/cvat-api-notes.md, "Shape mắt (2026-11-18)", câu 5; `ShapeManager.to_tracks`): keyframe ở frame f của
    shape rồi keyframe ở frame f+1 có cả 8 điểm Outside (thẻ <skeleton> không mang `outside`); shape ở frame cuối của job chỉ có frame f.
    Ứng viên: frame đầu f của track là keyframe và mọi frame sau đó đều Outside (`_key_outside`; frame f không bắt buộc có điểm không
    Outside, để shape có cả 8 điểm Outside vẫn nhận ra). Track thật bản xuất video ghi mọi frame từ keyframe đầu tới hết job nên chỉ giống ứng
    viên khi nằm ở frame cuối, hoặc khi mắt Outside hẳn ngay sau keyframe đầu. Mỗi shape đã gửi bỏ nhiều nhất một ứng viên cùng frame, chọn ứng
    viên có điểm gần shape nhất; vì vậy track thật không bao giờ bị bỏ nhiều hơn số shape, và track thật CVAT làm mất vẫn lộ ra ở phép đếm track."""
    cands: dict[int, list] = {}
    for t in tracks:
        if not t.keys:
            continue
        f = min(t.keys)
        if t.keys[f].keyframe and all(_key_outside(k) for g, k in t.keys.items() if g != f):
            cands.setdefault(f, []).append(t)
    drop = []
    for sh in sent:
        pool = cands.get(sh.key.frame)
        if pool:
            best = min(pool, key=lambda t: _key_dist(sh.key, t.keys[sh.key.frame]))
            pool.remove(best)
            drop.append(best)
    return drop


def _compare(video: Annotations, want: dict[str, list[_Want]], skip: set[int], nums: list[int],
             shapes: dict[str, list[EyeShape]] | None = None, cap: bool = True) -> list[str]:
    """V1 (vị trí), V2 (cờ), V3 (keyframe) của tests/verify_vs_cvat.py, trên bản xuất "CVAT for video" sau import. Frame trong `skip` (đã xoá) bỏ qua;
    frame CVAT không xuất mà không phải keyframe cũng bỏ qua (CVAT chỉ ghi keyframe khi nhận file, ghi từng frame khi xuất).
    `shapes` {nhãn: shape tool đã gửi}: bản xuất video đổi mỗi shape thành một track một frame; các track đó bị bỏ trước khi đếm và ghép
    (`_shape_tracks`; shape được đối chiếu riêng bằng JSON, `_compare_shapes`). `cap=False`: không cắt danh sách (người gọi cắt sau khi gộp)."""
    out: list[str] = []
    for label, spec in EYES.items():
        ws = sorted(want[label], key=lambda w: (min(w.keys), w.tid))
        tracks = video.tracks[label]
        if shapes and shapes.get(label):
            drop = {id(t) for t in _shape_tracks(tracks, shapes[label])}
            tracks = [t for t in tracks if id(t) not in drop]
        ts = sorted(tracks, key=lambda t: (min(t.keys) if t.keys else -1, int(t.attrs.get("id", 0)) if str(t.attrs.get("id", "")).isdigit() else 0))
        if len(ws) != len(ts):
            out.append(f"{label}: tool gửi {len(ws)} track, CVAT có {len(ts)} track")
        for w, t in zip(ws, ts):
            got_keys = {f for f, k in t.keys.items() if k.keyframe}
            for f in sorted(set(w.keys) - got_keys):
                if f not in skip:
                    out.append(f"{label} {_at(f, nums)}: CVAT thiếu keyframe tool đã gửi")
            for f in sorted(got_keys - set(w.keys)):
                if f not in skip:
                    out.append(f"{label} {_at(f, nums)}: CVAT có keyframe tool không gửi")
            for f in sorted(t.keys):
                if f in skip or f not in w.frames:
                    continue
                ours, flags = w.frames[f]
                for pid in spec.ids:
                    p = t.keys[f].points.get(pid)
                    if p is None or pid not in ours:
                        continue
                    have = "occluded" if p.occluded else ("outside" if p.outside else None)
                    if flags.get(pid) != have:
                        out.append(f"{label} {_at(f, nums)}, điểm {pid}: cờ {flags.get(pid) or 'không'} ở tool, {have or 'không'} ở CVAT")
                    if p.outside:
                        continue                              # điểm Outside không có toạ độ thật để so
                    exact = f in w.keys
                    ref = w.keys[f].points[pid].xy if exact else ours[pid]
                    d = math.dist(ref, p.xy)
                    if d > (TOL_KEY if exact else TOL_INTERP):
                        out.append(f"{label} {_at(f, nums)}, điểm {pid}: lệch {d:.2f} px (tool {ref[0]:.2f},{ref[1]:.2f}; CVAT {p.xy[0]:.2f},{p.xy[1]:.2f})"
                                   + ("" if exact else " giữa hai keyframe"))
    return _cap(out) if cap else out


def mark_synced(session: Session, client: CvatClient) -> str | None:
    """Ghi `updated_date` hiện tại của job vào session.cvat (dùng sau restore: lúc đó job đổi do chính EyePin). Trả về ngày đó."""
    updated = client.job(_require_cvat(session)).get("updated_date")
    session.cvat["updated"] = updated
    return updated


def _import_failure(client: CvatClient, job_id: int, err: CvatError, before: str | None) -> str:
    known = str(err).startswith(_CVAT_FAILED)
    parts = [str(err), "CVAT báo không nạp được file." if known else "Nhãn trên CVAT chưa rõ đã được nạp hay chưa."]
    try:
        now = client.job(job_id).get("updated_date")
    except CvatError:
        parts.append("Không đọc lại được ngày cập nhật của job nên chưa kiểm được. Hãy mở job trên CVAT xem nhãn, hoặc khôi phục bản trước khi gửi.")
    else:
        if now == before:
            parts.append(f"Ngày cập nhật của job trên CVAT vẫn là {now} (không đổi): nhiều khả năng nhãn chưa bị đổi.")
        else:
            parts.append(f"Ngày cập nhật của job trên CVAT đã đổi từ {before} thành {now}: nhãn trên CVAT có thể đã bị thay. "
                         "Hãy kiểm lại trên CVAT hoặc khôi phục bản trước khi gửi.")
    return " ".join(parts)


def send(session: Session, client: CvatClient, plan: SendPlan) -> SendResult:
    """Gửi nhãn mắt của phiên lên job bằng import, rồi đối chiếu với điều CVAT lưu. Không ném lỗi CvatError (trả ok=False với thông điệp);
    chỉ LoginNeeded trước khi gửi gì được ném lên để giao diện đăng nhập lại. `snapshot` là bản chụp nền để `restore` khi đã gọi import
    (kể cả khi import lỗi: chưa chắc CVAT có nạp hay không); lỗi trước lúc import thì `snapshot` là None vì job chưa bị EyePin đụng tới."""
    snap = plan.base_xml

    def fail(msg, mismatches=None):
        return SendResult(False, msg, mismatches or [], snap)

    def fail_unsent(msg):
        return SendResult(False, msg, [], None)

    if getattr(session, "stale", False):                     # nhãn tool tính cũ (bám lỗi sau lúc prepare): điều tool tuyên bố không đáng tin
        return fail_unsent(STALE_MSG)
    try:
        want = _expected(session)
        want_shapes = _expected_shapes(session)
        saved, session.ann = session.ann, plan.ann            # nền đã bỏ nhãn mắt; trả lại như cũ dù xuất lỗi
        try:
            with tempfile.TemporaryDirectory(prefix="eyepin_send_") as d:      # XML chỉ có toạ độ nên được ghi file tạm
                path = os.path.join(d, "eyepin.xml")
                session.export(path)
                with open(path, "rb") as fh:
                    data = fh.read()
        finally:
            session.ann = saved
    except (ValueError, KeyError) as e:
        return fail_unsent(f"Không dựng được file gửi: {e}")
    try:
        now = client.job(plan.job_id).get("updated_date")
    except LoginNeeded:
        raise
    except CvatError as e:
        return fail_unsent(f"Chưa gửi gì lên CVAT: {e}")
    if now != plan.server_updated:
        return fail_unsent(f"Chưa gửi gì: job vừa thay đổi trên CVAT sau lúc kiểm tra (cập nhật {plan.server_updated} thành {now}). "
                           "Hãy chuẩn bị gửi lại.")
    try:
        client.import_xml(plan.job_id, data)
    except CvatError as e:
        return fail(_import_failure(client, plan.job_id, e, plan.server_updated))
    try:
        session.cvat["updated"] = client.job(plan.job_id).get("updated_date")     # job đổi do chính lần gửi này
        aj = client.annotations(plan.job_id)
        after = _count_non_eye(aj, {i for i, n in plan.label_names.items() if n in EYE_NAMES})
        video = cvatxml.parse_bytes(client.export_xml(plan.job_id, VIDEO), session.source.frame_numbers)
    except (CvatError, ValueError) as e:
        return fail(f"Đã gửi file nhưng không đọc lại được từ CVAT để đối chiếu: {e}. Hãy kiểm nhãn trên CVAT.")
    lost = _count_diff(plan.non_eye, after, plan.label_names)                  # lưới an toàn: nhãn không phải mắt phải còn đủ
    skip, nums = set(session.source.deleted), session.source.frame_numbers
    n_shapes = sum(map(len, want_shapes.values()))
    kept_changed = _kept_changed(aj, plan.labels, plan.kept)  # chỉ có khi phiên đã nạp: shape không ai sửa phải còn y như trước khi gửi
    if n_shapes:                                              # track một frame do bản xuất video sinh ra từ shape bị bỏ; shape so bằng JSON
        mismatches = lost + _cap(_compare(video, want, skip, nums, want_shapes, cap=False)
                                 + _compare_shapes(aj, plan.labels, want_shapes, skip, nums, cap=False) + kept_changed)
    else:
        mismatches = lost + _compare(video, want, skip, nums) + kept_changed
    if lost:                                                  # bản chụp là cùng bản xuất nền nên có thể cũng thiếu các nhãn này: không hứa khôi phục
        return fail(f"Đã gửi, nhưng CVAT lưu khác tool ở {len(mismatches)} chỗ, trong đó có nhãn không phải mắt bị mất hoặc đổi số lượng. "
                    "Bản chụp trước khi gửi có thể không chứa các nhãn đó nên khôi phục có thể không lấy lại được: hãy kiểm trên CVAT ngay.",
                    mismatches)
    if mismatches:
        return fail(f"Đã gửi, nhưng CVAT lưu khác tool ở {len(mismatches)} chỗ. Xem danh sách và kiểm trên CVAT; có thể khôi phục bản trước khi gửi.",
                    mismatches)
    session.unsent = False                                    # chỉ khi gửi xong VÀ đối chiếu khớp: gửi lệch thì giữ "chưa gửi" (Đăng xuất sẽ hỏi)
    what = f"{plan.keyframes} keyframe và {n_shapes} shape mắt" if n_shapes else f"{plan.keyframes} keyframe mắt"
    return SendResult(True, f"Đã gửi {what} lên job #{plan.job_id}; CVAT lưu khớp với EyePin.", [], snap)


def restore(client: CvatClient, job_id: int, snapshot: bytes) -> None:
    """Đưa job về bản chụp bằng cách import lại bản xuất nền (nhãn khác giữ như trước khi gửi).

    Giới hạn: bản chụp là bản xuất nền theo định dạng nền của lúc gửi, nên nhãn mắt cũ chỉ được khôi phục đúng loại khi định dạng nền cũng là
    định dạng hiện nhãn mắt cũ (ví dụ nền "CVAT for images" trả track mắt cũ về thành shape ở mọi frame). Người dùng đã xác nhận xoá nhãn
    mắt cũ khi gửi; khôi phục chủ yếu để lấy lại nhãn nền. Phiên đã nạp shape không có giới hạn đó: bản chụp dựng từ JSON (`adopted_snapshot`)
    nên shape mắt về đúng là shape. Sau khi khôi phục nên gọi `mark_synced` để mốc cập nhật của phiên theo job."""
    client.import_xml(job_id, snapshot)
