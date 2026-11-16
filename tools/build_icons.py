"""Dựng bộ icon PNG của EyePin từ SVG gốc của CVAT (v2.75.0) và Ant Design (4.4.2), cả hai MIT.

Chạy: python tools/build_icons.py
Mỗi icon ra ba cỡ eyepin/assets/icons/<tên>-<px>.png (RGBA, RGB trắng, hình nằm ở kênh alpha)
để Tk tô lại màu tuỳ ý; kèm NOTICE.md chép nguyên văn hai giấy phép.
"""
import re
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF (tên mới)
except ImportError:
    import fitz
from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "icon_src"
OUT = HERE.parent / "eyepin" / "assets" / "icons"
SIZES = (16, 20, 24)

# Tên EyePin -> SVG (đường dẫn tương đối trong tools/icon_src/, không có .svg)
ICON_SOURCES = {
    "menu": "cvat/main-menu-icon",
    "save": "cvat/save-icon",
    "undo": "cvat/undo-icon",
    "redo": "cvat/redo-icon",
    "first": "cvat/first-icon",
    "last": "cvat/last-icon",
    "prev": "cvat/previous-icon",
    "next": "cvat/next-icon",
    "prev_filtered": "cvat/previous-filtered-icon",
    "next_filtered": "cvat/next-filtered-icon",
    "back10": "cvat/back-jump-icon",
    "fwd10": "cvat/forward-jump-icon",
    "play": "cvat/play-icon",
    "pause": "cvat/pause-icon",
    "fullscreen": "cvat/fullscreen-icon",
    "filter": "cvat/filter-icon",
    "outside": "cvat/object-outside-icon",
    "inside": "ant/outlined_select",
    "occluded": "ant/outlined_team",
    "not_occluded": "ant/outlined_user",
    "lock": "ant/filled_lock",
    "unlock": "ant/outlined_unlock",
    "eye": "ant/outlined_eye",
    "eye_off": "ant/filled_eye-invisible",
    "star": "ant/filled_star",
    "star_off": "ant/outlined_star",
    "pinned": "ant/filled_pushpin",
    "unpinned": "ant/outlined_pushpin",
    "caret_down": "ant/outlined_caret-down",
    "caret_up": "ant/filled_caret-up",
    "more": "ant/outlined_more",
    "info": "ant/outlined_info-circle",
    "cursor": "cvat/cursor-icon",
    "hand": "cvat/move-icon",
    "rotate": "cvat/rotate-icon",
    "fit": "cvat/fit-to-window-icon",
    "zoom": "cvat/zoom-icon",
    "skeleton": "cvat/skeleton-icon",
    "point": "cvat/point-icon",
    "display": "cvat/colorize-icon",
    "add": "cvat/plus-icon",
    "trash": "ant/outlined_delete",
    "copy": "ant/outlined_copy",
    "link": "ant/outlined_link",
    "check": "ant/outlined_check",
    "scan": "ant/outlined_scan",
    "export": "ant/outlined_export",
    "settings": "ant/outlined_setting",
    "keyboard": "ant/outlined_question-circle",
    "layer_up": "cvat/next-layer-icon",
    "layer_down": "cvat/previous-layer-icon",
    "foreground": "cvat/foreground-icon",
    "background": "cvat/background-icon",
    "upload": "ant/outlined_cloud-upload",
    "home": "ant/outlined_home",
    "logout": "ant/outlined_logout",
}

NOTICE_HEAD = """# Bản quyền biểu tượng

Các biểu tượng trong thư mục này được dựng lại (đổi sang PNG trắng, ba cỡ 16/20/24 px) từ
hai bộ biểu tượng mã nguồn mở, cả hai theo giấy phép MIT. Script dựng: `tools/build_icons.py`,
SVG gốc: `tools/icon_src/`.

## 1. CVAT (cvat-ai/cvat, v2.75.0), giấy phép MIT

Nguồn: https://github.com/cvat-ai/cvat (thẻ v2.75.0), các biểu tượng SVG của giao diện cvat-ui.

```
{cvat}
```

## 2. Ant Design Icons (@ant-design/icons-svg, 4.4.2), giấy phép MIT

Nguồn: gói npm `@ant-design/icons-svg` phiên bản 4.4.2 (https://github.com/ant-design/ant-design-icons),
các biểu tượng kiểu outlined và filled.

```
{ant}
```
"""


def _prepare_svg(svg_path: Path, px: int) -> bytes:
    """Đặt cỡ rõ ràng, thêm xmlns nếu thiếu, và đổi currentColor thành đen (đục)."""
    text = svg_path.read_text(encoding="utf-8")
    text = text.replace("currentColor", "#000000")
    # MuPDF không hiểu CSS transform; chuyển style="transform: scale(N)" thành thuộc tính SVG.
    # Ở thẻ gốc thì bỏ đi (trình duyệt phóng cả ô, ta giữ hình trong khung).
    text = re.sub(r'(<(?!svg)[^>]*?)\sstyle="transform:\s*([^";]+);?"', r'\1 transform="\2"', text)
    text = re.sub(r'\stransform-origin="[^"]*"', "", text)
    m = re.search(r"<svg\b[^>]*>", text)
    tag = m.group(0)
    new = re.sub(r'\s(?:width|height|style)="[^"]*"', "", tag)
    extra = f' width="{px}" height="{px}"'
    if "xmlns=" not in new:
        extra += ' xmlns="http://www.w3.org/2000/svg"'
    new = new[:4] + extra + new[4:]
    return text.replace(tag, new, 1).encode("utf-8")


def render(svg_path: Path, px: int) -> Image.Image:
    """SVG -> RGBA trắng cỡ px x px; độ phủ của nét vẽ nằm ở kênh alpha."""
    doc = fitz.open(stream=_prepare_svg(svg_path, px), filetype="svg")
    page = doc[0]
    s = px / page.rect.width
    # Vẽ đen lên nền trắng rồi lấy 255 - độ sáng làm alpha: nét sáng (vd. viền #F1F1F1 của
    # icon "outside") thành khe hở đúng như trong CVAT, và currentColor/stroke không bị rỗng.
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False, colorspace=fitz.csGRAY)
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    if im.size != (px, px):
        im = im.resize((px, px), Image.LANCZOS)
    alpha = im.point(lambda v: 255 - v)
    out = Image.new("RGBA", (px, px), (255, 255, 255, 0))
    out.putalpha(alpha)
    return out


def write_notice() -> None:
    cvat = (SRC / "cvat" / "LICENSE").read_text(encoding="utf-8").strip()
    ant = (SRC / "ant" / "LICENSE").read_text(encoding="utf-8").strip()
    (OUT / "NOTICE.md").write_text(
        NOTICE_HEAD.format(cvat=cvat, ant=ant), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rel in ICON_SOURCES.items():
        for px in SIZES:
            render(SRC / f"{rel}.svg", px).save(OUT / f"{name}-{px}.png")
    write_notice()
    print(f"{len(ICON_SOURCES)} icon x {len(SIZES)} cỡ -> {OUT}")


if __name__ == "__main__":
    main()
