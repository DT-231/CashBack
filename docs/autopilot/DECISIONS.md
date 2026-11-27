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
