"""refresh_tokens: access + refresh token dùng chung cho web và app mobile (T-010)

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.execute("""
        CREATE TABLE refresh_tokens (
          id bigserial PRIMARY KEY,
          user_id bigint NOT NULL REFERENCES users(id),
          token_hash text NOT NULL UNIQUE,
          expires_at timestamptz NOT NULL,
          revoked_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        )""")
    op.execute("CREATE INDEX refresh_tokens_user_idx ON refresh_tokens(user_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS refresh_tokens")
