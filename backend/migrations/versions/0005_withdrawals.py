"""rút tiền (T-040): idempotency, người duyệt/chi trả, mã giao dịch duy nhất; tài khoản ngân hàng có key_id/last4/thời gian chờ;
chặn TRUNCATE sổ cái và audit_logs; thu hồi quyền sửa/xóa/TRUNCATE của role ứng dụng `cashback_app` nếu có

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade():
    op.execute("""
        ALTER TABLE withdrawals
          ADD COLUMN idem_key text,
          ADD COLUMN approved_by bigint REFERENCES users(id),
          ADD COLUMN approved_at timestamptz,
          ADD COLUMN paid_by bigint REFERENCES users(id),
          ADD COLUMN paid_at timestamptz,
          ADD COLUMN decided_reason text,
          ADD CONSTRAINT withdrawals_paid_has_ref CHECK (status <> 'paid' OR provider_ref IS NOT NULL)""")
    # Bấm hai lần (cùng Idempotency-Key) không tạo hai yêu cầu; một mã giao dịch ngân hàng chỉ dùng cho một yêu cầu
    op.execute("CREATE UNIQUE INDEX withdrawals_user_idem ON withdrawals(user_id, idem_key) WHERE idem_key IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX withdrawals_provider_ref_uniq ON withdrawals(provider_ref) WHERE provider_ref IS NOT NULL")
    op.execute("CREATE INDEX withdrawals_status_idx ON withdrawals(status, created_at)")
    op.execute("""
        ALTER TABLE bank_accounts
          ADD COLUMN key_id text NOT NULL DEFAULT 'k1',
          ADD COLUMN last4 text NOT NULL DEFAULT '0000',
          ADD COLUMN created_at timestamptz NOT NULL DEFAULT now(),
          ADD COLUMN usable_from timestamptz NOT NULL DEFAULT now(),
          ADD COLUMN deactivated_at timestamptz""")
    op.execute("ALTER TABLE bank_accounts ALTER COLUMN key_id DROP DEFAULT, ALTER COLUMN last4 DROP DEFAULT")
    op.execute("ALTER TABLE bank_accounts ADD CONSTRAINT bank_accounts_last4_fmt CHECK (last4 ~ '^[0-9]{4}$')")
    op.execute("CREATE INDEX bank_accounts_user_idx ON bank_accounts(user_id)")
    # Đổi tài khoản = tạo dòng mới. Chỉ được đổi bản mã/key_id (đổi khóa) và deactivated_at.
    op.execute("""
        CREATE FUNCTION bank_accounts_guard() RETURNS trigger AS $$
        BEGIN
          IF NEW.user_id <> OLD.user_id OR NEW.bank_code <> OLD.bank_code OR NEW.account_name <> OLD.account_name
             OR NEW.last4 <> OLD.last4 OR NEW.usable_from <> OLD.usable_from OR NEW.created_at <> OLD.created_at THEN
            RAISE EXCEPTION 'bank_accounts: đổi tài khoản = tạo dòng mới, không sửa dòng cũ';
          END IF;
          RETURN NEW;
        END $$ LANGUAGE plpgsql""")
    op.execute("CREATE TRIGGER bank_accounts_no_edit BEFORE UPDATE ON bank_accounts FOR EACH ROW EXECUTE FUNCTION bank_accounts_guard()")
    # TRUNCATE không kích hoạt trigger mức dòng: cần trigger mức câu lệnh riêng
    op.execute("""
        CREATE TRIGGER audit_logs_no_truncate BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_immutable()""")
    op.execute("""
        CREATE TRIGGER wallet_entries_no_truncate BEFORE TRUNCATE ON wallet_entries
        FOR EACH STATEMENT EXECUTE FUNCTION wallet_entries_immutable()""")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cashback_app') THEN
            REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs, wallet_entries FROM cashback_app;
          END IF;
        END $$""")


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS wallet_entries_no_truncate ON wallet_entries")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS bank_accounts_no_edit ON bank_accounts")
    op.execute("DROP FUNCTION IF EXISTS bank_accounts_guard()")
    op.execute("DROP INDEX IF EXISTS bank_accounts_user_idx")
    op.execute("""
        ALTER TABLE bank_accounts DROP CONSTRAINT bank_accounts_last4_fmt,
          DROP COLUMN deactivated_at, DROP COLUMN usable_from, DROP COLUMN created_at,
          DROP COLUMN last4, DROP COLUMN key_id""")
    op.execute("DROP INDEX IF EXISTS withdrawals_status_idx")
    op.execute("DROP INDEX IF EXISTS withdrawals_provider_ref_uniq")
    op.execute("DROP INDEX IF EXISTS withdrawals_user_idem")
    op.execute("""
        ALTER TABLE withdrawals DROP CONSTRAINT withdrawals_paid_has_ref,
          DROP COLUMN decided_reason, DROP COLUMN paid_at, DROP COLUMN paid_by,
          DROP COLUMN approved_at, DROP COLUMN approved_by, DROP COLUMN idem_key""")
