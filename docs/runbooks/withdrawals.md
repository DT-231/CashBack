# Runbook: rút tiền (T-040) và khóa mã hóa số tài khoản

Mã: `backend/app/modules/payout/` (api, service, repository), `backend/app/modules/wallet/money.py` (bút toán ví), `backend/app/core/crypto.py` (AES-256-GCM). Chi trả **thủ công**: admin tự chuyển khoản ngoài hệ thống rồi ghi mã giao dịch.

## Bật rút tiền
1. Tạo khóa: `python3 -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`.
2. Đặt `BANK_ENC_KEY=<khóa>`, `BANK_ENC_KEY_ID=k1`, `WITHDRAWALS_ENABLED=1`. Khởi động **từ chối** nếu bật mà khóa thiếu, không đúng 32 byte base64, hoặc yếu.
3. **Sao lưu `BANK_ENC_KEY` NGOÀI `.env`** (trình quản lý mật khẩu, bản in cất tủ, hoặc ghi chú mã hóa; **không** trong repo, không dán vào chat, không để cùng nơi với bản sao lưu DB). **Mất khóa = không giải mã được số tài khoản của bất kỳ ai = không trả tiền được cho ai.** Có khóa mà mất DB cũng không dùng được: sao lưu cả hai, ở hai nơi khác nhau.
4. Điều kiện trước khi bật cho người thật: xem "Điều kiện mở đăng ký" trong `docs/12-backlog.md` (gồm: admin bật đăng nhập hai lớp TOTP, tài khoản DB riêng cho ứng dụng).

## Luồng
`POST /me/bank-accounts` (chờ `bank_change_cooldown_hours`, mặc định 48 giờ, trước khi rút lần đầu về tài khoản đó) → `POST /me/withdrawals` (header `Idempotency-Key` bắt buộc; khóa `rút được → đang khóa` trong một transaction có khóa dòng ví; tối thiểu `min_withdraw_vnd`; một yêu cầu mở mỗi user) → admin `approve` → admin `GET .../payout-account` (giải mã số tài khoản, **ghi audit `payout.view_account` mỗi lần**) → chuyển khoản ngoài hệ thống → `mark-paid` kèm mã giao dịch ngân hàng (duy nhất, không dùng lại). Từ chối (`reject`) hoặc chuyển khoản lỗi (`fail`) hoàn tiền bằng bút toán `refund_hold` mới, không sửa bút toán cũ.

## Quyền
Chỉ **admin** được duyệt, từ chối, đánh dấu đã chi trả, xem số tài khoản. **Staff không xem số tài khoản và không duyệt tiền** (kiểm ở API `require_admin` và lại ở service). Người dùng chỉ thấy 4 số cuối tài khoản của mình; số đầy đủ không bao giờ có trong response người dùng, log, audit hay thông báo lỗi.

## Đổi khóa mã hóa (xoay khóa)
1. Tạo khóa mới rồi đặt `BANK_ENC_KEY=<khóa mới>`, `BANK_ENC_KEY_ID=k2`, `BANK_ENC_OLD_KEYS=k1:<khóa cũ>`.
2. Bản mới dùng `k2`; bản mã cũ (`key_id=k1`) vẫn giải mã được. **Chưa có công cụ mã hóa lại hàng loạt** (backlog): chỉ bỏ `k1` khỏi `BANK_ENC_OLD_KEYS` khi không còn dòng `bank_accounts.key_id='k1'` (`SELECT key_id, count(*) FROM bank_accounts GROUP BY 1`).
3. Giữ bản sao lưu khóa cũ cho tới khi xác nhận bước 2.

## Sự cố thường gặp
| Triệu chứng | Làm gì |
|---|---|
| Khởi động báo thiếu/yếu `BANK_ENC_KEY` | Đặt khóa đúng định dạng; hoặc `WITHDRAWALS_ENABLED=0` |
| `GET .../payout-account` lỗi giải mã | `key_id` của dòng không còn trong `BANK_ENC_KEY`/`BANK_ENC_OLD_KEYS`: khôi phục khóa từ bản sao lưu |
| `409 invalid_transition` | Yêu cầu đã ở trạng thái khác (đã duyệt/trả/từ chối); xem `audit_logs` theo `target_type='withdrawal'` |
| `409 duplicate_provider_ref` | Mã giao dịch đó đã gắn với yêu cầu khác: kiểm tra có chuyển khoản trùng không |
| User bấm rút hai lần | Cùng `Idempotency-Key` trả lại yêu cầu cũ; khác key thì `409 withdrawal_open_exists` |
