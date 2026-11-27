# Việc cần PO (autopilot không làm được hoặc không được quyết)

| # | Việc | Vì sao cần | Ảnh hưởng nếu chưa có |
|---|---|---|---|
| 1 | Ngày Shopee trả hoa hồng gần nhất và các đơn đi kèm | Chốt `hold_days` (mặc định 7 có thể không an toàn) | Tiền có thể mở khóa cho user trước khi Shopee trả cho bạn |
| 2 | Mua thử một đơn thật theo `docs/runbooks/live-attribution-test.md` và gửi kết quả (HAR đã che bằng `backend/scripts/redact_har.py`) | Xác nhận `utm_content` còn nguyên chữ ký; chốt tên trạng thái/trường thời gian đơn | `normalize.py` đang đoán tên trường; đơn không đọc được trạng thái sẽ ở PENDING mãi |
| 3 | Domain riêng trên Cloudflare DNS (không chứa thương hiệu Shopee), đăng ký làm kênh quảng bá trong hồ sơ Affiliate | Tunnel hostname cố định, cookie `__Host-`, `WEB_ORIGIN` | Không mở được web cho người ngoài (T-061) |
| 4 | Xác nhận bằng văn bản với Shopee về mô hình cashback (R-02) | Điều khoản có thể cấm chia lại hoa hồng | Rủi ro mất hoa hồng chưa trả |
| 5 | Trang Điều khoản và Chính sách quyền riêng tư: luật sư xem bản nháp (T-064) | R-06, R-17 | Không mở cho người ngoài |
| 6 | Tạo role `cashback_app` (`infra/db/app-role.sql`) và đổi `DATABASE_URL` của API khi muốn thử rút tiền | Khởi động từ chối rút tiền nếu user DB là superuser/chủ bảng | Không bật được rút tiền (đúng ý) |
| 7 | Sao lưu `BANK_ENC_KEY` ngoài `.env` (hai nơi); bật TOTP cho tài khoản admin thật | Mất khóa = không trả được cho ai | Không được bật rút tiền thật |
| 8 | Duyệt và merge `autopilot/main` vào `main` | Autopilot không sửa `main` | Mọi thay đổi chỉ nằm ở `autopilot/main` |
| 9 | **Gỡ `.claude/settings.json` khỏi `autopilot/main` trước khi merge vào `main`** (`git rm --cached .claude/settings.json`) | Commit `Merge task/T-018` vô tình kéo theo file cấu hình plugin cục bộ (do `git add -A` khi plugin vừa cài). Autopilot không được sửa `.claude/` nên không tự gỡ; nội dung chưa kiểm có secret hay không | Cấu hình cục bộ lọt vào repo public |
| 10 | Đặt lịch sao lưu hằng ngày (cron) theo `docs/runbooks/backup.md`, tạo `BACKUP_ENC_KEY` riêng và cất ngoài máy; chọn nơi lưu bản sao thứ hai | Script đã có và đã thử trên DB dev; cron/khóa là việc ở máy của bạn | Chưa có sao lưu tự động: mất đĩa là mất sổ cái |
