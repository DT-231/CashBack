"""email_tokens: token một lần cho xác minh email và đặt lại mật khẩu (T-011). Chỉ lưu SHA-256 của token.

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade():
    op.execute("""
        CREATE TABLE email_tokens (
          id bigserial PRIMARY KEY,
          user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          purpose text NOT NULL CHECK (purpose IN ('verify', 'reset')),
          token_hash text NOT NULL UNIQUE,
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        )""")
    op.execute("CREATE INDEX email_tokens_user_idx ON email_tokens(user_id, purpose)")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cashback_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON email_tokens TO cashback_app;
            GRANT USAGE, SELECT ON SEQUENCE email_tokens_id_seq TO cashback_app;
          END IF;
        END $$""")


def downgrade():
    op.execute("DROP TABLE IF EXISTS email_tokens")
