# Chỉ dẫn cho trợ lý AI (Codex) — demo gán nhãn mắt

Đây là bản demo dùng một lần (spike), không phải công cụ chính thức. Thư mục này chứa các script để đặt nhãn
hai skeleton mắt `mattrai` (điểm 14–21) và `matphai` (điểm 22–29) cho một đoạn frame liên tiếp.

## Quy tắc bắt buộc

1. Chỉ làm việc với dữ liệu công khai trong `C:\Users\minhf\Downloads\dms_build\physdrive_seg`. Không mở ảnh nào
   lấy từ CVAT của công ty trừ khi người dùng nói rõ là được phép.
2. Không đưa ảnh hay nhãn lên mạng, lên GitHub hoặc dịch vụ nào khác.
3. Không tự import vào CVAT. Tạo file xong thì báo người dùng; người dùng tự import.
4. Trái/phải theo khung hình: mắt có toạ độ x nhỏ hơn là `mattrai`.
5. Báo đúng những gì đã làm và đã kiểm tra. Điểm ghim của bạn là ước lượng, không phải đáp án.

## Việc 1: ghim 4 điểm mỗi mắt (prelabel)

Điểm ghim: `14` khoé ngoài mắt trái, `16` giữa mí trên, `18` khoé trong, `20` giữa mí dưới;
`22` khoé trong mắt phải, `24` giữa mí trên, `26` khoé ngoài, `28` giữa mí dưới.

1. Tạo ảnh phóng to có lưới toạ độ cho frame cần ghim (vạch vàng cách nhau 10 px, số trên lưới là toạ độ ảnh gốc):

   ```
   python make_sheet.py C:\Users\minhf\Downloads\dms_build\physdrive_seg <chỉ số frame> 270 255 550 345 out\sheet.png 6
   ```

   Nếu mắt nằm ngoài vùng cắt, đổi bốn số `x0 y0 x1 y1`.
2. Xem ảnh, đọc toạ độ 8 điểm ghim, ghi vào `out\pins_ai.json` theo đúng cấu trúc đang có trong file.
   - Điểm đặt trên bờ mi (ranh giới mí và nhãn cầu), không đặt lên lông mi hay gọng kính.
   - Mắt nhắm: `16` và `20` trùng nhau trên đường khe mí; `24` và `28` cũng vậy.
3. Nên ghim ở frame đầu, frame cuối, và mọi frame mắt đổi dáng (bắt đầu nhắm, nhắm hẳn, mở lại) hoặc đầu đổi hướng.

## Việc 2: chạy và soát (QC)

1. Chạy `python run_demo.py`. Script suy ra đủ 8 điểm mỗi mắt, nội suy giữa các frame ghim, bám theo mắt bằng so
   khớp vùng ảnh để đối chiếu, rồi ghi kết quả vào `out\`.
2. Đọc `out\qc_report.md` và `out\d2_metrics.csv`. Các cột cần xem:
   - `lech_tam_so_huong1`: tâm mắt nội suy lệch bao nhiêu px so với kết quả bám. Trên 5 px là chỗ cần thêm frame ghim.
   - `diem_khop_huong1`: dưới 0,8 nghĩa là dáng mắt đã đổi so với frame đầu (thường là chớp mắt).
   - `ti_le_mo_trai`, `ti_le_mo_phai`: độ mở mắt chia bề rộng mắt. Thay đổi đột ngột là chớp mắt.
   - `dich_max_so_frame_truoc`: trên 15 px cần kiểm tra lại (guideline v1.3 mục 6.9).
3. Với mỗi đoạn frame bị lệch, ghim thêm một frame ở giữa đoạn (quay lại Việc 1), chạy lại, cho tới khi không còn
   đoạn nào lệch trên 5 px.
4. Báo cho người dùng: đã ghim những frame nào, còn đoạn nào đáng nghi, và file import nằm ở đâu.
