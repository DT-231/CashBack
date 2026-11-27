"""T-063: cookie Shopee do admin dán: mã hóa at-rest, không đọc lại qua HTTP, chỉ admin (+TOTP), trạng thái cho worker."""
import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.crypto import CryptoError, ShopeeCookieCipher
from app.main_api import create_app
from app.modules.shopee_session.service import ShopeeSessionService, clean_cookie
from tests.integration.pg import DB_URL, pg_available
from tests.integration.test_withdrawals import KEY  # noqa: F401  (khóa AES hợp lệ dùng chung cho test)

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
PW = "mat-khau-hop-le-1"
COOKIE = "SPC_ST=abcDEF123secretvalue; SPC_EC=zzz999anothersecret; csrftoken=tok123"


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    with eng.connect() as c:
        before = c.execute(text("SELECT id, cookie_enc, key_id, status, last_ok_at, failure_count, updated_by FROM shopee_sessions")).all()
    yield eng
    with eng.begin() as c:
        c.execute(text("DELETE FROM shopee_sessions"))
        for r in before:
            c.execute(text("INSERT INTO shopee_sessions(id, cookie_enc, key_id, status, last_ok_at, failure_count) VALUES (:i, :c, :k, :s, :l, :f)"),
                      {"i": r[0], "c": r[1], "k": r[2], "s": r[3], "l": r[4], "f": r[5]})
        users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
    eng.dispose()


@pytest.fixture
def settings(make_settings):
    return make_settings(database_url=DB_URL, jwt_secret="j" * 40, ip_salt="i" * 24, bank_enc_key=KEY, admin_mfa_required=False)


@pytest.fixture
def api(settings, pg):
    return TestClient(create_app(settings, engine=pg), raise_server_exceptions=False)


def user(api, pg, role="admin"):
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    with pg.begin() as c:
        c.execute(text("UPDATE users SET role = :r WHERE id = :i"), {"r": role, "i": uid})
    tok = api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return uid, {"Authorization": f"Bearer {tok}"}


def row(pg):
    with pg.connect() as c:
        return c.execute(text("SELECT cookie_enc, key_id, status, failure_count, last_ok_at, updated_by FROM shopee_sessions WHERE id = 1")).mappings().first()


def test_cookie_is_encrypted_audited_and_never_readable_over_http(api, pg, settings, caplog):
    caplog.set_level(logging.DEBUG)
    aid, ah = user(api, pg)
    r = api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": "Cookie: " + COOKIE})
    assert r.status_code == 204
    d = row(pg)
    assert d["key_id"] == "k1" and d["status"] == "unknown" and d["updated_by"] == aid
    for secret in ("SPC_ST", "abcDEF123", "secretvalue", "csrftoken", "tok123"):
        assert secret not in d["cookie_enc"], secret
    assert ShopeeSessionService(settings, pg).load_cookie() == COOKIE                  # tiền tố "Cookie:" đã được bỏ
    with pytest.raises(CryptoError):                                                    # gắn với đúng chủ sở hữu và đúng mục đích
        ShopeeCookieCipher(settings).decrypt(d["key_id"], d["cookie_enc"], 2)
    from app.core.crypto import BankCipher
    with pytest.raises(CryptoError):
        BankCipher(settings).decrypt(d["key_id"], d["cookie_enc"], 1)
    st = api.get("/api/v1/admin/shopee-session/status", headers=ah)
    assert st.status_code == 200 and st.json()["has_cookie"] is True and st.json()["status"] == "unknown"
    with pg.connect() as c:
        audit = json.dumps([dict(x) for x in c.execute(text("SELECT detail, action, actor_id FROM audit_logs WHERE action = 'shopee_session.set'")).mappings()], default=str)
    assert "shopee_session.set" in audit and f'"actor_id": {aid}' in audit
    blob = r.text + st.text + audit + "\n".join(x.getMessage() + str(x.__dict__) for x in caplog.records)
    for secret in ("SPC_ST", "abcDEF123", "secretvalue", "tok123", COOKIE):
        assert secret not in blob, secret


def test_no_route_returns_the_cookie(api):
    from tests.contract.test_audit_required import all_routes
    paths = {(m, r.path) for r in all_routes(api.app) if "shopee-session" in getattr(r, "path", "") for m in (r.methods or set()) if m not in ("HEAD", "OPTIONS")}
    assert paths == {("PUT", "/api/v1/admin/shopee-session"), ("GET", "/api/v1/admin/shopee-session/status")}   # không có GET trả cookie


def test_only_admin_and_validation(api, pg):
    _, mh = user(api, pg, "member")
    _, sh = user(api, pg, "staff")
    _, ah = user(api, pg)
    for hh, code in ((mh, 403), (sh, 403), ({}, 401)):
        assert api.put("/api/v1/admin/shopee-session", headers=hh, json={"cookie": COOKIE}).status_code == code
        assert api.get("/api/v1/admin/shopee-session/status", headers=hh).status_code == code
    for bad in ("khong-co-dau-bang", "a=" + "x" * 9000, ""):
        assert api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": bad}).status_code in (422,)
    r = api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": "x"})                              # min_length
    assert r.status_code == 422 and "x" not in r.text.replace("x-request", "")


def test_service_layer_refuses_non_admin_and_missing_audit(settings, pg):
    from app.core.errors import Forbidden
    from app.modules.audit.errors import InvalidAudit
    from app.modules.audit.service import Actor, AuditContext
    for role in ("staff", "user", "system"):
        with pytest.raises(Forbidden):
            ShopeeSessionService(settings, pg).set_cookie(COOKIE, audit=AuditContext(settings, Actor(9, role), None))
    with pytest.raises(InvalidAudit):
        ShopeeSessionService(settings, pg).set_cookie(COOKIE, audit=None)


def test_status_tracking_for_the_worker_and_reset_on_new_cookie(api, pg, settings):
    _, ah = user(api, pg)
    svc = ShopeeSessionService(settings, pg)
    svc.record_result("ok")
    assert row(pg) is None or row(pg)["status"] != "healthy"                        # chưa có cookie: không ghi gì
    api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": COOKIE})
    svc.record_result("ok")
    d = row(pg)
    assert d["status"] == "healthy" and d["failure_count"] == 0 and d["last_ok_at"] is not None
    svc.record_result("partial")
    assert row(pg)["status"] == "degraded" and row(pg)["failure_count"] == 0
    svc.record_result("failed")
    svc.record_result("failed", blocked=True)
    d = row(pg)
    assert d["status"] == "blocked" and d["failure_count"] == 2
    svc.record_result("ok")                                                         # phục hồi: về healthy và xóa bộ đếm lỗi
    d = row(pg)
    assert d["status"] == "healthy" and d["failure_count"] == 0
    svc.record_result("failed")
    api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": COOKIE + "; extra=1"})     # cookie mới: về unknown, đếm lại
    d = row(pg)
    assert d["status"] == "unknown" and d["failure_count"] == 0
    st = api.get("/api/v1/admin/shopee-session/status", headers=ah).json()
    assert st["status"] == "unknown" and st["failure_count"] == 0


def test_clean_cookie_shapes():
    assert clean_cookie("Cookie: a=b; c=d") == "a=b; c=d"
    assert clean_cookie("a=b\nc=d\r\ne=f") == "a=b; c=d; e=f"


def test_worker_uses_the_db_cookie_and_records_the_result(settings, pg, api, monkeypatch, capsys):
    from app import main_worker
    from app.modules.orders.service import SyncResult
    _, ah = user(api, pg)
    api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": COOKIE})
    seen = {}
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("SUBID_SECRET", "s" * 32)
    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setenv("BANK_ENC_KEY", KEY)
    monkeypatch.setenv("SHOPEE_COOKIE", "env-cookie=should-lose")
    monkeypatch.setattr(main_worker, "build_client", lambda s: seen.setdefault("cookie", s.shopee_cookie.get_secret_value()) and object())
    monkeypatch.setattr(main_worker.OrderSync, "run", lambda self, days=None: SyncResult("failed", error="403", blocked=True))
    main_worker.main(["sync-once"])
    assert seen["cookie"] == COOKIE                                                   # cookie trong DB thắng biến môi trường
    assert row(pg)["status"] == "blocked" and row(pg)["failure_count"] == 1
    assert COOKIE not in capsys.readouterr().out


# ---------- T-023: cảnh báo cookie chết / sync lỗi ----------
class Spy:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        return True


def _svc_at(settings, pg, clock):
    return ShopeeSessionService(settings, pg, clock=clock)


def test_blocked_alerts_once_then_repeats_after_six_hours_then_reports_recovery(api, pg, settings):
    from datetime import UTC, datetime, timedelta
    _, ah = user(api, pg)
    api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": COOKIE})
    t = [datetime(2100, 1, 1, tzinfo=UTC)]
    svc, spy = _svc_at(settings, pg, lambda: t[0]), Spy()
    svc.record_result("failed", blocked=True, notifier=spy)
    assert len(spy.sent) == 1 and "bị chặn" in spy.sent[0] and "PUT /api/v1/admin/shopee-session" in spy.sent[0]
    t[0] += timedelta(hours=5, minutes=59)
    svc.record_result("failed", blocked=True, notifier=spy)
    assert len(spy.sent) == 1                                                       # chưa đủ 6 giờ: không nhắc
    t[0] += timedelta(minutes=2)
    svc.record_result("failed", blocked=True, notifier=spy)
    assert len(spy.sent) == 2                                                       # đủ 6 giờ: nhắc lại
    svc.record_result("ok", notifier=spy)
    assert len(spy.sent) == 3 and "trở lại" in spy.sent[2] and row(pg)["status"] == "healthy"
    svc.record_result("ok", notifier=spy)
    assert len(spy.sent) == 3                                                       # đã khỏe: không báo lặp
    svc.record_result("failed", blocked=True, notifier=spy)
    assert len(spy.sent) == 4                                                       # hỏng lại: báo ngay (không bị chu kỳ cũ chặn)
    for text_ in spy.sent:
        assert "SPC_" not in text_ and COOKIE not in text_


def test_plain_failures_alert_only_after_n_in_a_row_and_partial_never_alerts(api, pg, settings):
    _, ah = user(api, pg)
    api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": COOKIE})
    svc, spy = ShopeeSessionService(settings, pg), Spy()
    svc.record_result("failed", notifier=spy)
    svc.record_result("failed", notifier=spy)
    svc.record_result("partial", notifier=spy)                                      # partial không tăng đếm và không báo
    assert spy.sent == [] and row(pg)["failure_count"] == 2
    svc.record_result("failed", notifier=spy)                                       # lần thứ 3
    assert len(spy.sent) == 1 and "3 lần" in spy.sent[0]
    svc.record_result("ok", notifier=spy)
    assert len(spy.sent) == 2
    svc.record_result("failed", notifier=spy)
    svc.record_result("ok", notifier=spy)                                           # hỏng 1 lần rồi ổn: không có gì để báo hồi phục
    assert len(spy.sent) == 2


def test_no_alert_without_a_stored_cookie_and_no_notifier_is_fine(settings, pg):
    spy = Spy()
    ShopeeSessionService(settings, pg).record_result("failed", blocked=True, notifier=spy)
    assert spy.sent == []                                                           # chưa có cookie trong DB: bỏ qua
    ShopeeSessionService(settings, pg).record_result("failed", blocked=True)       # không notifier: không lỗi


def test_new_cookie_clears_the_alert_state(api, pg, settings):
    _, ah = user(api, pg)
    api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": COOKIE})
    svc, spy = ShopeeSessionService(settings, pg), Spy()
    svc.record_result("failed", blocked=True, notifier=spy)
    api.put("/api/v1/admin/shopee-session", headers=ah, json={"cookie": COOKIE + "; n=1"})
    with pg.connect() as c:
        assert c.execute(text("SELECT last_alert_at FROM shopee_sessions WHERE id = 1")).scalar_one() is not None   # còn lưu: lần sau còn trong chu kỳ
    svc.record_result("failed", blocked=True, notifier=spy)
    assert len(spy.sent) == 1                                                       # cookie mới vẫn lỗi trong 6 giờ: không báo dồn dập
