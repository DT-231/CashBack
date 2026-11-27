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


# ---------- T-040b: khởi động từ chối nếu user DB là superuser / chủ bảng ----------
def test_startup_guard_rejects_owner_and_superuser_but_accepts_the_app_role(scratch):
    from app.core.config import ConfigError
    from app.core.db import assert_least_privilege

    owner, app = scratch
    with pytest.raises(ConfigError, match="superuser|chủ sở hữu"):
        assert_least_privilege(owner)
    assert_least_privilege(app)                       # role ứng dụng (từ app-role.sql): được chạy


def test_startup_guard_rejects_a_role_that_inherits_from_the_owner(scratch):
    from app.core.config import ConfigError
    from app.core.db import assert_least_privilege

    owner, app = scratch
    with owner.connect() as c:
        owner_role = c.execute(text("SELECT tableowner FROM pg_tables WHERE tablename = 'audit_logs'")).scalar_one()
        role = c.execute(text("SELECT current_user")).scalar_one()
        assert owner_role == role                      # trong DB tạm, người tạo là chủ bảng
        c.execute(text('CREATE ROLE "itest_member_of_owner" LOGIN INHERIT PASSWORD \'pw-member\' NOSUPERUSER'))
        c.execute(text(f'GRANT "{owner_role}" TO "itest_member_of_owner"'))
        c.execute(text('GRANT USAGE ON SCHEMA public TO "itest_member_of_owner"'))
    try:
        url = app.url.set(username="itest_member_of_owner", password="pw-member")
        member = create_engine(url.render_as_string(hide_password=False))
        with pytest.raises(ConfigError, match="chủ sở hữu"):
            assert_least_privilege(member)
        member.dispose()
    finally:
        with owner.connect() as c:
            c.execute(text('DROP OWNED BY "itest_member_of_owner"'))       # thu hồi quyền trong DB tạm trước khi xóa role
            c.execute(text('DROP ROLE IF EXISTS "itest_member_of_owner"'))


def test_startup_guard_reports_missing_tables(scratch):
    from app.core.config import ConfigError
    from app.core.db import assert_least_privilege

    _, app = scratch
    with pytest.raises(ConfigError, match="không thấy bảng"):
        import app.core.db as dbmod  # noqa: F401
        original = dbmod.IMMUTABLE_TABLES
        dbmod.IMMUTABLE_TABLES = ("audit_logs", "bang_khong_ton_tai")
        try:
            assert_least_privilege(app)
        finally:
            dbmod.IMMUTABLE_TABLES = original
