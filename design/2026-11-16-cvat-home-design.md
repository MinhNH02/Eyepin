# Trang chủ CVAT trong EyePin và nhớ đăng nhập (thiết kế, 2026-11-16)

Nối tiếp `design/2026-11-16-cvat-direct-design.md` (mở job CVAT trực tiếp). Chỉ làm với CVAT local (`http://localhost:8080`); server công ty để sau.

## 1. Vì sao
- Người dùng nói: "hơi khó để xác định job", muốn "1 giao diện trang chủ giống cvat", thêm trạng thái job ("new, in progress, prelabeled"), và "nên lưu mật khẩu trong khoảng 1 thời gian vì mỗi lần chọn job tôi đều phải đăng nhập lại".
- Hiện nay hộp "Mở từ CVAT…" (`eyepin/gui_cvat.py` `_build_cvat_dialog`) chỉ có hai danh sách chữ (`#id tên (N frame)` và `Job #id frame a–b … state / stage`): không ảnh, không project, không biết job đã có nhãn mắt chưa, nên phải nhớ số.
- Phải đăng nhập lại vì: không có đường quay về danh sách job trong cửa sổ đang mở (đóng tool rồi mở lại), và khoá đăng nhập không được lưu qua lần mở tool (thiết kế cũ). Người dùng nay **đổi quyết định đó**: cho phép nhớ đăng nhập có hạn.

## 2. Mục tiêu / không làm / thất bại dù chạy được
**Mục tiêu**
- Một trang chủ trong cửa sổ chính, giống trang Tasks của CVAT: nhìn là nhận ra job cần làm.
- Mỗi job hiện trạng thái CVAT (`state`: new / in progress / rejected / completed; `stage`) **và** nhãn riêng của EyePin: **prelabeled** = job đã có nhãn mắt (mở sẽ vào chế độ QC), ngược lại "chưa có nhãn mắt". (Người dùng xác nhận nghĩa của prelabeled.)
- Đi lại trang chủ ↔ job không cần đăng nhập lại; mở lại tool trong thời hạn cũng không cần.

**Không làm (lần này)**
- Trang Projects riêng, trang Jobs toàn cục, tạo/sửa/xoá task hay job, đổi state/stage/người được giao từ EyePin.
- Server công ty (vẫn chỉ nhận localhost như `CvatClient`).
- Lưu mật khẩu.

**Thất bại dù chạy được**
- Ảnh xem trước hoặc ảnh frame ghi ra đĩa (luật "ảnh chỉ trong bộ nhớ").
- Trang chủ đứng cửa sổ khi đang tải (mọi lệnh mạng chạy nền qua `_run_bg` hoặc tương đương).
- Nhãn "prelabeled" sai (báo chưa có nhãn mắt trong khi có): người dùng mở nhầm vào chế độ gán mới rồi gửi đè. Không chắc thì hiện "chưa rõ", không đoán.
- Rời job đang có thay đổi chưa gửi mà không hỏi.
- Khoá lưu dạng chữ thường đọc được, hoặc file khoá còn trên máy sau khi bấm Đăng xuất / hết hạn.
- EyePin huỷ khoá trên CVAT (làm đứt script và cửa sổ khác dùng cùng tài khoản).

## 3. Cách làm đã chọn (người dùng chọn A cả hai)
### 3a. Trang chủ — đã chọn A: nằm trong cửa sổ chính
- **A (chọn):** khi chưa mở job (hoặc bấm "← Trang chủ"), vùng thân cửa sổ (thanh công cụ trái + ảnh + panel phải) được thay bằng trang chủ; thanh cam trên cùng giữ menu, ẩn các nút điều hướng frame. Lý do: giống CVAT, quay về không phải mở lại tool.
- B (không chọn): hộp "Mở từ CVAT…" to hơn có ảnh và cột trạng thái. Ít sửa hơn nhưng vẫn là cửa sổ phụ, không giải quyết việc quay về.
- (Bỏ từ đầu) trang web riêng: lệch khỏi tool Tkinter đang có và phải giữ đăng nhập ở hai nơi.

### 3b. Nhớ đăng nhập — đã chọn A: lưu khoá, không lưu mật khẩu
- **A (chọn):** lưu khoá đăng nhập CVAT (token trả từ `POST /api/auth/login`), mã hoá bằng Windows DPAPI (`CryptProtectData`, gọi qua `ctypes`, không thêm thư viện), kèm địa chỉ CVAT, tên đăng nhập và thời điểm hết hạn. Hạn mặc định **8 giờ**, chỉnh trong Cài đặt. Ô "Ghi nhớ đăng nhập" ở màn đăng nhập (mặc định bật — đề xuất của mình), nút "Đăng xuất" trên trang chủ.
- B (không chọn): lưu mật khẩu — lộ là lộ mật khẩu, không phải một khoá có hạn và huỷ được.

## 4. Thiết kế
### 4.1 Luồng
1. `python -m eyepin gui --cvat http://localhost:8080` (không `--job`) → nếu có khoá còn hạn cho địa chỉ đó thì thử dùng (gọi một API nhẹ); dùng được → trang chủ; không thì màn đăng nhập.
2. `--job N` giữ như cũ: đăng nhập (hoặc khoá đã nhớ) rồi mở thẳng job N. Từ job đó bấm "← Trang chủ" vẫn về được trang chủ.
3. Menu "Mở từ CVAT…" → về trang chủ (thay hộp cũ). Hộp cũ bỏ đi; phần đăng nhập chuyển thành màn đăng nhập trên trang chủ (địa chỉ, tên, mật khẩu, ô ghi nhớ, nút Đăng nhập).
4. Mở thư mục ảnh / file XML (không CVAT) giữ nguyên, không đi qua trang chủ.

### 4.2 Trang chủ (phác thảo)
```
[≡ menu]  EyePin · CVAT localhost:8080 · minh        [⟳ Làm mới] [Đăng xuất]
Project: [Tất cả ▾]   Tìm: [__________]
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│  [ảnh xem  │ │  [ảnh]     │ │  [ảnh]     │ │  [ảnh]     │
│   trước]   │ │            │ │            │ │            │
│ #5 physd…  │ │ #6 dmd_…   │ │ …          │ │ …          │
│ eyes_label │ │ eyes_label │ │            │ │            │
│ 210 frame  │ │ 200 frame  │ │            │ │            │
│ 1 job      │ │ 2 job      │ │            │ │            │
└────────────┘ └────────────┘ └────────────┘ └────────────┘
```
Bấm một thẻ task → danh sách job của task (cùng trang, có "← Danh sách task"):
```
← Danh sách task    Task #6 dmd_…  (eyes_label)
[ảnh] Job #7   frame 0–99    in progress / annotation   prelabeled      sửa 16/11 14:02   [Mở]
[ảnh] Job #8   frame 100–199 new / annotation           chưa có nhãn mắt sửa 15/11 09:10   [Mở]
```
- Thẻ task: ảnh xem trước, `#id tên`, tên project (nếu có), số frame, số job. Lọc theo project và tìm theo tên/số.
- Dòng job: ảnh xem trước, `Job #id`, khoảng frame, `state / stage` của CVAT, nhãn EyePin (prelabeled / chưa có nhãn mắt / đang kiểm… / chưa rõ), người được giao nếu có, ngày sửa cuối. Bấm đúp hoặc "Mở" → `load_cvat`.
- Job mà EyePin sẽ từ chối mở (video, job thưa, task có start_frame/frame_step riêng) hiện mờ kèm lý do ngắn nếu biết được từ dữ liệu đã có; nếu chỉ biết lúc mở thì cứ để lỗi hiện như bây giờ.
- Màu và kiểu theo `theme.py` hiện có.

### 4.3 Trạng thái "prelabeled"
- Nguồn: `CvatClient.annotations(job_id)` (JSON). Hàm mới dùng chung, ví dụ `qc.json_has_eyes(aj)`: **có bất kỳ** shape hoặc track nhãn `mattrai`/`matphai` nào trong JSON (kể cả track rỗng, toàn Outside, ngoài khoảng frame) → prelabeled. Đây là quy tắc rộng, cố ý nghiêng về phía an toàn.
- *(Quyết định của mình sau khi người đọc thử chỉ ra)* Hiện `cvatsource.open_job` quyết định QC bằng XML đã parse (`qc.has_eye_labels`), và XML có thể bỏ sót đối tượng mắt mà JSON vẫn có. Đổi `open_job` thành: vào QC nếu **XML có mắt HOẶC `json_has_eyes`**. Như vậy trang chủ báo prelabeled thì mở job không bao giờ vào chế độ gán mới (nơi lần gửi sẽ xoá nhãn mắt đó). Test cũ của `open_job` phải chạy lại; thêm test cho trường hợp JSON có mắt mà XML không.
- Chỉ kiểm job của task đang xem (không kiểm cả server), chạy nền từng job, dòng hiện "đang kiểm…" trong lúc chờ; lỗi → "chưa rõ".
- Nhớ kết quả trong bộ nhớ theo `(job_id, updated_date)`; job đổi `updated_date` thì kiểm lại. Sau khi EyePin gửi nhãn thành công thì job đó coi như prelabeled.

### 4.4 Ảnh xem trước
- `GET /api/tasks/{id}/preview` và `GET /api/jobs/{id}/preview` (CVAT 2.x có; **chưa thử trên 2.75 local** — kiểm trước khi làm). Lỗi hoặc không có → khung xám.
- Giữ trong bộ nhớ (PIL/PhotoImage), thu nhỏ; không ghi đĩa, không cache ra file.

### 4.5 Rời job về trang chủ
- Nút "← Trang chủ" trên thanh cam khi đang mở job CVAT.
- *(Quyết định của mình)* Thêm cờ mới `Session.unsent`: bật khi nhãn đổi sau lúc mở job hoặc sau lần gửi thành công cuối, tắt khi `mark_synced`. Khác `dirty` (chỉ là chưa lưu file phiên trên máy).
- `unsent` bật → hỏi: **Gửi lên CVAT** / **Rời đi** (vẫn tự lưu phiên trên máy như `_save_outgoing` hiện nay; lần mở lại job tool hỏi khôi phục) / **Huỷ** (mặc định Huỷ). Không bao giờ tự gửi, và không xoá bản lưu trên máy, để không mất công sức.
- Về trang chủ thì làm mới danh sách job của task vừa làm.
- Đang mở thư mục ảnh (không phải CVAT) mà chọn "Mở từ CVAT…" thì giữ cách hiện nay (tự lưu phiên rồi chuyển).

### 4.5b Phiên hết hạn giữa lúc làm job
- *(Quyết định của mình)* Gặp 401 khi đang trong job thì hiện **hộp đăng nhập nhỏ nổi trên job** (giữ `_login_again(retry)` như hiện nay), không đổi sang trang chủ. Đăng nhập xong thì làm tiếp việc vừa hỏng (gửi, khôi phục, đọc frame). Trang chủ và hộp này dùng chung một khung nhập (địa chỉ, tên, mật khẩu, ô ghi nhớ).

### 4.6 Nhớ đăng nhập
- Lưu ở cùng thư mục với settings (`shortcuts.settings_path().parent`), file riêng (ví dụ `cvat_login.bin`): DPAPI-blob của `{url, user, token, expires_at}`. Mật khẩu không bao giờ lưu.
- Chỉ dùng khi `url` trùng và chưa hết hạn; gặp 401 → xoá file, về màn đăng nhập (ghim đang làm không mất, như `_login_again` hiện nay).
- **Không bao giờ gọi `POST /api/auth/logout`** (người dùng quyết: "chỉ đăng xuất ở máy cá nhân thôi không cần đăng xuất cvat"): CVAT có thể cấp một khoá chung cho mỗi tài khoản, huỷ nó làm đứt script `create_cvat_tasks.py` (`~/.cvat_token`) và cửa sổ EyePin khác. Hết hạn lúc mở tool: chỉ xoá file khoá.

### 4.6b Đăng xuất = dọn dữ liệu CVAT trên máy (người dùng đồng ý)
Lý do của người dùng: công ty quy định trước khi ra về phải xoá file trên máy. Ảnh vốn không ra đĩa nên đăng xuất **không** làm lần mở sau chậm hơn; cái mất duy nhất là công chưa gửi lên CVAT.
1. **Kiểm trước khi xoá**, gồm cả công đang mở trong cửa sổ (kể cả chưa Ctrl+S, dùng cờ `unsent` mục 4.5) và mọi file phiên của job CVAT trên máy có công chưa gửi.
2. **Job đang mở có công chưa gửi** → hỏi: **Gửi rồi đăng xuất** / **Đăng xuất và bỏ công này** / **Huỷ** (mặc định Huỷ). "Gửi" chạy đúng luồng gửi hiện có (hộp xác nhận, đối chiếu sau gửi); gửi lỗi hoặc người dùng huỷ ở hộp gửi → dừng đăng xuất, không xoá gì.
3. **Job khác có phiên chưa gửi** (do tự lưu 2 phút hoặc "Rời đi") → liệt kê (số job, số frame ghim) và hỏi: **Xoá luôn** / **Huỷ** (mặc định Huỷ). Tool không tự gửi các job này (gửi cần mở job và đối chiếu).
4. **Xoá:** file khoá đăng nhập; mọi file phiên của job CVAT (`sessions\*.json` có nguồn là CVAT — cần nhận ra được, ví dụ trường nguồn trong file phiên hoặc thư mục con riêng `sessions\cvat\`); tên đăng nhập CVAT trong `settings.json` (giữ địa chỉ). Rồi đóng job đang mở và về màn đăng nhập.
5. **Không xoá:** phiên của thư mục ảnh trên máy (dữ liệu công khai, như case 01); file người dùng tự lưu qua hộp "Lưu…" (bản chụp, XML xuất) — tool không biết người dùng còn cần không. HUONG_DAN ghi rõ người dùng tự dọn các file này.
6. Máy tắt đột ngột: phần tự lưu còn trên máy tới lần Đăng xuất sau. HUONG_DAN khuyên: trước khi về, mở EyePin bấm Đăng xuất.
7. Xoá thất bại một file (bị khoá…) → báo tên file, không giả vờ đã sạch.
- Bỏ ô "Ghi nhớ" → không ghi file, khoá chỉ sống trong cửa sổ đang mở (như hôm nay).
- Hạn: Cài đặt > "Nhớ đăng nhập CVAT (giờ)", mặc định 8, 0 = không nhớ.
- Lưu ý ghi vào HUONG_DAN: hạn 8 giờ và nút Đăng xuất chỉ là **của EyePin trên máy này**; khoá vẫn còn hiệu lực trên CVAT (muốn huỷ hẳn thì đăng xuất trên web CVAT).

### 4.7 API thêm vào `CvatClient`
- `tasks()` thêm `project_id`, `updated_date`, số job (từ `jobs.count` nếu có), `mode`/`dimension` nếu cần lọc.
- `projects()` → `{id: name}` để hiện tên project.
- `jobs()` thêm `assignee` (username), `updated_date`, `type`.
- `preview(kind, id) -> bytes | None`.
- `whoami()` hoặc `GET /api/users/self` để thử khoá đã nhớ.
- `use_token(token)` để nạp khoá đã nhớ (vẫn qua quy tắc localhost-only, `trust_env=False`, không redirect).

## 5. Ràng buộc
- Luật dự án trong `CLAUDE.md`: không model học máy; ảnh công ty không ra mạng/đĩa ngoài; chỉ CVAT local được thử tự do; không điều khiển trình duyệt vào server công ty.
- Ảnh (preview, frame) chỉ trong bộ nhớ.
- Không thêm thư viện ngoài (DPAPI qua `ctypes`).
- Không git: diff bằng bản sao lưu như các đợt trước; test `python -m unittest discover -s tests -p "test_*.py"`.
- Thử tay chỉ trên CVAT local; dùng `tests/fake_cvat.py` cho test tự động (thêm preview, logout, users/self, project).

## 6. Để người làm tự quyết
- Bố cục chính xác của lưới (số cột theo bề rộng cửa sổ), cỡ ảnh xem trước, cách cuộn.
- Tách file: đề xuất `eyepin/gui_home.py` (trang chủ) và `eyepin/cvatlogin.py` (DPAPI + file khoá), giữ `gui_cvat.py` cho mở/gửi job.
- Có phân trang hay không (8 task local thì không cần; viết sao cho trăm task vẫn không đứng cửa sổ).

## 7. Chưa kiểm
- Endpoint preview và `users/self` trên CVAT 2.75 local (chỉ đọc).
- `jobs.count` trong `/api/tasks` của 2.75.

## 8. Chờ người dùng (không chặn việc làm)
- Lối tắt Eyepin trên Desktop có đổi sang mở trang chủ (`--cvat http://localhost:8080`) không. Mặc định chưa đổi; lệnh `gui` không tham số vẫn mở cửa sổ trống như hiện nay. **→ Đã quyết ở mục 9 (2026-11-17).**

## 9. Bổ sung 2026-11-17: màn đăng nhập là cửa trước (người dùng chọn cách A)
Người dùng nói: "nên làm 1 màn đăng nhập trước khi vào trong eyepin", rồi chọn **A** trong ba cách (A: màn đăng nhập trước, có liên kết đi thẳng vào thư mục ảnh; B: bắt buộc đăng nhập, không có liên kết; C: chỉ hiện khi chạy `--cvat`). Mục này đổi mục 4.1 (lệnh `gui` không tham số, và mục 8). Phần còn lại của bản thiết kế này giữ nguyên.

**Làm lần này (lát cắt nhỏ, chạy được trước khi có trang chủ):**
- **Màn đăng nhập** (`eyepin/gui_login.py`, `LoginScreen`) hiện trong cửa sổ chính, trước khi dựng giao diện gán nhãn, khi chạy `python -m eyepin gui` không kèm thư mục ảnh. Gồm địa chỉ CVAT, tên đăng nhập, mật khẩu, ô "Ghi nhớ đăng nhập (N giờ)", nút Đăng nhập, và liên kết "Làm việc không cần CVAT → mở thư mục ảnh" (đi vào cửa sổ trống như hiện nay).
- **Nhớ đăng nhập** (`eyepin/cvatlogin.py`, đúng mục 3b và 4.6): khoá lưu mã hoá DPAPI ở `cvat_login.bin`, hạn mặc định 8 giờ, không bao giờ lưu mật khẩu, không gọi `POST /api/auth/logout`. Còn khoá hợp lệ thì **bỏ qua màn đăng nhập** (thử `GET /api/users/self` ở luồng nền): 401 → xoá file, hiện màn đăng nhập; CVAT tắt hoặc lỗi mạng → hiện màn đăng nhập kèm lỗi và **giữ** file khoá.
- Đăng nhập xong: `--job N` thì mở thẳng job N; không thì mở hộp "Mở từ CVAT…" đã đăng nhập sẵn (danh sách task/job). Trang chủ (mục 4.2) sẽ thay hộp này sau.
- **Đăng xuất…** trong menu (bản rút gọn của mục 4.6b; **đã được thay bằng bản đầy đủ ở mục 9b**): hỏi xác nhận, hỏi lưu nếu còn thay đổi chưa lưu, xoá file khoá đã nhớ và tên đăng nhập trong `settings.json`, rồi đóng cửa sổ. Bản này chưa dọn file phiên của job CVAT và chưa kiểm công chưa gửi.
- Cài đặt F2 > Workspace: "Nhớ đăng nhập CVAT (giờ)", 0 = không nhớ (và xoá khoá đang nhớ), tối đa 72.

**Không đổi:** `gui <thư_mục_ảnh>`, `--pins`, `--xml`, `--selftest` vào thẳng cửa sổ như cũ (đường demo/dòng lệnh, test dựa vào chúng). `--cvat URL [--job N]` vẫn dùng, nay mở màn đăng nhập với địa chỉ điền sẵn. Chỉ nhận localhost như `CvatClient` (server công ty để sau).

**Giới hạn cần nói thẳng:** màn này chỉ kiểm tài khoản CVAT. Nó không khoá được ảnh hay file trên máy (tool chạy local, có liên kết vào thư mục ảnh, và dòng lệnh vẫn mở thẳng), nên không phải cổng chặn người dùng.

**Cách đã cân nhắc:** (A) màn đăng nhập trước + liên kết thư mục ảnh (**chọn**); (B) bắt buộc đăng nhập, không liên kết (loại: demo case 01 và QC trên thư mục ảnh phải gõ lệnh); (C) chỉ hiện khi `--cvat` (loại: không cho người dùng thứ họ yêu cầu).

**Quyết định của mình (người dùng chưa duyệt từng cái):**
- Màn đăng nhập hiện trong cùng cửa sổ chính (không mở cửa sổ phụ), đóng bằng nút X thì thoát EyePin.
- Hạn nhớ lưu ở `settings["workspace"]["remember_login_hours"]`, **không** ở `settings["cvat"]` như kế hoạch cũ ghi: hộp "Mở từ CVAT…" hiện tại ghi đè nguyên `settings["cvat"]` mỗi lần đăng nhập nên sẽ làm mất giá trị người dùng đã chỉnh.
- Ô "Ghi nhớ" mặc định bật (như mục 3b). Bỏ ô này khi đăng nhập thì xoá khoá đang nhớ (nếu không, lần sau vẫn tự vào, trái ý người dùng).
- Mật khẩu bị xoá khỏi ô nhập sau mỗi lần thử, đúng hay sai.
- Hạn nhớ bị kẹp trong 0–72 giờ; giá trị hỏng trong `settings.json` coi là 8.
- Khoá mã hoá DPAPI có thêm "entropy" cố định của EyePin; chỉ tài khoản Windows đã tạo mới giải mã được. File hỏng hoặc của tài khoản khác: coi như không có, xoá, không sập.
- Lối tắt Desktop `Eyepin.lnk` đang trỏ tới `EyePin_case01.bat` (truyền sẵn thư mục case 01) nên **vẫn bỏ qua màn đăng nhập**; thêm `EyePin.bat` (chạy `gui` không tham số) nhưng không đổi lối tắt của người dùng.

## 9b. Bổ sung 2026-11-17: nút Đăng xuất đầy đủ (người dùng: "làm nút đăng xuất đi")
Làm nốt mục 4.6b (người dùng đã đồng ý từ 2026-11-16) cộng một **nút Đăng xuất nhìn thấy được** (icon `logout`, ngoài cùng bên phải thanh cam trên cùng; menu vẫn có mục "Đăng xuất…"). Thay bản rút gọn ở mục 9. Hành vi đúng 4.6b: kiểm công chưa gửi trước khi xoá; job đang mở chưa gửi → **Gửi rồi đăng xuất / Đăng xuất và bỏ công này / Huỷ** (mặc định Huỷ; gửi lỗi hoặc huỷ ở hộp gửi thì dừng, không xoá gì); job khác còn phiên chưa gửi → liệt kê và hỏi **Xoá luôn / Huỷ**; xoá khoá đã nhớ, tên đăng nhập (giữ địa chỉ) và mọi file phiên của job CVAT; không xoá phiên thư mục ảnh và file người dùng tự lưu; xoá lỗi một file thì báo tên file, không nói "đã sạch", không đóng cửa sổ. Không bao giờ gọi `POST /api/auth/logout`.

**Cờ "chưa gửi" `Session.unsent`** (kế hoạch Task 4): bật ở mọi thay đổi nhãn (`_push_undo`, `undo`, `redo`), tắt khi mở job và sau lần gửi **thành công và đối chiếu khớp** (gửi xong mà đối chiếu lệch thì vẫn "chưa gửi": an toàn hơn). Lưu vào file phiên của job CVAT (`unsent`).

**Khác kế hoạch cũ (mình tự quyết, chưa duyệt từng cái):**
- **Không tạo thư mục `sessions/cvat/` và không chuyển file cũ.** Nhận ra file phiên của job CVAT bằng nội dung: file có khoá `cvat` (từ trước tới nay `Session.state()` đã ghi khoá này cho job CVAT, nên cả file cũ cũng nhận ra được mà khỏi chuyển). Ít chỗ phải sửa hơn (`state_path` giữ nguyên) và không bỏ sót file cũ.
- **File phiên cũ chưa có trường `unsent`** (lưu trước hôm nay) mà có ghim: coi là "chưa rõ đã gửi hay chưa" và liệt kê cùng nhóm chưa gửi (nghiêng về an toàn; lần đăng xuất đầu có thể hỏi về các phiên thử cũ). Không có ghim thì không hỏi.
- **Khôi phục phiên đã lưu:** theo trường `unsent` trong file (kế hoạch cũ ghi "luôn True nếu có ghim", sẽ hỏi thừa với phiên đã gửi xong); thiếu trường thì True nếu có ghim.
- **Hộp hỏi gộp để khỏi hỏi dồn:** không có gì chưa gửi thì chỉ một hộp xác nhận; có công chưa gửi thì hộp "Gửi / Bỏ / Huỷ" thay cho hộp xác nhận chung, thêm hộp thứ hai chỉ khi còn job khác chưa gửi. Với job CVAT đang mở không hỏi "lưu rồi thoát" (bản lưu sắp bị xoá); phiên thư mục ảnh đang mở vẫn hỏi như khi đóng cửa sổ.
- ~~Đăng xuất đóng EyePin~~ **Người dùng chốt 2026-11-17: Đăng xuất (sau khi dọn dữ liệu như trên) chỉ quay về màn đăng nhập; chỉ khi đóng cửa sổ EyePin mới thoát tiến trình.** (Bản trước do Claude tự chọn: "đóng EyePin", lý do cũ: dựng lại `App` dễ sót phím gắn toàn cục và hẹn giờ — B13 đã thêm đường huỷ mọi hẹn giờ khi đóng, dùng được khi dựng lại.)
- Tự lưu bị huỷ trước khi xoá để một lần tự lưu không ghi lại file vừa xoá.

## 9c. Ghi chú 2026-11-17 khi cập nhật kế hoạch (không đổi quyết định nào của người dùng)
- Kế hoạch đã viết lại theo mã hiện tại (`design/2026-11-16-cvat-home-plan.md`, bản 2; đối chiếu ở `.superpowers/sdd/bugfix/PLAN2-check.md`).
- Mục 5 "Không git" đã cũ: dự án dùng git; việc của kế hoạch này làm trên nhánh `feature/cvat-home` từ `develop`.
- Mục 4.3: hàm dùng chung có chữ ký `qc.json_has_eyes(aj, eye_ids=None)` (nhận id nhãn mắt; trang chủ lấy nhãn của task một lần) — đề xuất của Claude.
- Mục 4.6b bước 4 ("đóng job đang mở và về màn đăng nhập") nay khớp lại với quyết định dòng 170; kế hoạch Task 2 làm việc này bằng cách gỡ `App` khỏi cửa sổ và dựng lại màn đăng nhập trong cùng cửa sổ.
- Mục 4.6 "gặp 401 → xoá file": hiện mới đúng ở màn đăng nhập; giữa job chưa đúng (kế hoạch Task 4).
