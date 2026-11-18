"""Đọc và ghi file nhãn "CVAT 1.1" (annotations.xml của CVAT for video / CVAT for images).

Nguyên tắc: chỉ động tới hai skeleton mắt. Mọi thẻ khác (nhãn của skeleton khác, box, polygon, thuộc tính, meta) giữ
nguyên văn khi ghi lại, vì import vào job xoá toàn bộ nhãn cũ nên file ghi ra phải chứa tất cả.

Trong file có hai dạng chứa skeleton mắt:
  <track label="mattrai"> ... <skeleton frame="N" keyframe="1" outside=".."> <points label="14" .../> ...   (track)
  <image id="N" ...> <skeleton label="mattrai"> <points label="14" .../> ... (shape)
"""
from __future__ import annotations

import bisect
import copy
import xml.etree.ElementTree as ET
from collections.abc import Sequence
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
class EyeShape:
    """Một shape mắt (một frame, không nội suy): đủ 8 điểm kèm cờ của một người tại `key.frame` (chỉ số EyePin)."""
    label: str
    key: EyeKey
    attrs: dict = field(default_factory=dict)        # {"id": "19"}: chỉ để tool dùng, không ghi ra file


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
    được điền là Outside để mọi chỗ dùng sau đó luôn thấy đủ điểm của label. Toạ độ (0, 0) ở đây chỉ là tạm: `_fill_absent` thay bằng toạ độ
    CVAT đang giữ cho điểm đó."""
    out = {}
    for p in sk.findall("points"):
        x, y = (float(v) for v in p.get("points").split(","))
        out[int(p.get("label"))] = PointState((x, y), _to_bool(p.get("outside", "0")), _to_bool(p.get("occluded", "0")),
                                              _to_bool(p.get("keyframe", "1")))
    if label in EYES:
        for pid in EYES[label].ids:
            out.setdefault(pid, PointState((0.0, 0.0), True, False, False))
    return out


def _absent_ids(sk: ET.Element, label: str) -> set[int]:
    """Các điểm của label không có thẻ <points> trong skeleton này."""
    return set(EYES[label].ids) - {int(p.get("label")) for p in sk.findall("points")}


def _fill_absent(keys: dict[int, EyeKey], absent: dict[int, set[int]]) -> None:
    """Thay toạ độ tạm (0, 0) của điểm vắng (`absent`: frame -> các điểm vắng) bằng toạ độ CVAT đang giữ, để bản xem trước và phép quét
    không thấy điểm nhảy về góc ảnh (B02). Cờ (Outside, không keyframe) giữ nguyên; chỉ đổi dữ liệu đọc ra, cây XML không đụng tới.

    CVAT for video chỉ bỏ thẻ <points> ở frame không phải keyframe của điểm mà keyframe bên trái của điểm đang Outside (keyframe Outside
    thì vẫn xuất, kèm toạ độ đã lưu); ở đó CVAT nội suy đường thẳng giữa keyframe trái và keyframe phải của chính điểm ấy
    (`dataset_manager/bindings.py` `_export_track`, `annotation.py` `get_interpolated_shapes`). Hai keyframe đó chính là hai frame gần
    nhất có mặt điểm này, nên toạ độ là nội suy giữa chúng; chỉ có một phía (trước keyframe đầu, sau keyframe cuối) thì lấy phía đó.
    Không frame nào có điểm này thì lấy trọng tâm các điểm có mặt của chính skeleton đó."""
    if not absent:
        return
    frames = sorted(keys)
    for pid in set().union(*absent.values()):
        have = [g for g in frames if pid not in absent.get(g, ())]
        for f in frames:
            if pid not in absent.get(f, ()):
                continue
            k = bisect.bisect_left(have, f)
            a = have[k - 1] if k > 0 else None
            b = have[k] if k < len(have) else None
            if a is not None and b is not None:
                pa, pb = keys[a].points[pid].xy, keys[b].points[pid].xy
                w = (f - a) / (b - a)
                xy = (pa[0] + w * (pb[0] - pa[0]), pa[1] + w * (pb[1] - pa[1]))
            elif a is not None or b is not None:
                xy = keys[a if a is not None else b].points[pid].xy
            else:
                rest = [ps.xy for i, ps in keys[f].points.items() if i not in absent[f]]
                if not rest:
                    continue
                xy = (sum(p[0] for p in rest) / len(rest), sum(p[1] for p in rest) / len(rest))
            keys[f].points[pid].xy = xy


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
        absent: dict[int, set[int]] = {}
        for sk in tr.findall("skeleton"):
            f = int(sk.get("frame"))
            et.keys[f] = EyeKey(f, _read_skeleton_points(sk, label), _to_bool(sk.get("keyframe", "1")), _to_bool(sk.get("outside", "0")))
            absent[f] = _absent_ids(sk, label)
        _fill_absent(et.keys, {f: s for f, s in absent.items() if s})
        tracks[label].append(et)
    shape_absent: dict[str, dict[int, set[int]]] = {l: {} for l in EYE_LABELS}
    for im in root.findall("image"):
        f = int(im.get("id"))
        frame_names[f] = im.get("name", "")
        for sk in im.findall("skeleton"):
            label = sk.get("label")
            if label in EYE_LABELS:
                shapes[label][f] = EyeKey(f, _read_skeleton_points(sk, label), True, _to_bool(sk.get("outside", "0")))
                shape_absent[label][f] = _absent_ids(sk, label)
            else:
                other += 1
        for tag in ("box", "polygon", "polyline", "points", "ellipse", "cuboid", "mask", "tag"):
            other += len(im.findall(tag))
    for label in EYE_LABELS:
        _fill_absent(shapes[label], {f: s for f, s in shape_absent[label].items() if s})
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
               new_shapes: dict[str, dict[int, EyeKey]] | list[EyeShape] | None = None,
               frame_names: Sequence[str] | None = None, size: tuple[int, int] | None = None) -> None:
    """Ghi file mới: bỏ mọi skeleton mắt cũ, thêm skeleton mắt mới; mọi thứ khác giữ nguyên.

    new_tracks: {label: EyeTrack} hoặc danh sách EyeTrack (một label có thể có nhiều track), keyframe đủ 8 điểm.
    new_shapes: {label: {frame: EyeKey}} (dạng cũ, mỗi frame một shape) hoặc danh sách EyeShape (nhiều shape cùng label, cùng frame).
    frame_names[i]: tên ảnh của chỉ số EyePin i; size: (rộng, cao). Hai tham số này chỉ dùng để tạo thẻ <image> cho frame mà file chưa
    có (CVAT ghép <image> với frame của job theo `name` rồi mới tới `id`); thiếu `frame_names` mà frame chưa có <image> thì KeyError.
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
    if isinstance(new_shapes, dict):                      # dạng dict: frame là khoá dict (cả id lẫn tên <image>), không phải key.frame
        shape_list = [EyeShape(label, key) for label, per_frame in new_shapes.items() for key in per_frame.values()]
        idx_frames = [f for per_frame in new_shapes.values() for f in per_frame]
    else:
        shape_list = list(new_shapes or [])
        idx_frames = [sh.key.frame for sh in shape_list]
    by_id = {int(im.get("id")): im for im in root.findall("image")}
    created: dict[int, ET.Element] = {}
    for sh, f in zip(shape_list, idx_frames):
        jf = to_job(f)
        if jf not in by_id:
            if frame_names is None or not 0 <= f < len(frame_names) or jf is None:
                raise KeyError(f"File không có <image id={jf}>; shape mắt chỉ ghi được khi export ở dạng 'CVAT for images'")
            attrs = {"id": str(jf), "name": frame_names[f]}
            wh = size if size is not None else ((ann.width, ann.height) if ann.width and ann.height else None)
            if wh is not None:
                attrs["width"], attrs["height"] = (str(int(v)) for v in wh)
            by_id[jf] = created[jf] = ET.Element("image", attrs)
        by_id[jf].append(_skeleton_el(sh.key, EYES[sh.label].ids, False, sh.label))
    if created:                                           # <image> mới nằm trước <track> đầu tiên, theo thứ tự id
        children = list(root)
        at = next((k for k, el in enumerate(children) if el.tag == "track"), len(children))
        for n, jf in enumerate(sorted(created)):
            root.insert(at + n, created[jf])
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
