"""Phiên làm việc của EyePin: trạng thái của một job, không phụ thuộc giao diện.

Luồng: mở thư mục ảnh (và file nhãn nếu có) → ghim 4 điểm mỗi mắt ở các frame cần ghim → tool suy 8 điểm, bám theo ảnh
tiến về phía sau → quét → xuất file import chứa mọi nhãn của job.

Một frame ghim có thể chỉ chứa một mắt (ghim từng mắt: `pin_eye`, `add_pin_one`; nạp file `--pins`: `load_pins`); bộ bám đi riêng từng mắt.
"""
from __future__ import annotations

import copy
import itertools
import math
import numbers
import os
import time
from contextlib import contextmanager
import xml.etree.ElementTree as ET
from collections import OrderedDict

import cv2
import numpy as np

from . import cvatxml, headturn, qc
from .frames import DirSource, IMAGE_EXT
from .cvatxml import Annotations, EyeKey, EyeShape, EyeTrack, PointState
from .geometry import (EYES, HIDDEN_ERR_PX, Point, assign_roles, derive, hidden_neighbours, split_eyes,
                       split_seven, validate_four)
from .scan import Finding, scan
from .tracking import TrackResult, pin_jump, reduce_keyframes, track_forward

KEYFRAME_TOL = 2.0          # px: CVAT nội suy giữa keyframe không được lệch quá mức này so với nhãn do tool tính
GRAY_BUDGET = 250_000_000  # byte RAM tối đa cho ảnh xám dùng để bám (không bao giờ ghi ra đĩa)
MATCH_FLAG = 0.85           # độ khớp dưới mức này thì đánh dấu "cần ghim" (mắt đổi dáng)


QC_MSG = "Job đã có nhãn mắt: đang ở chế độ QC. Muốn sửa thì bấm 'Xoá nhãn mắt cũ và gán lại'."
SHAPE_KEY_MSG = "shape không có keyframe"
SHAPE_OUTSIDE_MSG = "shape không có Outside cho cả mắt; đánh Outside từng điểm hoặc xoá shape"
SHAPE_PIN_MSG = ("frame này có shape: bỏ cả frame ghim sẽ xoá luôn shape đó; bỏ keyframe của từng mắt track (K) "
                 "hoặc xoá shape (Del)")
KINDS = ("track", "shape")

_EYE_UIDS = itertools.count(1)     # mã nội bộ của từng mắt (Layer.eye_uid): tăng mãi, không dùng lại, kể cả giữa các phiên


def empty_annotations() -> Annotations:
    root = ET.Element("annotations")
    ET.SubElement(root, "version").text = "1.1"
    return Annotations(ET.ElementTree(root), {}, {l: [] for l in EYES}, {l: {} for l in EYES}, 0)


class Layer:
    """Một "bộ đối tượng" của job: tối đa một mattrai và một matphai cùng với keyframe, cờ và nhãn do tool tính của chúng.
    Một job có thể có nhiều Layer (nhiều người); ID của đối tượng luôn khác nhau giữa các Layer, như ID trong CVAT."""

    def __init__(self):
        self.pins: dict[int, dict[int, Point]] = {}                 # frame -> điểm của các mắt có keyframe ở frame đó
        self.pending: dict[int, dict[str, dict[int, Point]]] = {}   # frame -> {mắt: 8 điểm} khi mới ghim một mắt
        self.flags: dict[int, dict[int, str]] = {}                  # frame ghim -> {điểm: 'occluded' | 'outside'}
        self.estimates: dict[int, dict[int, float]] = {}            # frame ghim -> {điểm ước lượng: bán kính sai số px}
        self.labels: dict[int, TrackResult] = {}
        self.arrival: dict[int, TrackResult] = {}
        self.need_pin: list[int] = []
        self.obj_ids: dict[str, int] = {}                           # nhãn mắt -> ID đối tượng (chỉ mắt kiểu track)
        # nhãn mắt -> "track" | "shape". Mắt shape: mỗi frame trong `pins` có đủ 8 điểm của nó là một shape độc lập, không bám, không keyframe;
        # cờ và ước lượng ở frame đó là của chính shape đó. Kiểu cố định khi mắt còn nhãn; mắt không còn nhãn nào thì về "track".
        self.kind: dict[str, str] = {l: "track" for l in EYES}
        self.shape_ids: dict[str, dict[int, int]] = {l: {} for l in EYES}   # nhãn mắt -> {frame: ID của shape ở frame đó}
        self.segments: dict = {}                                    # đoạn bám đã tính (bộ nhớ đệm)
        # nhãn mắt -> mã nội bộ ổn định của mắt (có cả khi chưa có ID). Giao diện gắn ẩn riêng / khoá / Pinned vào mã này nên chúng đi
        # theo đúng mắt khi chỉ số người dịch (xoá người giữa), khi đổi label và khi hoàn tác / làm lại (mã nằm trong bản chụp hoàn tác).
        self.eye_uid: dict[str, int] = {l: next(_EYE_UIDS) for l in EYES}


def _layer_attr(name: str):
    return property(lambda self: getattr(self.layers[self.cur], name), lambda self, v: setattr(self.layers[self.cur], name, v))


class Session:
    # các thuộc tính cũ (pins, flags, ...) luôn là của Layer đang chọn nên mã dùng một đối tượng không phải đổi gì
    pins = _layer_attr("pins")
    pending = _layer_attr("pending")
    flags = _layer_attr("flags")
    estimates = _layer_attr("estimates")
    labels = _layer_attr("labels")
    arrival = _layer_attr("arrival")
    need_pin = _layer_attr("need_pin")
    obj_ids = _layer_attr("obj_ids")
    kind = _layer_attr("kind")
    shape_ids = _layer_attr("shape_ids")
    eye_uid = _layer_attr("eye_uid")
    _segments = _layer_attr("segments")

    def __init__(self, frames_dir: str | None = None, xml_path: str | None = None, *, source=None, ann: Annotations | None = None):
        if source is None:
            if frames_dir is None:
                raise ValueError("Cần thư mục ảnh hoặc một nguồn ảnh")
            source = DirSource(frames_dir)
        self.source = source
        self.frames_dir = frames_dir                         # None khi ảnh không đến từ một thư mục
        self.names = source.names
        self.n_frames = len(self.names)
        self.width, self.height = source.width, source.height
        self.ann = ann if ann is not None else cvatxml.parse(xml_path) if xml_path else empty_annotations()
        self.layers: list[Layer] = [Layer()]                 # các bộ đối tượng (nhiều người); self.cur là bộ đang chọn
        self.cur = 0
        self.qc = False                                      # True: job đã có nhãn mắt, chỉ xem (chỉ nơi gọi chọn CVAT mới bật)
        self.cvat: dict | None = None                        # {"job", "updated"} khi mở từ một job CVAT (cvatsource.open_job đặt sau khi tạo)
        self.base_format: str | None = None                  # định dạng nền khi gửi lên CVAT / định dạng hiện nhãn mắt (cũng do open_job đặt)
        self.display_format: str | None = None
        self._old_eyes: tuple | None = None                  # (ann cũ, ID đối tượng của bộ đầu, next_id) từ lúc clear_old_eyes
        self.findings: list[Finding] = []
        self.next_id = 1                                     # ID đối tượng kế tiếp (toàn job); ID đã xoá không dùng lại, như CVAT
        self._ids_from_ann()
        self.touched: dict[str, float] = {}                  # nhãn mắt -> lần sửa gần nhất (để sắp xếp theo thời gian cập nhật)
        self.deleted: set[int] = set(source.deleted)         # frame đã đánh dấu xoá (bỏ qua khi điều hướng, khôi phục được)
        self.dirty = False                                   # có thay đổi chưa lưu vào file phiên làm việc
        self.unsent = False                                  # job CVAT: có thay đổi nhãn chưa gửi lên CVAT (khác `dirty`: lưu file phiên không phải là gửi); cvatsync.send xoá cờ khi gửi và đối chiếu khớp
        self.stale = False                                   # True: lần tính lại gần nhất lỗi (ví dụ mất kết nối CVAT), nhãn do tool tính có thể cũ; không lưu vào file phiên
        self._undo: list[dict] = []                          # bản chụp các điểm ghim trước mỗi thay đổi
        self._redo: list[dict] = []
        self._gray: OrderedDict[int, np.ndarray] = OrderedDict()   # ảnh xám cho bộ bám: nhiều frame hơn _cache để tính lại không phải giải mã lại ảnh
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()   # ảnh chỉ giữ trong bộ nhớ, tối đa 40 frame
        self.turns: list[headturn.TurnReport] = []                  # đoạn quay đầu của từng bộ đối tượng (người), tính lại sau mỗi recompute
        self._refresh_turns()

    @property
    def source_key(self) -> str:
        return self.source.key

    @property
    def title(self) -> str:
        return self.source.title

    # ---- ảnh ----
    def bgr(self, f: int) -> np.ndarray:
        if f in self._cache:
            self._cache.move_to_end(f)
            return self._cache[f]
        img = self.source.read(f)
        self._cache[f] = img
        if len(self._cache) > 40:
            self._cache.popitem(last=False)
        return img

    def gray(self, f: int) -> np.ndarray:
        """Ảnh xám của frame f (giữ trong RAM theo ngân sách GRAY_BUDGET). Không đụng bộ nhớ đệm ảnh màu đang hiển thị."""
        g = self._gray.get(f)
        if g is not None:
            self._gray.move_to_end(f)
            return g
        src = self._cache.get(f)
        if src is None:
            src = self.source.read(f)
        g = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
        self._gray[f] = g
        cap = max(40, GRAY_BUDGET // max(1, self.width * self.height))
        while len(self._gray) > cap:
            self._gray.popitem(last=False)
        return g

    # ---- ghim ----
    def add_pin(self, frame: int, label: str, four: dict[int, Point]) -> bool:
        """Ghi 4 điểm ghim của một mắt tại `frame`. Trả True khi frame đã đủ hai mắt và trở thành frame ghim."""
        self._guard_qc()                                     # add_pin đổi pending/touched trước khi gọi _push_undo
        spec = EYES[label]
        self.pending.setdefault(frame, {})[label] = derive(spec, {i: four[i] for i in spec.pins})
        self.touched[label] = time.time()
        if len(self.pending[frame]) == len(EYES):
            self._push_undo()
            self.pins[frame] = {i: p for eye in self.pending.pop(frame).values() for i, p in eye.items()}
            self.flags.pop(frame, None)
            self.estimates.pop(frame, None)
            self.recompute()
            return True
        return False

    def load_pins(self, data: dict) -> int:
        """Ghim từ dữ liệu của file --pins: {"frame": {"id điểm": [x, y]}}; khoá frame bắt đầu bằng "_" là ghi chú và bị bỏ qua.

        Mắt có mặt trong một frame cần đủ 4 điểm ghim (mattrai 14, 16, 18, 20; matphai 22, 24, 26, 28); điểm suy ra (15, 17...) nếu có thì chỉ được
        kiểm rồi bỏ, tool suy lại từ 4 điểm ghim. Frame chỉ có một mắt thì thành keyframe của riêng mắt đó, mắt kia ở frame đó giữ nguyên (như `pin_eye`).
        Kiểm HẾT mọi frame trước khi đổi gì: frame là số nguyên trong phạm vi, không lặp, có ít nhất một mắt; id điểm thuộc 14–29; toạ độ là hai số
        hữu hạn nằm trong ảnh (0..rộng, 0..cao, như luật "ngoài khung" của scan); hai khoé không trùng và 4 điểm giống một con mắt (`validate_four`).
        Sai một chỗ thì ném ValueError tiếng Việt nêu frame, mắt, điểm và lý do, phiên không đổi gì (ghim, cờ, hoàn tác). Hợp lệ hết thì ghim mọi frame
        trong MỘT bước hoàn tác rồi tính lại một lần. Trả số frame của file đã thành frame ghim."""
        self._guard_qc()
        if not isinstance(data, dict):
            raise ValueError("file ghim phải là một đối tượng JSON {frame: {id: [x, y]}}")
        owner = {i: label for label, spec in EYES.items() for i in spec.ids}
        plan: dict[int, dict[str, dict[int, Point]]] = {}
        for k, d in data.items():
            if str(k).startswith("_"):
                continue
            try:
                f = int(k)
            except (TypeError, ValueError):
                raise ValueError(f"khoá frame không phải số: {k!r}") from None
            if not 0 <= f < self.n_frames:
                raise ValueError(f"frame {k} ngoài phạm vi 0–{self.n_frames - 1}")
            if f in plan:
                raise ValueError(f"frame {f} xuất hiện hai lần trong file ghim (khoá {k!r})")
            if not isinstance(d, dict):
                raise ValueError(f"frame {k}: điểm ghim sai định dạng (cần {{id: [x, y]}})")
            pts: dict[int, Point] = {}
            for i, v in d.items():
                try:
                    pid = int(i)
                except (TypeError, ValueError):
                    raise ValueError(f"frame {k}: id điểm không phải số: {i!r}") from None
                if pid not in owner:
                    raise ValueError(f"frame {k}: id điểm {i} không thuộc mắt nào (mattrai 14–21, matphai 22–29)")
                where = f"frame {k}, mắt {owner[pid]}, điểm {pid}"
                if not (isinstance(v, (list, tuple)) and len(v) == 2
                        and all(isinstance(c, numbers.Real) and not isinstance(c, bool) for c in v)):
                    raise ValueError(f"{where}: toạ độ phải là hai số [x, y], đang là {v!r}")
                try:
                    x, y = float(v[0]), float(v[1])
                except OverflowError:                                # số nguyên quá lớn cho float (JSON 1e400 viết không có dấu chấm)
                    raise ValueError(f"{where}: toạ độ không hữu hạn (số quá lớn)") from None
                if not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError(f"{where}: toạ độ không hữu hạn ({v[0]}, {v[1]})")
                if not (0 <= x <= self.width and 0 <= y <= self.height):
                    raise ValueError(f"{where}: ({x:g}, {y:g}) nằm ngoài ảnh {self.width}×{self.height}")
                pts[pid] = (x, y)
            eyes: dict[str, dict[int, Point]] = {}
            for label, spec in EYES.items():
                if not any(i in pts for i in spec.ids):
                    continue                                         # frame không có mắt này: mắt này ở frame đó giữ nguyên
                miss = [i for i in spec.pins if i not in pts]
                if miss:
                    raise ValueError(f"frame {k}, mắt {label}: thiếu điểm ghim {miss} (cần {list(spec.pins)})")
                four = {i: pts[i] for i in spec.pins}
                try:
                    if math.dist(four[spec.first], four[spec.last]) < 1e-6:
                        raise ValueError("hai khoé mắt trùng nhau")
                    validate_four(spec, four)
                except ValueError as err:
                    raise ValueError(f"frame {k}, mắt {label}: {err}") from None
                eyes[label] = derive(spec, four)
            if not eyes:
                raise ValueError(f"frame {k}: không có điểm ghim nào")
            plan[f] = eyes
        if not plan:
            return 0
        self._push_undo()                                            # cả file là một bước hoàn tác
        now = time.time()
        for f, eyes in sorted(plan.items()):
            merged = dict(self.pins.get(f, {}))
            for label, eye in eyes.items():
                ids = EYES[label].ids
                merged = {i: p for i, p in merged.items() if i not in ids}
                merged.update(eye)
                for store in (self.flags, self.estimates):          # cờ và ước lượng cũ của mắt này ở frame này không còn đúng (như pin_eye)
                    if f in store:
                        store[f] = {i: val for i, val in store[f].items() if i not in ids}
                        if not store[f]:
                            del store[f]
                self.touched[label] = now
            self.pins[f] = merged
        self.recompute()
        return len(plan)

    def add_pin_free(self, frame: int, clicks: list[Point]) -> dict[int, Point]:
        """Ghim từ 8 điểm bấm theo thứ tự tuỳ ý: tự chia hai mắt và gán vai trò từng điểm. Báo ValueError nếu không hợp lệ.
        Trả về {id điểm ghim: toạ độ} để giao diện hiển thị lại."""
        left, right = split_eyes(clicks)
        roles = {"mattrai": assign_roles(EYES["mattrai"], left), "matphai": assign_roles(EYES["matphai"], right)}
        for label, four in roles.items():
            self.add_pin(frame, label, four)
        return {i: p for four in roles.values() for i, p in four.items()}

    def add_pin_hidden(self, frame: int, clicks: list[Point]) -> dict:
        """Ghim khi một khoé bị che: 7 điểm bấm (4 điểm một mắt + 3 điểm mắt kia). Khoé bị che được ước lượng, khoé đó cùng hai điểm
        suy ra kề nó được đánh Occluded (theo guideline v1.3 mục 4.2). Trả về mô tả để hiển thị."""
        r = split_seven(clicks)
        full_label, full4 = r["full"]
        part_label, known, hidden, est = r["partial"]
        spec = EYES[part_label]
        four = dict(known)
        four[hidden] = est
        self.add_pin(frame, full_label, full4)
        self.add_pin(frame, part_label, four)
        near = hidden_neighbours(spec, hidden)
        self.flags[frame] = {hidden: "occluded", **{i: "occluded" for i in near}}
        self.estimates[frame] = {hidden: HIDDEN_ERR_PX, **{i: HIDDEN_ERR_PX for i in near}}
        return {"eye": part_label, "hidden": hidden, "estimate": est, "occluded": [hidden, *near]}

    def toggle_pin_here(self, f: int) -> bool:
        """Giống phím K của CVAT: biến frame do tool tính thành frame ghim (nhận nguyên nhãn đang hiển thị và cờ đang hiệu lực);
        nếu đã là frame ghim thì bỏ ghim. Trả True nếu sau thao tác frame là frame ghim."""
        self._guard_qc()
        if any(self.has_shape(l, f) for l in EYES):
            raise ValueError(SHAPE_KEY_MSG)
        if f in self.pins:
            self.remove_pin(f)
            return False
        if f not in self.labels:
            raise ValueError("frame này chưa có nhãn do tool tính; hãy ghim một frame đứng trước nó trước")
        self._push_undo()
        flags = self.flags_at(f)
        self.pins[f] = dict(self.labels[f].points)
        if flags:
            self.flags[f] = flags
        self.recompute()
        return True

    FILTERS = {"all": "Tất cả frame", "pinned": "Frame ghim", "need": "Frame cần ghim", "flagged": "Frame có Occluded/Outside",
               "red": "Cảnh báo đỏ", "yellow": "Cảnh báo vàng", "nolabel": "Frame chưa có nhãn"}

    def matches(self, f: int, mode: str) -> bool:
        """Frame f có thoả bộ lọc `mode` không (xem FILTERS)."""
        if mode == "all":
            return True
        if mode == "pinned":
            return f in self.pins
        if mode == "need":
            return f in self.need_pin
        if mode == "flagged":
            return bool(self.flags_at(f)) and f in self.labels
        if mode in ("red", "yellow"):
            return any(fd.level == mode and fd.frame <= f <= fd.last for fd in self.findings)
        if mode == "nolabel":
            return self.points_at(f) is None
        raise ValueError(mode)

    def next_match(self, f: int, step: int, mode: str) -> int | None:
        """Frame gần nhất theo hướng `step` (±1) thoả bộ lọc, không tính chính f."""
        rng = range(f + 1, self.n_frames) if step > 0 else range(f - 1, -1, -1)
        return next((g for g in rng if self.matches(g, mode)), None)

    def next_pin(self, f: int, step: int = 1) -> int | None:
        frames = sorted(self.pins)
        cand = [g for g in frames if g > f] if step > 0 else [g for g in frames if g < f][::-1]
        return cand[0] if cand else None

    def flags_at(self, f: int) -> dict[int, str]:
        """Cờ Occluded/Outside đang hiệu lực tại frame f: mỗi điểm lấy từ keyframe gần nhất (<= f) của chính mắt chứa nó, như CVAT (mỗi
        phần của skeleton có keyframe riêng). Trước đây lấy theo frame ghim gần nhất của cả hai mắt, nên ghim riêng một mắt làm mất cờ của mắt kia."""
        out: dict[int, str] = {}
        for label, spec in EYES.items():
            if self.kind[label] == "shape":                  # shape: chỉ cờ của chính shape ở frame f, không kế thừa
                if self.has_shape(label, f):
                    out.update({i: k for i, k in self.flags.get(f, {}).items() if i in spec.ids})
                continue
            prior = [g for g, pts in self.pins.items() if g <= f and all(i in pts for i in spec.ids)]
            if prior:
                out.update({i: k for i, k in self.flags.get(max(prior), {}).items() if i in spec.ids})
        return out

    def _flag_key(self, frame: int, label: str) -> bool | None:
        """Chuẩn bị đổi cờ của mắt `label` ở `frame` (đã gồm một bước hoàn tác). Frame chưa là keyframe của mắt đó thì, như CVAT, thành keyframe
        của riêng mắt đó: nhận nhãn đang hiển thị và cờ đang hiệu lực. Trả True nếu vừa tạo keyframe, False nếu đã có, None nếu frame chưa có nhãn."""
        self._guard_qc()                                     # báo QC cả khi frame chưa có nhãn (khi đó sẽ không gọi _push_undo)
        spec = EYES[label]
        if all(i in self.pins.get(frame, {}) for i in spec.ids):
            self._push_undo()
            return False
        if frame not in self.labels or not all(i in self.labels[frame].points for i in spec.ids):
            return None
        inherited = {i: k for i, k in self.flags_at(frame).items() if i in spec.ids}
        self._push_undo()
        self.pins.setdefault(frame, {}).update({i: self.labels[frame].points[i] for i in spec.ids})
        if inherited:
            self.flags.setdefault(frame, {}).update(inherited)
        self.touched[label] = time.time()
        return True

    def toggle_flag(self, frame: int, pid: int, kind: str) -> str | None:
        """Bật/tắt cờ `kind` ('occluded' | 'outside') của một điểm. Frame do tool tính thì thành keyframe của riêng mắt chứa điểm đó (một bước
        hoàn tác). Trả về cờ mới; None nếu vừa tắt cờ hoặc frame chưa có nhãn của mắt đó."""
        self._guard_qc()
        label = next((l for l, sp in EYES.items() if pid in sp.ids), None)
        made = None if label is None else self._flag_key(frame, label)
        if made is None:
            return None
        cur = self.flags.setdefault(frame, {})
        new = None if cur.get(pid) == kind else kind
        if new:
            cur[pid] = kind
        else:
            cur.pop(pid, None)
        self.recompute() if made else self._refresh_turns()          # điểm Outside không tính vào khoảng cách hai mắt
        return new

    def toggle_eye_flag(self, frame: int, label: str, kind: str) -> str | None:
        """Cờ cho cả mắt (như nút Occluded/Outside của cả đối tượng trong CVAT): nếu cả 8 điểm đã mang cờ `kind` thì bỏ hết, không thì đặt cả 8.
        Frame do tool tính thì thành keyframe của riêng mắt đó. Trả cờ mới hoặc None (đã bỏ, hoặc frame chưa có nhãn của mắt đó).
        Mắt shape không có Outside cả mắt (như CVAT): ValueError; Occluded cả mắt chỉ đổi shape ở frame đó."""
        self._guard_qc()
        if kind == "outside" and self.kind[label] == "shape":
            raise ValueError(SHAPE_OUTSIDE_MSG)
        made = self._flag_key(frame, label)
        if made is None:
            return None
        ids = EYES[label].ids
        cur = self.flags.setdefault(frame, {})
        new = None if all(cur.get(i) == kind for i in ids) else kind
        for i in ids:
            if new:
                cur[i] = kind
            else:
                cur.pop(i, None)
        self.recompute() if made else self._refresh_turns()
        return new

    def remove_pin(self, frame: int) -> None:
        """Bỏ cả frame ghim (mọi mắt). Frame có shape thì ValueError (`SHAPE_PIN_MSG`), không đổi gì: bỏ cả frame sẽ xoá luôn đối tượng
        shape đó; bỏ keyframe từng mắt track bằng `toggle_eye_key`, xoá shape bằng `delete_shape`."""
        self._guard_qc()                                     # đổi pending/flags cả khi frame không phải frame ghim
        if any(self.has_shape(l, frame) for l in EYES):
            raise ValueError(SHAPE_PIN_MSG)
        if frame in self.pins:
            self._push_undo()
        self.flags.pop(frame, None)
        self.estimates.pop(frame, None)
        self.pins.pop(frame, None)
        self.pending.pop(frame, None)
        self.recompute()

    def move_point(self, frame: int, pid: int, xy: Point) -> None:
        """Kéo tay một điểm ở frame ghim; mọi frame sau nó (tới frame ghim kế tiếp) được tính lại."""
        self._guard_qc()
        if frame in self.pins:
            self._push_undo()
            self.pins[frame][pid] = xy
            self.estimates.get(frame, {}).pop(pid, None)     # đã chỉnh tay: không còn là ước lượng
            self.recompute()

    def drag_point(self, frame: int, pid: int, xy: Point) -> bool:
        """Kéo thả một điểm (xem `drag_points`)."""
        return self.drag_points(frame, {pid: xy})

    def drag_points(self, frame: int, new: dict[int, Point]) -> bool:
        """Kéo thả điểm hoặc cả một mắt ở frame bất kỳ có nhãn do tool tính: mắt chứa các điểm trong `new` mà chưa là keyframe ở frame đó thì
        thành keyframe của RIÊNG mắt đó (nhận nhãn đang hiển thị và cờ đang hiệu lực của mắt đó), mắt kia giữ nguyên, như CVAT (B26, cùng cách
        `_flag_key`); rồi các điểm trong `new` được đặt vào toạ độ mới; các frame sau tính lại. Một bước hoàn tác.
        Mọi điểm trong `new` trùng toạ độ đang hiển thị thì không làm gì (trả False, không ghim, không hoàn tác). Trả True nếu vừa tạo keyframe mới."""
        self._guard_qc()
        if not new:
            return False
        have = self.pins.get(frame, {})
        eyes = [l for l, sp in EYES.items() if any(pid in sp.ids for pid in new)]
        keyed = {l: all(i in have for i in EYES[l].ids) for l in eyes}
        shown: dict[int, Point] = {}
        for l in eyes:
            ids = EYES[l].ids
            if not keyed[l] and self.kind[l] == "shape":     # shape chỉ sửa được ở chính frame của nó; không tạo shape mới bằng kéo
                raise ValueError(f"frame này không có shape của {l}")
            if not keyed[l] and (frame not in self.labels or not all(i in self.labels[frame].points for i in ids)):
                raise ValueError("frame này chưa có nhãn do tool tính; hãy ghim một frame đứng trước nó trước")
            src = have if keyed[l] else self.labels[frame].points
            shown.update({i: src[i] for i in ids})
        if all(pid in shown and tuple(shown[pid]) == tuple(xy) for pid, xy in new.items()):
            return False                                     # toạ độ không đổi (bấm không kéo): không ghim, không thêm bước hoàn tác rỗng
        inherited = self.flags_at(frame)                     # tính trước khi đổi pins
        self._push_undo()
        newly = False
        for l in eyes:
            if keyed[l]:
                continue
            ids = EYES[l].ids
            self.pins.setdefault(frame, {}).update({i: self.labels[frame].points[i] for i in ids})
            mine = {i: k for i, k in inherited.items() if i in ids}
            if mine:
                self.flags.setdefault(frame, {}).update(mine)
            newly = True
        for pid, xy in new.items():
            self.pins.setdefault(frame, {})[pid] = xy
            self.touched.update({l: time.time() for l, sp in EYES.items() if pid in sp.ids})
            self.estimates.get(frame, {}).pop(pid, None)
        self.recompute()
        return newly

    def paste_points(self, frame: int, pts: dict[int, Point]) -> None:
        """Dán nhãn vào `frame` (thành frame ghim, một bước hoàn tác): đủ 16 điểm hai mắt, hoặc 8 điểm của một mắt
        (khi đó frame phải đã có nhãn, trừ mắt shape: dán một mắt shape vào frame chưa có nhãn nào thì tạo shape mới ở đó).
        Dán một mắt chỉ làm mắt đó thành keyframe và chỉ bỏ cờ của mắt đó; mắt kia và cờ của nó giữ nguyên (B26)."""
        self._guard_qc()
        every = {i for spec in EYES.values() for i in spec.ids}
        one = next((spec for spec in EYES.values() if set(pts) == set(spec.ids)), None)
        if set(pts) == every:
            self._push_undo()
            self.pins[frame] = {i: tuple(p) for i, p in pts.items()}
            self.flags.pop(frame, None)
            self.estimates.pop(frame, None)
        elif one is not None:
            eye = next(l for l, sp in EYES.items() if sp is one)
            if self.kind[eye] != "shape" and not self.pins.get(frame) and frame not in self.labels:
                raise ValueError("frame này chưa có nhãn mắt kia nên chưa dán được một mắt")
            self._push_undo()
            self.pins.setdefault(frame, {}).update({i: tuple(p) for i, p in pts.items()})
            for store in (self.flags, self.estimates):               # cờ và ước lượng cũ của mắt được dán ở frame này không còn đúng
                if frame in store:
                    store[frame] = {i: v for i, v in store[frame].items() if i not in one.ids}
                    if not store[frame]:
                        del store[frame]
        else:
            raise ValueError("nhãn dán phải đủ 16 điểm của hai mắt hoặc đủ 8 điểm của một mắt")
        self.touched.update({l: time.time() for l, sp in EYES.items() if set(sp.ids) & set(pts)})
        self.recompute()

    def swap_eyes(self) -> None:
        """Hoán đổi vai trò mattrai và matphai ở mọi frame ghim (sửa khi tool gán nhầm trái/phải). Một bước hoàn tác.
        Mã nội bộ `eye_uid`, kiểu (`kind`) và ID shape đổi chỗ cùng dữ liệu (ẩn riêng / Pinned của giao diện đi theo mắt); ID đối tượng
        của mắt track giữ theo label như trước."""
        a, b = EYES["mattrai"].ids, EYES["matphai"].ids
        mp = {**dict(zip(a, b)), **dict(zip(b, a))}
        self._push_undo()
        self.eye_uid = {"mattrai": self.eye_uid["matphai"], "matphai": self.eye_uid["mattrai"]}
        self.kind = {"mattrai": self.kind["matphai"], "matphai": self.kind["mattrai"]}
        self.shape_ids = {"mattrai": self.shape_ids["matphai"], "matphai": self.shape_ids["mattrai"]}
        self.pins = {f: {mp[i]: p for i, p in pts.items()} for f, pts in self.pins.items()}
        self.flags = {f: {mp[i]: k for i, k in fl.items()} for f, fl in self.flags.items()}
        self.estimates = {f: {mp[i]: r for i, r in es.items()} for f, es in self.estimates.items()}
        self.recompute()

    def _propagate_source(self, frame: int) -> dict[int, Point]:
        """Điểm sẽ được nhân từ `frame`: điểm ghim của frame nếu frame là frame ghim, không thì nhãn do tool tính (như trước)."""
        if frame not in self.labels and frame not in self.pins:
            raise ValueError("frame này chưa có nhãn để nhân")
        return dict(self.pins.get(frame) or self.labels[frame].points)

    def propagate_eyes(self, frame: int) -> list[str]:
        """Các mắt (người đang chọn) mà `propagate` từ `frame` sẽ nhân; mắt khác ở frame đích giữ nguyên. Frame chưa có nhãn thì ValueError."""
        pts = self._propagate_source(frame)
        return [l for l, sp in EYES.items() if any(i in pts for i in sp.ids)]

    def propagate(self, frame: int, count: int = 0, direction: int = 1, start: int | None = None, end: int | None = None) -> int:
        """Nhân nhãn đang hiển thị ở `frame` sang các frame khác (mỗi frame thành frame ghim, chép cả cờ), như hộp "Confirm propagation" của CVAT:
        `count` bản sao theo `direction` (+1 sang sau, -1 sang trước), hoặc cả khoảng frame [start, end] nếu có start và end.
        Mắt shape nhân thành shape mới (mỗi frame đích một ID riêng, `recompute` cấp), mắt track nhân thành keyframe như cũ.
        Nhân THEO TỪNG MẮT (`propagate_eyes`): ở frame đích chỉ điểm, cờ và ước lượng của mắt được nhân bị thay; mắt kia (keyframe, cờ Outside,
        shape của nó) giữ nguyên. Trước đây cả frame đích bị thay nên shape hay keyframe của mắt kia mất mà không báo gì.
        Trả về số frame đã nhân (không tính chính `frame`)."""
        self._guard_qc()
        pts = self._propagate_source(frame)
        moved = {i for l in self.propagate_eyes(frame) for i in EYES[l].ids}
        flags = {i: k for i, k in self.flags_at(frame).items() if i in moved}
        if start is not None and end is not None:
            lo, hi = sorted((max(0, int(start)), min(self.n_frames - 1, int(end))))
            targets = [g for g in range(lo, hi + 1) if g != frame]
        elif direction >= 0:
            targets = list(range(frame + 1, min(self.n_frames, frame + 1 + max(0, count))))
        else:
            targets = [g for g in range(frame - 1, max(-1, frame - 1 - max(0, count)), -1)]
        if not targets:
            return 0
        self._push_undo()
        for g in targets:
            keep = {i: p for i, p in self.pins.get(g, {}).items() if i not in moved}
            self.pins[g] = {**keep, **pts}
            es = {i: r for i, r in self.estimates.get(g, {}).items() if i not in moved}
            fl = {**{i: k for i, k in self.flags.get(g, {}).items() if i not in moved}, **flags}
            for store, val in ((self.estimates, es), (self.flags, fl)):
                if val:
                    store[g] = val
                else:
                    store.pop(g, None)
        self.touched.update({l: time.time() for l in EYES if set(EYES[l].ids) & moved})
        self.recompute()
        return len(targets)

    # ---- xoá label (mắt) ----
    def eyes_in_pin(self, frame: int) -> list[str]:
        pts = self.pins.get(frame, {})
        return [l for l, sp in EYES.items() if all(i in pts for i in sp.ids)]

    def missing_eyes(self) -> list[str]:
        """Mắt không còn trong frame ghim nào (đã bị xoá) trong khi mắt kia vẫn còn; rỗng nếu chưa xoá hay chưa có nhãn."""
        have = {l for f in self.pins for l in self.eyes_in_pin(f)}
        return [l for l in EYES if l not in have] if have else []

    def delete_eye(self, label: str) -> int:
        """Xoá mắt `label` khỏi mọi frame ghim (như xoá đối tượng trong CVAT); mắt kia không đổi. Hoàn tác được. Trả về số frame ghim bị đổi."""
        self._guard_qc()
        ids = set(EYES[label].ids)
        hit = [f for f, pts in self.pins.items() if ids & set(pts)]
        if not hit:
            raise ValueError(f"{label} chưa có nhãn nào để xoá")
        self._push_undo()
        for f in hit:
            self.pins[f] = {i: p for i, p in self.pins[f].items() if i not in ids}
            for store in (self.flags, self.estimates):
                if f in store:
                    store[f] = {i: v for i, v in store[f].items() if i not in ids}
                    if not store[f]:
                        del store[f]
            if not self.pins[f]:
                del self.pins[f]
                self.flags.pop(f, None)
                self.estimates.pop(f, None)
        self.touched[label] = time.time()
        self.obj_ids.pop(label, None)                            # ID của đối tượng đã xoá không dùng lại (như CVAT)
        self.eye_uid[label] = next(_EYE_UIDS)                    # vẽ lại mắt này là đối tượng mới; Ctrl+Z trả mã cũ (và trạng thái giao diện của nó)
        if not self.pins and len(self.layers) > 1:               # bộ đối tượng không còn gì thì bỏ luôn
            del self.layers[self.cur]
            self.cur = min(self.cur, len(self.layers) - 1)
        self.recompute()
        return len(hit)

    def delete_shape(self, label: str, frame: int) -> None:
        """Xoá shape của mắt `label` ở `frame` (như xoá một đối tượng shape trong CVAT): bỏ 8 điểm, cờ và ước lượng của mắt đó ở frame đó;
        mắt kia và các shape khác không đổi. ID của shape đã xoá không dùng lại. Một bước hoàn tác. Frame không có shape thì ValueError.
        Bộ đối tượng (người) không còn nhãn nào và job có hơn một người thì bỏ luôn người đó (như `delete_eye`)."""
        self._guard_qc()
        if not self.has_shape(label, frame):
            raise ValueError(f"frame này không có shape của {label}")
        ids = set(EYES[label].ids)
        self._push_undo()
        self.pins[frame] = {i: p for i, p in self.pins[frame].items() if i not in ids}
        for store in (self.flags, self.estimates):
            if frame in store:
                store[frame] = {i: v for i, v in store[frame].items() if i not in ids}
                if not store[frame]:
                    del store[frame]
        if not self.pins[frame]:
            del self.pins[frame]
            self.flags.pop(frame, None)                          # frame hết ghim thì không còn gì để mang cờ / ước lượng (như delete_eye)
            self.estimates.pop(frame, None)
        self.touched[label] = time.time()
        if not self._eye_has_labels(label):
            self.eye_uid[label] = next(_EYE_UIDS)                # hết shape: vẽ lại mắt này là đối tượng mới (như delete_eye)
        if not self.pins and len(self.layers) > 1:
            del self.layers[self.cur]
            self.cur = min(self.cur, len(self.layers) - 1)
        self.recompute()

    def end_eye_here(self, label: str, frame: int) -> None:
        """Kết thúc nhãn của `label` từ `frame` trở đi: đánh Outside cả 8 điểm của mắt đó tại `frame`; cờ chép sang các frame sau. Frame chưa là
        keyframe của mắt đó thì thành keyframe của RIÊNG mắt đó (nhận nhãn đang hiển thị), mắt kia không đổi, như CVAT. Một bước hoàn tác.
        Mắt shape không có lệnh này (ValueError)."""
        self._guard_qc()
        if self.kind[label] == "shape":
            raise ValueError(SHAPE_OUTSIDE_MSG)
        if self._flag_key(frame, label) is None:             # _flag_key đã gồm bước hoàn tác và chỉ ghim mắt `label`
            raise ValueError("frame này chưa có nhãn của mắt đó")
        self.flags.setdefault(frame, {}).update({i: "outside" for i in EYES[label].ids})
        self.touched[label] = time.time()
        self.recompute()

    def pin_eye(self, frame: int, label: str, four: dict[int, Point], kind: str | None = None) -> None:
        """Ghim riêng mắt `label` ở `frame` từ 4 điểm ghim đã biết vai trò (mắt vẽ trong bảng Vẽ mắt rồi Apply). Không gán lại vai trò,
        chỉ kiểm hình (ValueError nếu không giống một mắt); không biến nhãn do tool tính của mắt kia ở frame này thành keyframe, như vẽ
        một skeleton trong CVAT.
        `kind` ("track" | "shape"): mắt chưa có nhãn nào thì nhận kiểu đó; None thì giữ kiểu đang có. Mắt đang có nhãn mà `kind` khác kiểu
        hiện tại thì ValueError và phiên không đổi gì. Mắt shape: ghim ở `frame` là shape ở frame đó (frame đã có shape thì vẽ đè, giữ ID)."""
        self._guard_qc()
        spec = EYES[label]
        cur = self.kind[label]
        kind = cur if kind is None else kind
        if kind not in KINDS:
            raise ValueError(f"kiểu nhãn không hợp lệ: {kind!r} (cần 'track' hoặc 'shape')")
        if kind != cur and self._eye_has_labels(label):
            raise ValueError(f"{label} của người này đang là {cur}; xoá nhãn đó hoặc thêm người mới (+) để vẽ kiểu khác")
        validate_four(spec, four)
        self._push_undo()
        self.kind[label] = kind
        base = {i: p for i, p in self.pins.get(frame, {}).items() if i not in spec.ids}
        base.update(derive(spec, {i: four[i] for i in spec.pins}))
        self.pins[frame] = base
        for store in (self.flags, self.estimates):                # cờ và ước lượng cũ của mắt này ở frame này không còn đúng
            if frame in store:
                store[frame] = {i: v for i, v in store[frame].items() if i not in spec.ids}
                if not store[frame]:
                    del store[frame]
        self.touched[label] = time.time()
        self.recompute()

    def add_pin_one(self, frame: int, clicks: list[Point], label: str | None = None) -> str:
        """Ghim một mắt từ 4 điểm bấm (thứ tự tuỳ ý) vào `frame`, giữ nguyên mắt kia: dùng để ghim lại mắt đã xoá hoặc ghim từng mắt riêng.
        Nếu không nói rõ `label`: mắt đang thiếu; nếu cả hai đều có thì chọn theo vị trí so với mắt kia. Trả về nhãn đã gán."""
        self._guard_qc()
        base = dict(self.pins.get(frame) or (self.labels[frame].points if frame in self.labels else {}))
        if label is None:
            miss = self.missing_eyes()
            cx = sum(p[0] for p in clicks) / len(clicks)
            here = [l for l in EYES if all(i in base for i in EYES[l].ids)]
            if len(miss) == 1:
                label = miss[0]
            elif len(here) == 2:                                   # cả hai mắt đang có ở frame này: sửa lại mắt gần các điểm bấm nhất
                label = min(here, key=lambda l: abs(sum(base[i][0] for i in EYES[l].ids) / 8 - cx))
            elif len(here) == 1:                                   # chỉ có một mắt ở frame này: mắt mới là mắt còn lại
                label = next(l for l in EYES if l != here[0])
            else:
                label = "mattrai" if cx < self.width / 2 else "matphai"
        spec = EYES[label]
        four = assign_roles(spec, list(clicks))
        eye = derive(spec, four)
        self._push_undo()
        base.update(eye)
        self.pins[frame] = base
        self.estimates.pop(frame, None)
        self.touched[label] = time.time()
        self.recompute()
        return label

    def pin_count(self) -> int:
        """Tổng số frame ghim của MỌI người trong job (phạm vi của clear_all), không chỉ người đang chọn."""
        return sum(len(L.pins) for L in self.layers)

    def clear_all(self) -> int:
        """Xoá mọi frame ghim, cờ và ước lượng (như Remove annotations của CVAT); hoàn tác được. Trả về số frame ghim đã xoá."""
        self._guard_qc()                                     # đổi layers/pending cả khi không có frame ghim
        n = self.pin_count()
        if n or len(self.layers) > 1:                        # bỏ cả bộ trống của người khác thì cũng phải hoàn tác được
            self._push_undo()
        for L in self.layers:
            L.pins, L.flags, L.estimates, L.pending = {}, {}, {}, {}
        self.layers, self.cur = self.layers[:1], 0
        self.recompute()
        return n

    def delete_frame(self, f: int) -> None:
        self.deleted.add(f)
        self.dirty = True

    def restore_frame(self, f: int) -> None:
        self.deleted.discard(f)
        self.dirty = True

    def next_visible(self, f: int, step: int, show_deleted: bool = False) -> int | None:
        """Frame kế (step > 0) hoặc trước (step < 0) f không bị xoá; None nếu hết."""
        g = f + (1 if step > 0 else -1)
        while 0 <= g < self.n_frames:
            if show_deleted or g not in self.deleted:
                return g
            g += 1 if step > 0 else -1
        return None

    # ---- hoàn tác ----
    def _snapshot(self) -> dict:
        return {"layers": [{"pins": copy.deepcopy(L.pins), "flags": copy.deepcopy(L.flags), "estimates": copy.deepcopy(L.estimates),
                            "ids": dict(L.obj_ids), "uid": dict(L.eye_uid), "kind": dict(L.kind),
                            "shape_ids": {l: dict(d) for l, d in L.shape_ids.items()}} for L in self.layers],
                "cur": self.cur, "next_id": self.next_id}

    def _restore(self, snap: dict) -> None:
        while len(self.layers) < len(snap["layers"]):
            self.layers.append(Layer())
        del self.layers[len(snap["layers"]):]
        for L, d in zip(self.layers, snap["layers"]):                    # dùng lại Layer cũ để giữ bộ nhớ đệm đoạn bám
            L.pins, L.flags, L.estimates, L.obj_ids = d["pins"], d["flags"], d["estimates"], dict(d["ids"])
            L.eye_uid = dict(d.get("uid", L.eye_uid))                   # mã mắt theo bản chụp: trạng thái giao diện về đúng mắt (B08, B09)
            L.kind = dict(d.get("kind") or {l: "track" for l in EYES})  # kiểu và ID shape theo bản chụp: xoá shape rồi hoàn tác trả đúng ID cũ
            L.shape_ids = {l: dict(v) for l, v in (d.get("shape_ids") or {l: {} for l in EYES}).items()}
        self.cur, self.next_id = min(snap["cur"], len(self.layers) - 1), snap["next_id"]
        self.recompute()

    def _ids_from_ann(self) -> None:
        """Lấy ID track mắt có sẵn trong file nhãn đã mở; ID mới đánh tiếp sau ID lớn nhất của mọi track trong file."""
        root = self.ann.tree.getroot() if self.ann.tree is not None else None
        every = [int(t.get("id")) for t in root.findall("track") if (t.get("id") or "").isdigit()] if root is not None else []
        for label, trs in self.ann.tracks.items():
            if trs and str(trs[0].attrs.get("id", "")).isdigit():
                self.obj_ids[label] = int(trs[0].attrs["id"])
        self.next_id = 1 + max(every + list(self.obj_ids.values()) + [0])

    def _assign_ids(self) -> None:
        """Cấp ID cho đối tượng mới của Layer đang chọn. Mắt track: một ID cho cả mắt khi nó có keyframe đầu tiên. Mắt shape: mỗi shape một ID,
        cấp theo frame tăng dần; mục của frame không còn shape bị bỏ (ID đó không dùng lại). Mắt không còn nhãn nào thì kiểu về "track"."""
        for label, spec in EYES.items():
            if not self._eye_has_labels(label):
                self.kind[label] = "track"
            if self.kind[label] == "shape":
                self.obj_ids.pop(label, None)                    # mắt shape không có ID của cả mắt
                have = self._shape_frames(label)
                got = self.shape_ids[label]
                for f in [f for f in got if f not in have]:
                    del got[f]
                for f in have:
                    if f not in got:
                        got[f] = self.next_id
                        self.next_id += 1 + len(spec.ids)
                continue
            if self.shape_ids[label]:
                self.shape_ids[label] = {}                       # mắt vừa hết shape và về track: bỏ ID shape cũ (không dùng lại)
            if label not in self.obj_ids and any(all(i in pts for i in spec.ids) for pts in self.pins.values()):
                self.obj_ids[label] = self.next_id
                self.next_id += 1 + len(spec.ids)                # CVAT đánh số cả 8 điểm con: skeleton thứ nhất là 1, thứ hai là 10, rồi 19...

    def object_id(self, label: str, frame: int | None = None) -> int | None:
        """ID đối tượng của mắt `label`: mắt track thì ID của cả mắt (bỏ qua `frame`); mắt shape thì ID của shape ở `frame` (None nếu không có)."""
        if self.kind[label] == "shape":
            return None if frame is None else self.shape_ids[label].get(frame)
        return self.obj_ids.get(label)

    def frame_ids(self, frame: int) -> dict[str, int]:
        """ID đối tượng của từng mắt (người đang chọn) đang hiện ở `frame`: mắt track như `obj_ids`, mắt shape là ID của shape ở frame đó
        (không có shape thì không có mục). Dùng cho chữ và màu theo đối tượng khi vẽ."""
        return {l: n for l in EYES if (n := self.object_id(l, frame)) is not None}

    def eye_kind(self, label: str) -> str:
        """Kiểu của mắt `label` của người đang chọn: "track" hoặc "shape"."""
        return self.kind[label]

    def has_shape(self, label: str, frame: int) -> bool:
        """Mắt `label` của người đang chọn là shape và có shape ở `frame`."""
        return self.kind[label] == "shape" and all(i in self.pins.get(frame, {}) for i in EYES[label].ids)

    def _shape_frames(self, label: str) -> list[int]:
        return sorted(f for f, pts in self.pins.items() if all(i in pts for i in EYES[label].ids))

    def _eye_has_labels(self, label: str) -> bool:
        ids = set(EYES[label].ids)
        return any(ids & set(pts) for pts in self.pins.values())

    def eye_keyframes(self, label: str) -> list[int]:
        """Frame ghim (keyframe) của riêng mắt `label`. Mắt shape không có keyframe: trả []."""
        if self.kind[label] == "shape":
            return []
        return sorted(f for f, pts in self.pins.items() if all(i in pts for i in EYES[label].ids))

    def toggle_eye_key(self, label: str, f: int) -> bool:
        """Phím K của CVAT cho một đối tượng: nếu `f` là keyframe của mắt này thì bỏ keyframe riêng của nó (mắt kia không đổi);
        không thì biến nhãn do tool tính tại `f` thành keyframe của riêng mắt này. Trả True nếu sau thao tác là keyframe. Mắt shape: ValueError."""
        self._guard_qc()
        if self.kind[label] == "shape":
            raise ValueError(SHAPE_KEY_MSG)
        ids = set(EYES[label].ids)
        if f in self.pins and ids <= set(self.pins[f]):
            self._push_undo()
            self.pins[f] = {i: p for i, p in self.pins[f].items() if i not in ids}
            for store in (self.flags, self.estimates):
                if f in store:
                    store[f] = {i: v for i, v in store[f].items() if i not in ids}
                    if not store[f]:
                        del store[f]
            if not self.pins[f]:
                del self.pins[f]
            self.recompute()
            return False
        if f not in self.labels or not ids <= set(self.labels[f].points):
            raise ValueError("frame này chưa có nhãn do tool tính cho mắt đó; hãy ghim một frame đứng trước nó trước")
        self._push_undo()
        flags = {i: k for i, k in self.flags_at(f).items() if i in ids}
        self.pins.setdefault(f, {}).update({i: self.labels[f].points[i] for i in ids})
        if flags:
            self.flags.setdefault(f, {}).update(flags)
        self.touched[label] = time.time()
        self.recompute()
        return True

    def _guard_qc(self) -> None:
        if self.qc:
            raise ValueError(QC_MSG)

    def _push_undo(self) -> None:
        self._guard_qc()
        self.dirty = True
        self.unsent = True
        self._undo.append(self._snapshot())
        del self._undo[:-100]
        self._redo.clear()

    def undo(self) -> bool:
        self._guard_qc()
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        self.dirty = True
        self.unsent = True
        return True

    def redo(self) -> bool:
        self._guard_qc()
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        self.dirty = True
        self.unsent = True
        return True

    # ---- lưu / mở phiên làm việc (chỉ toạ độ và cờ, không có ảnh) ----
    def state(self) -> dict:
        """Mọi thứ người dùng đã làm: với từng bộ đối tượng, các frame ghim, cờ Occluded/Outside, điểm ước lượng, ID, kiểu (track/shape) của
        từng mắt và ID của từng shape. Nhãn do tool tính được tính lại khi mở. Bản 3 thêm `kind` và `shape_ids`; bản 1, 2 mở được (toàn track)."""
        out = {"version": 3, "frames": self.n_frames, "names": [self.names[0], self.names[-1]], "deleted": sorted(self.deleted),
               "cur": self.cur, "next_id": self.next_id,
               "layers": [{"pins": {str(f): {str(i): list(p) for i, p in pts.items()} for f, pts in L.pins.items()},
                           "flags": {str(f): {str(i): k for i, k in fl.items()} for f, fl in L.flags.items()},
                           "estimates": {str(f): {str(i): r for i, r in es.items()} for f, es in L.estimates.items()},
                           "ids": dict(L.obj_ids), "kind": dict(L.kind),
                           "shape_ids": {l: {str(f): v for f, v in d.items()} for l, d in L.shape_ids.items()}} for L in self.layers]}
        if self.cvat is not None:
            out["cvat"] = dict(self.cvat)                        # mốc cập nhật của job lúc bắt đầu làm việc (để biết CVAT có bị sửa không)
            out["unsent"] = bool(self.unsent)                    # còn công chưa gửi lên CVAT (Đăng xuất dựa vào đây để hỏi trước khi xoá file phiên)
        return out

    def load_state(self, d: dict) -> None:
        """Nạp file phiên. Lỗi khi tính lại (ví dụ mất kết nối CVAT) thì phiên trở về đúng như trước khi gọi và lỗi được ném lại."""
        self._guard_qc()
        if d.get("version") not in (1, 2, 3) or d.get("frames") != self.n_frames:
            raise ValueError("file phiên làm việc không khớp thư mục ảnh này")
        saved_names = d.get("names")                                    # tên ảnh đầu, cuối lúc lưu (file bản 1 chưa có): cùng số frame mà ảnh khác thì không nạp
        now_names = [self.names[0], self.names[-1]]
        if saved_names is not None and (not isinstance(saved_names, (list, tuple)) or list(saved_names) != now_names):
            was = f"{saved_names[0]} … {saved_names[-1]}" if isinstance(saved_names, (list, tuple)) and len(saved_names) == 2 else str(saved_names)
            raise ValueError(f"file phiên làm việc thuộc dãy ảnh khác (đã lưu: ảnh đầu / cuối {was}; hiện tại: {now_names[0]} … {now_names[1]}), "
                             "không nạp lên ảnh này")
        before = (self.layers, self.cur, self.cvat, self.deleted, self.next_id, list(self._undo), list(self._redo), self.stale, self.dirty, self.unsent)
        try:
            self._load_state(d)
        except BaseException:
            (self.layers, self.cur, self.cvat, self.deleted, self.next_id, self._undo[:], self._redo[:], self.stale, self.dirty, self.unsent) = before
            self._refresh_turns()
            raise

    def _load_state(self, d: dict) -> None:
        parts = d["layers"] if d["version"] >= 2 else [d]               # bản 1 chỉ có một bộ đối tượng
        self.layers = [Layer() for _ in parts] or [Layer()]
        for L, p in zip(self.layers, parts):
            L.pins = {int(f): {int(i): tuple(q) for i, q in pts.items()} for f, pts in p.get("pins", {}).items()}
            L.flags = {int(f): {int(i): k for i, k in fl.items()} for f, fl in p.get("flags", {}).items()}
            L.estimates = {int(f): {int(i): r for i, r in es.items()} for f, es in p.get("estimates", {}).items()}
            L.obj_ids = {k: int(v) for k, v in p.get("ids", {}).items()}
            kinds = p.get("kind") or {}                                 # bản 1, 2 không có: toàn track
            L.kind = {l: (kinds.get(l) if kinds.get(l) in KINDS else "track") for l in EYES}
            sh = p.get("shape_ids") or {}
            L.shape_ids = {l: {int(f): int(v) for f, v in (sh.get(l) or {}).items()} for l in EYES}
        self.cur = min(int(d.get("cur", 0)), len(self.layers) - 1)
        saved = d.get("cvat")
        if self.cvat is not None and isinstance(saved, dict) and saved.get("job") == self.cvat.get("job"):
            self.cvat = {"job": saved["job"], "updated": saved.get("updated")}   # file phiên cũ không có trường này thì giữ mốc của lúc mở
        if self.cvat is not None:
            self.deleted = set(self.source.deleted)                     # job CVAT: frame xoá do CVAT quyết, không theo file phiên
        else:
            self.deleted = set(int(f) for f in d.get("deleted", []))
        top = max([v for L in self.layers for v in list(L.obj_ids.values()) + [v for d in L.shape_ids.values() for v in d.values()]] + [0])
        self.next_id = int(d.get("next_id", top + 9))
        self._undo.clear()
        self._redo.clear()
        self.recompute()
        self.dirty = False
        self.unsent = bool(d["unsent"]) if "unsent" in d else any(L.pins for L in self.layers)     # file cũ chưa có cờ: có ghim thì coi là chưa gửi (an toàn)

    def save_state(self, path: str) -> None:
        import json
        tmp = path + ".tmp"
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.state(), fh, ensure_ascii=False)
        os.replace(tmp, path)                                # ghi nguyên tử: mất điện giữa chừng không làm hỏng bản cũ
        self.dirty = False

    # ---- tính ----
    def recompute(self) -> None:
        """Tính lại nhãn của mọi Layer (đoạn không đổi thì dùng lại bộ nhớ đệm). Lỗi giữa chừng (đọc ảnh từ CVAT lỗi...) thì đặt `stale`
        (nhãn do tool tính có thể không còn khớp ghim) rồi ném lại; tính xong trọn vẹn thì bỏ `stale`."""
        saved = self.cur
        try:
            for i in range(len(self.layers)):
                self.cur = i
                self._recompute_current()
        except BaseException:
            self.stale = True
            raise
        finally:
            self.cur = saved
        self.stale = False
        self._refresh_turns()

    def _refresh_turns(self) -> None:
        self.turns = headturn.for_session(self)

    def _recompute_current(self) -> None:
        """Tính lại nhãn do tool bám của Layer đang chọn, riêng từng mắt: mỗi mắt có các frame ghim (keyframe) riêng và từ mỗi keyframe bám tiến tới keyframe kế của
        chính mắt đó. Đoạn nào không đổi (cùng điểm ghim, cùng frame kế) thì dùng lại kết quả cũ nên sửa một keyframe chỉ tính lại một đoạn.
        Mắt shape không bám: mỗi shape là nhãn của đúng frame đó (độ khớp 1,0), không vào `need_pin`, không có `arrival`."""
        self._assign_ids()
        if not self.pins:
            self.labels, self.arrival, self.need_pin, self._segments = {}, {}, [], {}
            return
        per_frame: dict[int, list[TrackResult]] = {}
        per_arrival: dict[int, list[TrackResult]] = {}
        fresh: dict = {}
        for label, spec in EYES.items():
            if self.kind[label] == "shape":                  # shape: không bám, chỉ có nhãn ở chính frame của nó, độ khớp 1,0, không có arrival
                for f in self._shape_frames(label):
                    per_frame.setdefault(f, []).append(TrackResult(f, {i: self.pins[f][i] for i in spec.ids}, 1.0, {label: 1.0}))
                continue
            have = self.eye_keyframes(label)
            for k, f0 in enumerate(have):
                f1 = have[k + 1] if k + 1 < len(have) else self.n_frames
                sub = {i: self.pins[f0][i] for i in spec.ids}
                key = (f0, f1, label, tuple(sorted(sub.items())))
                hit = self._segments.get(key)
                if hit is None:
                    part_l: dict[int, TrackResult] = {}
                    part_a = None
                    for r in track_forward(self.gray, f0, min(f1 + 1, self.n_frames), sub):
                        if r.frame < f1:
                            part_l[r.frame] = r
                        elif r.frame == f1 and f1 in have:
                            part_a = r
                    hit = (part_l, part_a)
                fresh[key] = hit
                for f, r in hit[0].items():
                    per_frame.setdefault(f, []).append(r)
                if hit[1] is not None:
                    per_arrival.setdefault(f1, []).append(hit[1])

        def merge(rs: list[TrackResult]) -> TrackResult:
            pts, scores = {}, {}
            for r in rs:
                pts.update(r.points)
                scores.update(r.scores)
            return TrackResult(rs[0].frame, pts, min(scores.values()), scores)
        self._segments = fresh
        self.labels = {f: merge(rs) for f, rs in per_frame.items()}
        self.arrival = {f: merge(rs) for f, rs in per_arrival.items()}
        pinned = {l: set(self.eye_keyframes(l)) for l in EYES}
        self.need_pin = [f for f in sorted(self.labels)
                         if any(sc < MATCH_FLAG and f not in pinned[l] for l, sc in self.labels[f].scores.items())]

    def drift_before(self, frame: int) -> float | None:
        """Độ trôi (px) của đoạn đứng trước frame ghim `frame`."""
        a = self.arrival.get(frame)
        return None if a is None else pin_jump(a, self.pins[frame])

    # ---- chế độ QC ----
    def clear_old_eyes(self) -> qc.EyeLabels:
        """Bỏ nhãn mắt có sẵn của job (giữ bản cũ để khôi phục) và thoát chế độ QC. Trả về những gì đã bỏ."""
        gone = qc.eye_labels(self.ann)
        self._old_eyes = (self.ann, dict(self.layers[0].obj_ids), self.next_id)
        self.ann = qc.without_eyes(self.ann)
        for label in list(self.obj_ids):
            if not any(all(i in pts for i in EYES[label].ids) for pts in self.pins.values()):
                del self.obj_ids[label]
        self._ids_from_ann()
        self.qc = False
        return gone

    def restore_old_eyes(self) -> bool:
        """Khôi phục nhãn mắt cũ và vào lại chế độ QC; chỉ được khi chưa có ghim nào sau lúc xoá. Trả True nếu đã khôi phục."""
        if self._old_eyes is None or any(L.pins or L.pending for L in self.layers):
            return False
        ann, ids, next_id = self._old_eyes
        self.ann, self._old_eyes = ann, None
        self.layers, self.cur = self.layers[:1], 0
        self.layers[0].obj_ids = dict(ids)
        self.next_id = next_id
        self._undo.clear()
        self._redo.clear()
        self.qc = True
        return True

    # ---- nhiều bộ đối tượng (nhiều người) ----
    def add_layer(self) -> int:
        """Thêm một bộ đối tượng trống (người mới) và chọn nó; ghim vào đó sẽ cấp ID mới. Hoàn tác được. Trả về chỉ số bộ."""
        self._push_undo()
        self.layers.append(Layer())
        self.cur = len(self.layers) - 1
        return self.cur

    @contextmanager
    def layer_ctx(self, i: int):
        """Tạm thời chọn bộ đối tượng i (để đọc trạng thái của nó bằng các thuộc tính pins, labels... quen thuộc), xong trả lại bộ cũ."""
        saved, self.cur = self.cur, i
        try:
            yield self
        finally:
            self.cur = saved

    def select_layer(self, i: int) -> None:
        if not 0 <= i < len(self.layers):
            raise ValueError("không có bộ đối tượng này")
        self.cur = i

    def objects(self) -> list[tuple[int, str, int]]:
        """Mọi đối tượng của job: (chỉ số bộ, nhãn mắt, ID), sắp theo ID tăng dần."""
        return sorted(((i, l, v) for i, L in enumerate(self.layers) for l, v in L.obj_ids.items()), key=lambda t: t[2])

    def other_views(self, f: int) -> list[dict]:
        """Nhãn của các bộ đối tượng KHÁC bộ đang chọn tại frame f, để vẽ cùng lúc: [{layer, points, flags, est, ids, source}]."""
        out = []
        for i, L in enumerate(self.layers):
            if i == self.cur or f not in L.labels:
                continue
            with self.layer_ctx(i):
                flags = self.flags_at(f)                          # cờ theo keyframe của từng mắt, như bộ đang chọn
                ids = self.frame_ids(f)                           # mắt shape: ID của shape ở frame này
            out.append({"layer": i, "points": L.labels[f].points, "flags": flags,
                        "est": L.estimates.get(f), "ids": ids, "source": "MANUAL" if f in L.pins else "AUTO"})
        return out

    def points_at(self, f: int) -> dict[int, Point] | None:
        """Nhãn hai mắt tại frame f: do tool tính nếu có, không thì nhãn đọc từ file nhãn."""
        if f in self.labels:
            return self.labels[f].points
        out = {}
        from .scan import eye_at
        for label, spec in EYES.items():
            k = eye_at(self.ann, label, f)
            if k is not None:
                out.update({i: ps.xy for i, ps in k.points.items()})
        return out or None

    def run_scan(self, **kw) -> list[Finding]:
        self.findings = scan(self.ann, self.n_frames, width=self.width, height=self.height, **kw)
        return self.findings

    # ---- xuất ----
    def build_tracks(self, tol: float = KEYFRAME_TOL) -> dict[str, EyeTrack]:
        """Track mắt cho file import: mỗi mắt có ít keyframe nhất sao cho nội suy của CVAT lệch không quá `tol`, mỗi keyframe đủ 8 điểm.
        Mắt đã bị xoá thì không có track; mắt ghim sau thì track bắt đầu từ frame ghim đầu tiên của nó. Mắt kiểu shape không phải track
        (xem `build_shapes`); bộ đối tượng chỉ có shape thì trả {}. Không có nhãn nào thì ném ValueError."""
        if not self.labels:
            raise ValueError("Chưa có frame ghim nào")
        tracks = {}
        for label, spec in EYES.items():
            if self.kind[label] == "shape":
                continue
            have = [f for f in sorted(self.pins) if all(i in self.pins[f] for i in spec.ids)]
            if not have:
                continue
            frames = [f for f in range(have[0], self.n_frames) if f in self.labels and all(i in self.labels[f].points for i in spec.ids)]
            pos = [{i: self.labels[f].points[i] for i in spec.ids} for f in frames]
            where = {f: k for k, f in enumerate(frames)}
            keys = [frames[k] for k in reduce_keyframes(pos, tol, forced=[where[f] for f in have if f in where])]
            tr = EyeTrack(label, attrs={"id": str(self.obj_ids[label])} if label in self.obj_ids else {})
            for f in keys:
                pts = self.labels[f].points
                fl = self.flags_at(f)
                tr.keys[f] = EyeKey(f, {i: PointState(pts[i], fl.get(i) == 'outside', fl.get(i) == 'occluded') for i in spec.ids})
            tracks[label] = tr
        return tracks

    def build_shapes(self) -> list[EyeShape]:
        """Shape mắt của mọi bộ đối tượng cho file import, sắp theo (frame, ID); mỗi shape đủ 8 điểm kèm cờ của chính nó. Không có thì []."""
        saved, out = self.cur, []
        try:
            for i in range(len(self.layers)):
                self.cur = i
                for label, spec in EYES.items():
                    if self.kind[label] != "shape":
                        continue
                    for f in self._shape_frames(label):
                        pts, fl = self.pins[f], self.flags_at(f)
                        key = EyeKey(f, {j: PointState(pts[j], fl.get(j) == 'outside', fl.get(j) == 'occluded') for j in spec.ids})
                        out.append(EyeShape(label, key, {"id": str(self.shape_ids[label][f])}))
        finally:
            self.cur = saved
        return sorted(out, key=lambda sh: (sh.key.frame, int(sh.attrs["id"])))

    def build_all_tracks(self, tol: float = KEYFRAME_TOL) -> list[EyeTrack]:
        """Track của mọi bộ đối tượng (một label có thể có nhiều track), sắp theo ID."""
        saved, out = self.cur, []
        try:
            for i in range(len(self.layers)):
                self.cur = i
                if self.pins:
                    out.extend(self.build_tracks(tol).values())
        finally:
            self.cur = saved
        if not out:
            raise ValueError("Chưa có frame ghim nào")
        return sorted(out, key=lambda t: int(t.attrs.get("id", 10 ** 9)))

    def export(self, out_path: str, tol: float = KEYFRAME_TOL) -> dict:
        """Ghi file import có cả track lẫn shape mắt. Không có cả hai thì ném ValueError("Chưa có frame ghim nào")."""
        try:
            tracks = self.build_all_tracks(tol)
        except ValueError:
            tracks = []
        shapes = self.build_shapes()
        if not tracks and not shapes:
            raise ValueError("Chưa có frame ghim nào")
        cvatxml.write_eyes(self.ann, out_path, new_tracks=tracks, new_shapes=shapes,
                           frame_names=self.names, size=(self.width, self.height))
        first = min(f for L in self.layers for f in L.pins)
        return {"keyframes": sum(len(t.keys) for t in tracks), "frames": self.n_frames - first, "path": out_path,
                "tracks": sorted(t.label for t in tracks), "shapes": len(shapes)}
