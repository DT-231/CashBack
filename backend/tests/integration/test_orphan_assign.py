"""T-044: admin gán tay đơn mồ côi cho user; ví tự ghi nhận ở lần chốt sau; chỉ admin; gán một lần; audit."""
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main_api import create_app
from app.modules.audit.service import Actor, AuditContext
from app.modules.orders.admin_service import OrphanAdmin
from app.modules.wallet.service import WalletService
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
PW = "mat-khau-hop-le-1"
COMMISSION = 4_037_500_000          # 40.375đ -> 60% = 24.225đ


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
        c.execute(text("DELETE FROM orphan_orders WHERE order_id IN (SELECT id FROM shopee_orders WHERE order_sn LIKE 'ITEST-O-%')"))
        c.execute(text("DELETE FROM shopee_orders WHERE order_sn LIKE 'ITEST-O-%'"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))


@pytest.fixture
def settings(make_settings):
    return make_settings(database_url=DB_URL, jwt_secret="j" * 40, ip_salt="i" * 24, admin_mfa_required=False)


@pytest.fixture
def api(settings, pg):
    return TestClient(create_app(settings, engine=pg), raise_server_exceptions=False)


def new_user(api, pg, role="member", status=None):
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    with pg.begin() as c:
        c.execute(text("UPDATE users SET role = :r, status = COALESCE(:s, status) WHERE id = :i"), {"r": role, "s": status, "i": uid})
    tok = api.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return uid, ({"Authorization": f"Bearer {tok.json()['access_token']}"} if tok.status_code == 200 else {})


def orphan(pg, reason="invalid_sub_id: chữ ký sai", user_id=None):
    with pg.begin() as c:
        oid = c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, commission_micro, user_id) "
                             "VALUES (:s, 'PENDING', 'unknown', :c, :u) RETURNING id"),
                        {"s": f"ITEST-O-{uuid.uuid4().hex[:8]}", "c": COMMISSION, "u": user_id}).scalar_one()
        c.execute(text("INSERT INTO orphan_orders(order_id, reason) VALUES (:i, :r)"), {"i": oid, "r": reason})
    return oid


def pending(pg, uid):
    with pg.connect() as c:
        r = c.execute(text("SELECT pending_vnd FROM wallets WHERE user_id = :u"), {"u": uid}).scalar_one_or_none()
    return r or 0


def test_admin_assigns_orphan_wallet_accrues_and_audit_is_written(api, pg, settings):
    aid, ah = new_user(api, pg, "admin")
    uid, _ = new_user(api, pg)
    oid = orphan(pg)
    listed = api.get("/api/v1/admin/orphans", headers=ah)
    assert listed.status_code == 200 and oid in [x["id"] for x in listed.json()]
    assert [x for x in listed.json() if x["id"] == oid][0]["commission_vnd"] == COMMISSION // 100_000
    r = api.post(f"/api/v1/admin/orphans/{oid}/assign", headers=ah, json={"user_id": uid, "reason": "khiếu nại có bằng chứng"})
    assert r.status_code == 204
    with pg.connect() as c:
        o = c.execute(text("SELECT user_id, source_type FROM shopee_orders WHERE id = :i"), {"i": oid}).one()
        oo = c.execute(text("SELECT assigned_to_user, assigned_by FROM orphan_orders WHERE order_id = :i"), {"i": oid}).one()
    assert tuple(o) == (uid, "user") and tuple(oo) == (uid, aid)
    assert oid not in [x["id"] for x in api.get("/api/v1/admin/orphans", headers=ah).json()]    # không còn trong hàng đợi
    assert pending(pg, uid) == 0
    WalletService(settings, pg).settle()
    assert pending(pg, uid) == 24_225                                                          # ví tự ghi nhận đúng 60%
    with pg.connect() as c:
        a = c.execute(text("SELECT actor_id, actor_role, detail FROM audit_logs WHERE action = 'orders.assign_orphan' AND target_id = :t"), {"t": str(oid)}).mappings().one()
    assert (a["actor_id"], a["actor_role"]) == (aid, "admin") and a["detail"]["user_id"] == uid and "khiếu nại" in a["detail"]["reason"]


def test_assignment_is_once_only_and_validated(api, pg):
    aid, ah = new_user(api, pg, "admin")
    uid, _ = new_user(api, pg)
    locked, _ = new_user(api, pg, status="locked")
    oid = orphan(pg)
    body = lambda u: {"user_id": u, "reason": "khiếu nại"}                                     # noqa: E731
    assert api.post(f"/api/v1/admin/orphans/{oid}/assign", headers=ah, json=body(aid)).json()["error"]["code"] == "invalid_assignee"      # tự gán
    assert api.post(f"/api/v1/admin/orphans/{oid}/assign", headers=ah, json=body(locked)).json()["error"]["code"] == "invalid_assignee"  # user bị khóa
    assert api.post(f"/api/v1/admin/orphans/{oid}/assign", headers=ah, json=body(99999999)).json()["error"]["code"] == "invalid_assignee"
    assert api.post(f"/api/v1/admin/orphans/{oid}/assign", headers=ah, json={"user_id": uid, "reason": "x"}).status_code == 422             # lý do quá ngắn
    assert api.post("/api/v1/admin/orphans/999999999/assign", headers=ah, json=body(uid)).json()["error"]["code"] == "order_not_found"
    assert api.post(f"/api/v1/admin/orphans/{oid}/assign", headers=ah, json=body(uid)).status_code == 204
    again = api.post(f"/api/v1/admin/orphans/{oid}/assign", headers=ah, json=body(new_user(api, pg)[0]))
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_an_orphan"      # không gán lại / không chiếm đơn người khác
    owned = orphan(pg, user_id=uid)                                                            # đơn đã có chủ (dòng orphan cũ) không gán lại
    assert api.post(f"/api/v1/admin/orphans/{owned}/assign", headers=ah, json=body(new_user(api, pg)[0])).status_code == 409


def test_only_admin_can_list_or_assign(api, pg):
    uid, mh = new_user(api, pg)
    _, sh = new_user(api, pg, "staff")
    oid = orphan(pg)
    for hh, code in ((mh, 403), (sh, 403), ({}, 401)):
        assert api.get("/api/v1/admin/orphans", headers=hh).status_code == code
        assert api.post(f"/api/v1/admin/orphans/{oid}/assign", headers=hh, json={"user_id": uid, "reason": "khiếu nại"}).status_code == code
    with pg.connect() as c:
        assert c.execute(text("SELECT user_id FROM shopee_orders WHERE id = :i"), {"i": oid}).scalar_one() is None


def test_service_layer_refuses_non_admin_and_missing_audit(settings, pg, api):
    from app.core.errors import Forbidden
    from app.modules.audit.errors import InvalidAudit
    uid, _ = new_user(api, pg)
    oid = orphan(pg)
    for role in ("staff", "user", "system"):
        with pytest.raises(Forbidden):
            OrphanAdmin(settings, pg).assign(oid, uid, "khiếu nại", audit=AuditContext(settings, Actor(999, role), None))
    with pytest.raises(InvalidAudit):
        OrphanAdmin(settings, pg).assign(oid, uid, "khiếu nại", audit=None)


def test_concurrent_assignments_only_one_wins(settings, pg, api):
    from concurrent.futures import ThreadPoolExecutor
    aid, _ = new_user(api, pg, "admin")
    users = [new_user(api, pg)[0] for _ in range(4)]
    oid = orphan(pg)
    ctx = AuditContext(settings, Actor(aid, "admin"), None)

    def go(u):
        try:
            OrphanAdmin(settings, pg).assign(oid, u, "khiếu nại", audit=ctx)
            return "ok"
        except Exception as e:  # noqa: BLE001
            return type(e).__name__
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(go, users))
    assert res.count("ok") == 1 and set(res) <= {"ok", "NotAnOrphan"}, res
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM audit_logs WHERE action = 'orders.assign_orphan' AND target_id = :t"), {"t": str(oid)}).scalar_one() == 1
        assert c.execute(text("SELECT user_id FROM shopee_orders WHERE id = :i"), {"i": oid}).scalar_one() in users


def test_sync_does_not_overwrite_a_manual_assignment(settings, pg, api):
    """Đơn đã gán tay rồi Shopee báo lại cùng order_sn: user_id giữ nguyên (update_order không đụng user_id)."""
    from app.modules.orders import repository
    from app.modules.orders.normalize import NormalizedOrder
    aid, _ = new_user(api, pg, "admin")
    uid, _ = new_user(api, pg)
    oid = orphan(pg)
    OrphanAdmin(settings, pg).assign(oid, uid, "khiếu nại", audit=AuditContext(settings, Actor(aid, "admin"), None))
    with pg.begin() as c:
        sn = c.execute(text("SELECT order_sn FROM shopee_orders WHERE id = :i"), {"i": oid}).scalar_one()
        o = NormalizedOrder(order_sn=sn, raw_status="COMPLETED", status="COMPLETED", utm_content="", commission_micro=COMMISSION,
                            purchase_time=datetime.now(UTC), completed_at=datetime.now(UTC), items=[], raw={})
        repository.update_order(c, oid, o, "COMPLETED", datetime.now(UTC))
        assert c.execute(text("SELECT user_id FROM shopee_orders WHERE id = :i"), {"i": oid}).scalar_one() == uid
