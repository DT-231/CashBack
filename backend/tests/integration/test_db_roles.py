"""Quyền DB cho ứng dụng: sổ cái và audit_logs chỉ thêm/đọc kể cả với TRUNCATE; role ứng dụng không tắt được trigger.
Dựng role tạm từ CHÍNH script `infra/db/app-role.sql` (nguồn duy nhất), trên database tạm."""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

from tests.integration.pg import DB_URL, pg_available

BACKEND = Path(__file__).resolve().parents[2]
SQL = BACKEND.parent / "infra" / "db" / "app-role.sql"
pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")


@pytest.fixture
def scratch():
    tag = uuid.uuid4().hex[:8]
    db, role, pw = f"roletest_{tag}", f"itest_app_{tag}", "pw-" + uuid.uuid4().hex
    admin = create_engine(DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{db}"'))
    owner_url = make_url(DB_URL).set(database=db).render_as_string(hide_password=False)
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=dict(os.environ, DATABASE_URL=owner_url),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]
    owner = create_engine(owner_url, isolation_level="AUTOCOMMIT")
    sql = SQL.read_text().replace(':"app_role"', f'"{role}"').replace(":'app_password'", f"'{pw}'")
    body = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))   # bỏ chú thích (có thể chứa dấu ;)
    with owner.connect() as c:
        for stmt in [x.strip() for x in body.split(";") if x.strip()]:
            c.execute(text(stmt))
    app = create_engine(make_url(owner_url).set(username=role, password=pw).render_as_string(hide_password=False), isolation_level="AUTOCOMMIT")
    yield owner, app
    owner.dispose()
    app.dispose()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)'))
        c.execute(text(f'DROP ROLE IF EXISTS "{role}"'))


def test_truncate_is_blocked_even_for_the_owner(scratch):
    owner, _ = scratch
    for table in ("audit_logs", "wallet_entries"):
        with pytest.raises(DBAPIError, match="chỉ được|không được"):
            with owner.connect() as c:
                c.execute(text(f"TRUNCATE {table}"))


def test_app_role_cannot_modify_ledger_or_audit_or_disable_triggers(scratch):
    owner, app = scratch
    with owner.connect() as c:
        c.execute(text("INSERT INTO users(email, password_hash, status) VALUES ('r@example.test', 'x', 'active')"))
        uid = c.execute(text("SELECT id FROM users WHERE email = 'r@example.test'")).scalar_one()
        c.execute(text("INSERT INTO wallets(user_id) VALUES (:u)"), {"u": uid})
    with app.connect() as c:
        c.execute(text("INSERT INTO audit_logs(action, actor_role) VALUES ('t.insert', 'system')"))        # thêm được
        assert c.execute(text("SELECT count(*) FROM audit_logs")).scalar_one() == 1                         # đọc được
        c.execute(text("INSERT INTO wallet_entries(user_id, kind, state, amount_vnd, idem_key) VALUES (:u, 'accrual', 'pending', 5, 'k-1')"), {"u": uid})
    denied = [
        "UPDATE audit_logs SET action = 'x.y'", "DELETE FROM audit_logs", "TRUNCATE audit_logs",
        "UPDATE wallet_entries SET amount_vnd = 1", "DELETE FROM wallet_entries", "TRUNCATE wallet_entries",
        "ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_change", "ALTER TABLE wallet_entries DISABLE TRIGGER ALL",
        "DROP TRIGGER audit_logs_no_change ON audit_logs", "DROP TABLE audit_logs", "DELETE FROM users",
        "TRUNCATE rate_limits", "DROP TABLE alembic_version",
    ]
    for sql in denied:
        with pytest.raises((ProgrammingError, DBAPIError), match="permission denied|must be owner"):
            with app.connect() as c:
                c.execute(text(sql))
    with owner.connect() as c:
        assert c.execute(text("SELECT count(*) FROM audit_logs")).scalar_one() == 1
        assert c.execute(text("SELECT count(*) FROM wallet_entries")).scalar_one() == 1


def test_app_role_can_do_the_normal_work(scratch):
    _, app = scratch
    with app.connect() as c:
        c.execute(text("INSERT INTO users(email, password_hash, status) VALUES ('w@example.test', 'x', 'active')"))
        c.execute(text("UPDATE users SET status = 'locked' WHERE email = 'w@example.test'"))
        c.execute(text("INSERT INTO rate_limits(key, count) VALUES ('k', 1)"))
        c.execute(text("DELETE FROM rate_limits WHERE key = 'k'"))
        c.execute(text("INSERT INTO settings(key, value, effective_from) VALUES ('hold_days', '7'::jsonb, now()) ON CONFLICT DO NOTHING"))
