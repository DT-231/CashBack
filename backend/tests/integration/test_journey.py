"""Hành trình đầu-cuối trên Postgres thật, đi qua API và các service như vận hành thật:
đăng ký → tạo link → click /go → đơn Shopee (đồng bộ) → ví (chờ → rút được) → rút tiền → admin duyệt → chi trả,
rồi kiểm sổ cái, đối soát, audit. Mock duy nhất: client Shopee (dữ liệu đơn) và đồng hồ đồng bộ."""
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core import subid
from app.main_api import create_app
from app.modules.orders.service import OrderSync
from app.modules.wallet.service import WalletService
from tests.integration.pg import DB_URL, pg_available
from tests.integration.test_orders_sync import FakeClient, order_row
from tests.integration.test_withdrawals import KEY, make_usable

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
SECRET = "s" * 32
PW = "mat-khau-hop-le-1"
COMMISSION = 20_000_000_000          # 200.000đ Shopee -> 60% = 120.000đ cho user


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    with eng.connect() as c:
        last_run = c.execute(text("SELECT coalesce(max(id), 0) FROM sync_runs")).scalar_one()
    yield eng
    users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
    with eng.begin() as c:
        c.execute(text("ALTER TABLE wallet_entries DISABLE TRIGGER wallet_entries_no_change"))
        c.execute(text(f"DELETE FROM wallet_entries WHERE user_id IN {users}"))
        c.execute(text("ALTER TABLE wallet_entries ENABLE TRIGGER wallet_entries_no_change"))
        c.execute(text(f"DELETE FROM withdrawals WHERE user_id IN {users}"))
        c.execute(text(f"DELETE FROM bank_accounts WHERE user_id IN {users}"))
        c.execute(text(f"DELETE FROM wallets WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM orphan_orders WHERE order_id IN (SELECT id FROM shopee_orders WHERE order_sn LIKE 'ITEST-%')"))
        c.execute(text("DELETE FROM shopee_order_items WHERE order_id IN (SELECT id FROM shopee_orders WHERE order_sn LIKE 'ITEST-%')"))
        c.execute(text("DELETE FROM shopee_orders WHERE order_sn LIKE 'ITEST-%'"))
        c.execute(text("DELETE FROM sync_runs WHERE id > :i"), {"i": last_run})
        c.execute(text(f"DELETE FROM clicks WHERE link_id IN (SELECT id FROM links WHERE user_id IN {users})"))
        c.execute(text(f"DELETE FROM links WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM products WHERE shop_id BETWEEN 990001 AND 990009"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
    eng.dispose()


@pytest.fixture
def settings(make_settings):
    return make_settings(database_url=DB_URL, jwt_secret="j" * 40, ip_salt="i" * 24, subid_secret=SECRET, withdrawals_enabled=True,
                         bank_enc_key=KEY, admin_mfa_required=False)


@pytest.fixture
def api(settings, pg):
    return TestClient(create_app(settings, engine=pg), raise_server_exceptions=False, follow_redirects=False)


def register_login(api, pg, role="member"):
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    if role != "member":
        with pg.begin() as c:
            c.execute(text("UPDATE users SET role = :r WHERE id = :i"), {"r": role, "i": uid})
    tok = api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return uid, {"Authorization": f"Bearer {tok}"}


def click_through_link(api, headers):
    code = api.post("/api/v1/links", headers=headers, json={"url": "https://shopee.vn/product/990004/100004"}).json()["code"]
    utm = parse_qs(urlsplit(api.get(f"/go/{code}", headers={"user-agent": "Mozilla/5.0 (iPhone)"}).headers["location"]).query)["utm_content"][0]
    return code, utm


def sync_order(settings, pg, utm, status, at, sn):
    row, _ = order_row(sn=sn, utm=utm, commission=COMMISSION, order_status=status)
    res = OrderSync(settings, pg, FakeClient([row]), clock=lambda: at).run(60)
    assert res.result == "ok", res
    return res


def wallet(pg, uid):
    with pg.connect() as c:
        return tuple(c.execute(text("SELECT pending_vnd, available_vnd, held_vnd FROM wallets WHERE user_id = :u"), {"u": uid}).one())


def test_full_journey_from_click_to_paid_withdrawal(api, pg, settings):
    now = datetime.now(UTC)
    uid, uh = register_login(api, pg)
    aid, ah = register_login(api, pg, "admin")
    code, utm = click_through_link(api, uh)
    assert subid.decode(utm, SECRET).owner == uid                                  # sub_id trong link gắn đúng user
    sn = f"ITEST-J-{uuid.uuid4().hex[:8]}"

    # 1) Đơn PENDING từ Shopee: khớp về đúng user, ví ghi 60% vào "chờ xác nhận"
    sync_order(settings, pg, utm, "PENDING", now - timedelta(days=11), sn)
    WalletService(settings, pg).settle()
    assert wallet(pg, uid) == (120_000, 0, 0)
    orders = api.get("/api/v1/me/orders", headers=uh).json()
    assert [(o["status"], o["refund_state"], o["refund_vnd"], o["expected_release_at"]) for o in orders] == [("PENDING", "pending", 120_000, None)]

    # 2) Hoàn tất cách đây 10 ngày (> hold_days 7): sang "rút được", không sớm hơn
    sync_order(settings, pg, utm, "COMPLETED", now - timedelta(days=10), sn)
    WalletService(settings, pg).settle()
    assert wallet(pg, uid) == (0, 120_000, 0)
    assert api.get("/api/v1/me/wallet", headers=uh).json()["available_vnd"] == 120_000
    assert [o["refund_state"] for o in api.get("/api/v1/me/orders", headers=uh).json()] == ["available"]

    # 3) Thêm tài khoản (chờ 48 giờ), rút hết, admin duyệt, xem số tài khoản, chi trả
    acct = api.post("/api/v1/me/bank-accounts", headers=uh, json={"bank_code": "vcb", "account_no": "0123456789012", "account_name": "nguyen van a"}).json()
    early = api.post("/api/v1/me/withdrawals", headers={**uh, "Idempotency-Key": "k-early-0001"}, json={"amount_vnd": 120_000, "bank_account_id": acct["id"]})
    assert early.status_code == 409 and early.json()["error"]["code"] == "bank_account_cooling_down" and wallet(pg, uid) == (0, 120_000, 0)
    make_usable(pg, acct["id"])
    w = api.post("/api/v1/me/withdrawals", headers={**uh, "Idempotency-Key": "k-journey-0001"}, json={"amount_vnd": 120_000, "bank_account_id": acct["id"]})
    assert w.status_code == 201 and w.json()["status"] == "requested" and wallet(pg, uid) == (0, 0, 120_000)
    wid = w.json()["id"]
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=uh).status_code == 403            # người dùng không tự duyệt
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=ah).json()["status"] == "approved"
    view = api.get(f"/api/v1/admin/withdrawals/{wid}/payout-account", headers=ah).json()
    assert (view["account_no"], view["amount_vnd"], view["bank_code"]) == ("0123456789012", 120_000, "VCB")
    paid = api.post(f"/api/v1/admin/withdrawals/{wid}/mark-paid", headers=ah, json={"provider_ref": f"FT-{uuid.uuid4().hex[:10]}"}).json()
    assert paid["status"] == "paid" and wallet(pg, uid) == (0, 0, 0)
    assert [x["status"] for x in api.get("/api/v1/me/withdrawals", headers=uh).json()] == ["paid"]

    # 4) Nhất quán: sổ cái khớp ví, đối soát khớp, audit đủ chuỗi
    integrity = api.get("/api/v1/admin/ledger-integrity", headers=ah).json()
    assert integrity["mismatches"] == 0
    with pg.connect() as c:
        kinds = [r[0] for r in c.execute(text("SELECT kind FROM wallet_entries WHERE user_id = :u ORDER BY id"), {"u": uid})]
        actions = [r[0] for r in c.execute(text("SELECT action FROM audit_logs WHERE actor_id IN (:u, :a) OR (target_type = 'withdrawal' AND target_id = :w) ORDER BY id"),
                                           {"u": uid, "a": aid, "w": str(wid)})]
    assert kinds == ["accrual", "release", "hold", "payout"]
    expected = ["auth.register", "auth.register", "auth.login", "auth.login", "bank_account.add", "wallet.hold", "withdrawal.request",
                "withdrawal.approve", "payout.view_account", "wallet.payout", "withdrawal.mark_paid"]
    assert [a for a in actions if a in set(expected)] .__len__() >= len(expected) and all(a in actions for a in expected)
    month = now.strftime("%Y-%m")
    rec = api.get("/api/v1/admin/reconciliation", params={"month": month}, headers=ah).json()
    assert rec["completed"]["shopee_commission_vnd"] >= 200_000 and rec["completed"]["user_share_accrued_vnd"] >= 120_000
    assert rec["paid_out_vnd"] >= 120_000


def test_return_after_release_before_withdrawal_reverses_and_blocks_the_withdrawal(api, pg, settings):
    now = datetime.now(UTC)
    uid, uh = register_login(api, pg)
    _, ah = register_login(api, pg, "admin")
    _, utm = click_through_link(api, uh)
    sn = f"ITEST-J-{uuid.uuid4().hex[:8]}"
    sync_order(settings, pg, utm, "COMPLETED", now - timedelta(days=10), sn)
    WalletService(settings, pg).settle()
    assert wallet(pg, uid) == (0, 120_000, 0)
    sync_order(settings, pg, utm, "RETURNED", now - timedelta(days=1), sn)                      # Shopee thu hồi
    WalletService(settings, pg).settle()
    assert wallet(pg, uid) == (0, 0, 0)
    acct = api.post("/api/v1/me/bank-accounts", headers=uh, json={"bank_code": "acb", "account_no": "9876543210", "account_name": "tran b"}).json()
    make_usable(pg, acct["id"])
    r = api.post("/api/v1/me/withdrawals", headers={**uh, "Idempotency-Key": "k-returned-0001"}, json={"amount_vnd": 100_000, "bank_account_id": acct["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_funds"           # không rút được tiền đã bị thu hồi
    assert [o["refund_state"] for o in api.get("/api/v1/me/orders", headers=uh).json()] == ["reversed"]
    assert api.get("/api/v1/admin/ledger-integrity", headers=ah).json()["mismatches"] == 0


def test_return_after_the_user_already_withdrew_records_an_admin_loss_and_never_goes_negative(api, pg, settings):
    now = datetime.now(UTC)
    uid, uh = register_login(api, pg)
    _, ah = register_login(api, pg, "admin")
    _, utm = click_through_link(api, uh)
    sn = f"ITEST-J-{uuid.uuid4().hex[:8]}"
    sync_order(settings, pg, utm, "COMPLETED", now - timedelta(days=10), sn)
    WalletService(settings, pg).settle()
    acct = api.post("/api/v1/me/bank-accounts", headers=uh, json={"bank_code": "vcb", "account_no": "1112223334", "account_name": "le c"}).json()
    make_usable(pg, acct["id"])
    wid = api.post("/api/v1/me/withdrawals", headers={**uh, "Idempotency-Key": "k-loss-00001"}, json={"amount_vnd": 120_000, "bank_account_id": acct["id"]}).json()["id"]
    api.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=ah)
    api.post(f"/api/v1/admin/withdrawals/{wid}/mark-paid", headers=ah, json={"provider_ref": f"FT-{uuid.uuid4().hex[:10]}"})
    assert wallet(pg, uid) == (0, 0, 0)
    sync_order(settings, pg, utm, "RETURNED", now - timedelta(days=1), sn)                      # thu hồi SAU khi đã trả tiền
    WalletService(settings, pg).settle()
    assert wallet(pg, uid) == (0, 0, 0) and min(wallet(pg, uid)) >= 0                            # ví không bao giờ âm
    rec = api.get("/api/v1/admin/reconciliation", params={"month": now.strftime("%Y-%m")}, headers=ah).json()
    assert rec["admin_loss_vnd"] >= 120_000                                                      # khoản lỗ ghi cho admin (adjust), không trừ âm ví
    assert api.get("/api/v1/admin/ledger-integrity", headers=ah).json()["mismatches"] == 0
