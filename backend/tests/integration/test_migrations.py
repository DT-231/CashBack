"""Migration hai chiều trên một database tạm (không đụng DB dev): up -> down -> up."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.integration.pg import DB_URL, pg_available

BACKEND = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")


@pytest.fixture
def scratch_url():
    name = "migtest_" + uuid.uuid4().hex[:8]
    admin = create_engine(DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    yield make_url(DB_URL).set(database=name).render_as_string(hide_password=False)
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def alembic(url, *args):
    env = dict(os.environ, DATABASE_URL=url)
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]


def names(url, kind):
    q = {"index": "SELECT indexname FROM pg_indexes WHERE schemaname='public'",
         "table": "SELECT tablename FROM pg_tables WHERE schemaname='public'"}[kind]
    with create_engine(url).connect() as c:
        return {r[0] for r in c.execute(text(q))}


def test_up_down_up(scratch_url):
    alembic(scratch_url, "upgrade", "head")
    assert "clicks_sub_id_idx" in names(scratch_url, "index") and "wallets" in names(scratch_url, "table")
    assert "refresh_tokens" in names(scratch_url, "table")
    cols = lambda: {r[0] for r in create_engine(scratch_url).connect().execute(text(  # noqa: E731
        "SELECT column_name FROM information_schema.columns WHERE table_name='audit_logs'"))}
    colsof = lambda t: {r[0] for r in create_engine(scratch_url).connect().execute(text(  # noqa: E731
        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": t})}
    bank_cols, wd_cols = (lambda: colsof("bank_accounts")), (lambda: colsof("withdrawals"))
    assert {"actor_role", "target_type", "target_id", "ip_hash", "request_id"} <= cols() and "target" not in cols()
    assert "key_id" in bank_cols() and "idem_key" in wd_cols()
    assert {"user_mfa", "mfa_recovery_codes"} <= names(scratch_url, "table") and "mfa_at" in colsof("refresh_tokens")
    assert {"key_id", "updated_by"} <= colsof("shopee_sessions")
    alembic(scratch_url, "downgrade", "0006")
    assert not {"key_id", "updated_by"} & colsof("shopee_sessions")
    alembic(scratch_url, "upgrade", "head")
    alembic(scratch_url, "downgrade", "0005")
    assert not {"user_mfa", "mfa_recovery_codes"} & names(scratch_url, "table") and "mfa_at" not in colsof("refresh_tokens")
    alembic(scratch_url, "upgrade", "head")
    alembic(scratch_url, "downgrade", "0004")
    assert "key_id" not in bank_cols() and "idem_key" not in wd_cols() and "withdrawals_user_idem" not in names(scratch_url, "index")
    alembic(scratch_url, "downgrade", "0003")
    assert "target" in cols() and "ip_hash" not in cols()
    alembic(scratch_url, "upgrade", "head")
    alembic(scratch_url, "downgrade", "0002")
    assert "refresh_tokens" not in names(scratch_url, "table")
    alembic(scratch_url, "downgrade", "0001")
    assert "clicks_sub_id_idx" not in names(scratch_url, "index") and "wallets" in names(scratch_url, "table")
    alembic(scratch_url, "downgrade", "base")
    assert "wallets" not in names(scratch_url, "table")
    alembic(scratch_url, "upgrade", "head")
    assert "shopee_orders_status_idx" in names(scratch_url, "index")
