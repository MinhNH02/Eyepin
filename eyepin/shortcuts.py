"""Danh mục phím tắt và cài đặt của EyePin: một nơi duy nhất định nghĩa mọi hành động, phím mặc định (theo CVAT khi có thể),
phím CVAT tương ứng để đối chiếu, và đọc/ghi cài đặt người dùng.

Phím viết theo cú pháp Tk (`<Control-z>`, `n`, `N` = Shift+n). Người dùng gán lại phím trong hộp Cài đặt (F2); guide phím tắt xem ở F1
hoặc sinh ra file Markdown bằng `python -m eyepin shortcuts`.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Action:
    id: str
    group: str
    label: str
    keys: tuple[str, ...]
    cvat: str = ""            # phím của CVAT cho hành động tương ứng (để đối chiếu); rỗng = CVAT không có
    note: str = ""


G_GEN, G_FRAME, G_OBJ, G_DRAW, G_VIEW = "Chung", "Frame", "Đối tượng", "Ghim / vẽ", "Hiển thị"

ACTIONS: tuple[Action, ...] = (
    Action("shortcuts", G_GEN, "Mở guide phím tắt", ("<F1>",), "F1"),
    Action("settings", G_GEN, "Mở cài đặt", ("<F2>",), "F2"),
    Action("undo", G_GEN, "Hoàn tác", ("<Control-z>",), "Ctrl+Z"),
    Action("redo", G_GEN, "Làm lại", ("<Control-y>", "<Control-Z>"), "Ctrl+Shift+Z / Ctrl+Y"),
    Action("save", G_GEN, "Lưu phiên làm việc", ("<Control-s>",), "Ctrl+S", "CVAT lưu lên server; EyePin lưu file phiên trên máy (có tự lưu)"),
    Action("export", G_GEN, "Xuất file import cho CVAT", ("<Control-S>",), "", "ghi file XML để import vào job"),
    Action("run_actions", G_GEN, "Chạy hành động (Run actions)", ("<Control-e>",), "Ctrl+E"),
    Action("scan", G_GEN, "Quét nhãn có sẵn", ("<Control-E>",), "", "CVAT không có phím riêng; Ctrl+E mở hộp Run actions"),
    Action("open_cvat", G_GEN, "Mở một job từ CVAT trên máy (đăng nhập, chọn task và job)", (), "", "chỉ CVAT localhost; gán phím trong Cài đặt nếu cần"),
    Action("send_cvat", G_GEN, "Gửi lên CVAT (thay toàn bộ nhãn của job đang mở, có hỏi trước và đối chiếu sau)", (), "", "tắt khi job ở chế độ QC"),
    Action("qc_clear", G_GEN, "Xoá nhãn mắt cũ và gán lại (rời chế độ QC)", (), "", "CVAT chưa đổi gì cho tới khi gửi"),
    Action("remove_annotations", G_GEN, "Xoá toàn bộ nhãn (Remove annotations)", (), "", "có hộp xác nhận, hoàn tác được"),
    Action("finish_job", G_GEN, "Hoàn tất job (lưu và xuất)", (), "", "mục Finish the job trong Menu"),
    Action("cancel", G_GEN, "Huỷ chế độ đang làm (ghim dở)", ("<Escape>",), "Esc"),
    Action("frame_next", G_FRAME, "Frame kế", ("f",), "F"),
    Action("frame_prev", G_FRAME, "Frame trước", ("d",), "D"),
    Action("step_fwd", G_FRAME, "Tiến theo bước (bước đặt trong Cài đặt)", ("v",), "V"),
    Action("step_back", G_FRAME, "Lùi theo bước", ("c",), "C"),
    Action("search_next", G_FRAME, "Frame kế thoả bộ lọc", ("<Right>",), "→", "không lọc thì đi từng frame"),
    Action("search_prev", G_FRAME, "Frame trước thoả bộ lọc", ("<Left>",), "←"),
    Action("jump_fwd", G_FRAME, "Tiến 10 frame", ("<Shift-Right>",), "", "CVAT không có phím này"),
    Action("jump_back", G_FRAME, "Lùi 10 frame", ("<Shift-Left>",), "", "CVAT không có phím này"),
    Action("first", G_FRAME, "Về frame đầu", ("<Home>",), ""),
    Action("last", G_FRAME, "Tới frame cuối", ("<End>",), ""),
    Action("play", G_FRAME, "Phát / dừng", ("<space>",), "Space"),
    Action("focus_frame", G_FRAME, "Nhảy vào ô nhập số frame", ("<grave>",), "`"),
    Action("next_keyframe", G_FRAME, "Frame ghim (keyframe) kế", ("r",), "R"),
    Action("prev_keyframe", G_FRAME, "Frame ghim (keyframe) trước", ("e",), "E"),
    Action("next_object", G_OBJ, "Chọn đối tượng kế", ("<Tab>",), "Tab"),
    Action("prev_object", G_OBJ, "Chọn đối tượng trước", ("<ISO_Left_Tab>", "<Shift-Tab>"), "Shift+Tab"),
    Action("label_mattrai", G_OBJ, "Chọn mắt trái (mattrai)", ("<Control-Key-1>",), "Ctrl+1"),
    Action("label_matphai", G_OBJ, "Chọn mắt phải (matphai)", ("<Control-Key-2>",), "Ctrl+2"),
    Action("lock", G_OBJ, "Khoá/mở khoá mắt đang chọn", ("l",), "L"),
    Action("lock_all", G_OBJ, "Khoá/mở khoá cả hai mắt", ("L",), "T L", "CVAT dùng chuỗi T rồi L"),
    Action("hide", G_OBJ, "Ẩn/hiện mắt đang chọn", ("h",), "H"),
    Action("hide_all", G_OBJ, "Ẩn/hiện toàn bộ nhãn", ("H",), "T H", "CVAT dùng chuỗi T rồi H"),
    Action("occluded", G_OBJ, "Occluded cho điểm (đang chọn hoặc dưới chuột)", ("q", "<slash>"), "Q hoặc /"),
    Action("outside", G_OBJ, "Outside cho điểm", ("o",), "O"),
    Action("keyframe", G_OBJ, "Ghim / bỏ ghim frame này (keyframe)", ("k",), "K"),
    Action("delete", G_OBJ, "Xoá mắt (label) đang chọn", ("<Delete>",), "Del", "xoá cả đường của mắt đó, hoàn tác được (Ctrl+Z)"),
    Action("delete_force", G_OBJ, "Xoá mắt đang chọn kể cả khi bị khoá", ("<Shift-Delete>",), "Shift+Del"),
    Action("end_label", G_OBJ, "Kết thúc nhãn từ frame này (Outside)", (), "", "đánh Outside cả 8 điểm của mắt đang chọn"),
    Action("pinned", G_OBJ, "Pinned: khoá dời nguyên mắt và xoay", ("p",), "P"),
    Action("propagate", G_OBJ, "Nhân nhãn sang N frame sau (Propagate)", ("<Control-b>",), "Ctrl+B"),
    Action("change_color", G_OBJ, "Đổi màu mắt đang chọn", ("<Return>",), "Enter"),
    Action("swap_labels", G_OBJ, "Hoán đổi mattrai và matphai", (), "", "ô chọn label trên thẻ đối tượng của CVAT"),
    Action("focus_object", G_OBJ, "Phóng vào mắt đang chọn", (), "", "nhấp đúp dòng trong panel Đối tượng"),
    Action("delete_frame", G_FRAME, "Xoá / khôi phục frame hiện tại", ("<Alt-Delete>",), "Alt+Del"),
    Action("search_frame", G_FRAME, "Tìm frame theo tên", ("<Control-f>",), "", "CVAT có hộp Search frame by name"),
    Action("copy", G_OBJ, "Sao chép nhãn hai mắt của frame", ("<Control-c>",), "Ctrl+C"),
    Action("paste", G_OBJ, "Dán nhãn vào frame hiện tại (thành frame ghim)", ("<Control-v>",), "Ctrl+V"),
    Action("new_object", G_DRAW, "Đối tượng mới (người mới): ghim 8 điểm với ID mới", ("<Control-n>",), "", "CVAT: vẽ đối tượng mới bằng công cụ vẽ"),
    Action("draw_eye", G_DRAW, "Vẽ một mắt: chọn label, bấm 4 điểm hoặc kéo khung, chỉnh rồi Apply", ("n",), "N",
           "CVAT: vẽ (lặp lại công cụ vẽ trước)"),
    Action("draw_full", G_DRAW, "Ghim 8 điểm hai mắt cùng lúc (cách cũ)", (), "", "gán phím trong Cài đặt nếu cần"),
    Action("draw_hidden", G_DRAW, "Ghim khi che khoé (7 điểm)", ("N",), "Shift+N", "CVAT: vẽ lại hình đang chọn"),
    Action("fullscreen", G_VIEW, "Toàn màn hình", ("<F11>",), "", "CVAT có nút, không có phím mặc định"),
    Action("info", G_VIEW, "Thông tin job", ("<Control-i>",), "", "CVAT có nút Info"),
    Action("eye_rot_cw", G_OBJ, "Xoay mắt đang chọn 1° theo chiều kim đồng hồ", ("<period>",), "", "CVAT xoay bằng tay cầm; Shift = 5°"),
    Action("eye_rot_ccw", G_OBJ, "Xoay mắt đang chọn 1° ngược chiều", ("<comma>",), "", "Shift = 5°"),
    Action("eye_rot_cw5", G_OBJ, "Xoay mắt đang chọn 5° theo chiều kim đồng hồ", ("<greater>",), ""),
    Action("eye_rot_ccw5", G_OBJ, "Xoay mắt đang chọn 5° ngược chiều", ("<less>",), ""),
    Action("rotate_cw", G_VIEW, "Xoay ảnh 90° theo chiều kim đồng hồ", ("<Control-r>",), "Ctrl+R"),
    Action("rotate_ccw", G_VIEW, "Xoay ảnh 90° ngược chiều kim đồng hồ", ("<Control-R>",), "Ctrl+Shift+R"),
    Action("tool_cursor", G_VIEW, "Công cụ Con trỏ (kéo nhãn)", (), "", "chọn bằng nút trên thanh trái"),
    Action("tool_hand", G_VIEW, "Công cụ Dời ảnh (kéo chuột là dời ảnh)", (), "", "chọn bằng nút trên thanh trái"),
    Action("zoom_in", G_VIEW, "Phóng to", ("<plus>", "<equal>"), "cuộn chuột"),
    Action("zoom_out", G_VIEW, "Thu nhỏ", ("<minus>",), "cuộn chuột"),
    Action("fit", G_VIEW, "Vừa khung (tự động)", ("0",), ""),
    Action("toggle_ids", G_VIEW, "Ẩn/hiện số điểm", ("i",), ""),
    Action("marker_up", G_VIEW, "Điểm to hơn", ("<bracketright>",), "", "CVAT chỉnh trong Settings"),
    Action("marker_down", G_VIEW, "Điểm nhỏ hơn", ("<bracketleft>",), ""),
    Action("swap_top", G_VIEW, "Đổi mắt nằm trên", ("T",), "+ / -", "CVAT: đưa đối tượng lên/xuống lớp"),
    Action("image_setups", G_VIEW, "Mở Image setups (lưới, độ sáng, tương phản, bão hoà, gamma)", ("<Control-g>",), "",
           "CVAT: nút ^ giữa mép dưới khung ảnh"),
    Action("grid", G_VIEW, "Bật/tắt lưới ảnh", ("g",), "", "CVAT: ô Image grid trong Image setups"),
)
BY_ID = {a.id: a for a in ACTIONS}

# Phím của CVAT mà EyePin không có (không áp dụng cho skeleton mắt); chỉ để guide nói rõ.
NOT_APPLICABLE = (
    ("P", "pinned property của đối tượng"), ("Enter", "đổi màu"), ("Ctrl+B", "nhân đối tượng sang frame sau (EyePin tự bám theo ảnh)"),
    ("G, Shift+G, M, Alt+M, J, Alt+J", "nhóm, gộp, tách, nối, cắt (polygon/mask)"), ("Shift+1..4", "công cụ mask"),
    ("Ctrl+R, Ctrl+Shift+R", "xoay"), ("X, B", "chương trước/sau"), ("Alt+Del", "xoá frame"), ("Ctrl+Alt+Enter", "lưới giao diện"),
)

DEFAULT_SETTINGS = {
    "player": {"step": 10, "speed_ms": 120, "fit_on_frame": False, "smooth": True, "bg": "#2B2A27", "rotate_all": True, "show_deleted": False},
    "workspace": {"remember_display": True, "autosave": True, "autosave_min": 2, "text_always": False, "text_content": ["id", "label", "source"],
                  "font_size": 1.0, "focus_padding": 60, "zoom_step": 1.25, "mouse_speed": 1.0},
    "display": {},
    "shortcuts": {},
    "cvat": {"url": "http://localhost:8080", "user": ""},        # chỉ địa chỉ và tên đăng nhập gần nhất; mật khẩu và khoá không bao giờ lưu
}


def settings_path() -> Path:
    return Path(os.environ.get("EYEPIN_HOME") or Path.home() / ".eyepin") / "settings.json"


def load_settings(path: Path | None = None) -> dict:
    """Đọc cài đặt, điền giá trị mặc định cho chỗ thiếu; file hỏng hoặc không có thì dùng mặc định."""
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        data = json.loads((path or settings_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
    return out


def save_settings(settings: dict, path: Path | None = None) -> Path:
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def bindings(settings: dict) -> dict[str, tuple[str, ...]]:
    """Phím đang hiệu lực của từng hành động: phím người dùng gán lại nếu có, không thì mặc định."""
    over = settings.get("shortcuts", {})
    return {a.id: tuple(over.get(a.id) or a.keys) for a in ACTIONS}


def conflicts(b: dict[str, tuple[str, ...]]) -> dict[str, list[str]]:
    """Phím được gán cho từ hai hành động trở lên: {phím: [id hành động]}."""
    seen: dict[str, list[str]] = {}
    for aid, keys in b.items():
        for k in keys:
            seen.setdefault(k, []).append(aid)
    return {k: v for k, v in seen.items() if len(v) > 1}


_NAMES = {"space": "Space", "grave": "`", "slash": "/", "plus": "+", "minus": "-", "equal": "=", "bracketright": "]",
          "bracketleft": "[", "Escape": "Esc", "Delete": "Del", "Home": "Home", "End": "End", "Tab": "Tab", "ISO_Left_Tab": "Shift+Tab",
          "Left": "←", "Right": "→", "Up": "↑", "Down": "↓"}


def pretty(seq: str) -> str:
    """`<Control-z>` -> `Ctrl+Z`, `N` -> `Shift+N`."""
    if not seq.startswith("<"):
        return f"Shift+{seq}" if len(seq) == 1 and seq.isalpha() and seq.isupper() else seq
    parts = seq[1:-1].split("-")
    parts = [x for x in parts if x != "Key"]
    mods, key = parts[:-1], parts[-1]
    if not mods and len(key) == 1 and key.isupper():
        return f"Shift+{key}"
    names = [{"Control": "Ctrl", "Shift": "Shift", "Alt": "Alt"}.get(m, m) for m in mods]
    k = _NAMES.get(key, key.upper() if len(key) == 1 else key)
    if len(key) == 1 and key.isupper() and "Control" in mods:
        names.append("Shift")
        k = key
    return "+".join(names + [k])


def event_to_seq(keysym: str, state: int) -> str | None:
    """Đổi một sự kiện phím (keysym + trạng thái modifier của Tk) sang chuỗi phím Tk; None nếu chỉ là phím modifier."""
    if keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Meta_L", "Meta_R", "Caps_Lock", "Num_Lock"):
        return None
    # Tk trên Windows: Alt = 0x20000, còn 0x8 (Mod1) là đèn NumLock; trên X11 thì Alt = Mod1 (0x8)
    ctrl, shift = bool(state & 0x4), bool(state & 0x1)
    alt = bool(state & 0x20000) if sys.platform == "win32" else bool(state & 0x8)
    if keysym == "ISO_Left_Tab":
        return "<ISO_Left_Tab>"
    if not (ctrl or alt):
        if len(keysym) == 1:
            return keysym                                  # chữ cái (đã mang dấu Shift trong keysym) và chữ số
        if shift:
            return f"<Shift-{keysym}>"
        return f"<{keysym}>"
    mods = ("Control-" if ctrl else "") + ("Alt-" if alt else "")
    if len(keysym) == 1 and keysym.isalpha():
        return f"<{mods}{keysym.upper() if shift else keysym.lower()}>"
    if len(keysym) == 1 and keysym.isdigit():
        return f"<{mods}Key-{keysym}>"
    return f"<{mods}{'Shift-' if shift else ''}{keysym}>"


def guide_markdown(b: dict[str, tuple[str, ...]] | None = None) -> str:
    """Guide phím tắt dạng Markdown (EyePin đối chiếu CVAT)."""
    b = b or {a.id: a.keys for a in ACTIONS}
    lines = ["# Phím tắt của EyePin", "",
             "Phím mặc định theo CVAT 2.75 khi có hành động tương ứng. Đổi phím trong Cài đặt (F2) → tab Phím tắt; xem nhanh bằng F1.", ""]
    for group in dict.fromkeys(a.group for a in ACTIONS):
        lines += [f"## {group}", "", "| Hành động | Phím EyePin | Phím CVAT | Ghi chú |", "| --- | --- | --- | --- |"]
        for a in (x for x in ACTIONS if x.group == group):
            keys = " / ".join(pretty(k) for k in b[a.id])
            lines.append(f"| {a.label} | {keys} | {a.cvat or '—'} | {a.note} |")
        lines.append("")
    lines += ["## Phím CVAT mà EyePin không có (không áp dụng cho skeleton mắt)", "", "| Phím CVAT | Việc |", "| --- | --- |"]
    lines += [f"| {k} | {v} |" for k, v in NOT_APPLICABLE]
    lines += ["", "## Chuột", "",
              "- Cuộn chuột: phóng to/thu nhỏ quanh con trỏ. Chuột phải hoặc giữa, hoặc kéo ở chỗ trống: dời ảnh.",
              "- Kéo một điểm: dời điểm đó. Kéo vào thân mắt (không trúng điểm): dời cả mắt. Frame chưa ghim sẽ tự thành frame ghim.", ""]
    return "\n".join(lines)
