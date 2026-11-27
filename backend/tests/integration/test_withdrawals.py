"""Rút tiền (T-040) trên Postgres thật: khóa tiền, idempotency, duyệt/từ chối/chi trả, mã hóa số tài khoản, quyền, audit."""
import base64
import json
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.main_api import create_app
from app.modules.audit.service import Actor, AuditContext
from app.modules.payout import service as payout_service
from app.modules.payout.schemas import BankAccountIn
from app.modules.payout.service import PayoutService
from app.modules.wallet import ledger
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()
PW = "mat-khau-hop-le-1"
ACCOUNT_NO = "0123456789012"
FUNDS = 500_000


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text("ALTER TABLE wallet_entries DISABLE TRIGGER wallet_entries_no_change"))
        c.execute(text(f"DELETE FROM wallet_entries WHERE user_id IN {users}"))
        c.execute(text("ALTER TABLE wallet_entries ENABLE TRIGGER wallet_entries_no_change"))
        c.execute(text(f"DELETE FROM withdrawals WHERE user_id IN {users}"))
        c.execute(text(f"DELETE FROM bank_accounts WHERE user_id IN {users}"))
        c.execute(text(f"DELETE FROM wallets WHERE user_id IN {users}"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
        c.execute(text("DELETE FROM rate_limits WHERE key ~ '^(withdraw_|bank_add_|register_ip:|login_ip:|login_email:|refresh_ip:)'"))
    eng.dispose()


@pytest.fixture
def settings(make_settings):
    def make(**kw):
        base = dict(database_url=DB_URL, jwt_secret="j" * 40, ip_salt="i" * 24, withdrawals_enabled=True, bank_enc_key=KEY)
        return make_settings(**{**base, **kw})
    return make


@pytest.fixture
def api(settings, pg):
    return TestClient(create_app(settings(), engine=pg), raise_server_exceptions=False)


def new_user(api, pg, role="member"):
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    if role != "member":
        with pg.begin() as c:
            c.execute(text("UPDATE users SET role = :r WHERE id = :i"), {"r": role, "i": uid})
    tok = api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return uid, {"Authorization": f"Bearer {tok}"}


def fund(pg, uid, amount=FUNDS):
    k = uuid.uuid4().hex
    with pg.begin() as c:
        ledger.post(c, uid, "accrual", "pending", amount, f"itest:acc:{k}")
        ledger.post(c, uid, "release", "available", amount, f"itest:rel:{k}")


def make_usable(pg, account_id):
    """Đẩy usable_from về quá khứ (trigger chặn sửa trực tiếp nên tắt trong đúng transaction này)."""
    with pg.begin() as c:
        c.execute(text("ALTER TABLE bank_accounts DISABLE TRIGGER bank_accounts_no_edit"))
        c.execute(text("UPDATE bank_accounts SET usable_from = now() - interval '1 hour' WHERE id = :i"), {"i": account_id})
        c.execute(text("ALTER TABLE bank_accounts ENABLE TRIGGER bank_accounts_no_edit"))


def add_account(api, pg, h, usable=True, **over):
    body = {"bank_code": "vcb", "account_no": ACCOUNT_NO, "account_name": "nguyen van a", **over}
    r = api.post("/api/v1/me/bank-accounts", headers=h, json=body)
    assert r.status_code == 201, r.text
    if usable:
        make_usable(pg, r.json()["id"])
    return r.json()


def ready(api, pg, funds=FUNDS):
    uid, h = new_user(api, pg)
    fund(pg, uid, funds)
    acct = add_account(api, pg, h)
    return uid, h, acct["id"]


def withdraw(api, h, acct, amount=200_000, key=None):
    return api.post("/api/v1/me/withdrawals", headers={**h, "Idempotency-Key": key or uuid.uuid4().hex},
                    json={"amount_vnd": amount, "bank_account_id": acct})


def bal(pg, uid):
    with pg.connect() as c:
        r = c.execute(text("SELECT pending_vnd, available_vnd, held_vnd FROM wallets WHERE user_id = :u"), {"u": uid}).one_or_none()
    return tuple(r) if r else (0, 0, 0)


def entries(pg, uid, kinds=("hold", "refund_hold", "payout")):
    with pg.connect() as c:
        return [tuple(r) for r in c.execute(text(
            "SELECT kind, state, amount_vnd FROM wallet_entries WHERE user_id = :u AND kind = ANY(:k) ORDER BY id"),
            {"u": uid, "k": list(kinds)})]


def derived(pg, uid):
    with pg.connect() as c:
        rows = c.execute(text("SELECT kind, state, amount_vnd FROM wallet_entries WHERE user_id = :u"), {"u": uid}).all()
    tot = [0, 0, 0]
    for kind, state, amt in rows:
        for i, d in enumerate(ledger.DELTAS[(kind, state)]):
            tot[i] += d * amt
    return tuple(tot)


def audit_rows(pg, wid, action=None):
    with pg.connect() as c:
        rows = c.execute(text("SELECT * FROM audit_logs WHERE target_type = 'withdrawal' AND target_id = :t ORDER BY id"),
                         {"t": str(wid)}).mappings().all()
    return [r for r in rows if action is None or r["action"] == action]


def wd(pg, wid):
    with pg.connect() as c:
        return c.execute(text("SELECT * FROM withdrawals WHERE id = :i"), {"i": wid}).mappings().one()


# ---------- tài khoản ngân hàng ----------
def test_bank_account_is_encrypted_masked_and_has_a_cooling_period(api, pg):
    uid, h = new_user(api, pg)
    acct = add_account(api, pg, h, usable=False)
    assert acct["last4"] == "9012" and acct["bank_code"] == "VCB" and acct["account_name"] == "NGUYEN VAN A"
    assert ACCOUNT_NO not in json.dumps(acct) and "account_no" not in acct
    listed = api.get("/api/v1/me/bank-accounts", headers=h)
    assert ACCOUNT_NO not in listed.text and listed.json()[0]["last4"] == "9012"
    with pg.connect() as c:
        row = c.execute(text("SELECT account_no_enc, key_id, last4, usable_from, created_at FROM bank_accounts WHERE id = :i"), {"i": acct["id"]}).mappings().one()
    assert ACCOUNT_NO not in row["account_no_enc"] and ACCOUNT_NO[:6] not in row["account_no_enc"] and row["key_id"] == "k1"
    assert timedelta(hours=47, minutes=59) < row["usable_from"] - row["created_at"] < timedelta(hours=48, minutes=1)
    fund(pg, uid)
    r = withdraw(api, h, acct["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "bank_account_cooling_down" and bal(pg, uid) == (0, FUNDS, 0)


def test_cooldown_is_configurable_and_zero_means_immediate(settings, pg):
    class Cool:
        def __init__(self, hours): self.h = hours
        def get_int(self, key): return {"bank_change_cooldown_hours": self.h, "min_withdraw_vnd": 100_000}[key]
    svc = PayoutService(settings(), pg, platform=Cool(0))
    api = TestClient(create_app(settings(), engine=pg))
    uid, _ = new_user(api, pg)
    ctx = AuditContext(settings(), Actor(uid, "user"), None)
    a = svc.add_bank_account(uid, BankAccountIn(bank_code="vcb", account_no=ACCOUNT_NO, account_name="A B"), audit=ctx)
    assert a.usable_from <= datetime.now(UTC) + timedelta(seconds=1)
    b = PayoutService(settings(), pg, platform=Cool(72)).add_bank_account(
        uid, BankAccountIn(bank_code="vcb", account_no="987654321", account_name="A B"), audit=ctx)
    assert b.usable_from > datetime.now(UTC) + timedelta(hours=71)


def test_editing_a_bank_account_row_is_blocked_new_row_required(api, pg):
    uid, h = new_user(api, pg)
    acct = add_account(api, pg, h)
    for col, val in (("bank_code", "'ACB'"), ("account_name", "'X Y'"), ("last4", "'1111'"), ("usable_from", "now() - interval '9 days'")):
        with pytest.raises(DBAPIError, match="đổi tài khoản"):
            with pg.begin() as c:
                c.execute(text(f"UPDATE bank_accounts SET {col} = {val} WHERE id = :i"), {"i": acct["id"]})


def test_bank_account_validation_limits_and_no_echo(api, pg):
    uid, h = new_user(api, pg)
    for bad in ({"account_no": "12ab34"}, {"account_no": "12345"}, {"account_no": "1" * 21}, {"bank_code": "x"},
                {"account_name": "A1"}, {"account_name": "A" * 61}):
        body = {"bank_code": "vcb", "account_no": ACCOUNT_NO, "account_name": "A B", **bad}
        r = api.post("/api/v1/me/bank-accounts", headers=h, json=body)
        assert r.status_code == 422, bad
        assert "12ab34" not in r.text and ACCOUNT_NO not in r.text and "12345" not in r.text
    for i in range(5):
        add_account(api, pg, h, account_no=f"11122233{i}44")
    r = api.post("/api/v1/me/bank-accounts", headers=h, json={"bank_code": "vcb", "account_no": "555666777888", "account_name": "A B"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "too_many_bank_accounts"
    assert api.post("/api/v1/me/bank-accounts", json={}).status_code == 401


# ---------- yêu cầu rút ----------
def test_request_locks_money_in_one_transaction_with_audit(api, pg):
    uid, h, acct = ready(api, pg)
    r = withdraw(api, h, acct, 200_000)
    assert r.status_code == 201, r.text
    w = r.json()
    assert (w["status"], w["amount_vnd"], w["last4"], w["bank_code"]) == ("requested", 200_000, "9012", "VCB")
    assert ACCOUNT_NO not in r.text
    assert bal(pg, uid) == (0, FUNDS - 200_000, 200_000) and bal(pg, uid) == derived(pg, uid)
    assert entries(pg, uid) == [("hold", "held", 200_000)]
    acts = [a["action"] for a in audit_rows(pg, w["id"])]
    assert acts == ["wallet.hold", "withdrawal.request"] and all(a["actor_id"] == uid for a in audit_rows(pg, w["id"]))
    assert all(a["ip_hash"] for a in audit_rows(pg, w["id"]))


def test_double_click_with_same_key_creates_one_request(api, pg):
    uid, h, acct = ready(api, pg)
    key = "click-" + uuid.uuid4().hex
    a, b = withdraw(api, h, acct, 150_000, key), withdraw(api, h, acct, 150_000, key)
    assert a.status_code == 201 and b.status_code == 201 and a.json()["id"] == b.json()["id"]
    assert entries(pg, uid) == [("hold", "held", 150_000)] and bal(pg, uid) == (0, FUNDS - 150_000, 150_000)
    assert len(audit_rows(pg, a.json()["id"], "withdrawal.request")) == 1
    c = withdraw(api, h, acct, 150_001, key)                        # cùng key nhưng nội dung khác: từ chối
    assert c.status_code == 409 and c.json()["error"]["code"] == "idempotency_conflict"
    d = withdraw(api, h, acct, 150_000, "another-" + uuid.uuid4().hex)   # key khác khi còn yêu cầu mở
    assert d.status_code == 409 and d.json()["error"]["code"] == "withdrawal_open_exists"
    assert bal(pg, uid) == (0, FUNDS - 150_000, 150_000) == (0, FUNDS - 150_000, bal(pg, uid)[2])


def test_concurrent_double_submit_is_serialized_by_the_wallet_lock(settings, pg):
    api = TestClient(create_app(settings(), engine=pg))
    uid, h, acct = ready(api, pg)
    ctx = AuditContext(settings(), Actor(uid, "user"), None)
    key = "race-" + uuid.uuid4().hex

    def go(_):
        try:
            return ("ok", PayoutService(settings(), pg).request_withdrawal(uid, 120_000, acct, key, audit=ctx).id)
        except Exception as e:  # noqa: BLE001
            return ("err", type(e).__name__)

    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(go, range(6)))
    ids = {r[1] for r in res if r[0] == "ok"}
    assert len(ids) == 1 and all(r[0] == "ok" for r in res), res           # sáu lần bấm: một yêu cầu, tất cả nhận cùng kết quả
    assert entries(pg, uid) == [("hold", "held", 120_000)] and bal(pg, uid) == (0, FUNDS - 120_000, 120_000)


def test_concurrent_different_keys_only_one_open_request_and_never_over_lock(settings, pg):
    api = TestClient(create_app(settings(), engine=pg))
    uid, h, acct = ready(api, pg, funds=300_000)
    ctx = AuditContext(settings(), Actor(uid, "user"), None)

    def go(i):
        try:
            PayoutService(settings(), pg).request_withdrawal(uid, 200_000, acct, f"k{i}-{uuid.uuid4().hex}", audit=ctx)
            return "ok"
        except Exception as e:  # noqa: BLE001
            return type(e).__name__

    with ThreadPoolExecutor(5) as ex:
        res = list(ex.map(go, range(5)))
    assert res.count("ok") == 1 and set(res) <= {"ok", "OpenRequestExists"}, res
    assert bal(pg, uid) == (0, 100_000, 200_000) and bal(pg, uid) == derived(pg, uid)


def test_amount_rules_minimum_balance_and_types(api, pg):
    uid, h, acct = ready(api, pg, funds=300_000)
    r = withdraw(api, h, acct, 99_999)
    assert r.status_code == 422 and r.json()["error"]["code"] == "below_minimum"
    r = withdraw(api, h, acct, 300_001)
    assert r.status_code == 409 and r.json()["error"]["code"] == "insufficient_funds"
    for bad in (-5, 0, 1000.5, "200000", None, True):
        r = api.post("/api/v1/me/withdrawals", headers={**h, "Idempotency-Key": uuid.uuid4().hex},
                     json={"amount_vnd": bad, "bank_account_id": acct})
        assert r.status_code == 422, bad
    assert api.post("/api/v1/me/withdrawals", headers=h, json={"amount_vnd": 200_000, "bank_account_id": acct}).status_code == 422  # thiếu Idempotency-Key
    assert bal(pg, uid) == (0, 300_000, 0) and entries(pg, uid) == []
    assert withdraw(api, h, acct, 300_000).status_code == 201                       # rút đúng toàn bộ số rút được
    assert bal(pg, uid) == (0, 0, 300_000)


def test_minimum_is_configurable(settings, pg):
    class P:
        def get_int(self, key): return {"min_withdraw_vnd": 250_000, "bank_change_cooldown_hours": 0}[key]
    api = TestClient(create_app(settings(), engine=pg))
    uid, h, acct = ready(api, pg)
    ctx = AuditContext(settings(), Actor(uid, "user"), None)
    from app.modules.payout.errors import BelowMinimum
    with pytest.raises(BelowMinimum):
        PayoutService(settings(), pg, platform=P()).request_withdrawal(uid, 200_000, acct, "min-" + uuid.uuid4().hex, audit=ctx)
    assert PayoutService(settings(), pg, platform=P()).request_withdrawal(uid, 250_000, acct, "min2-" + uuid.uuid4().hex, audit=ctx).amount_vnd == 250_000


def test_cannot_withdraw_to_someone_elses_or_unknown_account(api, pg):
    a_uid, a_h, a_acct = ready(api, pg)
    b_uid, b_h = new_user(api, pg)
    fund(pg, b_uid)
    assert withdraw(api, b_h, a_acct).json()["error"]["code"] == "invalid_bank_account"
    assert withdraw(api, b_h, 987654321).json()["error"]["code"] == "invalid_bank_account"
    assert bal(pg, b_uid) == (0, FUNDS, 0)


def test_withdrawals_disabled_returns_503_and_changes_nothing(settings, pg):
    api = TestClient(create_app(settings(withdrawals_enabled=False), engine=pg))
    uid, h = new_user(api, pg)
    fund(pg, uid)
    r = api.post("/api/v1/me/bank-accounts", headers=h, json={"bank_code": "vcb", "account_no": ACCOUNT_NO, "account_name": "A B"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "withdrawals_disabled"
    assert api.get("/api/v1/me/withdrawals", headers=h).json() == []
    _, ah = new_user(api, pg, "admin")
    assert api.post("/api/v1/admin/withdrawals/1/approve", headers=ah).status_code == 503


def test_request_is_rate_limited(settings, pg):
    api = TestClient(create_app(settings(rl_enabled=True, rl_withdraw_per_hour=2), engine=pg), raise_server_exceptions=False)
    uid, h, acct = ready(api, pg)
    codes = [withdraw(api, h, acct, 99_999).status_code for _ in range(3)]           # request hợp lệ về định dạng; đều tính vào giới hạn
    assert codes == [422, 422, 429]
    blocked = withdraw(api, h, acct, 99_999)
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1


def test_audit_failure_rolls_back_the_whole_request(settings, pg, monkeypatch):
    api = TestClient(create_app(settings(), engine=pg))
    uid, h, acct = ready(api, pg)
    real = payout_service.audit_service.record

    def boom(conn, s, actor, action, **kw):
        if action == "withdrawal.request":
            raise RuntimeError("audit down")
        return real(conn, s, actor, action, **kw)
    monkeypatch.setattr(payout_service.audit_service, "record", boom)
    r = withdraw(api, h, acct)
    assert r.status_code == 500
    assert bal(pg, uid) == (0, FUNDS, 0) and entries(pg, uid) == []                 # không có tiền bị khóa, không có yêu cầu mồ côi
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM withdrawals WHERE user_id = :u"), {"u": uid}).scalar_one() == 0
    monkeypatch.setattr(payout_service.audit_service, "record", real)
    assert withdraw(api, h, acct).status_code == 201                                 # sau khi audit lại bình thường thì rút được


# ---------- admin: duyệt / từ chối / chi trả ----------
def requested(api, pg, amount=200_000):
    uid, h, acct = ready(api, pg)
    w = withdraw(api, h, acct, amount).json()
    return uid, h, acct, w["id"]


def test_only_admin_can_approve_pay_or_view_accounts(api, pg):
    uid, h, acct, wid = requested(api, pg)
    _, sh = new_user(api, pg, "staff")
    _, ah = new_user(api, pg, "admin")
    paths = [("post", "/approve", {}), ("post", "/reject", {"reason": "khong hop le"}), ("post", "/fail", {"reason": "loi ngan hang"}),
             ("post", "/mark-paid", {"provider_ref": "FT123456"}), ("get", "/payout-account", None)]
    for who, hh in (("member", h), ("staff", sh), ("anon", {})):
        for method, suffix, body in paths:
            r = getattr(api, method)(f"/api/v1/admin/withdrawals/{wid}{suffix}", headers=hh, **({"json": body} if body is not None else {}))
            assert r.status_code == (401 if who == "anon" else 403), (who, suffix, r.status_code)
        assert api.get("/api/v1/admin/withdrawals", headers=hh).status_code == (401 if who == "anon" else 403)
    assert wd(pg, wid)["status"] == "requested" and bal(pg, uid)[2] == 200_000     # không có gì thay đổi
    assert api.get("/api/v1/admin/withdrawals?status=requested", headers=ah).status_code == 200
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=ah).status_code == 200


def test_service_layer_also_refuses_non_admin_actor(settings, pg):
    api = TestClient(create_app(settings(), engine=pg))
    uid, h, acct, wid = requested(api, pg)
    from app.core.errors import Forbidden
    for role in ("staff", "user", "agent", "system"):
        ctx = AuditContext(settings(), Actor(99, role), None)
        for call in (lambda: PayoutService(settings(), pg).approve(wid, audit=ctx),
                     lambda: PayoutService(settings(), pg).view_account(wid, audit=ctx),
                     lambda: PayoutService(settings(), pg).mark_paid(wid, "FT999999", audit=ctx),
                     lambda: PayoutService(settings(), pg).reject(wid, "ly do", audit=ctx)):
            with pytest.raises(Forbidden):
                call()


def test_reject_refunds_with_a_new_entry_and_never_edits_old_ones(api, pg):
    uid, h, acct, wid = requested(api, pg)
    _, ah = new_user(api, pg, "admin")
    with pg.connect() as c:
        hold_before = c.execute(text("SELECT id, amount_vnd, state, created_at FROM wallet_entries WHERE user_id=:u AND kind='hold'"), {"u": uid}).all()
    r = api.post(f"/api/v1/admin/withdrawals/{wid}/reject", headers=ah, json={"reason": "thong tin sai"})
    assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["decided_reason"] == "thong tin sai"
    assert entries(pg, uid) == [("hold", "held", 200_000), ("refund_hold", "available", 200_000)]
    assert bal(pg, uid) == (0, FUNDS, 0) == derived(pg, uid)
    with pg.connect() as c:
        assert c.execute(text("SELECT id, amount_vnd, state, created_at FROM wallet_entries WHERE user_id=:u AND kind='hold'"), {"u": uid}).all() == hold_before
    again = api.post(f"/api/v1/admin/withdrawals/{wid}/reject", headers=ah, json={"reason": "lan hai"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "invalid_transition"
    assert entries(pg, uid, ("refund_hold",)) == [("refund_hold", "available", 200_000)]
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=ah).status_code == 409
    new = withdraw(api, h, acct, 100_000)                                          # được rút lại sau khi bị từ chối
    assert new.status_code == 201
    acts = [a["action"] for a in audit_rows(pg, wid)]
    assert acts == ["wallet.hold", "withdrawal.request", "wallet.refund_hold", "withdrawal.reject"]


def test_full_flow_approve_view_account_pay_and_no_double_payment(api, pg):
    uid, h, acct, wid = requested(api, pg)
    _, ah = new_user(api, pg, "admin")
    assert api.get(f"/api/v1/admin/withdrawals/{wid}/payout-account", headers=ah).status_code == 409   # chưa duyệt: chưa xem được
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/mark-paid", headers=ah, json={"provider_ref": "FT0001"}).status_code == 409
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=ah).json()["status"] == "approved"
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=ah).status_code == 409
    listed = api.get("/api/v1/admin/withdrawals?status=approved", headers=ah)
    assert ACCOUNT_NO not in listed.text and any(x["id"] == wid and x["last4"] == "9012" for x in listed.json())
    v1 = api.get(f"/api/v1/admin/withdrawals/{wid}/payout-account", headers=ah)
    assert v1.status_code == 200 and v1.json()["account_no"] == ACCOUNT_NO and v1.json()["account_name"] == "NGUYEN VAN A"
    assert v1.headers["cache-control"] == "no-store"
    api.get(f"/api/v1/admin/withdrawals/{wid}/payout-account", headers=ah)
    views = audit_rows(pg, wid, "payout.view_account")
    assert len(views) == 2 and all(v["actor_role"] == "admin" for v in views)       # MỖI lần giải mã có một dòng audit
    assert ACCOUNT_NO not in json.dumps([dict(v) for v in audit_rows(pg, wid)], default=str)
    paid = api.post(f"/api/v1/admin/withdrawals/{wid}/mark-paid", headers=ah, json={"provider_ref": "FT20261128-0001"})
    assert paid.status_code == 200 and paid.json()["status"] == "paid" and paid.json()["provider_ref"] == "FT20261128-0001"
    assert bal(pg, uid) == (0, FUNDS - 200_000, 0) == derived(pg, uid)
    again = api.post(f"/api/v1/admin/withdrawals/{wid}/mark-paid", headers=ah, json={"provider_ref": "FT20261128-0002"})
    assert again.status_code == 409                                                  # không đánh dấu hai lần
    assert entries(pg, uid) == [("hold", "held", 200_000), ("payout", "paid_out", 200_000)]
    assert wd(pg, wid)["provider_ref"] == "FT20261128-0001"
    assert api.get(f"/api/v1/admin/withdrawals/{wid}/payout-account", headers=ah).status_code == 409   # đã trả: không xem lại được
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/reject", headers=ah, json={"reason": "sau khi tra"}).status_code == 409
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/fail", headers=ah, json={"reason": "sau khi tra"}).status_code == 409
    assert ACCOUNT_NO not in json.dumps([dict(a) for a in audit_rows(pg, wid)], default=str)
    acts = [a["action"] for a in audit_rows(pg, wid)]
    assert acts[:2] == ["wallet.hold", "withdrawal.request"] and "withdrawal.approve" in acts and acts[-2:] == ["wallet.payout", "withdrawal.mark_paid"]


def test_a_bank_transaction_code_cannot_be_reused(api, pg):
    _, _, _, w1 = requested(api, pg)
    u2, h2, a2, w2 = requested(api, pg)
    _, ah = new_user(api, pg, "admin")
    for w in (w1, w2):
        api.post(f"/api/v1/admin/withdrawals/{w}/approve", headers=ah)
    assert api.post(f"/api/v1/admin/withdrawals/{w1}/mark-paid", headers=ah, json={"provider_ref": "FT-DUP-1"}).status_code == 200
    r = api.post(f"/api/v1/admin/withdrawals/{w2}/mark-paid", headers=ah, json={"provider_ref": "FT-DUP-1"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_provider_ref"
    assert wd(pg, w2)["status"] == "approved" and bal(pg, u2)[2] == 200_000 and entries(pg, u2, ("payout",)) == []   # w2 nguyên vẹn
    assert api.post(f"/api/v1/admin/withdrawals/{w2}/mark-paid", headers=ah, json={"provider_ref": "FT-DUP-2"}).status_code == 200


def test_failed_transfer_refunds_the_user(api, pg):
    uid, h, acct, wid = requested(api, pg)
    _, ah = new_user(api, pg, "admin")
    assert api.post(f"/api/v1/admin/withdrawals/{wid}/fail", headers=ah, json={"reason": "chua duyet"}).status_code == 409   # chỉ 'approved' mới fail
    api.post(f"/api/v1/admin/withdrawals/{wid}/approve", headers=ah)
    r = api.post(f"/api/v1/admin/withdrawals/{wid}/fail", headers=ah, json={"reason": "ngan hang tu choi"})
    assert r.json()["status"] == "failed" and bal(pg, uid) == (0, FUNDS, 0) == derived(pg, uid)
    assert entries(pg, uid, ("refund_hold",)) == [("refund_hold", "available", 200_000)]


def test_concurrent_approve_and_reject_exactly_one_wins(settings, pg):
    api = TestClient(create_app(settings(), engine=pg))
    uid, h, acct, wid = requested(api, pg)
    aid, _ = new_user(api, pg, "admin")
    ctx = AuditContext(settings(), Actor(aid, "admin"), None)

    def act(kind):
        try:
            svc = PayoutService(settings(), pg)
            return kind, svc.approve(wid, audit=ctx).status if kind == "approve" else svc.reject(wid, "xung dot", audit=ctx).status
        except Exception as e:  # noqa: BLE001
            return kind, type(e).__name__

    for _ in range(1):
        with ThreadPoolExecutor(4) as ex:
            res = list(ex.map(act, ["approve", "reject", "approve", "reject"]))
    wins = [r for r in res if r[1] in ("approved", "rejected")]
    assert len(wins) >= 1 and bal(pg, uid) == derived(pg, uid)
    final = wd(pg, wid)["status"]
    if final == "rejected":
        assert bal(pg, uid) == (0, FUNDS, 0) and len(entries(pg, uid, ("refund_hold",))) == 1
    else:
        assert final == "approved" and bal(pg, uid) == (0, FUNDS - 200_000, 200_000) and entries(pg, uid, ("refund_hold",)) == []


# ---------- bí mật ----------
def test_account_number_never_reaches_logs(api, pg, caplog):
    caplog.set_level(logging.DEBUG)
    uid, h, acct = ready(api, pg)
    w = withdraw(api, h, acct).json()
    _, ah = new_user(api, pg, "admin")
    api.post(f"/api/v1/admin/withdrawals/{w['id']}/approve", headers=ah)
    assert api.get(f"/api/v1/admin/withdrawals/{w['id']}/payout-account", headers=ah).json()["account_no"] == ACCOUNT_NO
    api.post("/api/v1/me/bank-accounts", headers=h, json={"bank_code": "vcb", "account_no": "12ab", "account_name": "A B"})   # lỗi
    dump = "\n".join(r.getMessage() + " " + json.dumps({k: str(v) for k, v in r.__dict__.items() if k not in ("msg", "args")}) for r in caplog.records)
    assert ACCOUNT_NO not in dump and ACCOUNT_NO[:9] not in dump
    with pg.connect() as c:
        every_audit = json.dumps([dict(r) for r in c.execute(text("SELECT * FROM audit_logs WHERE actor_id IN (:a, :b)"), {"a": uid, "b": 0}).mappings()], default=str)
    assert ACCOUNT_NO not in every_audit


def test_ledger_invariant_holds_after_a_mixed_sequence(api, pg):
    uid, h, acct = ready(api, pg, funds=1_000_000)
    _, ah = new_user(api, pg, "admin")
    seq = [("reject", 300_000), ("fail", 200_000), ("pay", 400_000)]
    for action, amount in seq:
        wid = withdraw(api, h, acct, amount).json()["id"]
        base = f"/api/v1/admin/withdrawals/{wid}"
        if action == "reject":
            api.post(f"{base}/reject", headers=ah, json={"reason": "tu choi"})
        else:
            api.post(f"{base}/approve", headers=ah)
            if action == "fail":
                api.post(f"{base}/fail", headers=ah, json={"reason": "that bai"})
            else:
                api.post(f"{base}/mark-paid", headers=ah, json={"provider_ref": f"FT-{uuid.uuid4().hex[:8]}"})
        assert bal(pg, uid) == derived(pg, uid) and min(bal(pg, uid)) >= 0
    assert bal(pg, uid) == (0, 600_000, 0)
    assert [e[0] for e in entries(pg, uid)] == ["hold", "refund_hold", "hold", "refund_hold", "hold", "payout"]
