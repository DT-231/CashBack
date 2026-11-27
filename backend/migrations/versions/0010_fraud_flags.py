"""fraud_flags: chi tiết, cập nhật, người xử lý, chống trùng cờ đang mở (T-053)

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade():
    op.execute("""
        ALTER TABLE fraud_flags
          ADD COLUMN detail jsonb,
          ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
          ADD COLUMN resolved_by bigint REFERENCES users(id),
          ADD COLUMN resolved_at timestamptz,
          ADD COLUMN resolution_note text,
          ADD CONSTRAINT fraud_flags_rule_fmt CHECK (rule ~ '^[a-z][a-z_]*$')""")
    # Mỗi (user, rule) chỉ có MỘT cờ đang mở: quét lại cập nhật chứ không tạo thêm
    op.execute("CREATE UNIQUE INDEX fraud_flags_open_uniq ON fraud_flags(user_id, rule) WHERE status = 'open'")
    op.execute("CREATE INDEX fraud_flags_status_idx ON fraud_flags(status, id)")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cashback_app') THEN
            GRANT SELECT, INSERT, UPDATE ON fraud_flags TO cashback_app;
            GRANT USAGE, SELECT ON SEQUENCE fraud_flags_id_seq TO cashback_app;
          END IF;
        END $$""")


def downgrade():
    op.execute("DROP INDEX IF EXISTS fraud_flags_status_idx")
    op.execute("DROP INDEX IF EXISTS fraud_flags_open_uniq")
    op.execute("""
        ALTER TABLE fraud_flags DROP CONSTRAINT fraud_flags_rule_fmt, DROP COLUMN resolution_note, DROP COLUMN resolved_at,
          DROP COLUMN resolved_by, DROP COLUMN updated_at, DROP COLUMN detail""")
