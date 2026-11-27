"""index cho khóa ngoại và cột lọc hay dùng (audit #24, #28)

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"

INDEXES = [
    ("clicks_sub_id_idx", "clicks(sub_id)"),
    ("clicks_created_idx", "clicks(created_at)"),
    ("links_product_idx", "links(product_id)"),
    ("posts_product_idx", "posts(product_id)"),
    ("shopee_orders_click_idx", "shopee_orders(click_id)"),
    ("shopee_orders_post_idx", "shopee_orders(post_id)"),
    ("shopee_orders_status_idx", "shopee_orders(status)"),
    ("wallet_entries_order_idx", "wallet_entries(order_id)"),
    ("wallet_entries_withdrawal_idx", "wallet_entries(withdrawal_id)"),
]


def upgrade():
    for name, target in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")


def downgrade():
    for name, _ in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
