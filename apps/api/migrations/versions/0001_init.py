"""init schema theo docs/07-du-lieu.md

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None

TABLES = [
    "rate_limits", "audit_logs", "fraud_flags", "settings", "sync_runs", "shopee_sessions",
    "claims", "wallet_entries", "withdrawals", "bank_accounts", "wallets", "orphan_orders",
    "shopee_order_items", "shopee_orders", "posts", "agent_keys", "clicks", "links",
    "products", "users",
]

UP = """
CREATE TABLE users (
  id bigserial PRIMARY KEY,
  email text NOT NULL UNIQUE CHECK (email = lower(email)),
  password_hash text NOT NULL,
  role text NOT NULL DEFAULT 'member' CHECK (role IN ('member','staff','admin')),
  status text NOT NULL DEFAULT 'unverified' CHECK (status IN ('unverified','active','locked')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE products (
  id bigserial PRIMARY KEY,
  shop_id bigint NOT NULL,
  item_id bigint NOT NULL,
  name text,
  category text,
  comm_rate_pct numeric(6,2),
  UNIQUE (shop_id, item_id)
);
CREATE TABLE links (
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id),
  product_id bigint NOT NULL REFERENCES products(id),
  code text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, product_id)
);
CREATE TABLE clicks (
  id bigserial PRIMARY KEY,
  link_id bigint NOT NULL REFERENCES links(id),
  sub_id text NOT NULL,
  ip_hash text,
  ua_hash text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX clicks_link_idx ON clicks(link_id);
CREATE TABLE agent_keys (
  id bigserial PRIMARY KEY,
  name text NOT NULL,
  key_hash text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);
CREATE TABLE posts (
  id bigserial PRIMARY KEY,
  post_key text NOT NULL UNIQUE,
  product_id bigint REFERENCES products(id),
  agent_key_id bigint REFERENCES agent_keys(id),
  page_code text,
  category text,
  sub_id text,
  issued_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE shopee_orders (
  id bigserial PRIMARY KEY,
  order_sn text NOT NULL UNIQUE,
  raw_status text,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','COMPLETED','CANCELLED','RETURNED')),
  utm_content text,
  source_type text NOT NULL DEFAULT 'unknown' CHECK (source_type IN ('user','post','legacy','unknown')),
  user_id bigint REFERENCES users(id),
  click_id bigint REFERENCES clicks(id),
  post_id bigint REFERENCES posts(id),
  commission_micro bigint NOT NULL DEFAULT 0 CHECK (commission_micro >= 0),
  purchase_time timestamptz,
  completed_at timestamptz,
  raw jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX shopee_orders_user_idx ON shopee_orders(user_id);
CREATE TABLE shopee_order_items (
  id bigserial PRIMARY KEY,
  order_id bigint NOT NULL REFERENCES shopee_orders(id) ON DELETE CASCADE,
  item_id bigint,
  shop_id bigint,
  qty int NOT NULL DEFAULT 1,
  price_micro bigint NOT NULL DEFAULT 0,
  commission_micro bigint NOT NULL DEFAULT 0,
  platform_rate_bp int,
  brand_rate_bp int,
  category_lv1 text
);
CREATE TABLE orphan_orders (
  order_id bigint PRIMARY KEY REFERENCES shopee_orders(id),
  reason text NOT NULL,
  assigned_to_user bigint REFERENCES users(id),
  assigned_by bigint REFERENCES users(id)
);
CREATE TABLE wallets (
  user_id bigint PRIMARY KEY REFERENCES users(id),
  pending_vnd bigint NOT NULL DEFAULT 0 CHECK (pending_vnd >= 0),
  available_vnd bigint NOT NULL DEFAULT 0 CHECK (available_vnd >= 0),
  held_vnd bigint NOT NULL DEFAULT 0 CHECK (held_vnd >= 0)
);
CREATE TABLE bank_accounts (
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id),
  bank_code text NOT NULL,
  account_no_enc text NOT NULL,
  account_name text NOT NULL
);
CREATE TABLE withdrawals (
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id),
  amount_vnd bigint NOT NULL CHECK (amount_vnd > 0),
  status text NOT NULL DEFAULT 'requested'
    CHECK (status IN ('requested','approved','rejected','processing','paid','failed')),
  provider text NOT NULL DEFAULT 'manual',
  provider_ref text,
  bank_account_id bigint REFERENCES bank_accounts(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- Chỉ một yêu cầu rút "đang mở" cho mỗi user
CREATE UNIQUE INDEX withdrawals_one_open ON withdrawals(user_id)
  WHERE status IN ('requested','approved','processing');
CREATE TABLE wallet_entries (
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id),
  order_id bigint REFERENCES shopee_orders(id),
  withdrawal_id bigint REFERENCES withdrawals(id),
  kind text NOT NULL CHECK (kind IN
    ('accrual','release','cancel','reverse','hold','payout','refund_hold','adjust')),
  state text NOT NULL CHECK (state IN
    ('pending','available','cancelled','reversed','held','paid_out')),
  amount_vnd bigint NOT NULL CHECK (amount_vnd >= 0),
  share_bp int CHECK (share_bp BETWEEN 0 AND 10000),
  idem_key text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX wallet_entries_user_state_idx ON wallet_entries(user_id, state);
-- Sổ cái chỉ thêm: cấm sửa/xóa
CREATE FUNCTION wallet_entries_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'wallet_entries là sổ cái chỉ thêm, không được % ', TG_OP;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER wallet_entries_no_change BEFORE UPDATE OR DELETE ON wallet_entries
  FOR EACH ROW EXECUTE FUNCTION wallet_entries_immutable();
CREATE TABLE claims (
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id),
  order_sn text,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','rejected')),
  note text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE shopee_sessions (
  id bigserial PRIMARY KEY,
  cookie_enc text,
  status text NOT NULL DEFAULT 'unknown'
    CHECK (status IN ('unknown','healthy','degraded','expired','blocked')),
  last_ok_at timestamptz,
  failure_count int NOT NULL DEFAULT 0
);
CREATE TABLE sync_runs (
  id bigserial PRIMARY KEY,
  kind text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  result text CHECK (result IN ('ok','partial','failed')),
  rows int NOT NULL DEFAULT 0
);
CREATE TABLE settings (
  id bigserial PRIMARY KEY,
  key text NOT NULL,
  value jsonb NOT NULL,
  effective_from timestamptz NOT NULL DEFAULT now(),
  UNIQUE (key, effective_from)
);
CREATE TABLE fraud_flags (
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id),
  rule text NOT NULL,
  score int NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','dismissed','confirmed')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE audit_logs (
  id bigserial PRIMARY KEY,
  actor_id bigint,
  action text NOT NULL,
  target text,
  detail jsonb,
  at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE rate_limits (
  key text PRIMARY KEY,
  count int NOT NULL DEFAULT 0,
  window_start timestamptz NOT NULL DEFAULT now()
);
"""


def upgrade():
    op.execute(UP)


def downgrade():
    for t in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS wallet_entries_immutable() CASCADE")
