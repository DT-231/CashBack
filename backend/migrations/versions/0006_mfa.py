"""đăng nhập hai lớp TOTP cho admin (T-019): bí mật mã hóa, mã khôi phục băm dùng một lần, mfa_at trên refresh token

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade():
    op.execute("""
        CREATE TABLE user_mfa (
          user_id bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          secret_enc text NOT NULL,
          key_id text NOT NULL,
          enabled_at timestamptz,
          last_step bigint NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now()
        )""")
    op.execute("""
        CREATE TABLE mfa_recovery_codes (
          id bigserial PRIMARY KEY,
          user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          code_hash text NOT NULL,
          used_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (user_id, code_hash)
        )""")
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN mfa_at timestamptz")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cashback_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON user_mfa, mfa_recovery_codes TO cashback_app;
            GRANT USAGE, SELECT ON SEQUENCE mfa_recovery_codes_id_seq TO cashback_app;
          END IF;
        END $$""")


def downgrade():
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS mfa_at")
    op.execute("DROP TABLE IF EXISTS mfa_recovery_codes")
    op.execute("DROP TABLE IF EXISTS user_mfa")
