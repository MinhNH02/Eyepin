"""Đoạn thiếu nhãn của mắt kiểu shape (design/2026-11-19-qc-edit-design.md mục 6.3).

Chỉ xét mắt kiểu shape: mắt track có nhãn do tool bám nên không có "frame thiếu". Một frame thiếu của mắt là frame không bị xoá
(`Session.deleted`) mà mắt không có shape ở đó; một đoạn là các frame thiếu liền nhau, frame đã xoá hoặc frame có shape cắt đoạn.
Mắt không có shape nào ở bất kỳ frame nào chỉ được báo (một mục `first = -1`) khi mắt kia của cùng người có ít nhất một shape.

Module không biết Tkinter, và không nạp `eyepin.session` (session nạp module này): nhận đối tượng phiên làm tham số và chỉ dùng thuộc tính,
phương thức công khai của nó. Kết quả luôn tính lại từ trạng thái hiện tại của phiên, nên theo kịp mọi lần vẽ, dán, xoá, hoàn tác.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import EYES


@dataclass(frozen=True)
class Gap:
    layer: int          # chỉ số người (Layer) trong phiên
    label: str          # "mattrai" hoặc "matphai"
    first: int          # -1 khi mắt chưa có shape nào ở bất kỳ frame nào
    last: int
    count: int          # số frame thiếu trong đoạn (0 với mục "chưa có nhãn nào")


def _shape_frames(session, label: str) -> set[int]:
    """Frame có shape của mắt `label` của người đang chọn."""
    return {f for f in session.pins if session.has_shape(label, f)}


def _segments(layer: int, label: str, have: set[int], deleted: set[int], n_frames: int) -> list[Gap]:
    """Các đoạn frame thiếu của một mắt đã có ít nhất một shape (`have` là frame có shape)."""
    out = []
    start = None
    for f in range(n_frames + 1):                            # frame n_frames là lính canh để đóng đoạn cuối
        missing = f < n_frames and f not in deleted and f not in have
        if missing and start is None:
            start = f
        elif not missing and start is not None:
            out.append(Gap(layer, label, start, f - 1, f - start))
            start = None
    return out


def find_gaps(session) -> list[Gap]:
    """Mọi đoạn thiếu nhãn của mọi người trong phiên. Mục "chưa có nhãn nào" (first = -1) đứng trước, theo (người, nhãn); rồi các đoạn theo
    (first, người, nhãn)."""
    out: list[Gap] = []
    for i in range(len(session.layers)):
        with session.layer_ctx(i):
            have = {label: _shape_frames(session, label) for label in EYES if session.kind[label] == "shape"}
            for label, frames in have.items():
                if frames:
                    out += _segments(i, label, frames, session.deleted, session.n_frames)
                elif any(other for name, other in have.items() if name != label):
                    out.append(Gap(i, label, -1, -1, 0))
    out.sort(key=lambda g: (g.first, g.layer, g.label))      # first = -1 (chưa có nhãn nào) tự đứng đầu
    return out


def missing_frames(session) -> set[int]:
    """Frame mà ít nhất một mắt shape của một người còn thiếu. Mắt chưa có nhãn nào (mà mắt kia có) thì thiếu ở mọi frame không bị xoá."""
    out: set[int] = set()
    for g in find_gaps(session):
        if g.first >= 0:
            out.update(range(g.first, g.last + 1))
        else:
            out.update(f for f in range(session.n_frames) if f not in session.deleted)
    return out


def gap_text(gap: Gap, many_people: bool) -> str:
    """Chữ của một đoạn thiếu nhãn; `many_people` (job có hơn một người) thì thêm tiền tố "người N · "."""
    if gap.first < 0:
        text = f"{gap.label} chưa có nhãn nào"
    elif gap.first == gap.last:
        text = f"Thiếu nhãn {gap.label} · frame {gap.first} (1 frame)"
    else:
        text = f"Thiếu nhãn {gap.label} · frame {gap.first}–{gap.last} ({gap.count} frame)"
    return f"người {gap.layer + 1} · {text}" if many_people else text


def gap_at(session, label: str, frame: int) -> Gap | None:
    """Đoạn thiếu của mắt `label` (người đang chọn) chứa `frame`; None khi frame có shape, đã xoá hoặc mắt không có đoạn nào ở đó. Mục "chưa có
    nhãn nào" không có frame cụ thể nên không bao giờ được trả."""
    return next((g for g in find_gaps(session) if g.layer == session.cur and g.label == label and 0 <= g.first <= frame <= g.last), None)
