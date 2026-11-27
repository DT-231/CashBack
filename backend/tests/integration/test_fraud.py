"""T-053: cờ gian lận (cùng ip_hash, tỷ lệ hủy/trả cao, click dồn). Chỉ tạo cờ; không tự khóa/giữ tiền; admin xử lý có audit."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main_api import create_app
from app.modules.fraud.service import FraudService
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
PW = "mat-khau-hop-le-1"
SHOP = 990051


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text(f"DELETE FROM fraud_flags WHERE user_id IN {users}"))
        c.execute(text(f"DELETE FROM clicks WHERE link_id IN (SELECT id FROM links WHERE user_id IN {users})"))
        c.execute(text(f"DELETE FROM links WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM products WHERE shop_id BETWEEN 990051 AND 990059"))
        c.execute(text("DELETE FROM shopee_orders WHERE order_sn LIKE 'ITEST-F-%'"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
    eng.dispose()


@pytest.fixture
def settings(make_settings):
    return make_settings(database_url=DB_URL, jwt_secret="j" * 40, ip_salt="i" * 24, admin_mfa_required=False)


@pytest.fixture
def api(settings, pg):
    return TestClient(create_app(settings, engine=pg), raise_server_exceptions=False)


def user(api, pg, role="member"):
    email = f"itest-{uuid.uuid4().hex[:8]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    with pg.begin() as c:
        c.execute(text("UPDATE users SET role = :r WHERE id = :i"), {"r": role, "i": uid})
    return uid, {"Authorization": "Bearer " + api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]}


_item = [0]


def link(pg, uid):
    _item[0] += 1
    with pg.begin() as c:
        pid = c.execute(text("INSERT INTO products(shop_id, item_id, name) VALUES (:s, :i, 'x') RETURNING id"), {"s": SHOP + (_item[0] % 9), "i": uuid.uuid4().int % 10**12}).scalar_one()
        return c.execute(text("INSERT INTO links(user_id, product_id, code) VALUES (:u, :p, :c) RETURNING id"), {"u": uid, "p": pid, "c": uuid.uuid4().hex[:8]}).scalar_one()


def clicks(pg, link_id, ip, n=1, hours_ago=1):
    with pg.begin() as c:
        c.execute(text("INSERT INTO clicks(link_id, sub_id, ip_hash, created_at) SELECT :l, 'x', :ip, date_trunc('hour', now()) - make_interval(hours => :h) + interval '10 minutes' + make_interval(secs => g) "
                       "FROM generate_series(1, :n) g"), {"l": link_id, "ip": ip, "h": hours_ago, "n": n})


def order(pg, uid, status, days_ago=1):
    with pg.begin() as c:
        c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, user_id, commission_micro, purchase_time) "
                       "VALUES (:s, :st, 'user', :u, 1000, now() - make_interval(days => :d))"), {"s": f"ITEST-F-{uuid.uuid4().hex[:8]}", "st": status, "u": uid, "d": days_ago})


def flags(pg, uid, status=None):
    with pg.connect() as c:
        return [dict(r) for r in c.execute(text("SELECT rule, score, status, detail FROM fraud_flags WHERE user_id = :u" + (" AND status = :s" if status else "") + " ORDER BY id"),
                                           {"u": uid, "s": status}).mappings()]


def test_shared_ip_flags_every_link_owner_only_at_the_threshold(api, pg, settings):
    a, b, c3, d = (user(api, pg)[0] for _ in range(4))
    ip = "ip-" + uuid.uuid4().hex[:10]
    for u in (a, b):
        clicks(pg, link(pg, u), ip, 2)
    FraudService(settings, pg).scan()
    assert flags(pg, a) == [] and flags(pg, b) == []                               # mới 2 chủ link: dưới ngưỡng 3
    clicks(pg, link(pg, c3), ip, 1)
    clicks(pg, link(pg, d), "khac-" + uuid.uuid4().hex[:8], 5)                      # ip khác: không liên quan
    res = FraudService(settings, pg).scan()
    for u in (a, b, c3):
        assert flags(pg, u) == [{"rule": "shared_ip", "score": 3, "status": "open", "detail": {"distinct_users": 3}}]
    assert flags(pg, d) == [] and res.by_rule["shared_ip"] >= 3


def test_shared_ip_ignores_old_clicks_and_missing_hashes(api, pg, settings):
    users = [user(api, pg)[0] for _ in range(3)]
    ip = "ip-" + uuid.uuid4().hex[:10]
    for u in users[:2]:
        clicks(pg, link(pg, u), ip, 1)
    clicks(pg, link(pg, users[2]), ip, 1, hours_ago=24 * 8)                         # quá 7 ngày
    FraudService(settings, pg).scan()
    assert all(flags(pg, u) == [] for u in users)
    with pg.begin() as c:
        c.execute(text("INSERT INTO clicks(link_id, sub_id, ip_hash) SELECT id, 'x', NULL FROM links WHERE user_id = :u"), {"u": users[2]})
    for u in users[:2]:
        with pg.begin() as c:
            c.execute(text("INSERT INTO clicks(link_id, sub_id, ip_hash) SELECT id, 'x', NULL FROM links WHERE user_id = :u"), {"u": u})
    FraudService(settings, pg).scan()
    assert all(flags(pg, u) == [] for u in users)                                   # 3 chủ link cùng click với ip_hash NULL: vẫn KHÔNG phải "cùng IP"


def test_high_cancel_rate_thresholds_and_window(api, pg, settings):
    hit, low, few, old, unmatched = (user(api, pg)[0] for _ in range(5))
    for st in ("CANCELLED", "RETURNED", "CANCELLED", "COMPLETED", "PENDING"):
        order(pg, hit, st)                                                          # 3/5 = 60%
    for st in ("CANCELLED", "RETURNED", "COMPLETED", "COMPLETED", "PENDING"):
        order(pg, low, st)                                                          # 2/5 = 40%
    for _ in range(4):
        order(pg, few, "CANCELLED")                                                 # 100% nhưng chỉ 4 đơn (< 5)
    for _ in range(5):
        order(pg, old, "CANCELLED", days_ago=70)                                    # ngoài cửa sổ 60 ngày
    with pg.begin() as c:
        for _ in range(6):                                                          # đơn mồ côi (user_id NULL) không tính cho ai
            c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, commission_micro) VALUES (:s, 'CANCELLED', 'unknown', 1)"), {"s": f"ITEST-F-{uuid.uuid4().hex[:8]}"})
    FraudService(settings, pg).scan()
    assert flags(pg, hit) == [{"rule": "high_cancel_rate", "score": 60, "status": "open", "detail": {"orders": 5, "cancelled_or_returned": 3}}]
    for u in (low, few, old, unmatched):
        assert flags(pg, u) == []
    order(pg, low, "CANCELLED")                                                     # 3/6 = 50% đúng ngưỡng: cờ
    FraudService(settings, pg).scan()
    assert flags(pg, low)[0]["score"] == 50


def test_click_burst_needs_one_ip_on_one_link_within_an_hour(api, pg, settings):
    u1, u2, u3 = (user(api, pg)[0] for _ in range(3))
    l1, l2 = link(pg, u1), link(pg, u2)
    clicks(pg, l1, "a-" + uuid.uuid4().hex[:8], 60, hours_ago=2)                    # đúng 60 trong một giờ: cờ
    clicks(pg, l2, "b-" + uuid.uuid4().hex[:8], 59, hours_ago=2)                    # 59: chưa
    l3 = link(pg, u3)
    for i in range(4):
        clicks(pg, l3, "c-" + uuid.uuid4().hex[:8], 20, hours_ago=2)                # 80 click nhưng từ 4 ip khác nhau: không phải một nguồn
    FraudService(settings, pg).scan()
    assert flags(pg, u1)[0]["rule"] == "click_burst" and flags(pg, u1)[0]["detail"] == {"max_clicks_per_hour": 60}
    assert flags(pg, u2) == [] and flags(pg, u3) == []


def test_scan_is_idempotent_updates_the_score_and_never_acts_on_the_account(api, pg, settings):
    u, _ = user(api, pg)
    for st in ("CANCELLED",) * 3 + ("COMPLETED",) * 2:
        order(pg, u, st)
    first = FraudService(settings, pg).scan()
    second = FraudService(settings, pg).scan()
    assert len(flags(pg, u)) == 1 and first.created >= 1 and second.created == 0 and second.updated >= 1
    for _ in range(3):
        order(pg, u, "CANCELLED")
    FraudService(settings, pg).scan()
    assert len(flags(pg, u)) == 1 and flags(pg, u)[0]["score"] == 75                # 6/8: cùng cờ, điểm được cập nhật
    with pg.connect() as c:
        assert c.execute(text("SELECT status FROM users WHERE id = :u"), {"u": u}).scalar_one() == "active"     # không tự khóa
        assert c.execute(text("SELECT count(*) FROM wallet_entries WHERE user_id = :u"), {"u": u}).scalar_one() == 0


def test_thresholds_come_from_settings(make_settings, pg, api):
    s = make_settings(database_url=DB_URL, fraud_cancel_min_orders=2, fraud_cancel_rate_pct=100)
    u, _ = user(api, pg)
    order(pg, u, "CANCELLED")
    order(pg, u, "CANCELLED")
    FraudService(s, pg).scan()
    assert flags(pg, u)[0]["score"] == 100


def test_resolve_dismiss_confirm_audit_and_cooldown(api, pg, settings):
    aid, ah = user(api, pg, "admin")
    u, _ = user(api, pg)
    for st in ("CANCELLED",) * 3 + ("COMPLETED",) * 2:
        order(pg, u, st)
    FraudService(settings, pg).scan()
    listed = api.get("/api/v1/admin/fraud-flags", params={"status": "open"}, headers=ah).json()
    fid = [f for f in listed if f["user_id"] == u][0]["id"]
    assert api.post(f"/api/v1/admin/fraud-flags/{fid}/resolve", headers=ah, json={"status": "dismissed", "note": "cùng nhà, đã xác minh"}).status_code == 204
    again = api.post(f"/api/v1/admin/fraud-flags/{fid}/resolve", headers=ah, json={"status": "confirmed", "note": "lại"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "flag_closed"
    assert api.post("/api/v1/admin/fraud-flags/999999999/resolve", headers=ah, json={"status": "confirmed", "note": "abc"}).json()["error"]["code"] == "flag_not_found"
    for bad in ({"status": "open", "note": "abc"}, {"status": "confirmed", "note": "x"}, {"status": "confirmed"}):
        assert api.post(f"/api/v1/admin/fraud-flags/{fid}/resolve", headers=ah, json=bad).status_code == 422
    row = [f for f in api.get("/api/v1/admin/fraud-flags", params={"status": "dismissed"}, headers=ah).json() if f["id"] == fid][0]
    assert row["resolved_by"] == aid and row["resolution_note"] == "cùng nhà, đã xác minh" and row["status"] == "dismissed"
    with pg.connect() as c:
        a = c.execute(text("SELECT actor_id, actor_role, detail FROM audit_logs WHERE action = 'fraud.resolve' AND target_id = :t"), {"t": str(fid)}).mappings().one()
    assert a["actor_id"] == aid and a["detail"]["status"] == "dismissed" and a["detail"]["rule"] == "high_cancel_rate"
    res = FraudService(settings, pg).scan()                                         # vừa bỏ qua: không tạo lại trong thời gian chờ
    assert flags(pg, u, "open") == [] and res.suppressed >= 1
    from app.core.config import Settings
    s0 = Settings(**{**settings.model_dump(), "fraud_dismiss_cooldown_days": 0})
    FraudService(s0, pg).scan()
    assert len(flags(pg, u, "open")) == 1                          # hết thời gian chờ (0 ngày): tạo lại
    fid2 = [f for f in api.get("/api/v1/admin/fraud-flags", params={"status": "open"}, headers=ah).json() if f["user_id"] == u][0]["id"]
    api.post(f"/api/v1/admin/fraud-flags/{fid2}/resolve", headers=ah, json={"status": "confirmed", "note": "xác nhận gian lận"})
    FraudService(s0, pg).scan()
    assert len(flags(pg, u, "open")) == 1                                           # đã xác nhận (không phải bỏ qua): lần quét sau vẫn tạo cờ mới nếu còn vi phạm


def test_only_admin_can_list_or_resolve(api, pg):
    _, mh = user(api, pg)
    _, sh = user(api, pg, "staff")
    for hh, code in ((mh, 403), (sh, 403), ({}, 401)):
        assert api.get("/api/v1/admin/fraud-flags", headers=hh).status_code == code
        assert api.post("/api/v1/admin/fraud-flags/1/resolve", headers=hh, json={"status": "dismissed", "note": "abc"}).status_code == code
    _, ah = user(api, pg, "admin")
    assert api.get("/api/v1/admin/fraud-flags", params={"status": "nope"}, headers=ah).status_code == 422


def test_service_layer_refuses_non_admin_and_missing_audit(settings, pg):
    from app.core.errors import Forbidden
    from app.modules.audit.errors import InvalidAudit
    from app.modules.audit.service import Actor, AuditContext
    for role in ("staff", "user", "system"):
        with pytest.raises(Forbidden):
            FraudService(settings, pg).resolve(1, "dismissed", "ghi chú", audit=AuditContext(settings, Actor(9, role), None))
    with pytest.raises(InvalidAudit):
        FraudService(settings, pg).resolve(1, "dismissed", "ghi chú", audit=None)


def test_worker_fraud_scan_command_prints_json(monkeypatch, capsys, pg):
    from app import main_worker
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("SUBID_SECRET", "s" * 32)
    assert main_worker.main(["fraud-scan"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out["fraud"]) == {"created", "updated", "suppressed", "by_rule"}


def test_service_rejects_invalid_status_before_touching_the_db(settings, pg):
    from app.core.errors import AppError
    from app.modules.audit.service import Actor, AuditContext
    with pytest.raises(AppError) as e:
        FraudService(settings, pg).resolve(1, "open", "ghi chú", audit=AuditContext(settings, Actor(9, "admin"), None))
    assert e.value.code == "invalid_status"
