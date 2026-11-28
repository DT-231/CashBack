"""shopee_sessions.last_alert_at: nhắc lại cảnh báo cookie chết theo chu kỳ (T-023)

Revision ID: 0008
Revises: 0007
"""
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade():
    op.execute("ALTER TABLE shopee_sessions ADD COLUMN last_alert_at timestamptz")


def downgrade():
    op.execute("ALTER TABLE shopee_sessions DROP COLUMN IF EXISTS last_alert_at")
