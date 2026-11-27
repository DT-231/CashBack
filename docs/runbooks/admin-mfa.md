# Runbook: đăng nhập hai lớp (TOTP) cho admin (T-019)

Mã: `backend/app/modules/auth/{mfa_service,mfa_api}.py`, `backend/app/core/totp.py`. Mọi route `/api/v1/admin/*` (duyệt, từ chối, chi trả, xem số tài khoản) yêu cầu admin **đã bật TOTP và đã nhập mã gần đây** (`ADMIN_MFA_REQUIRED=1`, mặc định). Chưa bật hoặc phiên chưa xác minh: `403 mfa_required`. Bật rút tiền (`WITHDRAWALS_ENABLED=1`) mà `ADMIN_MFA_REQUIRED=0` thì khởi động bị từ chối.

## Thiết lập lần đầu (admin)
1. Đăng nhập bình thường, rồi `POST /api/v1/auth/mfa/setup` → nhận `secret` (hiện **một lần**) và `otpauth_uri` (mã QR). Thêm vào Google Authenticator, Authy, 1Password...
2. `POST /auth/mfa/enable {code}` bằng mã 6 số hiện trong ứng dụng → nhận **8 mã khôi phục** (hiện một lần; server chỉ lưu bản băm). **Cất ngoài máy** (trình quản lý mật khẩu hoặc bản in cất tủ), không chụp màn hình gửi chat.
3. `POST /auth/mfa/verify {code}` → nhận cặp token mới có `mfa_at`; dùng cặp này cho route admin. Phiên hết hiệu lực xác minh sau `MFA_MAX_AGE_HOURS` (mặc định 12 giờ; làm mới token **không** gia hạn): nhập lại mã.

## Thông tin kỹ thuật
- Bí mật TOTP mã hóa AES-GCM bằng **cùng khóa `BANK_ENC_KEY`** (khác AAD với số tài khoản, có `key_id`): cần `BANK_ENC_KEY` để dùng TOTP, dù chưa bật rút tiền. Mất khóa = không giải mã được bí mật TOTP của ai: dùng mã khôi phục để vào, rồi tắt và thiết lập lại.
- Mỗi mã dùng **một lần** (bước 30 giây ghi nguyên tử, chống phát lại kể cả hai request song song); chấp nhận lệch đồng hồ ±30 giây. Thử mã giới hạn `RL_MFA_PER_MINUTE` (5) theo user và theo IP; mỗi lần sai ghi audit `mfa.*_failed` (không ghi mã).
- Audit: `mfa.setup`, `mfa.enable`, `mfa.verify`, `mfa.recovery_used` (kèm số mã còn lại), `mfa.disable`, `mfa.verify_failed`, `mfa.enable_failed`, `mfa.disable_failed`.
- Trạng thái TOTP kiểm DB mỗi request: tắt TOTP hoặc hạ quyền có hiệu lực ngay.

## Mất điện thoại / không có mã
- Còn mã khôi phục: `POST /auth/mfa/verify {recovery_code}` (mỗi mã một lần, không phân biệt hoa thường/dấu gạch), sau đó `POST /auth/mfa/disable {code}` **không** làm được nếu không có mã TOTP: dùng quy trình quản trị DB bên dưới rồi thiết lập lại.
- Hết cách (mất cả mã khôi phục): chủ DB chạy (ghi lại việc đã làm; hành động này ngoài ứng dụng nên **không có audit tự động**):
  ```sql
  DELETE FROM mfa_recovery_codes WHERE user_id = <id>; DELETE FROM user_mfa WHERE user_id = <id>;
  ```
  rồi admin thiết lập lại từ bước 1. Chỉ làm sau khi xác minh danh tính người yêu cầu ngoài kênh.

## Tạo admin đầu tiên
Không có endpoint tự nâng quyền. Đăng ký tài khoản thường rồi chủ DB chạy `UPDATE users SET role = 'admin' WHERE email = '<email>'`, sau đó admin thiết lập TOTP như trên. Ghi lại việc nâng quyền. Dev: `backend/scripts/seed.py` có sẵn admin dev (không dùng ở production).
