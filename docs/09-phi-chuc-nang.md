# 09 — Yêu cầu phi chức năng

## Bảo mật
| Hạng mục | Yêu cầu |
|---|---|
| Mật khẩu | argon2id; tối thiểu 10 ký tự; kiểm tra danh sách mật khẩu phổ biến |
| Phiên | Cookie `HttpOnly; Secure; SameSite=Lax`, hết hạn 7 ngày, thu hồi được; CSRF token cho thao tác ghi |
| Phân quyền | RBAC kiểm tra ở backend cho mọi route; `member` chỉ thấy dữ liệu của mình (lọc theo `user_id` ở tầng truy vấn) |
| Rate limit | Đăng ký/đăng nhập/quên mật khẩu theo IP+email; `/go/` theo IP; Tool API theo key. Lưu ở Postgres |
| IP | Lưu `ip_hash` bằng HMAC với khóa bí mật; không lưu IP thô quá 7 ngày (chỉ để chống tấn công) |
| Cookie Shopee | AES-GCM trước khi lưu DB, khóa `APP_ENC_KEY` ở `.env`; không log, không trả qua API, chỉ admin cập nhật; log che mọi header `cookie` |
| Bí mật | `.env` không commit; `.gitignore` đầy đủ; quét secret trong CI |
| Đầu vào | Validate bằng schema; chỉ chấp nhận host Shopee cho link (chống SSRF/open redirect); đích `/go/` lấy từ DB, không từ query |
| Ví | Sổ cái chỉ thêm; transaction + khóa dòng; kiểm tra không âm bằng `CHECK` ở DB |
| Admin | 2FA TOTP (Should); audit log mọi hành động; thao tác nhạy cảm (duyệt rút, gán đơn mồ côi) ghi người làm |
| CORS | Chỉ domain web; bỏ `*` |
| Tunnel | Chỉ expose route cần thiết; admin có thể đặt sau Cloudflare Access (miễn phí cho ít người dùng, cần kiểm tra khi cấu hình) |

## Hiệu năng
- `/go/`: p95 < 200 ms (một lần ghi DB). Nếu ghi click lỗi vẫn phải redirect.
- Web: tải ban đầu < 3 s trên 4G.
- Dự kiến tải MVP: vài nghìn click/ngày; Postgres một máy là đủ. Index trên `clicks(link_id)`, `shopee_orders(order_sn)`, `wallet_entries(user_id,state)`.

## Khả năng chịu lỗi khi cookie chết
- Phát hiện sớm: health-check mỗi 15 phút; lỗi 401/403/HTML → `expired`.
- Cảnh báo Telegram/Email ngay và nhắc lại mỗi 6 giờ cho tới khi sửa.
- **Không cộng tiền và không chuyển `pending→available` khi phiên không healthy hoặc lần sync thành công gần nhất cũ hơn 24 giờ.** Nhận click vẫn chạy.
- Dự phòng: import CSV báo cáo xuất tay từ dashboard Shopee, đi qua cùng pipeline khớp `sub_id`.
- Không bao giờ cắt im lặng dữ liệu: nếu phân trang vượt giới hạn thì lần sync đánh dấu `partial` và không dùng để chuyển tiền.

## Logging / monitoring
- Log JSON có `request_id`; che cookie, token, mật khẩu, số tài khoản.
- Endpoint `/health` (không lộ cấu hình), `/admin/health` chi tiết: DB, sync gần nhất, cookie, backup gần nhất.
- Cảnh báo: cookie chết, sync lỗi > 2 lần liên tiếp, backup lỗi, yêu cầu rút > ngưỡng, đối soát lệch.

## Backup / khôi phục
- `pg_dump` hằng ngày lúc 03:00, nén + mã hóa, giữ 14 bản hằng ngày + 8 bản hằng tuần.
- Lưu ổ ngoài + Google Drive (rclone).
- Test khôi phục mỗi tháng (một story trong backlog). RPO ≤ 24 giờ, RTO ≤ 4 giờ.
- Ví là dữ liệu tiền: tăng tần suất dump lên 6 giờ/lần khi đã có user thật (đề xuất).

## Dữ liệu cá nhân
- Thu thập tối thiểu: email, tài khoản ngân hàng khi rút, `ip_hash`.
- Có Điều khoản + Chính sách quyền riêng tư (soạn Sprint 6); cho user xóa tài khoản khi không còn số dư/đơn treo; giữ dữ liệu giao dịch theo thời hạn pháp luật yêu cầu. **Cần tư vấn pháp lý/kế toán** về nghĩa vụ lưu trữ và bảo vệ dữ liệu cá nhân (Nghị định về bảo vệ dữ liệu cá nhân), không kết luận thay.
- Số tài khoản ngân hàng mã hóa; chỉ hiện 4 số cuối trên UI.
- Không đưa thông tin cá nhân vào `sub_id` hoặc URL.

## Khả dụng
- Mục tiêu MVP: best-effort (máy nhà). Mất điện/mạng thì xử lý như `06-kien-truc.md` mục 5.
