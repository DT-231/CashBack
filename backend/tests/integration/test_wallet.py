"""Ví trên Postgres thật. Đồng hồ giả ở năm 2100 để không đụng dữ liệu dev; mọi dữ liệu test được dọn sạch."""
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.main_api import create_app
from app.modules.orders.service import OrderReader, SyncHealth
from app.modules.platform_settings.errors import InvalidSetting
from app.modules.platform_settings.service import PlatformSettings
from app.modules.wallet import ledger
from app.modules.wallet.errors import LedgerError
from app.modules.wallet.service import WalletService
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
D = lambda day: datetime(2100, 1, day, tzinfo=UTC)   # noqa: E731
COMMISSION = 4_037_500_000                            # 40.375đ -> 60% = 24.225đ
PW = "mat-khau-hop-le-1"


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        c.execute(text("ALTER TABLE wallet_entries DISABLE TRIGGER wallet_entries_no_change"))
        users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text(f"DELETE FROM wallet_entries WHERE user_id IN {users}"))
        c.execute(text("ALTER TABLE wallet_entries ENABLE TRIGGER wallet_entries_no_change"))
        c.execute(text(f"DELETE FROM wallets WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM shopee_orders WHERE order_sn LIKE 'ITEST-W-%'"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
        c.execute(text("DELETE FROM settings WHERE effective_from >= '2099-01-01'"))
    eng.dispose()


class Reader(OrderReader):
    """Đọc đơn thật từ DB, nhưng sức khỏe sync do test điều khiển."""
    def __init__(self, engine, clock, healthy=True, age=timedelta(0)):
        super().__init__(engine)
        self.clock, self.healthy, self.age = clock, healthy, age

    def sync_health(self):
        return SyncHealth("ok" if self.healthy else "partial", self.clock() - self.age)


def wallet_svc(settings, pg, now, **kw):
    clock = lambda: now   # noqa: E731
    return WalletService(settings, pg, Reader(pg, clock, **kw), PlatformSettings(pg, clock), clock)


@pytest.fixture
def settings(make_settings):
    return make_settings(database_url=DB_URL, jwt_secret="j" * 40, subid_secret="s" * 32)


def make_user(pg):
    with pg.begin() as c:
        return c.execute(text("INSERT INTO users(email, password_hash, status) VALUES (:e, 'x', 'active') RETURNING id"),
                         {"e": f"itest-{uuid.uuid4().hex[:10]}@example.test"}).scalar_one()


def make_order(pg, user_id, commission=COMMISSION, status="PENDING", completed_at=None):
    with pg.begin() as c:
        return c.execute(text(
            "INSERT INTO shopee_orders(order_sn, status, source_type, user_id, commission_micro, completed_at) "
            "VALUES (:s, :st, 'user', :u, :c, :ca) RETURNING id"),
            {"s": f"ITEST-W-{uuid.uuid4().hex[:8]}", "st": status, "u": user_id, "c": commission, "ca": completed_at}).scalar_one()


def set_order(pg, order_id, **cols):
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    with pg.begin() as c:
        c.execute(text(f"UPDATE shopee_orders SET {sets} WHERE id = :id"), {**cols, "id": order_id})


def bal(pg, user_id):
    with pg.connect() as c:
        r = c.execute(text("SELECT pending_vnd, available_vnd, held_vnd FROM wallets WHERE user_id = :u"), {"u": user_id}).one_or_none()
    return tuple(r) if r else (0, 0, 0)


def derived(pg, user_id):
    """Số dư suy ra từ sổ cái: phải luôn bằng cột trong `wallets`."""
    with pg.connect() as c:
        rows = c.execute(text("SELECT kind, state, amount_vnd FROM wallet_entries WHERE user_id = :u"), {"u": user_id}).all()
    tot = [0, 0, 0]
    for kind, state, amt in rows:
        for i, d in enumerate(ledger.DELTAS[(kind, state)]):
            tot[i] += d * amt
    return tuple(tot)


def entries(pg, user_id):
    with pg.connect() as c:
        return [tuple(r) for r in c.execute(text("SELECT kind, state, amount_vnd FROM wallet_entries WHERE user_id = :u ORDER BY id"), {"u": user_id})]


def check_invariant(pg, *users):
    for u in users:
        assert bal(pg, u) == derived(pg, u) and min(bal(pg, u)) >= 0


# ---------- T-031: đơn -> ví ----------
def test_accrual_uses_60_percent_rounded_down_and_is_idempotent(pg, settings):
    u = make_user(pg)
    make_order(pg, u)
    w = wallet_svc(settings, pg, D(1))
    r = w.settle()
    assert (r.accrued, bal(pg, u)) == (1, (24_225, 0, 0))
    again = w.settle()
    assert (again.accrued, again.released, bal(pg, u)) == (0, 0, (24_225, 0, 0)) and len(entries(pg, u)) == 1
    check_invariant(pg, u)


def test_zero_commission_creates_nothing_and_orphans_are_ignored_until_assigned(pg, settings):
    u = make_user(pg)
    make_order(pg, u, commission=0)
    with pg.begin() as c:
        c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, commission_micro) "
                       "VALUES ('ITEST-W-orphan', 'PENDING', 'unknown', :c)"), {"c": COMMISSION})
    wallet_svc(settings, pg, D(1)).settle()
    assert entries(pg, u) == [] and bal(pg, u) == (0, 0, 0)
    with pg.begin() as c:                                    # staff gán tay đơn mồ côi
        c.execute(text("UPDATE shopee_orders SET user_id = :u, source_type = 'user' WHERE order_sn = 'ITEST-W-orphan'"), {"u": u})
    wallet_svc(settings, pg, D(2)).settle()
    assert bal(pg, u) == (24_225, 0, 0)


def test_share_change_applies_to_new_orders_only(pg, settings):
    u = make_user(pg)
    a = make_order(pg, u)
    wallet_svc(settings, pg, D(1)).settle()
    PlatformSettings(pg, lambda: D(2)).set_int("user_share_bp", 5000, effective_from=D(2))
    b = make_order(pg, u)
    wallet_svc(settings, pg, D(5)).settle()
    with pg.connect() as c:
        shares = dict(c.execute(text("SELECT order_id, share_bp FROM wallet_entries WHERE user_id = :u"), {"u": u}).all())
    assert shares == {a: 6000, b: 5000} and bal(pg, u)[0] == 24_225 + 20_187   # 40.375 x 50% = 20.187,5 -> 20.187
    set_order(pg, a, status="COMPLETED", completed_at=D(1))
    wallet_svc(settings, pg, D(20)).settle()
    assert bal(pg, u) == (20_187, 24_225, 0)                 # đơn cũ vẫn đúng 60%
    check_invariant(pg, u)


def test_release_waits_for_hold_days_and_a_healthy_sync(pg, settings):
    u = make_user(pg)
    make_order(pg, u, status="COMPLETED", completed_at=D(1))
    r = wallet_svc(settings, pg, D(5)).settle()              # mới 4 ngày < 7
    assert (r.released, r.release_blocked, bal(pg, u)) == (0, 0, (24_225, 0, 0))
    r = wallet_svc(settings, pg, D(9), healthy=False).settle()   # đủ hạn nhưng sync dở dang
    assert (r.released, r.release_blocked, bal(pg, u)) == (0, 1, (24_225, 0, 0))
    r = wallet_svc(settings, pg, D(9), age=timedelta(hours=25)).settle()   # sync ok nhưng đã cũ quá 24 giờ
    assert (r.released, r.release_blocked, bal(pg, u)) == (0, 1, (24_225, 0, 0))
    r = wallet_svc(settings, pg, D(9)).settle()
    assert (r.released, bal(pg, u)) == (1, (0, 24_225, 0))
    assert wallet_svc(settings, pg, D(10)).settle().released == 0 and bal(pg, u) == (0, 24_225, 0)
    check_invariant(pg, u)


def test_hold_days_is_configurable_and_zero_releases_immediately(pg, settings):
    u = make_user(pg)
    PlatformSettings(pg, lambda: D(1)).set_int("hold_days", 0, effective_from=D(1))
    make_order(pg, u, status="COMPLETED", completed_at=D(1))
    wallet_svc(settings, pg, D(1)).settle()
    assert bal(pg, u) == (0, 24_225, 0)


def test_completed_order_without_completion_time_is_never_released(pg, settings):
    u = make_user(pg)
    make_order(pg, u, status="COMPLETED", completed_at=None)
    wallet_svc(settings, pg, D(30)).settle()
    assert bal(pg, u) == (24_225, 0, 0)


def test_cancelled_while_pending_removes_the_pending_amount(pg, settings):
    u = make_user(pg)
    oid = make_order(pg, u)
    wallet_svc(settings, pg, D(1)).settle()
    set_order(pg, oid, status="CANCELLED")
    r = wallet_svc(settings, pg, D(2)).settle()
    assert (r.cancelled, bal(pg, u)) == (1, (0, 0, 0))
    wallet_svc(settings, pg, D(3)).settle()
    assert bal(pg, u) == (0, 0, 0) and len(entries(pg, u)) == 2
    check_invariant(pg, u)


def test_order_first_seen_already_cancelled_is_never_credited(pg, settings):
    u = make_user(pg)
    make_order(pg, u, status="CANCELLED")
    make_order(pg, u, status="RETURNED")
    wallet_svc(settings, pg, D(1)).settle()
    assert entries(pg, u) == []


def test_returned_after_release_reverses_available(pg, settings):
    u = make_user(pg)
    oid = make_order(pg, u, status="COMPLETED", completed_at=D(1))
    wallet_svc(settings, pg, D(9)).settle()
    set_order(pg, oid, status="RETURNED")
    r = wallet_svc(settings, pg, D(10)).settle()
    assert (r.reversed, r.losses, bal(pg, u)) == (1, 0, (0, 0, 0))
    wallet_svc(settings, pg, D(11)).settle()
    assert len(entries(pg, u)) == 3                          # accrual, release, reverse: không thu hồi lần hai
    check_invariant(pg, u)


def test_returned_after_the_user_already_withdrew_never_goes_negative(pg, settings):
    u = make_user(pg)
    oid = make_order(pg, u, status="COMPLETED", completed_at=D(1))
    wallet_svc(settings, pg, D(9)).settle()                  # available = 24.225
    with pg.begin() as c:                                    # user rút 20.000 (hold + payout)
        ledger.post(c, u, "hold", "held", 20_000, f"t:{oid}:h")
        ledger.post(c, u, "payout", "paid_out", 20_000, f"t:{oid}:p")
    assert bal(pg, u) == (0, 4_225, 0)
    set_order(pg, oid, status="RETURNED")
    r = wallet_svc(settings, pg, D(10)).settle()
    assert (r.reversed, r.losses, bal(pg, u)) == (1, 1, (0, 0, 0))
    assert ("adjust", "reversed", 20_000) in entries(pg, u) and ("reverse", "reversed", 4_225) in entries(pg, u)
    check_invariant(pg, u)


def test_money_held_for_a_withdrawal_is_not_clawed_back(pg, settings):
    u = make_user(pg)
    oid = make_order(pg, u, status="COMPLETED", completed_at=D(1))
    wallet_svc(settings, pg, D(9)).settle()
    with pg.begin() as c:
        ledger.post(c, u, "hold", "held", 24_225, f"t:{oid}:h")   # đang chờ chuyển khoản
    set_order(pg, oid, status="RETURNED")
    r = wallet_svc(settings, pg, D(10)).settle()
    assert (r.reversed, r.losses) == (0, 1) and bal(pg, u) == (0, 0, 24_225)   # khoản đang khóa không bị đụng
    check_invariant(pg, u)


def test_commission_change_adjusts_while_pending_but_not_after_release(pg, settings):
    u = make_user(pg)
    oid = make_order(pg, u, commission=COMMISSION)
    wallet_svc(settings, pg, D(1)).settle()
    set_order(pg, oid, commission_micro=2_000_000_000)        # 20.000đ -> 12.000đ
    wallet_svc(settings, pg, D(2)).settle()
    assert bal(pg, u) == (12_000, 0, 0)
    set_order(pg, oid, commission_micro=COMMISSION)           # tăng lại -> 24.225đ
    wallet_svc(settings, pg, D(3)).settle()
    assert bal(pg, u) == (24_225, 0, 0)
    set_order(pg, oid, status="COMPLETED", completed_at=D(3))
    wallet_svc(settings, pg, D(12)).settle()
    assert bal(pg, u) == (0, 24_225, 0)
    set_order(pg, oid, commission_micro=8_000_000_000)        # đã release: không điều chỉnh nữa
    wallet_svc(settings, pg, D(13)).settle()
    assert bal(pg, u) == (0, 24_225, 0)
    check_invariant(pg, u)


def test_concurrent_settles_never_double_credit(pg, settings):
    users = [make_user(pg) for _ in range(3)]
    for u in users:
        for _ in range(3):
            make_order(pg, u)
    errors = []

    def run():
        try:
            wallet_svc(settings, pg, D(1)).settle()
        except Exception as e:   # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=run) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    for u in users:
        assert bal(pg, u) == (3 * 24_225, 0, 0) and len(entries(pg, u)) == 3
    check_invariant(pg, *users)


def test_ledger_invariant_after_a_mixed_history(pg, settings):
    u = make_user(pg)
    ids = [make_order(pg, u, commission=c) for c in (COMMISSION, 1_000_000_000, 777_777_777, 5_000_000_000)]
    wallet_svc(settings, pg, D(1)).settle()
    set_order(pg, ids[0], status="COMPLETED", completed_at=D(1))
    set_order(pg, ids[1], status="CANCELLED")
    set_order(pg, ids[2], status="COMPLETED", completed_at=D(2))
    wallet_svc(settings, pg, D(12)).settle()
    set_order(pg, ids[2], status="RETURNED")
    set_order(pg, ids[3], commission_micro=123)
    wallet_svc(settings, pg, D(13)).settle()
    check_invariant(pg, u)
    assert bal(pg, u)[0] == 0 and bal(pg, u)[1] == 24_225


# ---------- T-030: sổ cái ----------
def test_ledger_rejects_bad_input_and_duplicates(pg):
    u = make_user(pg)
    with pg.begin() as c:
        assert ledger.post(c, u, "accrual", "pending", 100, "itest:dup") is True
        assert ledger.post(c, u, "accrual", "pending", 100, "itest:dup") is False     # trùng khóa: không đổi số dư
    assert bal(pg, u) == (100, 0, 0)
    for args in ((u, "accrual", "available", 5, "k1"), (u, "nope", "pending", 5, "k2"), (u, "accrual", "pending", 0, "k3"),
                 (u, "accrual", "pending", -5, "k4"), (u, "accrual", "pending", True, "k5"), (u, "accrual", "pending", 1.5, "k6")):
        with pytest.raises(LedgerError), pg.begin() as c:
            ledger.post(c, *args[:5])
    assert bal(pg, u) == (100, 0, 0) and len(entries(pg, u)) == 1


def test_ledger_cannot_overdraw_and_failed_post_leaves_no_trace(pg):
    u = make_user(pg)
    with pg.begin() as c:
        ledger.post(c, u, "accrual", "pending", 100, "itest:a")
    with pytest.raises(IntegrityError), pg.begin() as c:      # hold khi available = 0 -> CHECK ở DB chặn
        ledger.post(c, u, "hold", "held", 1, "itest:h")
    assert bal(pg, u) == (100, 0, 0) and len(entries(pg, u)) == 1
    check_invariant(pg, u)


def test_ledger_is_append_only(pg):
    u = make_user(pg)
    with pg.begin() as c:
        ledger.post(c, u, "accrual", "pending", 100, "itest:ao")
    for sql in ("UPDATE wallet_entries SET amount_vnd = 1 WHERE idem_key = 'itest:ao'",
                "DELETE FROM wallet_entries WHERE idem_key = 'itest:ao'"):
        with pytest.raises(DBAPIError), pg.begin() as c:
            c.execute(text(sql))
    assert entries(pg, u) == [("accrual", "pending", 100)]


def test_withdrawal_flow_primitives_keep_the_invariant(pg):
    u = make_user(pg)
    with pg.begin() as c:
        ledger.post(c, u, "accrual", "pending", 500, "itest:w1")
        ledger.post(c, u, "release", "available", 500, "itest:w2")
        ledger.post(c, u, "hold", "held", 300, "itest:w3")
        ledger.post(c, u, "refund_hold", "available", 100, "itest:w4")
        ledger.post(c, u, "payout", "paid_out", 200, "itest:w5")
    assert bal(pg, u) == (0, 300, 0)
    check_invariant(pg, u)


# ---------- T-032: cấu hình ----------
def test_platform_settings_defaults_effective_dates_and_validation(pg):
    ps = PlatformSettings(pg, lambda: D(1))
    assert ps.get_int("user_share_bp", at=datetime(1999, 1, 1, tzinfo=UTC)) == 6000   # trước mọi bản ghi: mặc định 60%
    ps.set_int("hold_days", 14, effective_from=D(10))
    assert ps.get_int("hold_days", at=D(9)) == 7 and ps.get_int("hold_days", at=D(10)) == 14
    with pytest.raises(InvalidSetting):                                                # cùng mốc: KHÔNG ghi đè
        ps.set_int("hold_days", 3, effective_from=D(10))
    assert ps.get_int("hold_days", at=D(11)) == 14
    with pytest.raises(InvalidSetting):                                                # quá khứ: KHÔNG đổi hồi tố
        ps.set_int("hold_days", 1, effective_from=D(1) - timedelta(seconds=1))
    ps.set_int("hold_days", 21)                                                        # mặc định: có hiệu lực từ bây giờ
    assert ps.get_int("hold_days", at=D(1)) == 21 and ps.get_int("hold_days", at=D(9)) == 21
    for key, bad in (("user_share_bp", 10_001), ("user_share_bp", -1), ("hold_days", 121), ("hold_days", True),
                     ("hold_days", 1.5), ("min_withdraw_vnd", -5), ("khong_co", 1)):
        with pytest.raises(InvalidSetting):
            ps.set_int(key, bad)
    with pytest.raises(InvalidSetting):
        ps.get_int("khong_co")


def test_corrupt_setting_value_falls_back_to_the_default(pg):
    with pg.begin() as c:
        c.execute(text("INSERT INTO settings(key, value, effective_from) VALUES ('user_share_bp', '\"abc\"'::jsonb, :t)"), {"t": D(1)})
        c.execute(text("INSERT INTO settings(key, value, effective_from) VALUES ('hold_days', '99999'::jsonb, :t)"), {"t": D(1)})
    ps = PlatformSettings(pg, lambda: D(2))
    assert ps.get_int("user_share_bp") == 6000 and ps.get_int("hold_days") == 7


# ---------- API ----------
@pytest.fixture
def api(settings, pg):
    return TestClient(create_app(settings, engine=pg), raise_server_exceptions=False)


def login_new_user(api):
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    tok = api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return uid, {"Authorization": f"Bearer {tok}"}


def test_wallet_api_shows_only_my_money(api, pg, settings):
    a, ha = login_new_user(api)
    b, hb = login_new_user(api)
    r = api.get("/api/v1/me/wallet", headers=ha)
    assert r.status_code == 200 and r.json() == {"pending_vnd": 0, "available_vnd": 0, "held_vnd": 0, "share_pct": 60.0}
    make_order(pg, a)
    wallet_svc(settings, pg, D(1)).settle()
    assert api.get("/api/v1/me/wallet", headers=ha).json()["pending_vnd"] == 24_225
    assert api.get("/api/v1/me/wallet", headers=hb).json()["pending_vnd"] == 0
    mine = api.get("/api/v1/me/wallet/entries", headers=ha).json()
    assert [(e["kind"], e["state"], e["amount_vnd"]) for e in mine] == [("accrual", "pending", 24_225)]
    assert api.get("/api/v1/me/wallet/entries", headers=hb).json() == []
    assert api.get("/api/v1/me/wallet/entries", params={"limit": 0}, headers=ha).status_code == 422


def test_wallet_api_requires_login(api):
    assert api.get("/api/v1/me/wallet").status_code == 401
    assert api.get("/api/v1/me/wallet/entries").status_code == 401


def test_worker_settle_once_runs_and_reports(monkeypatch, capsys, pg):
    import json

    from app import main_worker
    u = make_user(pg)
    make_order(pg, u)
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("SUBID_SECRET", "s" * 32)
    assert main_worker.main(["settle-once"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["settle"]["accrued"] >= 1 and out["settle"]["errors"] == 0
    assert bal(pg, u) == (24_225, 0, 0) or bal(pg, u)[0] > 0


# ---------- sửa theo review ----------
def test_cancelled_after_release_is_reversed_like_a_return(pg, settings):
    u = make_user(pg)
    oid = make_order(pg, u, status="COMPLETED", completed_at=D(1))
    wallet_svc(settings, pg, D(9)).settle()
    set_order(pg, oid, status="CANCELLED")                    # Shopee thu hồi sau khi hoàn tất
    r = wallet_svc(settings, pg, D(10)).settle()
    assert (r.reversed, r.losses, bal(pg, u)) == (1, 0, (0, 0, 0))
    check_invariant(pg, u)


def test_hold_days_follows_the_setting_in_force_when_the_order_completed(pg, settings):
    u = make_user(pg)
    early = make_order(pg, u, status="COMPLETED", completed_at=D(1))
    make_order(pg, u, status="COMPLETED", completed_at=D(6))
    PlatformSettings(pg, lambda: D(5)).set_int("hold_days", 30, effective_from=D(5))   # từ ngày 5 trở đi giữ 30 ngày
    w = wallet_svc(settings, pg, D(9))
    w.settle()
    with pg.connect() as c:
        released = {r[0] for r in c.execute(text("SELECT order_id FROM wallet_entries WHERE user_id = :u AND kind = 'release'"), {"u": u})}
    assert released == {early}                                # đơn hoàn tất trước khi đổi vẫn theo 7 ngày; đơn sau theo 30 ngày
    assert bal(pg, u) == (24_225, 24_225, 0)
    wallet_svc(settings, pg, D(6) + timedelta(days=30)).settle()
    assert bal(pg, u) == (0, 2 * 24_225, 0)


def test_failed_order_does_not_inflate_the_counters_or_leave_partial_ledger(pg, settings, monkeypatch):
    from app.modules.wallet import service as svc_mod
    u = make_user(pg)
    make_order(pg, u, status="COMPLETED", completed_at=D(1))
    real = ledger.post

    def flaky(conn, user_id, kind, *a, **kw):
        if kind == "release":
            raise RuntimeError("deadlock giả lập")
        return real(conn, user_id, kind, *a, **kw)
    monkeypatch.setattr(svc_mod.ledger, "post", flaky)
    r = wallet_svc(settings, pg, D(9)).settle()
    assert (r.accrued, r.released, r.errors, r.orders) == (0, 0, 1, 0)     # accrual đã bị rollback thì không được đếm
    assert entries(pg, u) == [] and bal(pg, u) == (0, 0, 0)
    monkeypatch.setattr(svc_mod.ledger, "post", real)
    r = wallet_svc(settings, pg, D(9)).settle()                            # lần sau tự lành (idempotent)
    assert (r.accrued, r.released, r.errors, bal(pg, u)) == (1, 1, 0, (0, 24_225, 0))


def test_settled_orders_are_skipped_without_touching_the_wallet_lock(pg, settings):
    u = make_user(pg)
    make_order(pg, u, status="COMPLETED", completed_at=D(1))
    make_order(pg, u, status="CANCELLED")
    wallet_svc(settings, pg, D(9)).settle()
    assert bal(pg, u) == (0, 24_225, 0)
    holder = pg.connect()
    out = {}
    try:
        holder.execute(text("SELECT 1 FROM wallets WHERE user_id = :u FOR UPDATE"), {"u": u})   # ai đó đang khóa ví (vd rút tiền)
        t = threading.Thread(target=lambda: out.setdefault("r", wallet_svc(settings, pg, D(20)).settle()))
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "settle bị chặn bởi khóa ví dù mọi đơn đã chốt"
    finally:
        holder.rollback()
        holder.close()
    assert out["r"].orders == 0 and out["r"].errors == 0


def test_needs_action_matrix_and_negative_commission_is_clamped(pg, settings):
    from app.modules.orders.service import AttributedOrder
    w = wallet_svc(settings, pg, D(20))
    share_at, hold_at = w.platform.resolver("user_share_bp"), w.platform.resolver("hold_days")

    def need(status, t, commission=COMMISSION, completed=D(1)):
        return w._needs_action(AttributedOrder(1, 1, status, commission, completed), t, D(20), share_at, hold_at)
    assert need("PENDING", {}) is True                                     # chưa accrual
    assert need("PENDING", {"accrual": 24_225, "_share": 6000}) is False   # đã khớp, chờ tiếp
    assert need("COMPLETED", {"accrual": 24_225, "_share": 6000}) is True  # hết hạn giữ: cần release
    assert need("COMPLETED", {"accrual": 24_225, "release": 24_225, "_share": 6000}) is False
    assert need("RETURNED", {"accrual": 24_225, "release": 24_225}) is True
    assert need("RETURNED", {"accrual": 24_225, "release": 24_225, "reverse": 24_225}) is False
    assert need("CANCELLED", {"accrual": 5, "cancel": 5}) is False and need("CANCELLED", {}) is False
    assert need("PENDING", {}, commission=-5) is False                     # âm = 0, không ném lỗi


def test_settle_result_orders_counts_only_processed_orders(pg, settings):
    u = make_user(pg)
    make_order(pg, u)
    make_order(pg, u, commission=0)
    assert wallet_svc(settings, pg, D(1)).settle().orders == 1


# ---------- GET /me/orders (T-034): mốc dự kiến do backend tính ----------
def by_id(orders):
    return {o.id: o for o in orders}


def test_my_orders_states_amounts_and_expected_release(pg, settings):
    u = make_user(pg)
    pending = make_order(pg, u)                                                        # PENDING: chưa biết ngày hoàn tất
    waiting = make_order(pg, u, status="COMPLETED", completed_at=D(5))                 # hoàn tất D(5), giữ 7 ngày => D(12)
    paid = make_order(pg, u, status="COMPLETED", completed_at=D(1))                    # hoàn tất D(1) => tới hạn D(8)
    cancelled = make_order(pg, u)
    nothing = make_order(pg, u, commission=0)
    wallet_svc(settings, pg, D(1)).settle()                                            # accrual cho các đơn có hoa hồng
    set_order(pg, cancelled, status="CANCELLED")
    wallet_svc(settings, pg, D(9)).settle()                                            # release "paid", cancel "cancelled", "waiting" chưa tới hạn
    got = by_id(wallet_svc(settings, pg, D(9)).my_orders(u))
    assert (got[pending].refund_state, got[pending].refund_vnd, got[pending].expected_release_at) == ("pending", 24_225, None)
    assert (got[waiting].refund_state, got[waiting].refund_vnd, got[waiting].expected_release_at) == ("pending", 24_225, D(12))
    assert (got[paid].refund_state, got[paid].refund_vnd, got[paid].expected_release_at) == ("available", 24_225, None)
    assert (got[cancelled].refund_state, got[cancelled].refund_vnd, got[cancelled].expected_release_at) == ("cancelled", 0, None)
    assert (got[nothing].refund_state, got[nothing].refund_vnd, got[nothing].expected_release_at) == ("none", 0, None)


def test_expected_release_is_completed_at_plus_hold_days_in_force_at_completion(pg, settings):
    u = make_user(pg)
    PlatformSettings(pg, lambda: D(1)).set_int("hold_days", 14, effective_from=D(10))
    early = make_order(pg, u, status="COMPLETED", completed_at=D(5))                  # hoàn tất trước D(10): giữ 7 ngày
    late = make_order(pg, u, status="COMPLETED", completed_at=D(12))                  # sau D(10): giữ 14 ngày
    wallet_svc(settings, pg, D(2)).settle()                                           # accrual only (chưa tới hạn)
    got = by_id(wallet_svc(settings, pg, D(2)).my_orders(u))
    assert got[early].expected_release_at == D(12) and got[late].expected_release_at == D(26)
    assert got[early].refund_state == got[late].refund_state == "pending"


def test_no_expected_release_for_an_order_returned_but_not_yet_settled(pg, settings):
    u = make_user(pg)
    oid = make_order(pg, u, status="COMPLETED", completed_at=D(1))
    wallet_svc(settings, pg, D(2)).settle()                                           # accrual, chưa tới hạn release
    assert wallet_svc(settings, pg, D(2)).my_orders(u)[0].expected_release_at == D(8)
    set_order(pg, oid, status="RETURNED")                                             # Shopee báo trả hàng, worker chưa chốt ví
    (o,) = wallet_svc(settings, pg, D(3)).my_orders(u)
    assert o.status == "RETURNED" and o.expected_release_at is None                   # không hứa "dự kiến vào ví" cho đơn đã trả


def test_returned_after_release_shows_reversed_zero(pg, settings):
    u = make_user(pg)
    oid = make_order(pg, u, status="COMPLETED", completed_at=D(1))
    wallet_svc(settings, pg, D(9)).settle()
    set_order(pg, oid, status="RETURNED")
    wallet_svc(settings, pg, D(10)).settle()
    (o,) = wallet_svc(settings, pg, D(10)).my_orders(u)
    assert (o.status, o.refund_state, o.refund_vnd, o.expected_release_at) == ("RETURNED", "reversed", 0, None)


def test_orders_api_only_mine_masked_ref_newest_first_and_requires_login(api, pg, settings):
    a, ha = login_new_user(api)
    b, hb = login_new_user(api)
    first = make_order(pg, a, status="COMPLETED", completed_at=D(1))
    second = make_order(pg, a)
    set_order(pg, first, purchase_time=D(1))
    set_order(pg, second, purchase_time=D(3))
    with pg.begin() as c:
        c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, commission_micro) VALUES ('ITEST-W-orphan2','PENDING','unknown',1)"))
        sn = c.execute(text("SELECT order_sn FROM shopee_orders WHERE id = :i"), {"i": first}).scalar_one()
    wallet_svc(settings, pg, D(2)).settle()
    mine = api.get("/api/v1/me/orders", headers=ha)
    assert mine.status_code == 200
    rows = mine.json()
    assert [r["id"] for r in rows] == [second, first]                                  # mới nhất trước
    assert set(rows[0]) == {"id", "order_ref", "status", "product_name", "purchased_at", "refund_vnd", "refund_state", "expected_release_at"}
    assert rows[1]["order_ref"] == sn[-4:] and sn not in mine.text and "ITEST-W-orphan2" not in mine.text
    assert rows[1]["expected_release_at"] == "2100-01-08T00:00:00Z" and rows[1]["refund_vnd"] == 24_225
    assert api.get("/api/v1/me/orders", headers=hb).json() == []                       # không thấy đơn của người khác hay đơn mồ côi
    assert len(api.get("/api/v1/me/orders", params={"limit": 1}, headers=ha).json()) == 1
    assert [r["id"] for r in api.get("/api/v1/me/orders", params={"limit": 1, "offset": 1}, headers=ha).json()] == [first]
    assert api.get("/api/v1/me/orders", params={"limit": 0}, headers=ha).status_code == 422
    assert api.get("/api/v1/me/orders").status_code == 401
