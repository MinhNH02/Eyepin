#!/usr/bin/env python3
"""SPIKE dùng một lần (2026-11-16, Task 7): kiểm file XML do chính EyePin viết với CVAT local THẬT, khi không có mật khẩu để chạy CvatClient.

Cầu nối: một máy chủ nhỏ trên localhost:8765 phục vụ file XML và nhận các bản xuất về; trang CVAT (Chrome đã đăng nhập) làm phần gọi API.

  python spike\\cvat_bridge_check.py build      # dựng phiên tổng hợp, ghi spike/out/bridge/eyepin_send.xml
  python spike\\cvat_bridge_check.py serve      # chạy máy chủ cầu nối (chạy nền)
  python spike\\cvat_bridge_check.py compare    # so bản CVAT xuất về với điều EyePin tuyên bố (cvatsync._expected/_compare)

Chỉ dùng ảnh tổng hợp (nhiễu làm mờ) và nhãn tổng hợp; không có ảnh người. Không sửa gói eyepin.
"""
import http.server
import json
import os
import socketserver
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
OUT = os.path.join(HERE, "out", "bridge")
N, W, H = 210, 1024, 576                       # đúng cỡ job #5 của CVAT local


class Synthetic:
    """Nguồn ảnh tổng hợp trong RAM, cùng giao diện với DirSource."""
    deleted: set = set()
    key, title = "synthetic", "synthetic"

    def __init__(self):
        rng = np.random.default_rng(3)
        self.base = cv2.GaussianBlur(rng.integers(0, 255, (H, W, 3)).astype(np.uint8), (0, 0), 3)
        self.names = [f"s_{i:04d}.jpg" for i in range(N)]
        self.width, self.height = W, H

    def read(self, i):
        M = np.float32([[1, 0, i * 0.4], [0, 1, 0]])
        return cv2.warpAffine(self.base, M, (W, H), borderMode=cv2.BORDER_REFLECT)


def build_session():
    from eyepin.geometry import EYES, four_in_box
    from eyepin.session import Session
    s = Session(source=Synthetic())
    for k, f in enumerate((0, 60, 120, 180)):
        for label, x0 in (("mattrai", 360), ("matphai", 580)):
            s.pin_eye(f, label, four_in_box(EYES[label], (x0 + 3 * k, 250 + k, x0 + 80 + 3 * k, 282 + k)))
    s.toggle_flag(60, 16, "occluded")
    s.toggle_flag(120, 24, "outside")
    return s


def build():
    os.makedirs(OUT, exist_ok=True)
    s = build_session()
    info = s.export(os.path.join(OUT, "eyepin_send.xml"))
    print("đã ghi", os.path.join(OUT, "eyepin_send.xml"), info)


def serve(port=8765):
    class H(http.server.BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def do_OPTIONS(self):
            self.send_response(204); self._cors(); self.end_headers()

        def do_GET(self):
            p = os.path.join(OUT, os.path.basename(self.path))
            if not os.path.isfile(p):
                self.send_response(404); self._cors(); self.end_headers(); return
            data = open(p, "rb").read()
            self.send_response(200); self._cors(); self.send_header("Content-Type", "text/xml"); self.send_header("Content-Length", str(len(data))); self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            name = os.path.basename(self.path) or "post.bin"
            with open(os.path.join(OUT, name), "wb") as fh:
                fh.write(self.rfile.read(n))
            self.send_response(200); self._cors(); self.end_headers(); self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), H) as srv:
        print("cầu nối chạy ở 127.0.0.1:%d" % port, flush=True)
        srv.serve_forever()


def compare():
    from eyepin import cvatxml
    from eyepin.cvatsync import _compare, _expected
    s = build_session()
    want = _expected(s)
    res = {}
    for name in ("after_video.xml", "after_images.xml"):
        p = os.path.join(OUT, name)
        if not os.path.isfile(p):
            print("thiếu", name); continue
        res[name] = cvatxml.parse_bytes(open(p, "rb").read(), list(range(N)))
    if "after_video.xml" in res:
        out = _compare(res["after_video.xml"], want, set(), list(range(N)))
        print("so khớp bản xuất VIDEO với điều EyePin tuyên bố:", "KHỚP" if not out else f"{len(out)} chỗ lệch")
        for line in out[:15]:
            print("  ", line)
        v = res["after_video.xml"]
        for label in ("mattrai", "matphai"):
            for t in v.tracks[label]:
                keys = sorted(f for f, k in t.keys.items() if k.keyframe)
                print(f"   {label} id={t.attrs.get('id')}: {len(t.keys)} skeleton, keyframe {keys}")
    if "after_images.xml" in res:
        a = res["after_images.xml"]
        print("bản xuất IMAGES: track mắt =", sum(len(a.tracks[l]) for l in a.tracks), "| shape mắt theo label:", {l: len(v) for l, v in a.shapes.items()})


if __name__ == "__main__":
    {"build": build, "serve": serve, "compare": compare}[sys.argv[1]]()
