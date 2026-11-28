# Runbook: email giao dịch (xác minh, đặt lại mật khẩu)

Mã: `backend/app/integrations/mail/` (SMTP, STARTTLS bắt buộc), `backend/app/modules/auth/account_service.py`. Không có `SMTP_HOST`/`SMTP_FROM` hoặc `MOCK=1`: **không gửi gì** (NullMailer), API vẫn trả 202.

## Cấu hình
`SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `WEB_ORIGIN` (gốc liên kết, ví dụ `https://cashback.example`; cần domain riêng, xem `docs/06`). Chọn nhà cung cấp có gói miễn phí, không cần thẻ (kiểm khi đăng ký; PO chọn). Gmail/Outlook cá nhân thường cần mật khẩu ứng dụng và giới hạn số thư/ngày.
`REQUIRE_EMAIL_VERIFY=1` chỉ khi SMTP đã chạy được: nếu không, người đăng ký mới không đăng nhập được.

## Hành vi cần biết
- Liên kết: `WEB_ORIGIN/verify-email?token=…` (24 giờ) và `WEB_ORIGIN/reset-password?token=…` (1 giờ). Trang web tương ứng chưa có (backlog); trang gọi `POST /auth/verify` hoặc `POST /auth/reset` với token.
- Token một lần, chỉ lưu SHA-256; yêu cầu mới làm token cũ vô hiệu. Thư gửi **sau** khi đã trả lời (không lộ email nào tồn tại qua độ trễ). SMTP hỏng chỉ ghi log `gửi email thất bại` (không có nội dung/người nhận), người dùng vẫn nhận 202 và có thể yêu cầu lại (giới hạn 3 lần/giờ/email).
- Đặt lại mật khẩu đăng xuất mọi thiết bị, không mở khóa tài khoản `locked`. Admin vẫn cần TOTP cho thao tác admin.
- Thử không cần SMTP thật: test dùng Mailer giả (`app.state.mailer`).
