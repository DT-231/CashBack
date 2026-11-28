"""shopee_sessions: key_id của khóa mã hóa, ai/lúc nào đặt cookie (T-063)

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade():
    op.execute("ALTER TABLE shopee_sessions ADD COLUMN key_id text, ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(), "
               "ADD COLUMN updated_by bigint REFERENCES users(id)")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cashback_app') THEN
            GRANT SELECT, INSERT, UPDATE ON shopee_sessions TO cashback_app;
          END IF;
        END $$""")


def downgrade():
    op.execute("ALTER TABLE shopee_sessions DROP COLUMN IF EXISTS updated_by, DROP COLUMN IF EXISTS updated_at, DROP COLUMN IF EXISTS key_id")
