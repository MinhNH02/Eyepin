"""Nạp shape mắt có sẵn của một job CVAT vào phiên làm việc để sửa tiếp, thay cho chế độ chỉ xem QC (design/2026-11-19-qc-edit-design.md).

Chỉ nạp khi gửi lại KHÔNG làm mất gì: mọi shape mắt của job phải đọc được đủ 8 điểm và toạ độ, cờ từng điểm; job không có track mắt và không có
thứ gì khác mà `cvatsync.prepare` sẽ từ chối gửi. `check` trả danh sách lý do không nạp được (rỗng = nạp được); `eye_shapes` đọc shape từ
JSON của `GET /api/jobs/{id}/annotations`, toạ độ nguyên văn như CVAT ghi (không làm tròn).

Module này nhập `cvatsync` và `cvatsource` (hai module đó nhập `session`), nên `session.py` KHÔNG nhập module này: `Session.adopt` chỉ đọc
`label`, `frame`, `points`, `flags` của từng `AdoptedShape`.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from . import qc
from .cvatsource import _eye_label_ids
from .cvatsync import _sublabel_points
from .cvatxml import Annotations
from .geometry import EYES

MAX_FRAMES = 3                  # số frame tối đa nêu trong một lý do; còn nữa thì thêm " …"


@dataclass(frozen=True)
class AdoptedShape:
    """Một shape mắt đọc từ job, sẵn sàng đưa vào phiên: đủ 8 điểm của mắt `label` tại chỉ số frame EyePin `frame`."""
    label: str                                   # "mattrai" | "matphai"
    frame: int                                   # chỉ số EyePin
    points: dict[int, tuple[float, float]]       # đủ 8 điểm của mắt, toạ độ nguyên văn
    flags: dict[int, str]                        # điểm -> "outside" | "occluded" (điểm không cờ thì không có mục)


def _frames_text(frames) -> str:
    """Tối đa `MAX_FRAMES` số frame (của job) tăng dần nối bằng ", ", thêm " …" nếu còn nữa."""
    ordered = sorted(set(frames))
    text = ", ".join(str(f) for f in ordered[:MAX_FRAMES])
    return text + " …" if len(ordered) > MAX_FRAMES else text


def _frame(o: dict) -> int:
    return int(o.get("frame", -1))


def _numeric(xy) -> bool:
    return (isinstance(xy, (list, tuple)) and len(xy) >= 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in xy[:2]))


def _elements(shape: dict, name: str, subs: dict[int, tuple[str, int]]) -> dict[int, dict] | None:
    """Phần tử của một shape mắt theo số điểm, nếu skeleton có đúng 8 phần tử, mỗi nhãn con của mắt `name` đúng một lần, đều có toạ độ;
    không thì None."""
    els = shape.get("elements") or []
    if len(els) != 8:
        return None
    out: dict[int, dict] = {}
    for el in els:
        who = subs.get(el.get("label_id"))
        if who is None or who[0] != name or who[1] in out or not _numeric(el.get("points")):
            return None
        out[who[1]] = el
    return out if set(out) == set(EYES[name].ids) else None


def _has_extras(shape: dict, els: list[dict]) -> bool:
    """Shape mang thứ EyePin chưa ghi lại được khi gửi: cờ cả skeleton, attributes, group, z_order, rotation (skeleton hoặc phần tử)."""
    if shape.get("occluded") or shape.get("outside"):
        return True
    return any(o.get("attributes") or o.get("group") not in (0, None) or o.get("z_order") not in (0, None) or o.get("rotation") not in (0, None)
               for o in (shape, *els))


def _non_eye_frames_on_deleted(aj: dict, eye_ids: set[int], deleted: set[int]) -> set[int]:
    """Số frame (của job) đã xoá mà có nhãn không phải mắt: shape, tag, và từng shape của track (kể cả shape trong `elements` của skeleton track)."""
    hit: set[int] = set()

    def add(o: dict) -> None:
        if o.get("frame") is not None and int(o["frame"]) in deleted:
            hit.add(int(o["frame"]))

    for o in aj.get("shapes") or []:
        if not qc.is_eye_obj(o, eye_ids):
            add(o)
    for o in aj.get("tags") or []:
        add(o)
    for t in aj.get("tracks") or []:
        if qc.is_eye_obj(t, eye_ids):
            continue
        for sh in t.get("shapes") or []:
            add(sh)
        for el in t.get("elements") or []:
            for sh in el.get("shapes") or []:
                add(sh)
    return hit


def check(aj: dict, labels: list[dict], frame_numbers: list[int], deleted_numbers: set[int]) -> list[str]:
    """Các lý do job KHÔNG nạp được thành shape sửa được (rỗng = nạp được), theo thứ tự cố định, mỗi lý do một chuỗi.

    `aj`: JSON của `GET /api/jobs/{id}/annotations`; `labels`: nhãn của job (có `sublabels`); `frame_numbers`: số frame của job theo chỉ số
    EyePin; `deleted_numbers`: số frame của job đã xoá trong CVAT. Số frame trong câu báo là số frame của job, như JSON ghi.
    Hai điều cuối (8, 9) là đúng hai trường hợp `cvatsync.prepare` từ chối gửi: báo ngay lúc mở thay vì sau khi người dùng đã sửa."""
    eye_ids = _eye_label_ids(labels)
    names = {lb["id"]: lb["name"] for lb in labels if lb.get("id") in eye_ids}
    subs = _sublabel_points(labels)
    shapes, tracks, tags = aj.get("shapes") or [], aj.get("tracks") or [], aj.get("tags") or []
    eyes = [o for o in shapes if qc.is_eye_obj(o, eye_ids)]
    eye_tracks = [t for t in tracks if qc.is_eye_obj(t, eye_ids)]
    other_shapes = [o for o in shapes if not qc.is_eye_obj(o, eye_ids)]
    other_tracks = [t for t in tracks if not qc.is_eye_obj(t, eye_ids)]
    valid = set(frame_numbers)
    out: list[str] = []
    if eye_tracks:
        out.append(f"Job có {len(eye_tracks)} track mắt (EyePin chưa sửa trực tiếp track có sẵn).")
    if other_shapes and other_tracks:
        out.append("Job có cả shape lẫn track của nhãn không phải mắt (gửi sẽ đổi shape của nhãn khác thành track).")
    short = [_frame(o) for o in eyes if _elements(o, names[o["label_id"]], subs) is None]
    if short:
        out.append(f"Shape mắt không đủ 8 điểm đúng tên ở frame {_frames_text(short)}.")
    twice = [f for (_, f), n in Counter((o["label_id"], _frame(o)) for o in eyes).items() if n > 1]
    if twice:
        out.append(f"Có hai shape cùng nhãn mắt ở cùng frame (hai người) ở frame {_frames_text(twice)}.")
    extra = [_frame(o) for o in eyes if _has_extras(o, o.get("elements") or [])]
    if extra:
        out.append("Shape mắt mang thuộc tính EyePin chưa ghi lại được (cờ cả skeleton, attributes, group, z_order, rotation) "
                   f"ở frame {_frames_text(extra)}.")
    both = [_frame(o) for o in eyes if any(el.get("outside") and el.get("occluded") for el in o.get("elements") or [])]
    if both:
        out.append(f"Điểm vừa Outside vừa Occluded ở frame {_frames_text(both)}.")
    gone = [_frame(o) for o in eyes if _frame(o) not in valid or _frame(o) in deleted_numbers]
    if gone:
        out.append(f"Shape mắt nằm trên frame đã xoá hoặc ngoài job ở frame {_frames_text(gone)}.")
    if tags and other_tracks:
        out.append("Job có tag và track của nhãn không phải mắt (gửi sẽ xoá tag).")
    lost = _non_eye_frames_on_deleted(aj, eye_ids, deleted_numbers)
    if lost:
        out.append(f"Nhãn không phải mắt nằm trên frame đã xoá trong CVAT ở frame {_frames_text(lost)} (gửi sẽ xoá chúng).")
    return out


def eye_shapes(aj: dict, labels: list[dict], frame_numbers: list[int]) -> list[AdoptedShape]:
    """Shape mắt của job, xếp theo (frame, label), toạ độ nguyên văn. Chỉ gọi khi `check` rỗng (không thì ValueError)."""
    eye_ids = _eye_label_ids(labels)
    names = {lb["id"]: lb["name"] for lb in labels if lb.get("id") in eye_ids}
    subs = _sublabel_points(labels)
    index = {n: i for i, n in enumerate(frame_numbers)}
    out = []
    for o in aj.get("shapes") or []:
        if not qc.is_eye_obj(o, eye_ids):
            continue
        name = names[o["label_id"]]
        els = _elements(o, name, subs)
        if els is None or _frame(o) not in index:
            raise ValueError(f"Shape mắt {name} ở frame {_frame(o)} không đọc được đủ 8 điểm: cần gọi adopt.check trước")
        points = {pid: (float(el["points"][0]), float(el["points"][1])) for pid, el in sorted(els.items())}
        flags = {pid: "outside" if el.get("outside") else "occluded" for pid, el in sorted(els.items()) if el.get("outside") or el.get("occluded")}
        out.append(AdoptedShape(name, index[_frame(o)], points, flags))
    return sorted(out, key=lambda s: (s.frame, s.label))


def shapes_from_ann(ann: Annotations) -> list[AdoptedShape]:
    """Shape mắt trong `ann.shapes` (file "CVAT for images" đã đọc), xếp theo (frame, label); cờ từ `PointState.outside` / `occluded`."""
    out = []
    for label, per_frame in ann.shapes.items():
        for frame, key in per_frame.items():
            pts = {i: key.points[i] for i in EYES[label].ids}
            out.append(AdoptedShape(label, frame, {i: tuple(p.xy) for i, p in pts.items()},
                                    {i: "outside" if p.outside else "occluded" for i, p in pts.items() if p.outside or p.occluded}))
    return sorted(out, key=lambda s: (s.frame, s.label))


def saved_shape_count(state: dict) -> int:
    """Số shape trong một file phiên đã đọc (`Session.state()` đọc từ file): số cặp (người, nhãn, frame) mà `pins[frame]` có đủ 8 id của mắt đó
    và `kind[nhãn] == "shape"`. File bản 1 (không có `layers`) và bản không có `kind` không có shape."""
    parts = state.get("layers") if state.get("version", 1) >= 2 else [state]
    total = 0
    for p in parts or []:
        kinds = p.get("kind") or {}
        for label, spec in EYES.items():
            if kinds.get(label) != "shape":
                continue
            need = {str(i) for i in spec.ids}
            total += sum(1 for pts in (p.get("pins") or {}).values() if need <= set(pts))
    return total
