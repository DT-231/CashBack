# DECISIONS

## 2026-11-28 T-018: nhiều khóa sub_id
- Bối cảnh: chữ ký 3 ký tự không có id khóa; phải thử lần lượt từng khóa.
- Chọn: `SUBID_SECRET_PREVIOUS` (tối đa 3, chỉ giải mã, không ký); khóa trùng/ngắn bị từ chối khi khởi động và khi sync. Kiểm tra sở hữu click/link ở `attribute` giữ nguyên.
- Thay thế: thêm id khóa vào s5 (đổi quy ước sub_id v1: cấm); chỉ 1 khóa cũ (kém linh hoạt).
- Đảo ngược: để `SUBID_SECRET_PREVIOUS` trống (hành vi cũ).
- PO nên xem: giới hạn 3 khóa và lập luận xác suất khớp nhầm (~N/46656, test thực nghiệm 60000 mẫu).
- Lưu ý: dùng 'git add <đường dẫn cụ thể>' thay vì 'git add -A' để không kéo file cục bộ vào commit.

## 2026-11-28 T-044: ai được gán đơn mồ côi
- Bối cảnh: backlog/`08-api.md` ghi "staff+"; nhưng gán đơn làm user nhận tiền (accrual ở lần chốt ví), và PO đã chốt staff không duyệt tiền.
- Chọn: **chỉ admin** (+TOTP), cấm tự gán cho mình, gán đúng một lần. Fail-closed.
- Thay thế: staff được gán nhưng admin duyệt (cần luồng duyệt mới); cho staff gán kèm giới hạn số tiền.
- Đảo ngược: đổi `require_admin` sang vai trò staff+ ở `orders/api.py` và bỏ kiểm tra role ở `admin_service.py` (cần PO quyết).
- PO nên xem lại.

## 2026-11-28 T-043: ai xem tổng quan/danh sách user và khóa user
- Bối cảnh: `08-api.md` ghi staff xem được; danh sách user chứa email và số dư (PII, tiền).
- Chọn: **admin + TOTP cho tất cả** endpoint T-043 (fail-closed, nhất quán với "staff không xem tiền").
- Quy tắc khóa: cấm tự khóa mình và cấm đổi trạng thái admin khác qua API (tránh tự khóa ra ngoài hoặc admin bị chiếm khóa admin còn lại); khóa xóa refresh token; role đổi bằng tay ở DB.
- Thay thế: staff xem (chỉ-đọc) sau khi PO xác nhận danh sách trường được phép; admin khóa được admin khác kèm xác nhận hai người.
- Đảo ngược: đổi `require_admin` ở `adminstats/api.py` sang dependency cho staff.
- PO nên xem lại.

## 2026-11-28 CSP chưa chặn script
- Bối cảnh: Next.js App Router dùng script nội tuyến; CSP `script-src 'self'` sẽ làm hỏng trang nếu không có nonce.
- Chọn: chỉ đặt các chỉ thị an toàn không cần nonce (frame-ancestors, base-uri, form-action, object-src). Chưa có `script-src`.
- Thay thế: middleware sinh nonce mỗi request và `script-src 'self' 'nonce-…' 'strict-dynamic'` (đề xuất làm khi có domain thật và có thể thử trên trình duyệt thật: không thử được trong môi trường này).
- Đảo ngược: xóa dòng CSP khỏi `next.config.ts`.
