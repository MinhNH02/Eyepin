# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Dự án là gì

**EyePin** (tên do người dùng chọn ngày 2026-11-13; gói Python là `eyepin`, thư mục dự án vẫn là `eye_label_tool`) là tool chạy trên máy (cửa sổ riêng, không phải web) hỗ trợ gán nhãn **tự động một phần** cho hai skeleton mắt của bài
DMS Landmark trong CVAT: `mattrai` (điểm 14–21) và `matphai` (điểm 22–29), cả kiểu **shape** lẫn **track**. Mục tiêu
trước mắt là một bản demo cho mentor và đội phát triển tool; nếu thành công, người dùng được truy cập dữ liệu lớn.

**Trạng thái (2026-11-13):** người dùng chọn cách xây dần: làm từng lát chạy được, thử trên dữ liệu, rồi sửa spec và
plan theo những gì phát hiện. Bản thiết kế `design/2026-11-13-eye-label-tool-design-v3.md` là định hướng chưa duyệt
chính thức; các bản v1, v2 và `design/design-notes.md` là lịch sử, khi khác nhau thì v3 thắng. Khi xây phát hiện điều gì
làm đổi thiết kế, ghi lại vào spec (mục 10 của v3 là danh sách câu hỏi mở).

Đã có (707 test trong 40 file `tests/test_*.py`, đều qua khi chạy từng file, 2026-11-17 12:00): lõi `eyepin/` (hình học, đọc ghi CVAT 1.1, bản xem trước khớp CVAT, bám theo ảnh, chọn keyframe, quét, đo IoU nội suy),
phiên làm việc `session.py` (ghim, hoàn tác, cờ Occluded/Outside), phần vẽ `render.py` và cửa sổ Tkinter `gui.py` (thanh điều hướng
frame, phát, phím tắt kiểu CVAT, ghim khi che khoé với vòng sai số). Lưu phiên (Ctrl+S, tự lưu mỗi 2 phút khi có thay đổi, hỏi khôi phục khi mở lại cùng thư mục) ghi `~/.eyepin/sessions/<mã>.json` chỉ gồm toạ độ và cờ; xuất file import là Ctrl+Shift+S. Giao diện: `eyepin/theme.py` (ba màu cam #FF6600, nền giấy #F6F6EF, chữ #1F1F1F; chữ trên nền cam luôn là chữ đen). Phím tắt và cài đặt: `eyepin/shortcuts.py` là nơi duy nhất định nghĩa hành động + phím (CVAT làm mặc định, gán lại được trong F2).
Chưa có: đo độ chính xác của ước lượng khoé trên đầu quay thật
(mới một mẫu), chia đoạn theo người, hai mắt ghim riêng ở hai frame khác nhau, import thẳng vào CVAT từ cửa sổ, kéo điểm ở frame
không-ghim.

## Kiến trúc và quy tắc cập nhật

Sơ đồ kiến trúc hiện tại: `.archify/architecture-eyepin-flow-20261117-105831/eyepin-architecture.html` (vẽ 2026-11-17 sau khi có `gui_sidebar.py`, icon PNG, nối CVAT trực tiếp, chế độ QC, `overlap.py` và đo; tạo bằng `/archify`, vẽ chi tiết luồng từ thư mục ảnh hoặc job CVAT đến điểm ghim, ba cách ghim, nhãn, file import; bản trước: `.archify/architecture-eyepin-flow-20261116-125400/` (chưa có sidebar, icon, CVAT trực tiếp); bản cũ
`.archify/architecture-eyepin-flow-20261116-113000/` là bản trước khi có đường vẽ khung và icon, `.archify/architecture-eyepin-objects-20261115-022446/` là bản module nhiều người, `.archify/architecture-eyepin-modules-20261113-155705/` là bản trước khi tách hai mixin, `.archify/architecture-eye-tool-20261113-000000/` là hướng A ban đầu, chỉ để tham khảo). Phân tầng: `gui.py` (+ `theme.py`) chỉ nối chuột, phím vào
`Session`; `render.py` vẽ ra ảnh numpy; `session.py` giữ mọi trạng thái (ghim, undo, lọc, lưu phiên) và gọi `geometry`, `tracking`, `scan`,
`cvatxml`; `shortcuts.py` định nghĩa phím và cài đặt; dữ liệu cục bộ ở `~/.eyepin/` (settings.json, sessions/*.json).

**Quy tắc (người dùng yêu cầu 2026-11-13): sau mỗi lần thay đổi một module lớn (thêm/bỏ/tách module, đổi luồng dữ liệu, đổi phân tầng), chạy `/archify`
để vẽ lại sơ đồ vào một thư mục `.archify/architecture-eyepin-<chủ đề>-<ngày-giờ>/` mới, rồi cập nhật đường dẫn ở đây và danh sách module trong mục "Mã trong dự án".**
Sửa nhỏ trong một module không cần vẽ lại.

## Danh sách việc

`TASKS.md` (thư mục gốc) là danh sách việc của dự án. **Quy tắc (người dùng yêu cầu 2026-11-13): làm xong việc nào thì tick `[x]` việc đó ngay trong `TASKS.md`,
việc mới phát sinh thì thêm vào đúng nhóm, đừng để file lệch với thực tế.**

## Quy tắc bắt buộc (người dùng đã chốt)

- **Không dùng model học máy** để tìm mắt hay sinh nhãn (MediaPipe, U-Net, landmark model... đều không). Xử lý ảnh
  thông thường (so khớp vùng ảnh, dò mép) đang được coi là được phép nhưng chưa xác nhận với công ty.
- Ảnh của công ty được lưu trên ổ đĩa máy, nhưng **không bao giờ đưa lên mạng, GitHub hay dịch vụ ngoài**. Không đặt
  ảnh có mặt tài xế thật vào thư mục này.
- Trong mạng nội bộ công ty chỉ được dùng **Codex** làm trợ lý AI. Logic phải nằm trong script chạy độc lập; chỉ
  dẫn cho Codex viết thành file văn bản (mẫu: `spike/AGENTS.md`).
- Ghi nhãn vào CVAT bằng **tính năng import**, không sửa từng nhãn qua API.
- CVAT local (`http://localhost:8080`) chứa dữ liệu công khai: được thử nghiệm, xem ảnh, ghi tự do. Server công ty
  thì không tự ghi, không điều khiển trình duyệt vào đó.

## Quy ước git (người dùng chốt 2026-11-16)

- **Nhánh:** `main` là nhánh phát hành và được bảo vệ: không push trực tiếp, không force push, không xoá. Thay đổi chỉ vào `main` qua pull request từ `develop`. `develop` là nhánh phát triển: làm việc và commit hằng ngày diễn ra ở đây. Việc lớn cần PR riêng thì tạo nhánh con từ `develop`: `feature/<tên-ngắn>`, `fix/<tên-ngắn>`, `docs/…`, `refactor/…`, `test/…` (chữ thường, gạch nối).
- **Commit theo Conventional Commits:** `<type>(<phạm vi>): <mô tả>`.
  - `type` viết thường, một trong: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `style`, `build`, `ci`, `chore`, `revert`.
  - `phạm vi` là module hoặc khu vực: `geometry`, `cvatxml`, `cvat`, `session`, `gui`, `render`, `tracking`, `headturn`, `scan`, `icons`, `shortcuts`, `tests`, `docs`. Có thể bỏ nếu thay đổi trải nhiều nơi.
  - `mô tả`: động từ ở đầu, không dấu chấm cuối, tối đa 72 ký tự, viết tiếng Việt có dấu.
  - Thân commit (khi cần): giải thích **vì sao** thay đổi, xuống dòng quanh 72 ký tự, cách tiêu đề một dòng trống.
  - Thay đổi phá vỡ tương thích: thêm `!` sau phạm vi (ví dụ `feat(cvat)!: ...`) và dòng `BREAKING CHANGE: ...` trong thân.
- **Mỗi commit một mục đích.** Không gộp sửa lỗi với đổi định dạng trong cùng commit.
- **Bảo vệ `main`:** GitHub không bật được branch protection cho repo riêng tư ở gói miễn phí. Thay bằng hook trong `.githooks/` (chặn commit và push trực tiếp lên `main`, kiểm tra tiêu đề commit). Sau khi clone, bật bằng `git config core.hooksPath .githooks`. Hook chỉ chạy trên máy đã bật và bỏ qua được bằng `--no-verify`, nên quy tắc này là thoả thuận làm việc, không phải khoá phía server.
- Không commit dữ liệu, ảnh, guideline công ty, `.superpowers/`, `.archify/` hay cache (đã chặn trong `.gitignore`); không dùng `git add -f` để lách.

## Những điều về CVAT phải nắm (đã kiểm trên bản 2.75)

Chi tiết và vị trí dòng mã: `design/cvat-keyframe-behaviour.md`.

- Track nội suy **đường thẳng** giữa hai keyframe; sau keyframe cuối giữ nguyên vị trí; Occluded/Outside ở frame giữa
  chép từ keyframe bên trái.
- Trong skeleton track, **mỗi điểm có keyframe riêng**; kéo một điểm trong CVAT chỉ ghim điểm đó. Tool phải luôn ghi
  keyframe đủ 8 điểm.
- **Import vào job mặc định xoá toàn bộ nhãn của job** rồi mới nạp. File import phải chứa mọi nhãn của job. Một file
  "CVAT 1.1" chứa được cả shape (`<image>`) lẫn track (`<track>`), và cả hai giữ nguyên kiểu sau import.
- Sau khi Docker Desktop khởi động lại, cổng 8080 có thể trả "empty reply" dù CVAT đã chạy trong container; sửa bằng
  `docker restart traefik`.
- Server công ty: `POST /api/auth/login` trả khoá dùng với `Authorization: Token <khoá>`; mọi lệnh gọi kèm
  `?org=2D`; không gửi `Accept: application/json` (bị 406).

## Mã trong dự án (`eyepin/`)

- `__main__.py`: lệnh `python -m eyepin` (gui, scan, turns, report, preview, shortcuts); `gui` nhận thư mục ảnh, `--xml`, `--pins` (các đường này vào thẳng cửa sổ); **không kèm thư mục ảnh thì hiện màn đăng nhập CVAT trước** (`gui_login.py`; `--cvat` điền sẵn địa chỉ, `--job` tự mở job sau khi đăng nhập). `EyePin.bat` chạy `gui` không tham số; lối tắt Desktop `Eyepin.lnk` trỏ tới `EyePin_case01.bat` (mở thẳng case 01) nên bỏ qua màn đăng nhập.
- `geometry.py`: `derive` suy 8 điểm từ 4 điểm ghim (parabol); `estimate_hidden_corner` đoán khoé bị che từ 3 điểm
  ghim còn lại (trung điểm hai điểm giữa mí nằm ở khoảng 0,49–0,515 dọc trục khoé–khoé).
- `cvatxml.py`: `parse` đọc file CVAT 1.1; `write_eyes` bỏ skeleton mắt cũ, thêm skeleton mắt mới và giữ nguyên mọi thứ
  khác. Shape mắt chỉ ghi được khi nền là file export "CVAT for images" (có thẻ `<image>`).
- `preview.py`: `position_at` tính vị trí từng frame đúng như CVAT hiển thị.
- `scan.py`: `scan` quét nhãn mắt (đỏ: thứ tự khoé, mí đảo, bắt chéo, ngoài khung; vàng: nhảy, keyframe thiếu, đứng yên) và gộp các frame
  liên tiếp thành một đoạn. Phép kiểm bắt chéo có dung sai 0,3 px để mắt nhắm (hai mí trùng nhau) không bị báo nhầm.
- `geometry.assign_roles`/`split_eyes`: người dùng bấm 8 điểm theo thứ tự tuỳ ý; tool chia hai mắt theo x, chọn hai khoé là cặp xa nhau nhất,
  điểm cao hơn là giữa mí trên; từ chối (ValueError tiếng Việt) khi 4 điểm không giống một con mắt (khoé quá gần, trục quá dốc, mí sát khoé).
- `session.py` (có undo/redo 100 bước cho các điểm ghim; trạng thái một job, ảnh chỉ giữ tối đa 40 frame trong bộ nhớ), `render.py` (vẽ ra ảnh, kiểm tra được không cần
  cửa sổ), `gui.py` (Tkinter mỏng, nối chuột và phím vào Session).
- Panel Đối tượng kiểu CVAT (từ 2026-11-16 là danh sách thẻ, xem `gui_sidebar.py` dưới): `#ID`, loại "skeleton track", nút keyframe (bấm = ghim/bỏ keyframe), khoá/ẩn/Occluded/Outside; chọn một mắt thì hiện tay cầm xoay phía mí trên (kéo để xoay quanh tâm, hoặc `,` `.` xoay 1°, `<` `>` xoay 5°). Khảo sát CVAT thật: `design/cvat-feature-inventory.md` mục 7.
- Mỗi mắt là một đối tượng có ID (`Session.obj_ids`; 1, 10, 19… như giao diện CVAT), keyframe riêng (`eye_keyframes`, `toggle_eye_key`) và bám riêng (`recompute` theo từng mắt). Một job có nhiều người: `Session.layers` là danh sách `Layer` (mỗi Layer một mattrai + một matphai); `pins`, `flags`, `labels`... luôn là của Layer đang chọn (`Session.cur`) nên mã một người không đổi; ID toàn job không trùng (1, 10, 19, 28…). Panel Đối tượng liệt kê mọi đối tượng (dòng `eye:mattrai@1` là của Layer 1); `LayerSet` giữ khoá và Pinned riêng từng người.
- Frame ghim có thể chỉ chứa một mắt (sau khi xoá label hoặc ghim từng mắt): `Session.delete_eye`, `end_eye_here`, `add_pin_one`; bộ bám, `build_tracks` và xuất file xử lý theo từng mắt.
- `gui_objects.py` (logic của panel Đối tượng: Sort by, menu ⋮, Pinned, Propagate, tab Labels, tab Issues; phần vẽ danh sách do `gui_sidebar.py` đảm nhận) và `gui_frames.py` (Menu Remove annotations / Run actions / Finish job, hàng tên frame, xoá frame, tìm theo tên, phóng vào mắt) là mixin của `App`; đối chiếu CVAT: `design/cvat-parity.md`.
- `icons.py`: nút biểu tượng và tooltip; vẽ icon GỐC của CVAT / Ant Design (MIT) dựng sẵn thành PNG mặt nạ alpha trắng 16/20/24 px ở `eyepin/assets/icons/` (giấy phép và nguồn: `eyepin/assets/icons/NOTICE.md`), không dùng phông biểu tượng. Không có chữ cố định cạnh icon, chữ (tiếng Việt + phím tắt) chỉ hiện thành tooltip khi trỏ chuột; thiếu file PNG thì nút lùi về chữ ngắn. Giao diện kiểu CVAT: thanh ngang trên (menu, lưu, hoàn tác, điều hướng; Thông tin, Toàn màn hình F11, Lọc, Hiển thị) và thanh công cụ dọc bên trái chỉ có biểu tượng.
- `tools/build_icons.py` (chạy `python tools/build_icons.py`): dựng lại `eyepin/assets/icons/*.png` (16/20/24 px) từ SVG trong `tools/icon_src/` (cần PyMuPDF, chỉ nạp lúc dựng: `tests/test_icon_assets.py` đọc `ICON_SOURCES` không cần nó). Thêm icon mới = bỏ SVG vào `tools/icon_src/`, chạy lại, ghi nguồn vào `NOTICE.md`.
- `gui_sidebar.py` (2026-11-16, thiết kế `design/2026-11-16-cvat-sidebar-icons-design.md`, kế hoạch `-plan.md`): panel phải kiểu CVAT. Tab `Objects | Labels | Issues | Frame lân cận`; `ObjectList` (nối bởi `App.tree`) là danh sách THẺ đối tượng: mỗi mắt một thẻ (ID, `SKELETON TRACK · <trạng thái>`, chọn label mattrai/matphai, menu ⋮, điều hướng keyframe đầu/trước/kế/cuối, rồi nút theo thứ tự CVAT: Outside, Lock, Occluded, Hidden, Keyframe, Pinned) và mục DETAILS liệt kê 8 điểm, mỗi điểm có nút Outside và Occluded riêng. Đầu danh sách: Items, Sort by, khoá/ẩn tất cả, thu/mở tất cả, "+", thùng rác. Bấm thẻ = chọn mắt, đúp = phóng vào mắt, phải = menu đối tượng; rê chuột trên mắt thì sáng thẻ và ngược lại (chỉ người đang chọn). Hành vi cố ý: Hidden và Lock trên THẺ (và phím `h`, `l`) chỉ tác động MỘT mắt của MỘT người (mắt đang hiện dưới chuột, không có thì thẻ đang chọn); `H` (ẩn mọi nhãn), `L` và nút khoá tất cả (`toggle_lock_all`: khoá/mở khoá mọi mắt của MỌI người, icon đặc khi tất cả đều khoá) và nút ở tab Labels tác động nhãn của mọi người. Del/q/o theo con trỏ trên ảnh (mắt/điểm ĐANG HIỆN dưới con trỏ trước — `App._eye_at(..., visible_only=True)`, `_nearest_pin_point(..., visible_only=True)` —, không có thì mục đang chọn); phím xoay `, . < >` từ chối mắt đang ẩn; bấm ảnh chỉ chọn người khác qua mắt đang hiện của người đó. Label ẩn ở tab Labels thì nút Hidden của thẻ mờ (`card["label_hidden"]`). Đổi label (ô label của thẻ, menu ⋮, `swap_labels`) từ chối khi một mắt đang khoá; ẩn riêng/Pinned đổi chỗ theo mắt; xoá mắt bỏ khoá/ẩn riêng/Pinned của đúng người. "+"/Ctrl+N bỏ chọn trong panel trước khi thêm người. Bấm ra ngoài ô số frame trả focus bàn phím về ảnh. Tab "Frame lân cận" tắt được ở F2 > Workspace > "Hiện tab Frame lân cận" (`show_neighbors`, mặc định bật; tắt thì gỡ tab và không tính ảnh nhỏ). Nút frame trước/sau ở thanh trên đi theo bộ lọc đang đặt (như ←/→).
- `shortcuts.py`: danh mục hành động và phím (mặc định theo CVAT, đối chiếu cột "phím CVAT"), đọc ghi `~/.eyepin/settings.json`; `theme.py`: bảng màu và style Tkinter.
- `scan.py` có thêm luật EAR (`eye_ear`; ngưỡng `EAR_CLOSED/WIDE/JUMP` chưa chỉnh theo dữ liệu thật).
- `headturn.py` (MVP 1 demo 2026-11-16): `detect` phát hiện đoạn quay đầu chỉ từ toạ độ và độ khớp (khoảng cách hai mắt so với mốc = phân vị 90 tại frame ghim, bỏ frame khớp < 0,85, vào 0,86 / ra 0,90, tối thiểu 5 frame, xác nhận bằng bề rộng mắt tại frame ghim); `for_session` tính theo từng người; `format_report` là văn bản của lệnh `turns`. `Session.turns` được tính lại sau mỗi `recompute` và khi đổi cờ; hiện ở dải cam trên dải thời gian (`render_timeline`) và đầu tab Issues (`gui_objects._turn_rows`). Ngưỡng chỉnh trên một clip (case 01); chưa kiểm trên dữ liệu khác. Thiết kế: `design/2026-11-15-headturn-mvp-design.md`, kế hoạch: `design/2026-11-16-headturn-mvp1-plan.md`.
- `evaluate.py` (MVP 2 + 3): với mỗi ghim giữa của một mắt (có ghim kề hai phía), so nhãn người ghim với ba cách đoán: đường thẳng giữa hai ghim kề (cái CVAT làm), `Session.arrival` (bám tiến) và hai chiều chọn theo độ khớp (MVP 3: `tracking.track_backward` từ ghim sau, `choose` lấy phía khớp ≥ `MATCH_FLAG` hoặc trộn theo thời gian; chỉ để so sánh, nhãn vẫn chỉ bám tiến). **Chỉ số chính là IoU vùng mắt** (người dùng chốt 2026-11-17), kèm Dice, Boundary IoU, Precision/Recall, sai số px và % bề rộng mắt; mỗi nhóm có "mốc" = IoU của chính nhãn đúng khi dời 1 px vuông góc trục mắt. Chia nhóm trong/ngoài đoạn quay đầu và chớp mắt (EAR < `EAR_CLOSED`); loại ghim trùng khít bám tiến (phím K, kéo một điểm); không tính IoU khi nhãn đúng có khoé ước lượng hoặc điểm Outside. `format_table` in bảng kèm số mẫu, khoảng cách ghim, nguồn ghim; nút trong hộp Thông tin (`App.accuracy_report`) và lệnh `report`. Chỉ đo, không đổi nhãn. Kết quả nghiên cứu: `design/2026-11-17-interp-iou-research.md`.
- `overlap.py` (2026-11-17): `compare(spec, đoán, đúng)` so hai vùng mắt (đa giác qua 8 điểm theo thứ tự id) bằng IoU, Dice, Boundary IoU (dải viền `BAND_FRAC` = 2,5% bề rộng mắt đúng, tối thiểu 1 px), Precision, Recall; lấy mẫu ở tâm ô lưới 8×8 mỗi pixel (đúng tới khoảng 0,001 IoU), dải viền bằng `cv2.distanceTransform`; hai vùng cùng rỗng (mắt nhắm hẳn) trả None, một vùng rỗng thì mọi chỉ số bằng 0.
- Nối thẳng CVAT local (2026-11-16, thiết kế `design/2026-11-16-cvat-direct-design.md`, ghi chú API thật `design/cvat-api-notes.md`): `frames.py` (nguồn ảnh: `DirSource`; `Session(source=...)`, `Session.frames_dir` là `None` với nguồn khác); `cvatapi.py` (`CvatClient`: đăng nhập, danh sách, ảnh, xuất, import; chỉ localhost, bỏ qua proxy, không theo chuyển hướng, ảnh chỉ trong RAM; import KHÔNG gửi `filename`); `cvatsource.py` (`CvatSource`, `open_job`, `base_format`: định dạng nền chọn theo loại đối tượng không phải mắt vì "images" trải track thành shape, "video" đổi shape thành track một frame); `cvatxml.parse_bytes`/`write_eyes` đổi số frame job ↔ chỉ số EyePin; `qc.py` + `Session.qc` (job đã có nhãn mắt: chỉ xem, mọi sửa ném `QC_MSG`; `clear_old_eyes`/`restore_old_eyes`); `cvatsync.py` (`prepare`/`send`/`restore`/`mark_synced`: cảnh báo, chống ghi đè theo `updated_date`, đối chiếu sau khi gửi, bản chụp); `gui_cvat.py` (hộp "Mở từ CVAT…", việc mạng chạy luồng nền `_run_bg` có khoá sửa). Lệnh: `python -m eyepin gui --cvat http://localhost:8080 --job <id>`. Số frame của job lấy từ `job.start_frame/stop_frame` (tương đối); từ chối mở task video, job thưa, task có start_frame/frame_step riêng; `Session.stale` khi bám lỗi mạng (không gửi); `prepare` từ chối khi đối tượng không phải mắt nằm trên frame đã xoá hoặc nền video mà job có tag. Đã kiểm trên CVAT 2.75.0 thật bằng cầu nối trình duyệt (`spike/cvat_bridge_check.py`); chưa thử GUI với đăng nhập thật, task nhiều job, frame đã xoá.
- Màn đăng nhập là cửa trước (2026-11-17, người dùng chọn cách A; thiết kế `design/2026-11-16-cvat-home-design.md` mục 9, kế hoạch gốc `design/2026-11-16-cvat-home-plan.md` Task 1 một phần, Task 3, Task 5 một phần, Task 7 rút gọn): `cvatlogin.py` (nhớ **khoá** đăng nhập, không bao giờ mật khẩu: DPAPI qua `ctypes`, entropy cố định, file `cvat_login.bin` cạnh `settings.json`, hạn `remember_hours(settings)` = `settings["workspace"]["remember_login_hours"]`, mặc định 8, kẹp 0–72; `save_login`/`load_login`/`forget_login`; hết hạn, khác địa chỉ, hỏng thì tự xoá; không bao giờ gọi `POST /api/auth/logout`) và `gui_login.py` (`LoginScreen`: khung trong cửa sổ chính, dựng TRƯỚC `App`, việc mạng chạy luồng nền riêng; còn khoá hợp lệ thì thử `CvatClient.use_token` + `whoami` rồi bỏ qua màn: 401 xoá file, CVAT tắt thì giữ file; bỏ ô Ghi nhớ thì xoá khoá cũ; mật khẩu xoá khỏi ô sau mỗi lần thử; liên kết "Làm việc không cần CVAT" luôn bấm được. `FrontDoor`: nối màn với `App`, đăng nhập xong thì mở `--job` hoặc hộp "Mở từ CVAT…" đã đăng nhập sẵn. `LoginMixin.logout` (nút icon `logout` ngoài cùng bên phải thanh cam `App.logout_btn`, và menu "Đăng xuất…"; 2026-11-17, thiết kế mục 9b): hỏi trước khi xoá công chưa gửi (`Session.unsent`: bật ở `_push_undo`/undo/redo, tắt chỉ khi `cvatsync.send` gửi VÀ đối chiếu khớp, lưu vào file phiên của job CVAT; file cũ chưa có cờ mà có ghim = "chưa rõ"): không có gì chưa gửi thì một hộp `ask_logout`; job đang mở chưa gửi thì `ask_logout_open_job` → send (chạy `send_cvat` với hook `_after_send`/`_send_finished` trong `gui_cvat.py`, chỉ đi tiếp khi gửi xong và khớp) / discard / cancel; job khác chưa gửi thì `ask_logout_others` (liệt kê); rồi `cvatlogin.wipe_local` (xoá mọi file phiên CVAT nhận ra bằng nội dung — KHÔNG có thư mục `sessions/cvat/` —, khoá đã nhớ, tên đăng nhập; giữ phiên thư mục ảnh và file người dùng tự lưu) và `App.shutdown()`; huỷ tự lưu trước khi xoá; xoá lỗi file nào thì báo tên file và không đóng; job CVAT đang mở không hỏi "lưu rồi thoát", phiên thư mục ảnh vẫn hỏi như khi đóng cửa sổ; không gọi `POST /api/auth/logout`). `CvatClient` thêm `token`, `use_token`, `whoami`. `App.on_close` tách thành hỏi + `App.shutdown`. F2 > Workspace có "Nhớ đăng nhập CVAT (giờ)". Trang chủ (lưới task có ảnh, nhãn prelabeled) vẫn CHƯA xây. Màn đăng nhập không phải cổng bảo vệ (tool chạy local, có liên kết và dòng lệnh vào thẳng thư mục ảnh).
- Vẽ từng mắt (2026-11-16): `App.start_draw` (phím N) mở bảng "Vẽ mắt" (label, kiểu Track; Shape chưa có), `begin_draw(label, "points"|"box")`, bản nháp `App.draft` vẽ màu cam qua `_preview_pts`, `apply_draft` gọi `Session.pin_eye` (giữ vai trò điểm, kiểm bằng `geometry.validate_four`, chỉ tạo keyframe cho mắt đó). `geometry.four_in_box` dựng mắt mẫu từ khung kéo.
- Đổi kích thước (2026-11-16): `render.resize_handles(view, hộp)` cho 8 tay cầm của khung chọn (vẽ trong `draw_overlay`, tag `resize:<tên>`); `App._resize_hit` nhường cho kéo điểm khi điểm gần con trỏ hơn; `App._resize_override` co giãn mắt theo tỉ lệ, thả chuột thì `Session.drag_points`. Mọi lần kéo đang dở (tay cầm, điểm, cả mắt, bản nháp, khung vẽ) bị huỷ sạch bằng `App._cancel_drag` khi đổi frame (`go`, nhịp phát), trước lệnh sửa nhãn (`edit_command`) và khi mở phiên khác (B05, như CVAT).
- Vẽ nhãn (2026-11-16): `render.draw_overlay(bút_vẽ, ...)` vẽ mọi thứ trên ảnh nền qua một "bút vẽ". `render.CvPainter` vẽ lên ảnh numpy (`render_main`, xem trước, test, và khi nhãn mờ < 100%); `gui.CanvasPainter` tạo đối tượng vector trên Canvas (mặc định trong cửa sổ, tag `ov`, điểm có tag `pt:<mắt>:<id>`). Khung nhìn tự động chỉ canh lại khi đổi frame, cỡ khung, xoay ảnh, frame vừa có nhãn lần đầu hoặc bấm Vừa khung (`App._auto_view`); sửa nhãn không dời ảnh.
- `Session.load_pins(data)` ghim từ dữ liệu file `--pins` (kiểm hết trước, sai thì không ghim gì; frame chỉ có một mắt nạp như `pin_eye`; cả file là MỘT bước hoàn tác; lệnh `preview`, `turns`, `report` in một dòng "Lỗi: ..." và trả mã 2 khi file hỏng). `App.scratch` (mở bằng `--pins`): không khôi phục và không ghi file phiên (mọi đường ghi đều qua `save_work`).
- `imagefx.py` (2026-11-16, hộp Image setups như CVAT; thiết kế `design/2026-11-16-grid-color-design.md`): `apply_color` chỉnh màu như CVAT (gamma bảng tra `pow(v/255, 1/gamma)` trước, rồi `brightness() contrast() saturate()` theo %; `render.Look.adjust` gọi nó), `migrate_display` bỏ giá trị lưu theo thang cũ, `grid_step`/`draw_grid` vẽ lưới vào ảnh nền trong `render_base` (đường tại toạ độ nguyên, tự thưa dưới 8 px màn hình), `axis_guides` thước theo trục mắt (vẽ trong `draw_overlay` khi `Look.axis_guide` và có mắt đang chọn), `readout` chữ đo ở góc phải dòng trạng thái (`App.measure_var`). Hộp: `App._build_image_setups`, `_apply_setup`, `show_image_setups` (Ctrl+G, nút `^`), `toggle_grid` (g). Quy ước pixel như CVAT: pixel i phủ [i, i+1) (`render.warp_image` bù nửa pixel; `design/cvat-api-notes.md`).
- `tracking.py`: `track_forward`/`propagate` bám mắt bằng so khớp vùng ảnh (OpenCV `matchTemplate`, không model) và chỉ đi
  về phía sau từ mỗi frame ghim (quy tắc đã chốt); `pin_jump` đo độ trôi trước một frame ghim; `reduce_keyframes` chọn ít keyframe
  nhất để nội suy đường thẳng của CVAT lệch không quá một ngưỡng pixel. Phép bám chỉ dời cả mắt, không đổi dáng mắt.
  `track_backward` (2026-11-17) bám lùi bằng cùng phép so khớp trên dãy frame đảo ngược; chỉ `evaluate.py` gọi.

## Bố cục

- `HUONG_DAN.md`: trang hướng dẫn sử dụng cho người dùng (mở tool, 5 bước gán nhãn, quay đầu, báo độ chính xác, giới hạn).
- `tools/`: công cụ dựng tài nguyên (`build_icons.py`, nguồn SVG ở `tools/icon_src/`); `eyepin/assets/icons/`: icon PNG đã dựng, kèm `NOTICE.md`.
- `design/`: bản thiết kế, hành vi keyframe của CVAT, bản phác giao diện (`mockups/*.html`).
- `guideline/`: guideline học viên v1.3 (nguồn luật chính) và tài liệu lấy từ CVAT ngày 14/7/2026 (OCR, Phụ lục B
  liệt kê chỗ mâu thuẫn với v1.3 — luật trạng thái mắt còn chờ mentor).
- `spike/`: bản demo **dùng một lần** (hai hướng: bám theo ảnh từ 1 frame ghim, và ghim 5 frame + nội suy). Kết quả ở
  `spike/out/qc_report.md`, trang so sánh `spike/out/viewer.html`. Chỉ tham khảo, không dùng lại nguyên trạng.
- Mã dùng lại được nằm ngoài thư mục này, ở `..\week2\tools\`:
  - `eye_interp.py`: từ 4 điểm ghim (14,16,18,20 / 22,24,26,28) suy ra 4 điểm còn lại bằng parabol theo tỉ lệ
    guideline v1.3 mục 3.3. `run_demo.py` import hàm `derive` từ đây.
  - `validate_eye_skeletons.py`: kiểm hình học (thứ tự điểm, mí trên/dưới, bắt chéo, Outside, điểm nhảy).
  - `eye_prelabel.py`: bản cũ dùng MediaPipe — **không còn được dùng** vì lệnh cấm model.

## Lệnh thường dùng

```bash
python -m eyepin gui [thư_mục_ảnh] [--xml annotations.xml]     # mở cửa sổ; phím tắt theo CVAT, xem F1 hoặc design/shortcuts.md; cài đặt F2 (lưu ở ~/.eyepin/settings.json)
python -m eyepin shortcuts --out design/shortcuts.md           # sinh lại guide phím tắt từ eyepin/shortcuts.py
python -m eyepin scan annotations.xml                          # quét nhãn mắt có sẵn, in danh sách frame cần chú ý
python -m eyepin turns <thư_mục_ảnh> --pins pins.json          # báo đoạn quay đầu từ điểm ghim (ví dụ spike/out/pins_case01_ai.json), không cần cửa sổ
python -m eyepin report <thư_mục_ảnh> --pins pins.json         # bảng độ chính xác tại frame ghim bị giấu (IoU chính): đường thẳng CVAT, bám tiến, hai chiều
python spike\interp_iou_spike.py                                # nghiên cứu nội suy bằng IoU trên case 01 (trần nhiễu ghim, 7 cách đoán), khoảng 2 phút
python -m eyepin gui <thư_mục_ảnh> --pins pins.json            # mở cửa sổ với ghim có sẵn; không đụng file phiên đã lưu
python -m eyepin gui                                           # màn đăng nhập CVAT trước (hoặc chạy EyePin.bat); có liên kết làm việc không cần CVAT
python -m eyepin gui --cvat http://localhost:8080 --job 5      # màn đăng nhập (điền sẵn địa chỉ), đăng nhập xong mở thẳng job 5
python -m eyepin preview <thư_mục_ảnh> out.png --frame N [--pins pins.json]   # vẽ khung nhìn ra PNG, không cần cửa sổ
```

```bash
# Test đơn vị (unittest có sẵn; máy chưa có pytest)
python -m unittest discover -s tests -v
# Test tích hợp với CVAT local: cần container chạy và job đích TRỐNG (nó import nhãn thử rồi xoá sạch job)
python tests\cvat_roundtrip.py 9
# Đối chiếu tool với CVAT thật (V1-V6: nội suy, cờ, keyframe, xoay, quét, số keyframe); cần job TRỐNG, mặc định job 5
python tests\verify_vs_cvat.py 5
```

```bash
# Bật CVAT local (tag mặc định 'dev' không kéo được)
cd C:\Users\minhf\cvat && $env:CVAT_VERSION='v2.75.0'; docker compose up -d     # PowerShell; server trả 502 khoảng 1 phút đầu

# Suy 8 điểm từ 4 điểm ghim trong một file CVAT XML; hoặc đo độ lệch trên file đã đủ 8 điểm
python ..\week2\tools\eye_interp.py vao.xml ra.xml
python ..\week2\tools\eye_interp.py --evaluate day_du.xml

# Kiểm hình học nhãn mắt (--no-temporal khi các frame không liên tiếp)
python ..\week2\tools\validate_eye_skeletons.py annotations.xml --report ket_qua.txt

# Chạy lại spike: đọc điểm ghim ở spike/out/pins_ai.json, ghi kết quả vào spike/out/
python spike\run_demo.py
# Ảnh phóng to vùng mắt có lưới toạ độ để đọc điểm ghim
python spike\make_sheet.py <thư_mục_frame> <chỉ_số_frame> x0 y0 x1 y1 out\sheet.png 6
```

Import một file vào job trên CVAT local đã làm được bằng cách gọi
`cvat.apps.dataset_manager.task.import_job_annotations(path, job_id, 'CVAT 1.1', False)` trong
`docker exec cvat_server python manage.py shell` (chỉ khi job đang trống hoặc người dùng đồng ý mất nhãn cũ).
Tạo task mới từ zip: `C:\Users\minhf\Downloads\dms_build\cases\create_cvat_tasks.py` (đọc khoá từ `~\.cvat_token`;
khoá của tài khoản local dùng tiền tố `Token`, không phải `Bearer`).

## Dữ liệu thử (CVAT local, project `eyes_label` #2)

Không có nhãn chuẩn do người gán cho dữ liệu nào. Nguồn ảnh ở `C:\Users\minhf\Downloads\dms_build\`.

| Task/job | Nội dung |
| --- | --- |
| #2 | 200 ảnh rời: 140 hồng ngoại (DMD), 60 ảnh màu (YawDD) |
| #3, #4 | 200 frame liên tiếp PhysDrive 2352–2551, mặt thẳng, cháy sáng; đang chứa track của spike |
| #5 | Quay đầu, mắt bên xa bị che một phần (7650–7859) — dữ liệu cho tính năng chính của demo |
| #6–#9 | Quay đầu/chớp/tóc che, mặt sát mép, quay hẳn đi (Outside), tay che mắt |

Video gốc: `C:\Users\minhf\Downloads\physdrive_video\RGB.mp4` (một người, ban ngày, không kính; README bộ dữ liệu có
giới hạn sử dụng — chỉ dùng nội bộ). Chưa có video ban đêm, hồng ngoại liên tiếp, kính loá, hay job nhiều người.

## Giao tiếp

Người dùng viết tiếng Việt; trả lời và viết tài liệu bằng tiếng Việt. Ghi rõ điều gì người dùng đã chốt, điều gì là
đề xuất, điều gì chưa kiểm.
