"""Chế độ QC: job đã có nhãn mắt thì chỉ xem; muốn gán lại thì bỏ nhãn mắt cũ (xem design/2026-11-16-cvat-direct-design.md mục 7)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .cvatxml import Annotations, EYE_LABELS

EYE_POINTS = 8                 # số điểm của một skeleton mắt


@dataclass
class EyeLabels:
    tracks: list[tuple[str, int, int, int]] = field(default_factory=list)   # (nhãn, id track, frame đầu, frame cuối)
    shapes: dict[str, int] = field(default_factory=dict)                    # nhãn -> số shape

    def empty(self) -> bool:
        return not self.tracks and not any(self.shapes.values())

    def message(self) -> str:
        if self.empty():
            return ""
        parts = []
        if self.tracks:
            desc = ", ".join(f"#{tid} ({label}, frame {a}–{b})" for label, tid, a, b in self.tracks)
            parts.append(f"{len(self.tracks)} track mắt {desc}")
        n = sum(self.shapes.values())
        if n:
            parts.append(f"{n} shape mắt")
        return " và ".join(parts)


def eye_labels(ann: Annotations) -> EyeLabels:
    tracks = []
    for label in EYE_LABELS:
        for t in ann.tracks.get(label, []):
            tid = int(t.attrs["id"]) if str(t.attrs.get("id", "")).isdigit() else -1
            frames = sorted(t.keys)
            tracks.append((label, tid, frames[0] if frames else 0, frames[-1] if frames else 0))
    shapes = {label: len(per) for label, per in ann.shapes.items() if per}
    return EyeLabels(tracks, shapes)


def has_eye_labels(ann: Annotations) -> bool:
    return not eye_labels(ann).empty()


def is_eye_obj(obj: dict, eye_ids: set[int] | None) -> bool:
    """Phần tử `shapes`/`tracks` của JSON `GET /api/jobs/{id}/annotations` có phải một mắt không (kể cả track rỗng hay toàn Outside).

    `eye_ids` là id nhãn của hai skeleton mắt; không biết (None) thì skeleton đủ 8 điểm được coi là mắt (shape và track skeleton đều có `elements`).
    """
    if eye_ids is not None:
        return obj.get("label_id") in eye_ids
    return len(obj.get("elements") or []) == EYE_POINTS


def json_has_eyes(annotations_json: dict, eye_ids: set[int] | None = None) -> bool:
    """True nếu JSON nhãn của job có bất kỳ mắt nào, kể cả khi XML đã xuất không còn thấy (track rỗng, toàn Outside, ngoài khoảng frame)."""
    return any(is_eye_obj(o, eye_ids) for k in ("shapes", "tracks") for o in annotations_json.get(k) or [])


def without_eyes(ann: Annotations) -> Annotations:
    """Bản sao không còn track và skeleton mắt; nhãn khác giữ nguyên."""
    out = copy.deepcopy(ann)
    root = out.tree.getroot()
    for tr in list(root.findall("track")):
        if tr.get("label") in EYE_LABELS:
            root.remove(tr)
    for im in root.findall("image"):
        for sk in list(im.findall("skeleton")):
            if sk.get("label") in EYE_LABELS:
                im.remove(sk)
    out.tracks = {l: [] for l in EYE_LABELS}
    out.shapes = {l: {} for l in EYE_LABELS}
    return out
