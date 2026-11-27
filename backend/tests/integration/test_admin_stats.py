"""T-043 (backend): tổng quan, danh sách user/đơn, khóa/mở user. Admin + TOTP, chỉ-đọc trừ đổi trạng thái (có audit)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main_api import create_app
from app.modules.audit.service import Actor, AuditContext
from app.modules.auth.service import AuthService
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
PW = "mat-khau-hop-le-1"


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text("ALTER TABLE wallet_entries DISABLE TRIGGER wallet_entries_no_change"))
        c.execute(text(f"DELETE FROM wallet_entries WHERE user_id IN {users}"))
        c.execute(text("ALTER TABLE wallet_entries ENABLE TRIGGER wallet_entries_no_change"))
        c.execute(text(f"DELETE FROM wallets WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM shopee_orders WHERE order_sn LIKE 'ITEST-S-%'"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
    eng.dispose()


@pytest.fixture
def settings(make_settings):
    return make_settings(database_url=DB_URL, jwt_secret="j" * 40, ip_salt="i" * 24, admin_mfa_required=False)


@pytest.fixture
def api(settings, pg):
    return TestClient(create_app(settings, engine=pg), raise_server_exceptions=False)


def user(api, pg, role="member", tag=""):
    email = f"itest-{tag}{uuid.uuid4().hex[:8]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    with pg.begin() as c:
        c.execute(text("UPDATE users SET role = :r WHERE id = :i"), {"r": role, "i": uid})
    tok = api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()
    return uid, email, {"Authorization": f"Bearer {tok['access_token']}"}, tok["refresh_token"]


def test_admin_endpoints_are_admin_only(api, pg):
    _, _, mh, _ = user(api, pg)
    _, _, sh, _ = user(api, pg, "staff")
    uid, *_ = user(api, pg)
    for hh, code in ((mh, 403), (sh, 403), ({}, 401)):
        for url in ("/api/v1/admin/overview", "/api/v1/admin/users", "/api/v1/admin/orders"):
            assert api.get(url, headers=hh).status_code == code, url
        assert api.patch(f"/api/v1/admin/users/{uid}", headers=hh, json={"status": "locked", "reason": "abc"}).status_code == code


def test_overview_counts_money_as_integers(api, pg):
    _, _, ah, _ = user(api, pg, "admin")
    u, *_ = user(api, pg)
    with pg.begin() as c:
        c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, commission_micro, user_id) VALUES "
                       "('ITEST-S-1', 'PENDING', 'user', 4037500000, :u), ('ITEST-S-2', 'PENDING', 'unknown', 1000, NULL)"), {"u": u})
        c.execute(text("INSERT INTO wallets(user_id, pending_vnd, available_vnd, held_vnd) VALUES (:u, 24225, 100, 7)"), {"u": u})
    before = api.get("/api/v1/admin/overview?days=30", headers=ah).json()
    assert before["days"] == 30 and before["users"]["total"] >= 3 and before["users"]["new"] >= 3
    assert before["orders"]["PENDING"]["count"] >= 2 and before["orders"]["PENDING"]["commission_micro"] >= 4037501000
    assert all(isinstance(v, int) for v in before["wallet_totals_vnd"].values())
    assert before["wallet_totals_vnd"]["pending"] >= 24225 and before["wallet_totals_vnd"]["held"] >= 7
    assert before["orphans_open"] >= 0 and isinstance(before["clicks"], int)
    assert api.get("/api/v1/admin/overview?days=0", headers=ah).status_code == 422
    assert api.get("/api/v1/admin/overview?days=366", headers=ah).status_code == 422


def test_users_search_is_literal_and_never_returns_password_hashes(api, pg):
    _, _, ah, _ = user(api, pg, "admin")
    uid, email, _, _ = user(api, pg, tag="zq")
    r = api.get("/api/v1/admin/users", params={"q": "ITEST-ZQ"}, headers=ah)
    assert r.status_code == 200 and [x["id"] for x in r.json()] == [uid]
    assert "password" not in r.text and set(r.json()[0]) == {"id", "email", "role", "status", "created_at", "available_vnd", "pending_vnd", "held_vnd"}
    for wild in ("%", "_", "%%", "\\"):                                                # ký tự đại diện LIKE không được hiểu là wildcard
        assert api.get("/api/v1/admin/users", params={"q": wild}, headers=ah).json() == []
    assert api.get("/api/v1/admin/users", params={"limit": 0}, headers=ah).status_code == 422


def test_orders_filters_and_validation(api, pg):
    _, _, ah, _ = user(api, pg, "admin")
    with pg.begin() as c:
        c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, commission_micro) VALUES "
                       "('ITEST-S-A', 'COMPLETED', 'unknown', 1), ('ITEST-S-B', 'PENDING', 'unknown', 1)"))
    ids = lambda **p: [x["order_sn"] for x in api.get("/api/v1/admin/orders", params={"limit": 100, **p}, headers=ah).json()]   # noqa: E731
    assert "ITEST-S-A" in ids(status="COMPLETED") and "ITEST-S-B" not in ids(status="COMPLETED")
    assert "ITEST-S-B" in ids(status="PENDING", source="unknown") and "ITEST-S-A" not in ids(status="PENDING")
    assert api.get("/api/v1/admin/orders", params={"status": "x'; DROP TABLE users;--"}, headers=ah).status_code == 422
    assert api.get("/api/v1/admin/orders", params={"source": "nope"}, headers=ah).status_code == 422


def test_lock_kills_sessions_immediately_and_unlock_restores_login(api, pg):
    aid, _, ah, _ = user(api, pg, "admin")
    uid, email, uh, refresh = user(api, pg)
    assert api.get("/api/v1/auth/me", headers=uh).status_code == 200
    assert api.patch(f"/api/v1/admin/users/{uid}", headers=ah, json={"status": "locked", "reason": "nghi ngờ gian lận"}).status_code == 204
    assert api.get("/api/v1/auth/me", headers=uh).status_code == 401                              # access token vô hiệu NGAY
    assert api.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401    # refresh token đã xóa
    login = api.post("/api/v1/auth/login", json={"email": email, "password": PW})
    assert login.status_code == 403 and login.json()["error"]["code"] == "account_locked"
    assert api.patch(f"/api/v1/admin/users/{uid}", headers=ah, json={"status": "active", "reason": "đã xác minh"}).status_code == 204
    assert api.post("/api/v1/auth/login", json={"email": email, "password": PW}).status_code == 200
    assert api.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401    # phiên cũ KHÔNG hồi sinh sau khi mở khóa
    with pg.connect() as c:
        rows = c.execute(text("SELECT actor_id, actor_role, detail FROM audit_logs WHERE action = 'users.set_status' AND target_id = :t ORDER BY id"), {"t": str(uid)}).mappings().all()
    assert [(r["actor_id"], r["actor_role"], r["detail"]["from"], r["detail"]["to"]) for r in rows] == [(aid, "admin", "active", "locked"), (aid, "admin", "locked", "active")]
    assert rows[0]["detail"]["reason"] == "nghi ngờ gian lận"


def test_cannot_lock_self_or_another_admin_or_unknown_and_input_is_validated(api, pg):
    aid, _, ah, _ = user(api, pg, "admin")
    other, *_ = user(api, pg, "admin")
    body = {"status": "locked", "reason": "thử"}
    assert api.patch(f"/api/v1/admin/users/{aid}", headers=ah, json=body).json()["error"]["code"] == "invalid_target"
    assert api.patch(f"/api/v1/admin/users/{other}", headers=ah, json=body).json()["error"]["code"] == "invalid_target"
    with pg.connect() as c:
        assert c.execute(text("SELECT status FROM users WHERE id = :i"), {"i": other}).scalar_one() == "active"     # đã rollback
    assert api.patch("/api/v1/admin/users/999999999", headers=ah, json=body).json()["error"]["code"] == "user_not_found"
    uid, *_ = user(api, pg)
    for bad in ({"status": "admin", "reason": "abc"}, {"status": "locked", "reason": "x"}, {"status": "locked"}, {"reason": "abc"}):
        assert api.patch(f"/api/v1/admin/users/{uid}", headers=ah, json=bad).status_code == 422, bad


def test_service_layer_refuses_non_admin_and_missing_audit(settings, pg, api):
    from app.core.errors import Forbidden
    from app.modules.audit.errors import InvalidAudit
    uid, *_ = user(api, pg)
    for role in ("staff", "user", "system"):
        with pytest.raises(Forbidden):
            AuthService(settings, pg).set_user_status(uid, "locked", "lý do", audit=AuditContext(settings, Actor(9, role), None))
    with pytest.raises(InvalidAudit):
        AuthService(settings, pg).set_user_status(uid, "locked", "lý do", audit=None)
    from app.core.errors import AppError
    with pytest.raises(AppError) as e:
        AuthService(settings, pg).set_user_status(uid, "admin", "lý do", audit=AuditContext(settings, Actor(9, "admin"), None))
    assert e.value.code == "invalid_status"
    assert AuthService.set_user_status.__audited__ is True


def test_adminstats_repository_is_read_only():
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "app" / "modules" / "adminstats" / "repository.py").read_text()
    assert not re.search(r"(?i)\b(insert\s+into|update\s+\w+\s+set|delete\s+from|truncate|drop\s+table|alter\s+table)\b", src)
