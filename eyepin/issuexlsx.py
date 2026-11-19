"""Ghi báo cáo issue CVAT ra file Excel (hai sheet: "Issue" và "Tổng hợp").

Không biết gì về Tkinter. `openpyxl` chỉ được nạp bên trong hàm: máy thiếu thư viện thì phần còn lại của tool vẫn chạy, và chỗ gọi bắt
`MissingOpenpyxl` để báo người dùng. File chỉ chứa chữ và số. Mọi chữ lấy từ CVAT đi qua `clean_text` và được ép kiểu chữ, nên mô tả bắt đầu
bằng `=` không thành công thức. Lưu qua file tạm cùng thư mục rồi `os.replace`: lưu hỏng thì file cũ còn nguyên.
"""
import os
import re
import tempfile
from datetime import datetime

from .issuereport import STATUS_OPEN, STATUS_RESOLVED, summary

SHEET_ISSUES, SHEET_SUMMARY = "Issue", "Tổng hợp"
HEADERS = ("STT", "Job", "Frame", "Link", "Mô tả lỗi", "Trạng thái", "Người báo", "Ngày báo", "Người được giao job", "Trao đổi thêm")
SUMMARY_HEADERS = ("Job", "Người được giao job", "Số issue", "Chưa sửa", "Đã sửa", "Ghi chú")
MAX_CELL = 32767
ALL = "Tất cả"
MISSING_MESSAGE = "Máy chưa có thư viện openpyxl nên chưa xuất được Excel. Cài bằng lệnh: pip install openpyxl"

_ISSUE_WIDTHS = (6, 8, 8, 45, 50, 12, 16, 18, 20, 50)
_SUMMARY_WIDTHS = (26, 44, 12, 12, 12, 40)
_DATE_FORMAT = "yyyy-mm-dd hh:mm"
_LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")


class MissingOpenpyxl(RuntimeError):
    """Máy chưa cài `openpyxl`; thông điệp là câu tiếng Việt hiện thẳng cho người dùng."""


def _openpyxl():
    try:
        import openpyxl
        import openpyxl.cell.cell
        import openpyxl.styles
        import openpyxl.utils
    except ImportError as exc:
        raise MissingOpenpyxl(MISSING_MESSAGE) from exc
    return openpyxl


def ensure_available() -> None:
    """Không làm gì nếu có `openpyxl`; thiếu thì ném `MissingOpenpyxl`. Để báo người dùng TRƯỚC khi hỏi nơi lưu file."""
    _openpyxl()


def clean_text(value) -> str:
    """Chữ an toàn để đặt vào một ô: bỏ ký tự điều khiển mà Excel không nhận và ký tự surrogate lẻ (đều làm hỏng file), cắt bớt nếu dài hơn một ô
    chứa được. Giới hạn của Excel tính bằng đơn vị UTF-16: ký tự ngoài BMP (emoji) tính hai đơn vị. Quá dài thì giữ đoạn đầu dài nhất, cắt đúng ranh
    giới ký tự, vừa trong `MAX_CELL - 1` đơn vị rồi thêm "…". None thành chuỗi rỗng."""
    illegal = _openpyxl().cell.cell.ILLEGAL_CHARACTERS_RE
    text = _LONE_SURROGATE.sub("", illegal.sub("", "" if value is None else str(value)))
    units = text.encode("utf-16-le")
    if len(units) // 2 <= MAX_CELL:
        return text
    return units[:2 * (MAX_CELL - 1)].decode("utf-16-le", errors="ignore") + "…"       # cặp surrogate bị cắt đôi ở cuối thì bỏ nửa lẻ


def default_name(report, now: datetime | None = None) -> str:
    """Tên file gợi ý: `bao-cao-issue_task-<mã>_<YYYYMMDD-HHMM>.xlsx`."""
    now = now if now is not None else datetime.now()
    return "bao-cao-issue_task-%d_%s.xlsx" % (report.task_id, now.strftime("%Y%m%d-%H%M"))


def _text(ws, row: int, col: int, value):
    """Đặt chữ vào ô, ép kiểu chữ (chuỗi bắt đầu bằng `=` không thành công thức). Chữ rỗng thì để ô trống. Trả ô, hoặc None nếu bỏ qua."""
    text = clean_text(value)
    if not text:
        return None
    cell = ws.cell(row=row, column=col, value=text)
    cell.data_type = "s"
    return cell


def _number(ws, row: int, col: int, value: int) -> None:
    ws.cell(row=row, column=col, value=value)


def _stamp(when: datetime) -> str:
    return when.strftime("%Y-%m-%d %H:%M")


def _fetched_text(fetched: datetime) -> str:
    """Giờ lấy dữ liệu kèm độ lệch múi giờ của máy tại thời điểm đó, ví dụ `2026-11-18 14:32 (UTC+07:00)`."""
    local = fetched.astimezone()
    minutes = int(local.utcoffset().total_seconds() // 60)
    return "%s (UTC%s%02d:%02d)" % (_stamp(local), "+" if minutes >= 0 else "-", abs(minutes) // 60, abs(minutes) % 60)


def _set_widths(ws, widths, openpyxl) -> None:
    for number, width in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(number)].width = width


def _fill_issues(ws, rows, openpyxl) -> None:
    bold, wrap = openpyxl.styles.Font(bold=True), openpyxl.styles.Alignment(wrap_text=True)
    for col, title in enumerate(HEADERS, 1):
        ws.cell(row=1, column=col, value=title).font = bold
    for number, r in enumerate(rows, 1):
        line = number + 1
        _number(ws, line, 1, number)
        _number(ws, line, 2, r.job)
        _number(ws, line, 3, r.frame)
        link = _text(ws, line, 4, r.link)
        if link is not None:
            link.hyperlink = link.value
        message = _text(ws, line, 5, r.message)
        _text(ws, line, 6, r.status)
        _text(ws, line, 7, r.owner)
        if r.created is not None:
            ws.cell(row=line, column=8, value=r.created).number_format = _DATE_FORMAT
        _text(ws, line, 9, r.assignee)
        replies = _text(ws, line, 10, r.replies)
        for cell in (message, replies):
            if cell is not None:
                cell.alignment = wrap
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = "A1:%s%d" % (openpyxl.utils.get_column_letter(len(HEADERS)), len(rows) + 1)
    _set_widths(ws, _ISSUE_WIDTHS, openpyxl)


def _fill_summary(ws, report, excluded, resolved, owner, now: datetime, openpyxl) -> None:
    bold = openpyxl.styles.Font(bold=True)
    _text(ws, 1, 1, "Báo cáo issue CVAT").font = bold
    status = ALL if resolved is None else (STATUS_RESOLVED if resolved else STATUS_OPEN)
    info = (("CVAT", report.url), ("Task", "#%d %s" % (report.task_id, report.task_name)), ("Tài khoản", report.user),
            ("Dữ liệu lấy từ CVAT lúc", _fetched_text(report.fetched)), ("Xuất file lúc", _stamp(now)),
            ("Bộ lọc", "Trạng thái: %s; Người báo: %s" % (status, ALL if owner is None else owner)))
    line = 2
    for label, value in info + tuple(("Cảnh báo", w) for w in report.warnings):
        _text(ws, line, 1, label)
        _text(ws, line, 2, value)
        line += 1
    line += 1                                                                 # một dòng trống trước bảng
    for col, title in enumerate(SUMMARY_HEADERS, 1):
        ws.cell(row=line, column=col, value=title).font = bold
    lines = summary(report, excluded, owner)
    for s in lines:
        line += 1
        _number(ws, line, 1, s.job)
        _text(ws, line, 2, s.assignee)
        _number(ws, line, 3, s.total)
        _number(ws, line, 4, s.open)
        _number(ws, line, 5, s.resolved)
        _text(ws, line, 6, s.note)
    counted = [s for s in lines if s.job not in excluded]
    line += 1
    _text(ws, line, 1, "Tổng")
    _number(ws, line, 3, sum(s.total for s in counted))
    _number(ws, line, 4, sum(s.open for s in counted))
    _number(ws, line, 5, sum(s.resolved for s in counted))
    _set_widths(ws, _SUMMARY_WIDTHS, openpyxl)


def write(path: str, report, rows, *, excluded=frozenset(), resolved: bool | None = None, owner: str | None = None,
          now: datetime | None = None) -> None:
    """Ghi `rows` (các dòng đang hiện) và bảng tổng hợp của `report` vào file `.xlsx` ở `path`. `excluded`, `resolved`, `owner` là bộ lọc đang đặt trên
    màn: chỉ để ghi lên sheet Tổng hợp (và `owner` để tính số đếm), `rows` được ghi nguyên như đưa vào.

    Lưu vào file tạm cùng thư mục rồi thay file đích: lỗi ở bước nào cũng xoá file tạm, để nguyên file đích và ném lại lỗi (`OSError` giữ nguyên kiểu).
    Thiếu `openpyxl` thì ném `MissingOpenpyxl`, chưa đụng tới đĩa."""
    openpyxl = _openpyxl()
    now = now if now is not None else datetime.now()
    wb = openpyxl.Workbook()
    issues = wb.active
    issues.title = SHEET_ISSUES
    _fill_issues(issues, rows, openpyxl)
    _fill_summary(wb.create_sheet(SHEET_SUMMARY), report, excluded, resolved, owner, now, openpyxl)

    handle, temp = tempfile.mkstemp(prefix=".eyepin-", suffix=".tmp", dir=os.path.dirname(os.path.abspath(path)))
    os.close(handle)
    try:
        wb.save(temp)
        os.replace(temp, path)
    except BaseException:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise
