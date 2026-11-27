"""audit_logs trên Postgres thật: ghi đúng, chỉ-thêm, IP chỉ ở dạng băm, không lộ bí mật, ghi cùng transaction."""
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.clientip import keyed_hash
from app.main_api import create_app
from app.modules.audit import repository
from app.modules.audit.errors import InvalidAudit
from app.modules.audit.service import SYSTEM, Actor, AuditContext, record, record_best_effort
from app.modules.platform_settings.service import PlatformSettings
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
SALT = "audit-itest-salt-0123456789"
IP = "198.51.100.77"
TAG = "itest-audit-"


@pytest.fixture
def eng():
    e = create_engine(DB_URL)
    yield e
    e.dispose()


@pytest.fixture
def settings(make_settings):
    return make_settings(ip_salt=SALT)


def rows(eng, action):
    with eng.connect() as c:
        return c.execute(text("SELECT * FROM audit_logs WHERE action = :a ORDER BY id"), {"a": action}).mappings().all()


def test_record_stores_who_what_target_when_and_hashed_ip(eng, settings):
    with eng.begin() as c:
        rid = record(c, settings, Actor(7, "admin"), "settings.set", target_type="setting", target_id="hold_days",
                     detail={"key": "hold_days", "value": 14}, ip=IP)
    r = [x for x in rows(eng, "settings.set") if x["id"] == rid][0]
    assert (r["actor_id"], r["actor_role"], r["target_type"], r["target_id"]) == (7, "admin", "setting", "hold_days")
    assert r["ip_hash"] == keyed_hash(settings, IP) and IP not in json.dumps(dict(r), default=str)
    assert abs((datetime.now(UTC) - r["at"]).total_seconds()) < 30


def test_without_ip_salt_no_ip_is_stored(eng, make_settings):
    with eng.begin() as c:
        rid = record(c, make_settings(), SYSTEM, "sync.finished", ip=IP)
    r = [x for x in rows(eng, "sync.finished") if x["id"] == rid][0]
    assert r["ip_hash"] is None and r["actor_id"] is None and r["actor_role"] == "system"


def test_rows_cannot_be_updated_or_deleted(eng, settings):
    with eng.begin() as c:
        rid = record(c, settings, Actor(1, "user"), "auth.register", target_type="user", target_id=1)
    for sql in ("UPDATE audit_logs SET action = 'x.y' WHERE id = :i", "DELETE FROM audit_logs WHERE id = :i"):
        with pytest.raises(DBAPIError, match="chỉ được thêm"):
            with eng.begin() as c:
                c.execute(text(sql), {"i": rid})
    assert len([x for x in rows(eng, "auth.register") if x["id"] == rid]) == 1


def test_secrets_in_detail_never_reach_the_table(eng, settings):
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4fwpMeJf36"
    with eng.begin() as c:
        rid = record(c, settings, Actor(2, "admin"), "withdrawal.approve", target_type="withdrawal", target_id=3, detail={
            "withdrawal_id": 3, "bank_account_id": 9, "amount_vnd": 150000, "password": "hunter2hunter2",
            "access_token": jwt, "cookie": "SPC_ST=abcdef", "bank_account_number": "0123456789012", "note": "STK 0123456789012"})
    r = [x for x in rows(eng, "withdrawal.approve") if x["id"] == rid][0]
    dump = json.dumps(r["detail"])
    for secret in ("hunter2", jwt, "SPC_ST", "0123456789012"):
        assert secret not in dump, secret
    assert r["detail"]["bank_account_id"] == 9 and r["detail"]["amount_vnd"] == 150000


def test_invalid_actions_and_roles_are_rejected(eng, settings):
    for bad in ("approve", "Settings.Set", "a.b.c", "x.", ""):
        with pytest.raises(InvalidAudit):
            with eng.begin() as c:
                record(c, settings, SYSTEM, bad)
    with pytest.raises(InvalidAudit):
        Actor(1, "root")
    with pytest.raises(IntegrityError):          # chặn cả ở DB, không chỉ ở service
        with eng.begin() as c:
            repository.insert(c, actor_id=1, actor_role="user", action="NOPE", target_type=None, target_id=None,
                              detail=None, ip_hash=None, request_id=None)
    with pytest.raises(IntegrityError):
        with eng.begin() as c:
            c.execute(text("INSERT INTO audit_logs (action, detail) VALUES ('a.b', '[1]'::jsonb)"))


def test_audit_is_written_in_the_same_transaction_as_the_action(eng, settings):
    ps = PlatformSettings(eng)
    ctx = AuditContext(settings, Actor(5, "admin"), IP)
    eff = datetime.now(UTC) + timedelta(days=3650, seconds=uuid.uuid4().int % 100000)
    eff2 = eff + timedelta(days=1)

    def count_setting(e):
        with eng.connect() as c:
            return c.execute(text("SELECT count(*) FROM settings WHERE key='hold_days' AND effective_from = :e"), {"e": e}).scalar_one()

    import app.modules.platform_settings.service as svc
    try:
        ps.set_int("hold_days", 9, effective_from=eff, audit_ctx=ctx)
        r = [x for x in rows(eng, "settings.set") if x["detail"].get("effective_from") == eff.isoformat()]
        assert len(r) == 1 and r[0]["actor_role"] == "admin" and r[0]["detail"]["value"] == 9 and count_setting(eff) == 1
        # lỗi khi ghi log => thao tác cũng hủy (không có cấu hình đổi mà không để lại dấu vết)
        before = len(rows(eng, "settings.set"))
        orig = svc.audit.record
        svc.audit.record = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("audit down"))
        try:
            with pytest.raises(RuntimeError):
                ps.set_int("hold_days", 10, effective_from=eff2, audit_ctx=ctx)
        finally:
            svc.audit.record = orig
        assert len(rows(eng, "settings.set")) == before and count_setting(eff2) == 0
    finally:
        with eng.begin() as c:        # `settings` không có trigger chặn xóa; không để lại mốc tương lai làm hỏng test khác
            c.execute(text("DELETE FROM settings WHERE key='hold_days' AND effective_from IN (:a, :b)"), {"a": eff, "b": eff2})


def test_best_effort_never_raises(eng, settings):
    record_best_effort(eng, settings, SYSTEM, "not-valid")                 # action sai: chỉ log, không ném
    broken = create_engine("postgresql+psycopg://x:y@127.0.0.1:1/none", connect_args={"connect_timeout": 1})
    record_best_effort(broken, settings, SYSTEM, "auth.register")          # DB hỏng: chỉ log, không ném


def test_register_and_logout_are_audited_via_api(make_settings):
    eng = create_engine(DB_URL)
    s = make_settings(database_url=DB_URL, jwt_secret="j" * 40, ip_salt=SALT, trust_proxy_headers=True)
    client = TestClient(create_app(s, engine=eng), raise_server_exceptions=False)
    email = f"{TAG}{uuid.uuid4().hex[:8]}@example.test"
    r = client.post("/api/v1/auth/register", headers={"cf-connecting-ip": IP}, json={"email": email, "password": "mat-khau-hop-le-1"})
    assert r.status_code == 201
    uid = r.json()["id"]
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "mat-khau-hop-le-1"}).json()
    assert client.post("/api/v1/auth/logout", headers={"authorization": f"Bearer {login['access_token']}", "cf-connecting-ip": IP}).status_code == 204
    logins = [x for x in rows(eng, "auth.login") if x["target_id"] == str(uid)]
    assert len(logins) == 1 and logins[0]["actor_id"] == uid and logins[0]["actor_role"] == "user" and logins[0]["ip_hash"] == keyed_hash(s, "testclient")
    bad = client.post("/api/v1/auth/login", json={"email": email, "password": "sai-mat-khau-1"})
    assert bad.status_code == 401 and len([x for x in rows(eng, "auth.login") if x["target_id"] == str(uid)]) == 1   # đăng nhập sai không ghi "auth.login"
    reg = [x for x in rows(eng, "auth.register") if x["target_id"] == str(uid)]
    out = [x for x in rows(eng, "auth.logout") if x["target_id"] == str(uid)]
    assert len(reg) == 1 and reg[0]["actor_id"] == uid and reg[0]["actor_role"] == "user" and reg[0]["ip_hash"] == keyed_hash(s, IP)
    assert len(out) == 1 and out[0]["actor_id"] == uid
    blob = json.dumps([dict(x) for x in reg + out + logins], default=str)
    assert email not in blob and "mat-khau" not in blob and IP not in blob and login["access_token"] not in blob
    with eng.begin() as c:
        c.execute(text("DELETE FROM refresh_tokens WHERE user_id = :u"), {"u": uid})
        c.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
    eng.dispose()
