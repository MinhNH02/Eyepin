"""Chế độ QC: job đã có nhãn mắt thì chỉ xem; muốn gán lại thì bỏ nhãn mắt cũ (xem design/2026-11-16-cvat-direct-design.md mục 7)."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .cvatxml import Annotations, EYE_LABELS


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
