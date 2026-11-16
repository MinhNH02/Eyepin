"""Đọc và ghi file nhãn "CVAT 1.1" (annotations.xml của CVAT for video / CVAT for images).

Nguyên tắc: chỉ động tới hai skeleton mắt. Mọi thẻ khác (nhãn của skeleton khác, box, polygon, thuộc tính, meta) giữ
nguyên văn khi ghi lại, vì import vào job xoá toàn bộ nhãn cũ nên file ghi ra phải chứa tất cả.

Trong file có hai dạng chứa skeleton mắt:
  <track label="mattrai"> ... <skeleton frame="N" keyframe="1" outside=".."> <points label="14" .../> ...   (track)
  <image id="N" ...> <skeleton label="mattrai"> <points label="14" .../> ... (shape)
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .geometry import EYES, Point

EYE_LABELS = tuple(EYES)


@dataclass
class PointState:
    xy: Point
    outside: bool = False
    occluded: bool = False
    keyframe: bool = True        # chỉ có nghĩa với điểm trong track: điểm này có keyframe riêng tại frame đó


@dataclass
class EyeKey:
    """Một keyframe (track) hoặc một shape: đủ 8 điểm của một mắt tại một frame."""
    frame: int
    points: dict[int, PointState]
    keyframe: bool = True
    outside: bool = False          # cờ outside của cả skeleton


@dataclass
class EyeTrack:
    label: str
    keys: dict[int, EyeKey] = field(default_factory=dict)       # theo frame
    attrs: dict = field(default_factory=dict)


@dataclass
class Annotations:
    tree: ET.ElementTree
    frame_names: dict[int, str]                                    # frame -> tên ảnh (chỉ có ở dạng images)
    tracks: dict[str, list[EyeTrack]]                              # label -> các track mắt có sẵn
    shapes: dict[str, dict[int, EyeKey]]                           # label -> {frame: shape}
    other_objects: int                                             # số đối tượng không phải mắt (để kiểm)
    n_frames: int = 0                                              # số frame của job (từ <meta>, nếu có)
    width: float | None = None                                     # cỡ ảnh gốc (từ <original_size>, nếu có)
    height: float | None = None
    frame_numbers: list[int] | None = None                         # chỉ số EyePin i -> số frame của task trong XML của CVAT (None: trùng nhau)
    dropped: int = 0                                               # số nhãn bị bỏ vì frame nằm ngoài `frame_numbers` (parse_bytes)


def _to_bool(v) -> bool:
    return str(v) == "1"


def _read_skeleton_points(sk: ET.Element, label: str | None = None) -> dict[int, PointState]:
    """Đọc các điểm của một skeleton. CVAT 2.75 khi xuất bỏ hẳn thẻ của điểm đang Outside (đã thấy trên bản xuất job thật); điểm vắng mặt
    được điền là Outside ở (0, 0) để mọi chỗ dùng sau đó luôn thấy đủ điểm của label."""
    out = {}
    for p in sk.findall("points"):
        x, y = (float(v) for v in p.get("points").split(","))
        out[int(p.get("label"))] = PointState((x, y), _to_bool(p.get("outside", "0")), _to_bool(p.get("occluded", "0")),
                                              _to_bool(p.get("keyframe", "1")))
    if label in EYES:
        for pid in EYES[label].ids:
            out.setdefault(pid, PointState((0.0, 0.0), True, False, False))
    return out


def _remap_frames(root: ET.Element, fn) -> int:
    """Đổi số frame trong cây: `<image id>` và mọi `frame=` của thẻ con track hoặc thẻ gốc (tag...). `fn(n)` trả số mới, hoặc None để bỏ
    phần tử đó (frame ngoài phạm vi); track hết phần tử thì bị bỏ. Số frame trong <meta> không đụng tới. Trả về số nhãn đã bỏ: mỗi thẻ con
    của một `<image>` bị bỏ, mỗi phần tử track, mỗi thẻ gốc có `frame=` (`<image>` trống không tính vì không mang nhãn nào)."""
    dropped = 0
    for el in list(root):
        if el.tag == "image":
            new = fn(int(el.get("id")))
            if new is None:
                root.remove(el)
                dropped += len(el)
            else:
                el.set("id", str(new))
        elif el.tag == "track":
            for ch in list(el):
                if ch.get("frame") is not None:
                    new = fn(int(ch.get("frame")))
                    if new is None:
                        el.remove(ch)
                        dropped += 1
                    else:
                        ch.set("frame", str(new))
            if not any(ch.get("frame") is not None for ch in el):
                root.remove(el)
        elif el.get("frame") is not None:
            new = fn(int(el.get("frame")))
            if new is None:
                root.remove(el)
                dropped += 1
            else:
                el.set("frame", str(new))
    return dropped


def parse(path: str) -> Annotations:
    return _from_tree(ET.parse(path))


def parse_bytes(data: bytes, frame_numbers: list[int] | None = None) -> Annotations:
    """Đọc XML "CVAT 1.1" từ bytes (không qua file). Số frame trong XML của CVAT là số frame của TASK: nếu có `frame_numbers`
    (phần tử thứ i là số frame của chỉ số EyePin i) thì cây được đổi sang chỉ số EyePin, frame ngoài danh sách bị bỏ (đếm vào
    `dropped`), và `write_eyes` đổi ngược lại khi ghi."""
    try:
        tree = ET.ElementTree(ET.fromstring(data))
    except ET.ParseError as e:
        raise ValueError(f"XML của CVAT không đọc được: {e}") from e
    dropped = 0
    if frame_numbers is not None:
        index = {n: i for i, n in enumerate(frame_numbers)}
        dropped = _remap_frames(tree.getroot(), index.get)
    ann = _from_tree(tree)
    if frame_numbers is not None:
        ann.frame_numbers = list(frame_numbers)
        ann.n_frames = len(frame_numbers)
        ann.dropped = dropped
    return ann


def _from_tree(tree: ET.ElementTree) -> Annotations:
    root = tree.getroot()
    frame_names: dict[int, str] = {}
    tracks: dict[str, list[EyeTrack]] = {l: [] for l in EYE_LABELS}
    shapes: dict[str, dict[int, EyeKey]] = {l: {} for l in EYE_LABELS}
    other = 0
    for tr in root.findall("track"):
        label = tr.get("label")
        if label not in EYE_LABELS:
            other += 1
            continue
        et = EyeTrack(label, attrs=dict(tr.attrib))
        for sk in tr.findall("skeleton"):
            f = int(sk.get("frame"))
            et.keys[f] = EyeKey(f, _read_skeleton_points(sk, label), _to_bool(sk.get("keyframe", "1")), _to_bool(sk.get("outside", "0")))
        tracks[label].append(et)
    for im in root.findall("image"):
        f = int(im.get("id"))
        frame_names[f] = im.get("name", "")
        for sk in im.findall("skeleton"):
            label = sk.get("label")
            if label in EYE_LABELS:
                shapes[label][f] = EyeKey(f, _read_skeleton_points(sk, label), True, _to_bool(sk.get("outside", "0")))
            else:
                other += 1
        for tag in ("box", "polygon", "polyline", "points", "ellipse", "cuboid", "mask", "tag"):
            other += len(im.findall(tag))
    n_frames, width, height = 0, None, None
    meta = root.find("meta")
    if meta is not None:
        for scope in ("job", "task"):
            size = meta.findtext(f"{scope}/size")
            if size and size.isdigit():
                n_frames = int(size)
                break
        w, h = meta.findtext("task/original_size/width"), meta.findtext("task/original_size/height")
        if w and h:
            width, height = float(w), float(h)
    last = max([f for l in EYE_LABELS for f in shapes[l]] + [k for l in EYE_LABELS for t in tracks[l] for k in t.keys] + [-1])
    n_frames = max(n_frames, last + 1, len(frame_names))
    return Annotations(tree, frame_names, tracks, shapes, other, n_frames, width, height)


def _fmt(v: float) -> str:
    return f"{v:.2f}"


def _skeleton_el(key: EyeKey, ids: list[int], with_frame: bool, label: str | None, frame: int | None = None) -> ET.Element:
    attrs = {}
    if label is not None:
        attrs["label"] = label
        attrs["source"] = "manual"
    if with_frame:
        attrs["frame"] = str(key.frame if frame is None else frame)
        attrs["keyframe"] = "1"
    attrs["outside"] = "1" if key.outside else "0"
    attrs["occluded"] = "0"
    attrs["z_order"] = "0"
    sk = ET.Element("skeleton", attrs)
    for pid in ids:
        ps = key.points[pid]
        pa = {"label": str(pid)}
        if with_frame:
            pa["keyframe"] = "1"
        else:
            pa["source"] = "manual"
        pa.update({"outside": "1" if ps.outside else "0", "occluded": "1" if ps.occluded else "0",
                   "points": f"{_fmt(ps.xy[0])},{_fmt(ps.xy[1])}"})
        sk.append(ET.Element("points", pa))
    return sk


def write_eyes(ann: Annotations, out_path: str, *, new_tracks: dict[str, EyeTrack] | list[EyeTrack] | None = None,
               new_shapes: dict[str, dict[int, EyeKey]] | None = None) -> None:
    """Ghi file mới: bỏ mọi skeleton mắt cũ, thêm skeleton mắt mới; mọi thứ khác giữ nguyên.

    new_tracks: {label: EyeTrack} hoặc danh sách EyeTrack (một label có thể có nhiều track), keyframe đủ 8 điểm.
    new_shapes: {label: {frame: EyeKey}} dạng shape từng frame.
    """
    tree = copy.deepcopy(ann.tree)
    root = tree.getroot()
    nums = ann.frame_numbers

    def to_job(i):                                        # cây và khoá frame đang theo chỉ số EyePin; ghi ra phải là số frame của task
        if nums is None:
            return i
        return nums[i] if 0 <= i < len(nums) else None

    if nums is not None:
        _remap_frames(root, to_job)
    for tr in list(root.findall("track")):
        if tr.get("label") in EYE_LABELS:
            root.remove(tr)
    for im in root.findall("image"):
        for sk in list(im.findall("skeleton")):
            if sk.get("label") in EYE_LABELS:
                im.remove(sk)
    used = {int(t.get("id", -1)) for t in root.findall("track")}
    next_id = 1 + max(used | {-1})
    track_list = list(new_tracks.values()) if isinstance(new_tracks, dict) else list(new_tracks or [])
    for et in track_list:
        label = et.label
        spec = EYES[label]
        want = et.attrs.get("id")
        if want is not None and str(want).isdigit() and int(want) not in used:       # giữ ID của đối tượng trong tool nếu không trùng
            tid = int(want)
        else:
            tid = next_id
            next_id += 1
        used.add(tid)
        tr = ET.Element("track", {"id": str(tid), "label": label, "source": "manual"})
        for f in sorted(et.keys):
            if to_job(f) is None:
                raise ValueError(f"frame {f} nằm ngoài job")
            tr.append(_skeleton_el(et.keys[f], spec.ids, True, None, to_job(f)))
        root.append(tr)
    for label, per_frame in (new_shapes or {}).items():
        spec = EYES[label]
        by_id = {int(im.get("id")): im for im in root.findall("image")}
        for f, key in per_frame.items():
            jf = to_job(f)
            if jf not in by_id:
                raise KeyError(f"File không có <image id={jf}>; shape mắt chỉ ghi được khi export ở dạng 'CVAT for images'")
            by_id[jf].append(_skeleton_el(key, spec.ids, False, label))
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
