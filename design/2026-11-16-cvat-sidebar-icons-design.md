# Thanh bên phải giống hệt CVAT và bộ icon CVAT (thiết kế, 2026-11-16)

## 1. Vì sao
- Người dùng: "nên làm thanh bên phải giống cvat", chọn **"b giống hệt cvat"**; "giữ nguyên frame lân cận và tính năng này tôi nghĩ có thể bật tắt".
- Người dùng: "nên có kiểu icon giống cvat, di vào thì có chữ hiển thị ra, không trỏ chuột vào thì mất chữ, lấy các icon giống cvat đi vì annotator đã quen với cvat rồi tool này của mình dựa trên cvat và cải tiến thêm".
- Hiện nay tab Đối tượng là một **bảng** (`ttk.Treeview`, `eyepin/gui.py` ~331) và một hàng nút chung bên dưới: phải chọn dòng rồi mới bấm nút, khác CVAT. Icon là ký tự font Windows hoặc chữ thay thế (`eyepin/icons.py`: `P`, `L`, `★`…), không giống CVAT. Bốn nút bên phải thanh trên có chữ cố định dưới icon.

## 2. Mục tiêu / không làm / thất bại dù chạy được
**Mục tiêu**
- Tab Objects là **danh sách thẻ** theo đúng bố cục CVAT 2.75 (mục 4), mỗi mắt một thẻ, nút nằm trên thẻ.
- Dùng **đúng icon của CVAT** (icon riêng của CVAT và icon Ant Design mà CVAT dùng) cho mọi nút có tương đương trong CVAT, ở cả thanh trên, thanh công cụ trái và thanh bên phải *(phạm vi toàn cửa sổ là quyết định của mình; người dùng có thể thu lại chỉ thanh bên phải)*.
- **Không có chữ cố định cạnh icon**; trỏ chuột vào mới hiện chữ (tiếng Việt + phím tắt), rời chuột thì mất.
- Tab theo thứ tự CVAT: **Objects | Labels | Issues**, rồi **Frame lân cận**; tab Frame lân cận bật/tắt được.

**Không làm**
- Đổi hành vi chỉnh nhãn (kéo điểm, bám, ghim…), đổi phím tắt, đổi tab Issues (nội dung EyePin riêng).
- Thêm thư viện chạy lúc dùng tool (Tk 8.6 không đọc SVG → dùng PNG làm sẵn, mục 5).

**Thất bại dù chạy được**
- Mất một tính năng panel đang có (Items, Sort by, khoá/ẩn/thu gọn tất cả, ⋮ menu: URL, Make a copy, Propagate, các lệnh lớp, Pinned, Occluded/Outside từng điểm, nhảy keyframe, nhấp đúp để phóng vào mắt, chuột phải mở menu).
- Phím `Del`, `q`, `o`, `k`, `l`, `h`, `p`, Tab/Shift+Tab, Ctrl+1/2 hoạt động khác trước (đặc biệt Del và q/o theo con trỏ vừa sửa ở `tests/test_keys_focus.py`).
- Panel giật hoặc làm chậm lúc phát (Space) hay kéo điểm: thẻ chỉ được dựng lại khi danh sách đối tượng đổi, còn trạng thái nút thì cập nhật tại chỗ.
- Icon mờ hơn phần còn lại của cửa sổ (xem 7b.2 về DPI).
- Thiếu ghi chú bản quyền MIT của CVAT và Ant Design.

## 3. Cách làm (người dùng đã chọn)
- **Chọn:** dựng lại tab Objects bằng thẻ Tk (khung cuộn + các `Frame`), theo đúng cấu trúc component của CVAT; icon PNG làm sẵn từ SVG gốc.
- Loại: giữ `Treeview` và chỉ đổi màu (không thể giống CVAT); nhúng trang web (thêm thư viện, hai giao diện).

## 4. Bố cục — chép từ mã nguồn CVAT v2.75.0
Nguồn đã đọc (tải về ngày 16/11, để tra lại: thư mục scratchpad `cvat_src/`; lấy lại từ `github.com/cvat-ai/cvat/tree/v2.75.0/cvat-ui/src/components/annotation-page/`):
`objects-side-bar/objects-side-bar.tsx`, `objects-list-header.tsx`, `object-item-basics.tsx`, `object-item-buttons.tsx`, `object-item-details.tsx`, `object-item-element.tsx`, `label-item.tsx`, `top-bar/left-group.tsx`, `right-group.tsx`, `player-buttons.tsx`, `controls-side-bar/*.tsx`, và `cvat-ui/src/icons.tsx`.

### 4.1 Đầu danh sách (objects-list-header)
`Items: N` · ô `Sort by` · nút **khoá tất cả** (UnlockOutlined / LockFilled) · **ẩn tất cả** (EyeOutlined / EyeInvisibleFilled) · **mở/thu tất cả** (CaretDownOutlined / CaretUpFilled). Nút "+ đối tượng mới" của EyePin (không có trong CVAT) giữ ở cuối hàng, icon `plus-icon`.

### 4.2 Thẻ đối tượng (track)
```
┃ 1   SKELETON TRACK          [mattrai ▾]        ⋮
┃      ⏮     ◀     ▶     ⏭
┃   Outside  Lock  Occluded  Hidden  Keyframe  Pinned
┃ ▸ DETAILS
┃     14  (Outside Lock Occluded Hidden)   … 8 điểm
```
- Hàng đầu (object-item-basics): số ID, chữ loại `SKELETON TRACK` (shape thì `SKELETON SHAPE`), ô chọn label (= hành động `swap_labels` hiện có), nút ⋮ (MoreOutlined) mở menu đối tượng hiện có (`_build_obj_menu`). Vạch màu bên trái theo màu label (`look.color_of`).
- Hàng 2 (object-item-buttons, track): keyframe đầu/trước/kế/cuối = `first-icon`, `previous-icon`, `next-icon`, `last-icon`; mờ khi không có keyframe theo hướng đó.
- Hàng 3, **đúng thứ tự CVAT**: Outside (`object-outside-icon` khi đang outside / SelectOutlined khi không), Lock (LockFilled / UnlockOutlined), Occluded (TeamOutlined khi occluded / UserOutlined khi không), Hidden (EyeInvisibleFilled / EyeOutlined), Keyframe (StarFilled / StarOutlined), Pinned (PushpinFilled / PushpinOutlined).
- **DETAILS** thu gọn được (object-item-details / object-item-element): mỗi điểm (14–21 hoặc 22–29) một dòng, tên điểm và nút Outside/Lock/Occluded/Hidden của điểm đó — nối vào cờ từng điểm đang có (`toggle_flag` theo pid). Nút nào EyePin chưa có ở mức điểm (Lock, Hidden từng điểm) thì *để người làm quyết*: làm nếu rẻ, không thì không hiện nút đó (không hiện nút giả).
- Chọn: bấm vào thẻ = chọn mắt đó (thay `tree.selection`). Thẻ đang chọn có viền đậm như CVAT. **Trỏ chuột vào mắt trên ảnh thì thẻ của nó sáng lên** và cuộn tới nếu khuất (CVAT "activated"); trỏ chuột vào thẻ thì mắt trên ảnh sáng lên.
- Nhấp đúp thẻ = phóng vào mắt (`focus_object`); chuột phải thẻ = menu ⋮.
- Nhiều người (layer): thẻ mỗi mắt của mỗi người, ID khác nhau, như hiện có hậu tố `@chỉ_số`.

### 4.3 Tab Labels (label-item)
Mỗi label một dòng: chấm màu, tên, Lock (LockFilled / UnlockOutlined), Hidden (EyeInvisibleFilled / EyeOutlined). Nội dung như `build_labels_tab` hiện có, chỉ đổi icon.

### 4.4 Tab Issues
Giữ nội dung EyePin (đoạn quay đầu + Quét). Chỉ đổi icon các nút đầu tab sang icon Ant tương ứng (check, eye, next/prev).

### 4.5 Tab Frame lân cận
Giữ nguyên nội dung. Thêm Cài đặt F2 → Workspace → "Hiện tab Frame lân cận" (mặc định bật, lưu trong `settings.json`). Tắt thì gỡ tab khỏi `Notebook` (không chỉ ẩn), và không tính ảnh thu nhỏ cho tab đó (đỡ tốn CPU khi phát).

### 4.6 Thanh trên và thanh công cụ trái
Đổi sang icon CVAT khi có tương đương; **bỏ chữ cố định** dưới icon ("Hiển thị", "Toàn màn hình", "Lọc", "Thông tin"). Bảng đề xuất (để người làm sửa nếu tìm được icon CVAT sát hơn):

| Nút EyePin | Icon |
|---|---|
| Menu, Lưu, Hoàn tác, Làm lại | `main-menu-icon`, `save-icon`, `undo-icon`, `redo-icon` |
| Frame đầu, lùi 10, trước, phát/dừng, kế, tiến 10, cuối | `first-icon`, `back-jump-icon`, `previous-icon` (`previous-filtered-icon` khi đang lọc), `play-icon`/`pause-icon`, `next-icon` (`next-filtered-icon`), `forward-jump-icon`, `last-icon` |
| Toàn màn hình, Thông tin, Lọc | `fullscreen-icon`, InfoCircleOutlined, `filter-icon` |
| Hiển thị (lớp, cỡ điểm, độ sáng) | `colorize-icon` *(đề xuất)* |
| Con trỏ, Dời ảnh, Xoay ảnh, Vừa khung, Phóng/thu | `cursor-icon`, `move-icon`, `rotate-icon` (ngược chiều thì lật ngang), `fit-to-window-icon`, `zoom-icon` |
| Vẽ một mắt (`n`) | `skeleton-icon` (CVAT vẽ skeleton bằng icon này) |
| Ghim khi che khoé (`Shift+N`), Ghim/bỏ ghim keyframe | `point-icon` *(đề xuất)*, StarOutlined/StarFilled |
| Quét, Xuất, Phím tắt, Cài đặt, Ẩn/hiện nhãn | ScanOutlined, ExportOutlined, QuestionCircleOutlined, SettingOutlined, EyeOutlined/EyeInvisibleFilled |
| Gửi lên CVAT, Trang chủ, Đăng xuất (thiết kế trang chủ) | CloudUploadOutlined, HomeOutlined, LogoutOutlined |
| Xoá, Sao chép, URL, Lớp lên/xuống/nền/trước | DeleteOutlined, CopyOutlined, LinkOutlined, `next-layer-icon`, `previous-layer-icon`, `foreground-icon`, `background-icon` |

### 4.7 Chữ khi trỏ chuột (tooltip)
- Mọi nút icon dùng `Tooltip` sẵn có của `IconButton`: hiện sau ~0,1–0,3 s khi trỏ vào, mất ngay khi rời. Nội dung tiếng Việt + phím tắt hiện hành (`kl(...)`), ví dụ "Occluded cho mắt này (q)".
- Ghi chú: CVAT thật có chữ nhỏ dưới một số nút thanh trên (`left-group.tsx` có `<span>Undo</span>`); theo ý người dùng, EyePin **không** hiện chữ cố định nào.

## 5. Icon: lấy, đổi, lưu
- Đã tải (người dùng cho phép) vào thư mục riêng `scratchpad/icons_dl/`: 34 SVG của CVAT (`raw.githubusercontent.com/cvat-ai/cvat/v2.75.0/cvat-ui/src/assets/`) + `LICENSE` (MIT, Intel/CVAT.ai); 32 SVG Ant Design (`unpkg.com/@ant-design/icons-svg@4.4.2/inline-svg/`) + `LICENSE` (MIT, Ant UED). 213 KB, đã kiểm không có `<script>`/`onload`. Thiếu icon nào thì tải thêm cùng nguồn, cùng phiên bản.
- Đổi SVG → PNG **một lần lúc làm**, bằng script trong `tools/` (không phải lúc chạy tool). Công cụ đổi do người làm chọn (ví dụ trình duyệt headless có sẵn trên máy, hoặc thư viện chỉ cài cho bước này); kết quả không phụ thuộc công cụ đó.
- Lưu **mặt nạ trong suốt (alpha) trắng** ở 16, 20, 24 px và bản @2x (32, 40, 48 px) trong `eyepin/assets/icons/`; lúc chạy tô màu theo trạng thái (thường / hover / bật / mờ) bằng PIL rồi tạo `PhotoImage`, cache trong bộ nhớ. Chọn cỡ theo DPI của Tk (`winfo_fpixels('1i')`).
- `eyepin/assets/icons/NOTICE.md`: nguồn, phiên bản, hai giấy phép MIT đầy đủ.
- `icons.py` giữ API `IconButton(name, …)`; bảng tên → file PNG thay cho bảng ký tự font. Thiếu file → chữ thay thế như hiện nay (không sập).

## 6. Ràng buộc
- Luật dự án (`CLAUDE.md`): không model học máy; ảnh không ra mạng; CVAT công ty không đụng. Phần này không chạm dữ liệu ảnh.
- Không git: sao lưu trước khi sửa, test bằng `python -m unittest discover -s tests -p "test_*.py"`.
- Khoảng 310 chỗ dùng `self.tree` / `app.tree` trong `eyepin/gui.py`, `gui_objects.py`, `tests/test_gui.py`, `test_parity.py`, `test_gui_cvat.py`, `test_keys_focus.py`. Cần một lớp chọn đối tượng mới (ví dụ `ObjectList` với `selection()`, `select(eye, layer, point)`, `clear()`) và chuyển test sang đó; **hành vi các test cũ phải giữ** (chỉ đổi cách truy cập).
- Máy người dùng đang thiếu bộ nhớ ảo (bộ test đủ bị `MemoryError` ngẫu nhiên); chạy test theo từng file khi cần.

## 7. Để người làm tự quyết
- Lớp cuộn của danh sách thẻ, cỡ chữ, khoảng cách; màu theo `theme.py` nhưng sát giao diện sáng của CVAT.
- Lock/Hidden mức điểm trong DETAILS: làm hay bỏ (mục 4.2).
- Tách file: đề xuất `eyepin/gui_sidebar.py` (thẻ đối tượng) và `tools/build_icons.py`.

## 7b. Quyết định của mình sau khi người đọc thử hỏi (người dùng kiểm khi duyệt)
1. **Thông tin trạng thái đang có trên bảng** (keyframe / tool tính / từ file / chưa có / đã xoá, "(không có nhãn)"): hiện bằng chữ nhỏ màu xám ngay sau chữ loại, ví dụ `SKELETON TRACK · keyframe`. Các nhãn [khoá] / [pinned] / [ẩn] không cần chữ nữa vì nút Lock / Pinned / Hidden trên thẻ đã cho thấy trạng thái. Dòng điểm trong DETAILS có chữ nhỏ "ghim" / "suy ra". Test cũ đọc chữ trạng thái chuyển sang đọc qua lớp danh sách mới (ví dụ `ObjectList.status_text(eye, layer)`), nghĩa giữ nguyên.
2. **DPI:** không bật chế độ DPI-aware cho cả cửa sổ trong đợt này (đụng phông, toạ độ chuột, khung vẽ — rủi ro lớn). Icon chỉ cần nét bằng phần còn lại của cửa sổ; bỏ tiêu chí "mờ ở 125–150%" khỏi mục 2. Dùng PNG đúng cỡ hiển thị (16/20/24) để không bị Tk co giãn thêm.
3. **Hidden và Lock trên thẻ tác động đúng một đối tượng** (mắt đó của người đó), như CVAT; nút ở tab Labels tác động mọi đối tượng cùng label (mọi người). Đây là đổi hành vi có chủ đích để giống CVAT: cần trạng thái ẩn theo (người, mắt) trong `look`/`render` và khoá theo (người, mắt). Phím `h`/`l` áp cho mắt đang chọn (hoặc dưới con trỏ), `H`/`L` cho tất cả, như hiện nay.
4. **Chọn một điểm:** bấm vào dòng điểm trong DETAILS = chọn điểm đó (dòng được tô nền), `q`/`o` khi chuột không ở trên ảnh sẽ áp cho điểm đó như hiện nay. Thu gọn DETAILS thì lựa chọn trở về cả mắt.
5. **Nút không có trên thẻ CVAT:** giữ nút Xoá (DeleteOutlined) ở hàng đầu danh sách cạnh nút "+", và thêm mục "Remove" vào menu ⋮ như CVAT. Nhảy keyframe của cả job và "ghim cả frame" vẫn có ở thanh trên (◀KF / KF▶), thanh trái (nút keyframe) và phím `r`/`e`/`k`, nên không mất.

## 8. Chưa kiểm
- Chưa chụp được CVAT thật để so (tiện ích Chrome mất kết nối giữa chừng); bố cục lấy từ mã nguồn v2.75.0. Khi xong, so lại với CVAT trên máy (job #4 có 2 track, dữ liệu công khai) bằng mắt hoặc ảnh chụp.
