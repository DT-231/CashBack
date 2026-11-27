-- Tài khoản DB riêng cho ỨNG DỤNG (API, worker). Chạy bằng tài khoản CHỦ SỞ HỮU/migration (không phải tài khoản ứng dụng):
--   psql "$OWNER_DATABASE_URL" -v app_role=cashback_app -v app_password='<mat-khau-dai-ngau-nhien>' -f infra/db/app-role.sql
-- Migrate (alembic) chạy bằng tài khoản chủ sở hữu; ứng dụng chạy bằng role này. Vì sao: xem docs/runbooks/db-roles.md.
--
-- Ứng dụng KHÔNG được: sở hữu bảng (nên không ALTER/DISABLE TRIGGER/DROP được), TRUNCATE, và sửa/xóa
-- sổ cái (wallet_entries) hay nhật ký kiểm toán (audit_logs). Trigger chỉ là lớp thứ hai; quyền là lớp thứ nhất.

CREATE ROLE :"app_role" LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT USAGE ON SCHEMA public TO :"app_role";

-- Mặc định: đọc, thêm, sửa. KHÔNG có DELETE/TRUNCATE trên bất kỳ bảng nào trừ danh sách bên dưới.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO :"app_role";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_role";

-- Chỉ những bảng mà code hiện tại cần xóa dòng (xem `grep "DELETE FROM" backend/app`)
GRANT DELETE ON rate_limits, refresh_tokens, orphan_orders, shopee_order_items, user_mfa, mfa_recovery_codes, email_tokens TO :"app_role";

-- Bất biến: sổ cái và audit chỉ thêm/đọc
REVOKE UPDATE, DELETE, TRUNCATE ON wallet_entries, audit_logs FROM :"app_role";
-- alembic_version do chủ sở hữu quản lý
REVOKE ALL ON alembic_version FROM :"app_role";

-- Bảng tạo SAU NÀY bởi migration (chủ sở hữu) không tự có quyền: cấp thêm trong chính migration/runbook của chúng.
