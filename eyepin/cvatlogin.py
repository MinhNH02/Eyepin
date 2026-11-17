"""Nhớ đăng nhập CVAT trên máy này, có hạn (thiết kế: design/2026-11-16-cvat-home-design.md mục 3b, 4.6, 9).

Lưu **khoá** đăng nhập (token CVAT trả từ `POST /api/auth/login`), không bao giờ lưu mật khẩu. Khoá được mã hoá bằng Windows DPAPI
(`CryptProtectData`, gọi qua `ctypes`, không thêm thư viện): chỉ tài khoản Windows đã tạo mới giải mã được. File nằm cạnh `settings.json`
(`cvat_login.bin`) và chứa {địa chỉ, tên đăng nhập, khoá, giờ hết hạn}; địa chỉ và tên cũng nằm trong phần mã hoá.

Không bao giờ gọi `POST /api/auth/logout` (CVAT có thể cấp một khoá chung cho mỗi tài khoản, huỷ nó làm đứt script và cửa sổ khác dùng cùng
tài khoản). "Quên" chỉ là xoá file ở máy này; khoá vẫn còn hiệu lực trên CVAT tới khi CVAT tự huỷ.
"""
from __future__ import annotations

import ctypes
import functools
import json
import math
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import NamedTuple

from . import shortcuts

DEFAULT_HOURS = 8                # hạn nhớ mặc định (giờ)
MAX_HOURS = 72                   # kẹp trên: gõ nhầm 8000 trong settings.json không thành khoá sống nhiều tháng
FILE_NAME = "cvat_login.bin"
_ENTROPY = b"EyePin/cvat-login/v1"       # trộn vào khoá mã hoá: blob DPAPI của chương trình khác không giải mã được bằng đường này
_UI_FORBIDDEN = 0x1                      # CRYPTPROTECT_UI_FORBIDDEN: không bao giờ bật hộp thoại của Windows


def login_path() -> Path:
    return shortcuts.settings_path().parent / FILE_NAME


def remember_hours(settings: dict) -> float:
    """Số giờ nhớ đăng nhập theo cài đặt (`workspace.remember_login_hours`): 0 = không nhớ; giá trị hỏng hoặc thiếu = mặc định; kẹp trong 0–72."""
    try:
        value = settings["workspace"]["remember_login_hours"]
    except (KeyError, TypeError):
        return DEFAULT_HOURS
    if isinstance(value, bool):
        return DEFAULT_HOURS
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return DEFAULT_HOURS
    if not math.isfinite(hours):
        return DEFAULT_HOURS
    return min(float(MAX_HOURS), max(0.0, hours))


# ---- DPAPI ----
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]


@functools.cache
def _api():
    if sys.platform != "win32":
        raise ValueError("Nhớ đăng nhập cần Windows (DPAPI); máy này không phải Windows.")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ptr = ctypes.POINTER(_Blob)
    crypt32.CryptProtectData.argtypes = [ptr, wintypes.LPCWSTR, ptr, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ptr]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [ptr, ctypes.c_void_p, ptr, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ptr]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _in_blob(data: bytes):
    buf = ctypes.create_string_buffer(data, max(len(data), 1))
    return _Blob(len(data), ctypes.addressof(buf)), buf             # `buf` phải sống tới sau lệnh gọi


def _crypt(encrypt: bool, data: bytes) -> bytes:
    crypt32, kernel32 = _api()
    src, keep_src = _in_blob(data)
    ent, keep_ent = _in_blob(_ENTROPY)
    out = _Blob()
    if encrypt:
        ok = crypt32.CryptProtectData(ctypes.byref(src), "EyePin CVAT login", ctypes.byref(ent), None, None, _UI_FORBIDDEN, ctypes.byref(out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(src), None, ctypes.byref(ent), None, None, _UI_FORBIDDEN, ctypes.byref(out))
    if not ok:
        raise ValueError("Không %s được khoá đăng nhập (Windows DPAPI báo lỗi %d)." % ("mã hoá" if encrypt else "giải mã", ctypes.get_last_error()))
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(data: bytes) -> bytes:
    """Mã hoá bằng DPAPI (phạm vi người dùng Windows hiện tại). Lỗi → ValueError."""
    return _crypt(True, data)


def unprotect(blob: bytes) -> bytes:
    """Giải mã blob DPAPI. Hỏng, của tài khoản khác, hoặc không phải blob → ValueError."""
    return _crypt(False, blob)


# ---- file khoá ----
def _norm(url: str) -> str:
    url = (url or "").strip()
    if "://" not in url:
        url = "http://" + url
    return url.lower().rstrip("/")


def save_login(url: str, user: str, token: str, hours: float, now: float | None = None) -> bool:
    """Ghi khoá đăng nhập có hạn `hours` giờ. `hours` <= 0 thì không ghi và xoá file cũ. Trả True nếu đã ghi; lỗi ghi hoặc mã hoá → False
    (không ném, không để lại file dở)."""
    if not hours or hours <= 0:
        forget_login()
        return False
    now = time.time() if now is None else now
    payload = json.dumps({"v": 1, "url": url, "user": user, "token": token, "expires_at": now + hours * 3600.0}).encode("utf-8")
    path = login_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        blob = protect(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(blob)
        os.replace(tmp, path)
    except (OSError, ValueError):
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    return True


def load_login(url: str, now: float | None = None) -> tuple[str, str] | None:
    """Khoá đã nhớ cho địa chỉ `url`: (tên đăng nhập, khoá), hoặc None. Hết hạn, khác địa chỉ, file hỏng hoặc không giải mã được thì xoá file
    và trả None; không đọc được file (đang bị khoá...) thì trả None mà không xoá."""
    path = login_path()
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    try:
        data = json.loads(unprotect(blob).decode("utf-8"))
        saved_url, user, token, expires = data["url"], data["user"], data["token"], float(data["expires_at"])
        ok = all(isinstance(x, str) and x for x in (saved_url, user, token)) and math.isfinite(expires)
    except (ValueError, KeyError, TypeError):
        ok = False
    if not ok or _norm(saved_url) != _norm(url) or (time.time() if now is None else now) >= expires:
        forget_login()
        return None
    return user, token


def forget_login() -> str | None:
    """Xoá file khoá. Trả tên file nếu không xoá được (để báo cho người dùng, không giả vờ đã sạch), không thì None."""
    path = login_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return None
    except OSError:
        return str(path)
    return None


# ---- phiên làm việc của job CVAT trên máy (cho Đăng xuất: design/2026-11-16-cvat-home-design.md mục 4.6b, 9b) ----
class UnsentSession(NamedTuple):
    path: Path
    job: int | None            # số job CVAT của phiên
    pins: int                  # số frame ghim (cộng mọi người)
    known: bool                # True: file ghi rõ chưa gửi; False: file cũ chưa có cờ, không biết đã gửi hay chưa


def sessions_dir() -> Path:
    return shortcuts.settings_path().parent / "sessions"


def _read_session(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _cvat_sessions() -> list[tuple[Path, dict]]:
    """Mọi file phiên của job CVAT trong thư mục phiên. Nhận ra bằng nội dung (khoá `cvat` mà `Session.state()` ghi cho job CVAT), nên cả file lưu
    từ trước khi có cờ `unsent` cũng nhận ra được; phiên của thư mục ảnh và file không đọc được thì không tính."""
    out = []
    for path in sorted(sessions_dir().glob("*.json")):
        data = _read_session(path)
        if data is not None and isinstance(data.get("cvat"), dict):
            out.append((path, data))
    return out


def cvat_session_files() -> list[Path]:
    return [p for p, _ in _cvat_sessions()]


def folder_session_files() -> list[Path]:
    """Mọi file phiên còn lại trong thư mục phiên (phiên của thư mục ảnh, kể cả file hỏng không đọc được): Đăng xuất cũng xoá chúng."""
    cvat = set(cvat_session_files())
    return [p for p in sorted(sessions_dir().glob("*.json")) if p not in cvat]


def _pin_count(data: dict) -> int:
    parts = data.get("layers")
    parts = parts if isinstance(parts, list) else [data]
    return sum(len(p.get("pins") or {}) for p in parts if isinstance(p, dict))


def unsent_sessions() -> list[UnsentSession]:
    """Phiên CVAT trên máy có thể còn công chưa gửi: file ghi `unsent: true` có ghim, và file cũ chưa có cờ mà có ghim (chưa rõ, nên cũng hỏi)."""
    out = []
    for path, data in _cvat_sessions():
        pins = _pin_count(data)
        if pins == 0:
            continue
        flag = data.get("unsent")
        if flag is True or flag is None:
            job = data["cvat"].get("job")
            out.append(UnsentSession(path, job if isinstance(job, int) else None, pins, flag is True))
    return out


def wipe_local(settings: dict) -> list[str]:
    """Đăng xuất = dọn dữ liệu làm việc trên máy: xoá MỌI file phiên (job CVAT và thư mục ảnh — người dùng chốt 2026-11-17 — cùng bản ghi dở
    `*.json.tmp`), file khoá đã nhớ, và tên đăng nhập trong `settings` (giữ địa chỉ và mọi cài đặt khác; đã lưu xuống đĩa). Chỉ đụng thư mục EyePin
    (`~/.eyepin`): không đụng ảnh gốc hay file người dùng tự xuất. Việc nào lỗi cũng làm hết phần còn lại; trả danh sách file không xoá/ghi được
    (rỗng = sạch), để nơi gọi báo tên file chứ không giả vờ đã sạch."""
    failed = []
    for path in [*cvat_session_files(), *folder_session_files(), *sorted(sessions_dir().glob("*.json.tmp"))]:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            failed.append(str(path))
    leftover = forget_login()
    if leftover:
        failed.append(leftover)
    settings.setdefault("cvat", {})["user"] = ""
    try:
        shortcuts.save_settings(settings)
    except OSError:
        failed.append(str(shortcuts.settings_path()))
    return failed
