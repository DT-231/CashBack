# Runbook: audit_logs (nhật ký kiểm toán)

Mã: `backend/app/modules/audit/` (service, sanitize, repository), migration `0004`. Bảng **chỉ thêm**: trigger DB chặn UPDATE/DELETE.

## Ghi gì
| Cột | Ý nghĩa |
|---|---|
| `actor_id`, `actor_role` | ai: `user`, `staff`, `admin`, `agent`, `system` (id rỗng cho `system`) |
| `action` | `<nhóm>.<hành_động>` chữ thường, ví dụ `settings.set`, `auth.register`, `auth.logout`, (T-040) `withdrawal.approve` |
| `target_type`, `target_id` | đối tượng bị tác động (`user`, `setting`, `withdrawal`...) |
| `detail` | JSON đã lọc (<= 4000 ký tự): giá trị mới/cũ, lý do. **Không** mật khẩu, token, cookie, số tài khoản |
| `ip_hash` | HMAC-SHA256(`IP_SALT`, IP) 16 hex; không có `IP_SALT` thì rỗng. Không bao giờ lưu IP thô |
| `request_id`, `at` | liên kết log truy cập; thời điểm |

## Cách dùng trong code
- **Thao tác admin/tiền** (phải nhất quán): trong chính transaction của thao tác gọi `audit.record(conn, settings, Actor(admin_id, "admin"), "withdrawal.approve", target_type="withdrawal", target_id=wid, detail={...}, ip=request_ip(request, settings))`. Lỗi ghi log thì cả thao tác hủy. Mẫu: `PlatformSettings.set_int(..., audit_ctx=AuditContext(settings, actor, ip))`. **Endpoint admin bắt buộc truyền `audit_ctx`** (tham số tùy chọn chỉ để test/seed).
- **Sự kiện thông tin** (đăng ký, đăng xuất): `record_best_effort(engine, ...)`, lỗi chỉ ghi log.
- `detail` luôn qua `sanitize_detail`: che khóa nhạy cảm (`password`, `token`, `secret`, `cookie`, `authorization`, `api_key`, `otp`, `pin`, `*account*` trừ `*_id`, ...) và che giá trị trông như JWT, bearer, chuỗi dài >= 32 ký tự, dãy >= 8 chữ số. Muốn log một khóa bị che nhầm thì đặt tên cụ thể hơn (`setting_key` thay vì `key`).
- Chỉ `modules/audit` được ghi bảng (test `test_architecture`).

## Truy vấn thường dùng
```sql
SELECT at, actor_role, actor_id, action, target_type, target_id, detail FROM audit_logs ORDER BY id DESC LIMIT 50;
SELECT * FROM audit_logs WHERE target_type='withdrawal' AND target_id='12' ORDER BY id;
```

## Lưu ý vận hành
- Không có cách xóa qua ứng dụng. Muốn dọn dữ liệu dev: `ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_change; DELETE ...; ALTER TABLE ... ENABLE TRIGGER ...` (chỉ trên máy dev; test tự làm sau mỗi phiên, xem `tests/integration/conftest.py`).
- Nên backup cùng DB; không xuất `detail` ra ngoài khi chưa xem lại.
