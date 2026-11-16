"""Đo tốc độ khung nhìn của EyePin trên case 01 (khung 1900×980): sang frame và kéo một điểm. Dùng một lần cho kế hoạch
design/2026-11-16-grid-color-plan.md (Task 1 trước khi sửa, Task 8 sau khi sửa); không phải test.

    python spike/perf_view.py                  # mặc định: lưới tắt, khung tự động
    python spike/perf_view.py --grid 100       # bật lưới Size 100 (chỉ chạy được sau Task 4)
    python spike/perf_view.py --grid 1 --k 8   # lưới Size 1, phóng ×8 quanh điểm 14

Cài đặt và phiên đọc từ một EYEPIN_HOME tạm, không đụng ~/.eyepin. Cửa sổ hiện lên trong lúc đo rồi tự đóng.
"""
import argparse
import json
import os
import statistics
import sys
import tempfile
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
os.environ["EYEPIN_HOME"] = tempfile.mkdtemp(prefix="eyepin_perf_")

MAIN = r"C:\Users\minhf\Documents\VinAI\Task\eye_label_tool"          # spike/out/ không có trong repo nên đọc từ thư mục chính
FRAMES = r"C:\Users\minhf\Downloads\dms_build\cases\01_quay_dau_mat_xa_bi_che"
PINS = os.path.join(MAIN, "spike", "out", "pins_case01_ai.json")


class Ev:
    def __init__(self, x, y):
        self.x, self.y, self.delta, self.state = x, y, 0, 0


def summary(name, ms):
    ms = sorted(ms)
    p90 = ms[min(len(ms) - 1, int(round(0.9 * (len(ms) - 1))))]
    print(f"{name}: trung vị {statistics.median(ms):.1f} ms, p90 {p90:.1f} ms ({len(ms)} lần)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", type=int, default=0, help="Size lưới (0 = tắt)")
    ap.add_argument("--k", type=float, default=0.0, help="mức phóng cố định quanh điểm 14 (0 = khung tự động)")
    args = ap.parse_args()

    import tkinter as tk
    from eyepin.gui import App
    from eyepin.render import View

    root = tk.Tk()
    root.geometry("1900x980+0+0")
    app = App(root)
    app.ask_restore = lambda n: False
    with open(PINS, encoding="utf-8") as fh:
        pins = json.load(fh)
    app.load(FRAMES, None, pins=pins)
    root.update()
    if args.grid:
        app.look.grid, app.look.grid_size = True, args.grid
    f0 = min(app.s.pins)
    app.go(f0)
    root.update()
    if args.k:
        p = app.s.pins[f0][14]
        w, h = app.render_size
        app.manual = View(p[0] - w / (2 * args.k), p[1] - h / (2 * args.k), args.k, w, h)
        app.refresh()
        root.update()
    print(f"khung {app.render_size}, k = {app.view.k:.3f}, lưới {'Size ' + str(args.grid) if args.grid else 'tắt'}")

    frame_ms = []
    for f in list(range(f0 + 1, min(app.s.n_frames, f0 + 21))):
        t0 = time.perf_counter()
        app.go(f)
        root.update_idletasks()
        frame_ms.append((time.perf_counter() - t0) * 1000)
    summary("sang frame", frame_ms)

    app.go(f0)
    root.update()
    sx, sy = app.view.to_screen(app.s.pins[f0][14])
    app.on_press(Ev(sx, sy))
    drag_ms = []
    for i in range(1, 31):
        t0 = time.perf_counter()
        app.on_motion(Ev(sx + i, sy))
        root.update_idletasks()
        drag_ms.append((time.perf_counter() - t0) * 1000)
    app.on_release(Ev(sx + 30, sy))
    summary("kéo điểm (mỗi lần di chuột)", drag_ms)
    root.destroy()


if __name__ == "__main__":
    main()
