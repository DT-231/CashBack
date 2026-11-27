"""T-052: đối soát theo tháng và kiểm tra toàn vẹn sổ cái (admin + TOTP, chỉ đọc)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main_api import create_app
from app.modules.wallet import ledger
from app.modules.wallet.service import WalletService
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
PW = "mat-khau-hop-le-1"
MONTH, OTHER_MONTH = "2099-03", "2099-04"
COMPLETED_MICRO = 4_037_500_000          # 40.375đ -> user 60% = 24.225đ


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
        c.execute(text("DELETE FROM orphan_orders WHERE order_id IN (SELECT id FROM shopee_orders WHERE order_sn LIKE 'ITEST-R-%')"))
        c.execute(text("DELETE FROM shopee_orders WHERE order_sn LIKE 'ITEST-R-%'"))
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


def order(pg, status, micro, user_id=None, when="2099-03-15 10:00+00"):
    with pg.begin() as c:
        return c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, user_id, commission_micro, purchase_time, completed_at) "
                              "VALUES (:s, :st, :src, :u, :m, CAST(:t AS timestamptz), CASE WHEN :st = 'COMPLETED' THEN CAST(:t AS timestamptz) ELSE NULL END) RETURNING id"),
                         {"s": f"ITEST-R-{uuid.uuid4().hex[:8]}", "st": status, "src": "user" if user_id else "unknown", "u": user_id, "m": micro, "t": when}).scalar_one()


def test_access_control_and_month_validation(api, pg):
    _, mh = user(api, pg)
    _, sh = user(api, pg, "staff")
    _, ah = user(api, pg, "admin")
    for hh, code in ((mh, 403), (sh, 403), ({}, 401)):
        assert api.get("/api/v1/admin/reconciliation", params={"month": MONTH}, headers=hh).status_code == code
        assert api.get("/api/v1/admin/ledger-integrity", headers=hh).status_code == code
    for bad in ("2099-13", "2099-00", "99-01", "2099-3", "1999-01", "2099-03-01", "' OR 1=1--", ""):
        assert api.get("/api/v1/admin/reconciliation", params={"month": bad}, headers=ah).status_code == 422, bad
    assert api.get("/api/v1/admin/reconciliation", headers=ah).status_code == 422
    assert api.get("/api/v1/admin/reconciliation", params={"month": "2099-12"}, headers=ah).status_code == 200      # tháng 12 (biên sang năm sau)


def test_reconciliation_numbers_match_the_ledger(api, pg, settings):
    u, _ = user(api, pg)
    _, ah = user(api, pg, "admin")
    order(pg, "COMPLETED", COMPLETED_MICRO, u)                         # user 24.225đ
    cancelled = order(pg, "PENDING", 2_000_000_000, u)                 # 20đ -> user 12đ rồi bị hủy
    order(pg, "PENDING", 1_000_000_000, None)                          # đơn mồ côi: có hoa hồng nhưng không chia cho ai
    order(pg, "COMPLETED", COMPLETED_MICRO, None, when="2099-04-02 00:00+00")   # tháng khác: không được lẫn
    WalletService(settings, pg).settle()
    with pg.begin() as c:
        c.execute(text("UPDATE shopee_orders SET status = 'CANCELLED' WHERE id = :i"), {"i": cancelled})
    WalletService(settings, pg).settle()
    r = api.get("/api/v1/admin/reconciliation", params={"month": MONTH}, headers=ah).json()
    assert r["month"] == MONTH
    assert r["orders"]["COMPLETED"] == {"count": 1, "commission_micro": COMPLETED_MICRO, "attributed_micro": COMPLETED_MICRO,
                                        "commission_vnd": 40_375, "attributed_vnd": 40_375}
    assert r["orders"]["CANCELLED"]["count"] == 1 and r["orders"]["PENDING"]["count"] == 1
    assert r["orders"]["PENDING"]["commission_vnd"] == 10_000 and r["orders"]["PENDING"]["attributed_vnd"] == 0
    assert r["ledger_by_order_status"]["COMPLETED"]["accrual"] == 24_225
    assert r["ledger_by_order_status"]["CANCELLED"] == {"accrual": 12_000, "cancel": 12_000}
    c = r["completed"]
    assert c == {"shopee_commission_vnd": 40_375, "attributed_commission_vnd": 40_375, "user_share_accrued_vnd": 24_225, "platform_margin_vnd": 16_150}
    assert c["user_share_accrued_vnd"] * 100 <= c["shopee_commission_vnd"] * 60                          # làm tròn xuống: không quá 60%
    assert r["admin_loss_vnd"] == 0
    other = api.get("/api/v1/admin/reconciliation", params={"month": OTHER_MONTH}, headers=ah).json()
    assert other["orders"] == {"COMPLETED": {"count": 1, "commission_micro": COMPLETED_MICRO, "attributed_micro": 0, "commission_vnd": 40_375, "attributed_vnd": 0}}
    assert other["completed"]["user_share_accrued_vnd"] == 0 and other["completed"]["platform_margin_vnd"] == 40_375   # đơn mồ côi: toàn bộ là biên
    empty = api.get("/api/v1/admin/reconciliation", params={"month": "2099-06"}, headers=ah).json()
    assert empty["orders"] == {} and empty["completed"]["platform_margin_vnd"] == 0 and empty["paid_out_vnd"] == 0   # chi trả ghi "bây giờ" không rơi vào tháng khác


def test_payouts_and_admin_loss_are_reported(api, pg):
    u, _ = user(api, pg)
    _, ah = user(api, pg, "admin")
    before = api.get("/api/v1/admin/reconciliation", params={"month": MONTH}, headers=ah).json()
    oid = order(pg, "COMPLETED", COMPLETED_MICRO, u)
    with pg.begin() as c:
        ledger.post(c, u, "accrual", "pending", 24_225, f"itest:r:acc:{oid}", order_id=oid)
        ledger.post(c, u, "release", "available", 24_225, f"itest:r:rel:{oid}", order_id=oid)
        ledger.post(c, u, "adjust", "reversed", 4_225, f"itest:r:adj:{oid}", order_id=oid)             # khoản lỗ admin (user đã rút trước)
        ledger.post(c, u, "hold", "held", 20_000, f"itest:r:hold:{oid}")
        ledger.post(c, u, "payout", "paid_out", 20_000, f"itest:r:pay:{oid}")
    now_month = api.get("/api/v1/admin/reconciliation", params={"month": MONTH}, headers=ah).json()
    assert now_month["admin_loss_vnd"] - before["admin_loss_vnd"] == 4_225
    assert now_month["ledger_by_order_status"]["COMPLETED"]["release"] - before["ledger_by_order_status"].get("COMPLETED", {}).get("release", 0) == 24_225
    from datetime import UTC, datetime
    m = datetime.now(UTC).strftime("%Y-%m")
    paid_now = api.get("/api/v1/admin/reconciliation", params={"month": m}, headers=ah).json()["paid_out_vnd"]
    assert paid_now >= 20_000                                                                          # khoản chi trả vừa ghi nằm trong tháng hiện tại


def test_ledger_integrity_detects_a_tampered_balance(api, pg):
    u, _ = user(api, pg)
    _, ah = user(api, pg, "admin")
    oid = order(pg, "COMPLETED", COMPLETED_MICRO, u)
    with pg.begin() as c:
        ledger.post(c, u, "accrual", "pending", 24_225, f"itest:i:acc:{oid}", order_id=oid)
        ledger.post(c, u, "release", "available", 24_225, f"itest:i:rel:{oid}", order_id=oid)
        ledger.post(c, u, "hold", "held", 10_000, f"itest:i:hold:{oid}")
    base = api.get("/api/v1/admin/ledger-integrity", headers=ah).json()
    assert base["mismatches"] == 0 and base["wallets_checked"] >= 1 and base["samples"] == []
    with pg.begin() as c:                                                                              # ai đó sửa số dư lưu trực tiếp (không qua sổ cái)
        c.execute(text("UPDATE wallets SET available_vnd = available_vnd + 1 WHERE user_id = :u"), {"u": u})
    bad = api.get("/api/v1/admin/ledger-integrity", headers=ah).json()
    assert bad["mismatches"] == 1 and len(bad["samples"]) == 1
    s = bad["samples"][0]
    assert (s["user_id"], s["stored_available"], s["derived_available"], s["stored_pending"], s["derived_pending"], s["stored_held"], s["derived_held"]) == \
        (u, 14_226, 14_225, 0, 0, 10_000, 10_000)
    with pg.begin() as c:
        c.execute(text("UPDATE wallets SET available_vnd = available_vnd - 1, pending_vnd = pending_vnd + 7 WHERE user_id = :u"), {"u": u})
    s2 = api.get("/api/v1/admin/ledger-integrity", headers=ah).json()["samples"][0]
    assert (s2["stored_pending"], s2["derived_pending"], s2["stored_available"], s2["derived_available"]) == (7, 0, 14_225, 14_225)
    with pg.begin() as c:
        c.execute(text("UPDATE wallets SET pending_vnd = 0, held_vnd = 0 WHERE user_id = :u"), {"u": u})
    assert api.get("/api/v1/admin/ledger-integrity", headers=ah).json()["samples"][0]["derived_held"] == 10_000      # held lệch cũng bị bắt
    with pg.begin() as c:
        c.execute(text("UPDATE wallets SET held_vnd = 10000 WHERE user_id = :u"), {"u": u})
    assert api.get("/api/v1/admin/ledger-integrity", headers=ah).json()["mismatches"] == 0


def test_integrity_covers_payout_and_refund_kinds(api, pg):
    u, _ = user(api, pg)
    _, ah = user(api, pg, "admin")
    with pg.begin() as c:
        ledger.post(c, u, "accrual", "pending", 100_000, f"itest:k:a:{u}")
        ledger.post(c, u, "release", "available", 100_000, f"itest:k:r:{u}")
        ledger.post(c, u, "hold", "held", 60_000, f"itest:k:h1:{u}")
        ledger.post(c, u, "refund_hold", "available", 60_000, f"itest:k:rf:{u}")
        ledger.post(c, u, "hold", "held", 30_000, f"itest:k:h2:{u}")
        ledger.post(c, u, "payout", "paid_out", 30_000, f"itest:k:p:{u}")
        ledger.post(c, u, "reverse", "reversed", 5_000, f"itest:k:rv:{u}")
    assert api.get("/api/v1/admin/ledger-integrity", headers=ah).json()["mismatches"] == 0


def test_endpoints_are_read_only(api, pg):
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "app" / "modules" / "adminstats" / "repository.py").read_text()
    assert not re.search(r"(?i)\b(insert\s+into|update\s+\w+\s+set|delete\s+from|truncate|drop\s+table|alter\s+table)\b", src)


def test_month_boundaries_are_half_open_including_december(api, pg):
    u, _ = user(api, pg)
    _, ah = user(api, pg, "admin")
    order(pg, "PENDING", 1_000_000_000, u, when="2099-03-01 00:00:00+00")        # đúng 0h ngày 1: thuộc tháng 3
    order(pg, "PENDING", 2_000_000_000, u, when="2099-03-31 23:59:59+00")        # giây cuối tháng 3
    order(pg, "PENDING", 4_000_000_000, u, when="2099-04-01 00:00:00+00")        # đúng 0h ngày 1 tháng 4: KHÔNG thuộc tháng 3
    order(pg, "PENDING", 8_000_000_000, u, when="2099-12-31 23:59:59+00")        # giây cuối năm: thuộc tháng 12
    order(pg, "PENDING", 16_000_000_000, u, when="2100-01-01 00:00:00+00")       # sang năm: KHÔNG thuộc tháng 12
    get = lambda m: api.get("/api/v1/admin/reconciliation", params={"month": m}, headers=ah).json()["orders"]["PENDING"]   # noqa: E731
    assert get("2099-03") == {"count": 2, "commission_micro": 3_000_000_000, "attributed_micro": 3_000_000_000, "commission_vnd": 30_000, "attributed_vnd": 30_000}
    assert get("2099-04")["commission_micro"] == 4_000_000_000
    assert get("2099-12")["commission_micro"] == 8_000_000_000 and get("2099-12")["count"] == 1


def test_partial_cancels_on_a_completed_order_reduce_the_user_share_and_raise_the_margin(api, pg):
    u, _ = user(api, pg)
    _, ah = user(api, pg, "admin")
    oid = order(pg, "COMPLETED", COMPLETED_MICRO, u, when="2099-07-10 00:00+00")
    with pg.begin() as c:
        ledger.post(c, u, "accrual", "pending", 24_225, f"itest:p:a:{oid}", order_id=oid)
        ledger.post(c, u, "cancel", "cancelled", 1_000, f"itest:p:c:{oid}", order_id=oid)          # hoa hồng bị Shopee điều chỉnh giảm
    c = api.get("/api/v1/admin/reconciliation", params={"month": "2099-07"}, headers=ah).json()["completed"]
    assert c["user_share_accrued_vnd"] == 23_225 and c["platform_margin_vnd"] == 40_375 - 23_225
