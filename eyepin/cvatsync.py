"""Gửi nhãn mắt của phiên về job CVAT đã mở (xem design/2026-11-16-cvat-direct-design.md mục 7, design/cvat-api-notes.md).

Ghi vào CVAT chỉ bằng import ("CVAT 1.1"), mà import thay TOÀN BỘ nhãn của job, nên quy trình là:
  prepare  đọc lại job (đã bị sửa chưa), nhãn hiện có bằng JSON (đúng loại track/shape), chọn định dạng nền, xuất nền mới nhất bỏ nhãn mắt,
           giữ bản XML nền gốc làm bản chụp để khôi phục; trả SendPlan để người dùng xác nhận.
  send     ghép nhãn mắt của phiên vào nền, import, rồi xuất lại "CVAT for video" và đối chiếu với điều tool tuyên bố (như tests/verify_vs_cvat.py:
           vị trí trong 2 px + làm tròn, cờ Occluded/Outside, keyframe).
  restore  import lại bản chụp.

Frame: mọi so sánh theo chỉ số EyePin (XML đọc về đã đổi sang chỉ số, xem cvatxml.parse_bytes); file gửi đi mang số frame của job. Frame bỏ qua khi
đối chiếu là frame CVAT đã xoá (`session.source.deleted`), không phải tập xoá của phiên.
Lưới an toàn: số đối tượng không phải mắt theo nhãn (JSON) trước và sau khi gửi phải bằng nhau.
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field

from . import cvatxml, qc
from .cvatapi import EYES as EYE_NAMES, CvatClient, CvatError, LoginNeeded
from .cvatsource import VIDEO, _eye_label_ids, _is_eye, base_format
from .cvatxml import Annotations, EyeKey
from .geometry import EYES
from .qc import EyeLabels
from .session import KEYFRAME_TOL, Session

TOL_KEY = 0.02                       # px: tại keyframe CVAT phải giữ đúng toạ độ (chỉ chênh làm tròn hai chữ số)
TOL_INTERP = KEYFRAME_TOL + 0.02     # px: giữa hai keyframe, CVAT nội suy đường thẳng và tool cho phép lệch tới KEYFRAME_TOL
MAX_MISMATCHES = 40                  # liệt kê tối đa chừng này chỗ lệch; còn lại chỉ đếm
_CVAT_FAILED = "CVAT báo thất bại"   # đầu thông điệp của cvatapi khi CVAT trả status `failed` (khác với mất kết nối: kết quả chưa rõ)


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
    base_xml: bytes = field(default=b"", repr=False)             # bản xuất nền gốc, nguyên văn: bản chụp để khôi phục
    non_eye: dict = field(default_factory=dict, repr=False)      # số đối tượng không phải mắt theo nhãn trước khi gửi (_count_non_eye)
    label_names: dict = field(default_factory=dict, repr=False)  # id nhãn -> tên (để báo)

    def needs_warning(self) -> bool:
        return self.changed_on_server or not self.replaced.empty() or self.mixed_types

    def text(self) -> str:
        lines = [f"EyePin sẽ thay toàn bộ nhãn của job #{self.job_id} trên CVAT bằng nhãn nền hiện có cộng {self.keyframes} keyframe mắt mới."]
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
    "CVAT for video" (định dạng này không ghi tag), nhãn nằm ngoài phạm vi frame của job."""
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
    updated = job.get("updated_date")
    return SendPlan(changed_on_server=updated != session.cvat.get("updated"), replaced=_eye_labels_from_json(aj, labels), mixed_types=mixed,
                    keyframes=keyframes, base_format=base, job_id=job_id, opened_updated=session.cvat.get("updated"), server_updated=updated,
                    ann=ann, base_xml=base_xml, non_eye=_count_non_eye(aj, eye_ids), label_names=names)


@dataclass
class _Want:
    tid: int
    keys: dict[int, EyeKey]                                   # keyframe tool gửi (điểm đủ 8, kèm cờ)
    frames: dict[int, tuple[dict, dict]]                      # frame -> (nhãn do tool tính {điểm: xy}, cờ hiệu lực {điểm: 'occluded'|'outside'})


def _expected(session: Session) -> dict[str, list[_Want]]:
    """Điều tool tuyên bố sẽ có trên CVAT, chụp trước khi gửi (ném ValueError như Session.export nếu không có gì để gửi)."""
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
    if not any(want.values()):
        raise ValueError("Chưa có nhãn mắt nào để gửi: hãy ghim ít nhất một frame.")
    return want


def _compare(video: Annotations, want: dict[str, list[_Want]], skip: set[int], nums: list[int]) -> list[str]:
    """V1 (vị trí), V2 (cờ), V3 (keyframe) của tests/verify_vs_cvat.py, trên bản xuất "CVAT for video" sau import. Frame trong `skip` (đã xoá) bỏ qua;
    frame CVAT không xuất mà không phải keyframe cũng bỏ qua (CVAT chỉ ghi keyframe khi nhận file, ghi từng frame khi xuất)."""
    out: list[str] = []

    def at(f):
        return f"frame {f}" + (f" (số {nums[f]} của job)" if nums[f] != f else "")

    for label, spec in EYES.items():
        ws = sorted(want[label], key=lambda w: (min(w.keys), w.tid))
        ts = sorted(video.tracks[label], key=lambda t: (min(t.keys) if t.keys else -1, int(t.attrs.get("id", 0)) if str(t.attrs.get("id", "")).isdigit() else 0))
        if len(ws) != len(ts):
            out.append(f"{label}: tool gửi {len(ws)} track, CVAT có {len(ts)} track")
        for w, t in zip(ws, ts):
            got_keys = {f for f, k in t.keys.items() if k.keyframe}
            for f in sorted(set(w.keys) - got_keys):
                if f not in skip:
                    out.append(f"{label} {at(f)}: CVAT thiếu keyframe tool đã gửi")
            for f in sorted(got_keys - set(w.keys)):
                if f not in skip:
                    out.append(f"{label} {at(f)}: CVAT có keyframe tool không gửi")
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
                        out.append(f"{label} {at(f)}, điểm {pid}: cờ {flags.get(pid) or 'không'} ở tool, {have or 'không'} ở CVAT")
                    if p.outside:
                        continue                              # điểm Outside không có toạ độ thật để so
                    exact = f in w.keys
                    ref = w.keys[f].points[pid].xy if exact else ours[pid]
                    d = math.dist(ref, p.xy)
                    if d > (TOL_KEY if exact else TOL_INTERP):
                        out.append(f"{label} {at(f)}, điểm {pid}: lệch {d:.2f} px (tool {ref[0]:.2f},{ref[1]:.2f}; CVAT {p.xy[0]:.2f},{p.xy[1]:.2f})"
                                   + ("" if exact else " giữa hai keyframe"))
    if len(out) > MAX_MISMATCHES:
        out[MAX_MISMATCHES:] = [f"… và {len(out) - MAX_MISMATCHES} chỗ lệch nữa"]
    return out


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
        after = _count_non_eye(client.annotations(plan.job_id), {i for i, n in plan.label_names.items() if n in EYE_NAMES})
        video = cvatxml.parse_bytes(client.export_xml(plan.job_id, VIDEO), session.source.frame_numbers)
    except (CvatError, ValueError) as e:
        return fail(f"Đã gửi file nhưng không đọc lại được từ CVAT để đối chiếu: {e}. Hãy kiểm nhãn trên CVAT.")
    lost = _count_diff(plan.non_eye, after, plan.label_names)                  # lưới an toàn: nhãn không phải mắt phải còn đủ
    mismatches = lost + _compare(video, want, set(session.source.deleted), session.source.frame_numbers)
    if lost:                                                  # bản chụp là cùng bản xuất nền nên có thể cũng thiếu các nhãn này: không hứa khôi phục
        return fail(f"Đã gửi, nhưng CVAT lưu khác tool ở {len(mismatches)} chỗ, trong đó có nhãn không phải mắt bị mất hoặc đổi số lượng. "
                    "Bản chụp trước khi gửi có thể không chứa các nhãn đó nên khôi phục có thể không lấy lại được: hãy kiểm trên CVAT ngay.",
                    mismatches)
    if mismatches:
        return fail(f"Đã gửi, nhưng CVAT lưu khác tool ở {len(mismatches)} chỗ. Xem danh sách và kiểm trên CVAT; có thể khôi phục bản trước khi gửi.",
                    mismatches)
    session.unsent = False                                    # chỉ khi gửi xong VÀ đối chiếu khớp: gửi lệch thì giữ "chưa gửi" (Đăng xuất sẽ hỏi)
    return SendResult(True, f"Đã gửi {plan.keyframes} keyframe mắt lên job #{plan.job_id}; CVAT lưu khớp với EyePin.", [], snap)


def restore(client: CvatClient, job_id: int, snapshot: bytes) -> None:
    """Đưa job về bản chụp bằng cách import lại bản xuất nền (nhãn khác giữ như trước khi gửi).

    Giới hạn: bản chụp là bản xuất nền theo định dạng nền của lúc gửi, nên nhãn mắt cũ chỉ được khôi phục đúng loại khi định dạng nền cũng là
    định dạng hiện nhãn mắt cũ (ví dụ nền "CVAT for images" trả track mắt cũ về thành shape ở mọi frame). Người dùng đã xác nhận xoá nhãn
    mắt cũ khi gửi; khôi phục chủ yếu để lấy lại nhãn nền. Sau khi khôi phục nên gọi `mark_synced` để mốc cập nhật của phiên theo job."""
    client.import_xml(job_id, snapshot)
