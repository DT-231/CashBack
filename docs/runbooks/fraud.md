# Runbook: cờ gian lận (T-053)

Mã: `backend/app/modules/fraud/`. Chạy quét: `python -m app.main_worker fraud-scan` (in JSON `{created, updated, suppressed, by_rule}`); đặt cron mỗi vài giờ trên máy chạy worker. Quét idempotent (cập nhật cờ đang mở, không tạo trùng).

| Luật | Điều kiện (mặc định, đổi bằng `FRAUD_*`) | Ý nghĩa và sai dương tính hay gặp |
|---|---|---|
| `shared_ip` | >= 3 chủ link khác nhau có click từ cùng một `ip_hash` trong 7 ngày | Trại tài khoản ảo tự click link của mình. Sai dương tính: cùng nhà/quán cà phê/wifi công ty, CGNAT của nhà mạng |
| `high_cancel_rate` | >= 5 đơn gán cho user trong 60 ngày và >= 50% là hủy/trả | Đơn ảo hoặc đặt rồi hủy để lấy hoa hồng. Sai dương tính: người mua hủy nhiều vì lý do hợp lệ |
| `click_burst` | >= 60 click trong một giờ từ MỘT ip_hash vào MỘT link | Bot bơm click. Sai dương tính: link được chia sẻ trong mạng nội bộ |

## Xử lý
1. `GET /api/v1/admin/fraud-flags?status=open` (admin + TOTP). Xem `detail` và đối chiếu đơn/click của user.
2. `POST /admin/fraud-flags/{id}/resolve {status, note}`: `dismissed` (không gian lận; cờ cùng luật không tạo lại 30 ngày, đổi `FRAUD_DISMISS_COOLDOWN_DAYS`) hoặc `confirmed` (đã xác nhận). Mọi xử lý có audit `fraud.resolve`.
3. Hành động lên tài khoản là việc RIÊNG và có chủ ý: khóa user (`PATCH /admin/users/{id}` kèm lý do); tiền của user không tự bị giữ hay trừ. Đơn đã chuyển sang rút được rồi mà bị Shopee thu hồi: xem `docs/runbooks/wallet.md` (bút toán `adjust`).

## Giới hạn đã biết
Không phát hiện được "tự mua" (chủ tài khoản affiliate = người mua): chỉ Shopee biết (R-08); dựa vào `hold_days` và tỷ lệ hủy. Chưa có luật theo UA/thiết bị vì chưa lưu dữ liệu đó ngoài `ua_hash`.
