"""Dòng lệnh: python -m eyepin scan <annotations.xml> [--jump 15] [--still 30]; turns <thư_mục_ảnh> --pins <file.json>; gui; preview; shortcuts"""
import argparse
import sys

from . import cvatxml
from .scan import scan


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="eyepin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="quét nhãn mắt có sẵn, liệt kê frame cần chú ý")
    sc.add_argument("xml", help="annotations.xml (CVAT 1.1) export từ job")
    sc.add_argument("--jump", type=float, default=15.0, help="ngưỡng điểm nhảy giữa hai frame (px)")
    sc.add_argument("--still", type=int, default=30, help="số frame liền nhãn đứng yên thì báo")
    pv = sub.add_parser("preview", help="vẽ khung nhìn của một frame ra file PNG (kiểm tra không cần cửa sổ)")
    pv.add_argument("frames_dir")
    pv.add_argument("out_png")
    pv.add_argument("--frame", type=int, default=0)
    pv.add_argument("--pins", help="file JSON điểm ghim: {frame: {id: [x, y]}} với 4 điểm ghim của mỗi mắt")
    pv.add_argument("--xml", help="file nhãn CVAT 1.1 (tuỳ chọn)")
    gu = sub.add_parser("gui", help="mở EyePin: không kèm thư mục ảnh thì hiện màn đăng nhập CVAT trước (có liên kết làm việc không cần CVAT); "
                                    "kèm thư mục ảnh thì vào thẳng cửa sổ")
    gu.add_argument("frames_dir", nargs="?")
    gu.add_argument("--xml")
    gu.add_argument("--pins", help="file JSON điểm ghim (như lệnh preview): mở với các ghim này, không khôi phục và không ghi file phiên")
    gu.add_argument("--selftest", action="store_true", help="mở cửa sổ, vẽ một lần rồi đóng (kiểm lỗi)")
    gu.add_argument("--cvat", help="địa chỉ CVAT trên máy (ví dụ http://localhost:8080) điền sẵn ở màn đăng nhập; mật khẩu hỏi trong cửa sổ")
    gu.add_argument("--job", type=int, help="số job CVAT tự mở sau khi đăng nhập (đi kèm --cvat)")
    tu = sub.add_parser("turns", help="báo các đoạn quay đầu từ điểm ghim (không cần cửa sổ)")
    tu.add_argument("frames_dir")
    tu.add_argument("--pins", required=True, help="file JSON điểm ghim: {frame: {id: [x, y]}} với 4 điểm ghim của mỗi mắt")
    rp = sub.add_parser("report", help="báo độ chính xác (IoU vùng mắt là chỉ số chính; Dice, Boundary IoU, Precision/Recall, sai số px) "
                                       "của các cách đoán tại frame ghim bị giấu (đường thẳng CVAT, bám tiến, hai chiều)")
    rp.add_argument("frames_dir")
    rp.add_argument("--pins", required=True, help="file JSON điểm ghim, như lệnh turns")
    sk = sub.add_parser("shortcuts", help="in (hoặc ghi ra file) guide phím tắt dạng Markdown")
    sk.add_argument("--out", help="ghi ra file này thay vì in ra màn hình")
    a = ap.parse_args(argv)
    if a.cmd == "shortcuts":
        from . import shortcuts
        text = shortcuts.guide_markdown()                  # luôn là phím MẶC ĐỊNH, không đọc phím cá nhân ở ~/.eyepin/settings.json
        if a.out:
            open(a.out, "w", encoding="utf-8").write(text)
            print(f"Đã ghi {a.out}")
        else:
            print(text)
        return 0
    if a.cmd == "preview":
        return _preview(a)
    if a.cmd in ("turns", "report"):
        return _from_pins(a)
    if a.cmd == "gui":
        if a.job is not None and not a.cvat:
            print("Lỗi: --job phải đi kèm --cvat (địa chỉ CVAT trên máy, ví dụ http://localhost:8080).")
            return 2
        if a.cvat:
            if a.frames_dir or a.xml or a.pins:
                print("Lỗi: --cvat mở một job của CVAT, không dùng cùng thư mục ảnh, --xml hay --pins.")
                return 2
            from .cvatapi import CvatClient, CvatError
            try:
                CvatClient(a.cvat).close()               # chỉ kiểm địa chỉ là máy này, chưa nối mạng
            except CvatError as err:
                print(f"Lỗi: {err}")
                return 2
        from .gui import run
        return run(a.frames_dir, a.xml, selftest=a.selftest, pins=a.pins, cvat=a.cvat, job=a.job)
    ann = cvatxml.parse(a.xml)
    found = scan(ann, ann.n_frames, width=ann.width, height=ann.height, jump_px=a.jump, still_frames=a.still)
    print(f"{ann.n_frames} frame; shape: " + ", ".join(f"{l} {len(v)}" for l, v in ann.shapes.items())
          + "; track: " + ", ".join(f"{l} {len(v)}" for l, v in ann.tracks.items()))
    if not found:
        print("Không có frame nào cần chú ý.")
    if found:
        import os
        os.system("")                                            # bật chuỗi màu ANSI trên cửa sổ console Windows
    for f in found:
        rng = f"{f.frame}" if f.frame == f.last else f"{f.frame}–{f.last}"
        dot = "\x1b[38;2;220;60;60m●\x1b[0m" if f.level == "red" else "\x1b[38;2;240;170;40m●\x1b[0m"   # đỏ #DC3C3C, vàng #F0AA28 như dải thời gian
        print(f"{dot} frame {rng:>9} {f.label:8s} {f.message}")
    return 1 if any(f.level == "red" for f in found) else 0


def _from_pins(a):
    """Lệnh turns và report: mở phiên không cửa sổ, ghim từ file --pins, in kết quả. Lỗi đầu vào in một dòng tiếng Việt và trả 2."""
    import json
    import os
    from .session import Session
    try:
        s = Session(a.frames_dir)
        with open(a.pins, encoding="utf-8") as fh:
            s.load_pins(json.load(fh))
    except (OSError, ValueError) as err:
        print(f"Lỗi: {err}")
        return 2
    source = os.path.basename(a.pins)
    if a.cmd == "turns":
        from .headturn import format_report
        print(format_report(s, source))
    else:
        from .evaluate import evaluate, format_table
        print(format_table(evaluate(s), source))
    return 0


def _preview(a):
    import json
    import cv2
    from .render import render_main, render_timeline, render_thumb, status_text
    from .session import Session
    try:
        s = Session(a.frames_dir, a.xml)
        if a.pins:
            with open(a.pins, encoding="utf-8") as fh:
                s.load_pins(json.load(fh))
    except (OSError, ValueError) as err:             # file ghim hỏng, thư mục ảnh/XML sai: một dòng tiếng Việt, không Traceback
        print(f"Lỗi: {err}")
        return 2
    s.run_scan()
    img, view = render_main(s, a.frame)
    try:
        ok = cv2.imwrite(a.out_png, img)
    except cv2.error:                                 # đuôi file không có bộ ghi (ví dụ .xyz)
        ok = False
    if not ok:                                        # imwrite trả False khi thư mục không có, hết chỗ, không ghi được: không được thoát 0
        print(f"Lỗi: không ghi được ảnh ra {a.out_png} (thư mục không tồn tại, không có quyền ghi hoặc đuôi file không hỗ trợ).")
        return 1
    print(status_text(s, a.frame))
    return 0


if __name__ == "__main__":
    sys.exit(main())
