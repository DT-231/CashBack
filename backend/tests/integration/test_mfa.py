"""Đăng nhập hai lớp TOTP cho admin (T-019) trên Postgres thật: thiết lập, xác minh, chống phát lại, mã khôi phục, hạn phiên."""
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

from app.core import totp
from app.core.crypto import CryptoError, MfaCipher
from app.main_api import create_app
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()
PW = "mat-khau-hop-le-1"


class Clock:
    def __init__(self):
        self.t = datetime.now(UTC)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text(f"DELETE FROM mfa_recovery_codes WHERE user_id IN {users}"))
        c.execute(text(f"DELETE FROM user_mfa WHERE user_id IN {users}"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
        c.execute(text("DELETE FROM rate_limits WHERE key ~ '^(mfa_|register_ip:|login_ip:|login_email:|refresh_ip:)'"))
    eng.dispose()


@pytest.fixture
def make(make_settings, pg):
    def build(**kw):
        base = dict(database_url=DB_URL, jwt_secret="j" * 40, ip_salt="i" * 24, bank_enc_key=KEY, withdrawals_enabled=True)
        s = make_settings(**{**base, **kw})
        app = create_app(s, engine=pg)
        app.state.mfa_clock = Clock()
        return TestClient(app, raise_server_exceptions=False), app.state.mfa_clock, s
    return build


@pytest.fixture
def api(make):
    return make()


def user(client, pg, role="admin"):
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    uid = client.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    with pg.begin() as c:
        c.execute(text("UPDATE users SET role = :r WHERE id = :i"), {"r": role, "i": uid})
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()
    return uid, {"Authorization": f"Bearer {r['access_token']}"}, r["refresh_token"], email


def code(secret, clock, offset=0):
    return totp.code_at(secret, totp.current_step(clock().timestamp()) + offset)


def enroll(client, clock, h, enable_offset=0):
    """setup + enable. Trả (secret, mã khôi phục)."""
    s = client.post("/api/v1/auth/mfa/setup", headers=h)
    assert s.status_code == 200, s.text
    secret = s.json()["secret"]
    e = client.post("/api/v1/auth/mfa/enable", headers=h, json={"code": code(secret, clock, enable_offset)})
    assert e.status_code == 200, e.text
    return secret, e.json()["recovery_codes"]


def verify(client, clock, h, secret, offset=0):
    clock.advance(seconds=30)                                    # mỗi mã dùng một bước thời gian riêng
    return client.post("/api/v1/auth/mfa/verify", headers=h, json={"code": code(secret, clock, offset)})


def admin_get(client, h):
    return client.get("/api/v1/admin/withdrawals", headers=h)


def audit(pg, uid):
    with pg.connect() as c:
        return [dict(r) for r in c.execute(text("SELECT action, actor_id, target_id, detail FROM audit_logs WHERE actor_id = :u ORDER BY id"), {"u": uid}).mappings()]


# ---------- chặn ----------
def test_admin_without_totp_is_blocked_everywhere(api, pg):
    client, clock, _ = api
    uid, h, _, _ = user(client, pg)
    r = admin_get(client, h)
    assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required" and "bật" in r.json()["error"]["message"]
    for method, path, body in [("post", "/1/approve", None), ("post", "/1/reject", {"reason": "abc"}), ("post", "/1/fail", {"reason": "abc"}),
                               ("post", "/1/mark-paid", {"provider_ref": "FT0001"}), ("get", "/1/payout-account", None)]:
        r = getattr(client, method)("/api/v1/admin/withdrawals" + path, headers=h, **({"json": body} if body else {}))
        assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required", path
    _, sh, _, _ = user(client, pg, "staff")
    assert admin_get(client, sh).json()["error"]["code"] == "forbidden"            # staff vẫn bị chặn bằng lý do vai trò


def test_flag_off_keeps_the_old_behaviour(make, pg):
    client, _, _ = make(admin_mfa_required=False)
    _, h, _, _ = user(client, pg)
    assert admin_get(client, h).status_code == 200


# ---------- luồng đầy đủ ----------
def test_full_flow_setup_enable_verify_unlocks_admin(api, pg):
    client, clock, _ = api
    uid, h, refresh, _ = user(client, pg)
    st = client.get("/api/v1/auth/mfa/status", headers=h).json()
    assert st == {"enabled": False, "pending": False, "verified": False}
    s = client.post("/api/v1/auth/mfa/setup", headers=h).json()
    assert s["otpauth_uri"].startswith("otpauth://totp/") and s["secret"] in s["otpauth_uri"]
    assert client.get("/api/v1/auth/mfa/status", headers=h).json() == {"enabled": False, "pending": True, "verified": False}
    assert admin_get(client, h).status_code == 403                                  # chưa kích hoạt
    bad = client.post("/api/v1/auth/mfa/enable", headers=h, json={"code": "000000"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "mfa_invalid"
    e = client.post("/api/v1/auth/mfa/enable", headers=h, json={"code": code(s["secret"], clock)})
    codes = e.json()["recovery_codes"]
    assert len(codes) == 8 and len(set(codes)) == 8 and all(len(c) == 11 and c[5] == "-" for c in codes)
    assert client.get("/api/v1/auth/mfa/status", headers=h).json() == {"enabled": True, "pending": False, "verified": False}
    r = admin_get(client, h)
    assert r.status_code == 403 and "nhập mã" in r.json()["error"]["message"]        # bật rồi nhưng phiên chưa xác minh
    v = verify(client, clock, h, s["secret"])
    assert v.status_code == 200, v.text
    h2 = {"Authorization": f"Bearer {v.json()['access_token']}"}
    assert admin_get(client, h2).status_code == 200
    assert client.get("/api/v1/auth/mfa/status", headers=h2).json()["verified"] is True
    assert admin_get(client, h).status_code == 403                                   # token cũ (chưa xác minh) vẫn bị chặn
    new_refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": v.json()["refresh_token"]}).json()
    assert admin_get(client, {"Authorization": f"Bearer {new_refresh['access_token']}"}).status_code == 200   # làm mới giữ trạng thái
    old = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).json()
    assert admin_get(client, {"Authorization": f"Bearer {old['access_token']}"}).status_code == 403          # refresh chưa xác minh thì không


def test_a_code_is_single_use_even_under_concurrency(make, pg):
    client, clock, _ = make()
    uid, h, _, _ = user(client, pg)
    secret, _ = enroll(client, clock, h)
    clock.advance(seconds=30)
    c = code(secret, clock)
    first = client.post("/api/v1/auth/mfa/verify", headers=h, json={"code": c})
    assert first.status_code == 200
    replay = client.post("/api/v1/auth/mfa/verify", headers=h, json={"code": c})
    assert replay.status_code == 401 and replay.json()["error"]["code"] == "mfa_invalid"
    clock.advance(seconds=30)
    c2 = code(secret, clock)

    def go(_):
        return client.post("/api/v1/auth/mfa/verify", headers=h, json={"code": c2}).status_code
    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(go, range(6)))
    assert codes.count(200) == 1 and codes.count(401) == 5, codes


def test_session_expires_and_recovery_codes_are_single_use(api, pg):
    client, clock, _ = api
    uid, h, _, _ = user(client, pg)
    secret, recovery = enroll(client, clock, h)
    v = verify(client, clock, h, secret)
    h2 = {"Authorization": f"Bearer {v.json()['access_token']}"}
    assert admin_get(client, h2).status_code == 200
    clock.advance(hours=11, minutes=59)
    assert admin_get(client, h2).status_code == 200
    clock.advance(minutes=2)                                                        # quá mfa_max_age_hours = 12
    r = admin_get(client, h2)
    assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_required"
    rv = client.post("/api/v1/auth/mfa/verify", headers=h, json={"recovery_code": recovery[0].upper()})   # không phân biệt hoa thường
    assert rv.status_code == 200
    assert admin_get(client, {"Authorization": f"Bearer {rv.json()['access_token']}"}).status_code == 200
    again = client.post("/api/v1/auth/mfa/verify", headers=h, json={"recovery_code": recovery[0]})
    assert again.status_code == 401                                                 # mỗi mã khôi phục dùng một lần
    assert client.post("/api/v1/auth/mfa/verify", headers=h, json={"recovery_code": recovery[1].replace("-", "")}).status_code == 200
    assert client.post("/api/v1/auth/mfa/verify", headers=h, json={"recovery_code": "aaaaa-bbbbb"}).status_code == 401
    rec_audit = [a for a in audit(pg, uid) if a["action"] == "mfa.recovery_used"]
    assert [a["detail"]["remaining"] for a in rec_audit] == [7, 6]


def test_stale_token_is_rejected_even_if_mfa_at_is_forged_in_the_future_or_missing(api, pg):
    from app.core import security
    client, clock, s = api
    uid, h, _, _ = user(client, pg)
    enroll(client, clock, h)
    now = int(clock().timestamp())
    for mfa_at in (None, now - 13 * 3600, now + 3600):
        tok = security.make_access_token(s, uid, "admin", mfa_at)
        assert admin_get(client, {"Authorization": f"Bearer {tok}"}).status_code == 403, mfa_at
    tok = security.make_access_token(s, uid, "admin", now)
    assert admin_get(client, {"Authorization": f"Bearer {tok}"}).status_code == 200
    other, oh, _, _ = user(client, pg)                                               # token có mfa_at nhưng user chưa bật TOTP
    assert admin_get(client, {"Authorization": f"Bearer {security.make_access_token(s, other, 'admin', now)}"}).status_code == 403


def test_disabling_totp_takes_effect_immediately(api, pg):
    client, clock, _ = api
    uid, h, _, _ = user(client, pg)
    secret, recovery = enroll(client, clock, h)
    v = verify(client, clock, h, secret)
    h2 = {"Authorization": f"Bearer {v.json()['access_token']}"}
    assert admin_get(client, h2).status_code == 200
    clock.advance(seconds=30)
    assert client.post("/api/v1/auth/mfa/disable", headers=h2, json={"code": "123456"}).status_code == 401      # sai mã: không tắt
    assert admin_get(client, h2).status_code == 200
    assert client.post("/api/v1/auth/mfa/disable", headers=h2, json={"code": code(secret, clock)}).status_code == 204
    r = admin_get(client, h2)
    assert r.status_code == 403 and "bật" in r.json()["error"]["message"]
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM user_mfa WHERE user_id = :u"), {"u": uid}).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM mfa_recovery_codes WHERE user_id = :u"), {"u": uid}).scalar_one() == 0
    assert client.post("/api/v1/auth/mfa/verify", headers=h, json={"recovery_code": recovery[0]}).status_code == 409   # mã khôi phục cũ vô hiệu


def test_setup_rules_pending_replace_and_already_enabled(api, pg):
    client, clock, _ = api
    uid, h, _, _ = user(client, pg)
    first = client.post("/api/v1/auth/mfa/setup", headers=h).json()["secret"]
    second = client.post("/api/v1/auth/mfa/setup", headers=h).json()["secret"]       # chưa kích hoạt: tạo lại được
    assert first != second
    assert client.post("/api/v1/auth/mfa/enable", headers=h, json={"code": code(first, clock)}).status_code == 401   # bí mật cũ vô hiệu
    assert client.post("/api/v1/auth/mfa/enable", headers=h, json={"code": code(second, clock)}).status_code == 200
    again = client.post("/api/v1/auth/mfa/setup", headers=h)
    assert again.status_code == 409 and again.json()["error"]["code"] == "mfa_state"  # đã bật: không thiết lập đè được
    assert client.post("/api/v1/auth/mfa/enable", headers=h, json={"code": code(second, clock)}).status_code == 409


def test_secret_is_encrypted_bound_to_the_user_and_never_leaks(make, pg, caplog):
    caplog.set_level(logging.DEBUG)
    client, clock, s = make()
    uid, h, _, email = user(client, pg)
    secret, recovery = enroll(client, clock, h)
    verify(client, clock, h, secret)
    client.post("/api/v1/auth/mfa/verify", headers=h, json={"code": "000000"})
    with pg.connect() as c:
        row = c.execute(text("SELECT secret_enc, key_id FROM user_mfa WHERE user_id = :u"), {"u": uid}).mappings().one()
        hashes = [r[0] for r in c.execute(text("SELECT code_hash FROM mfa_recovery_codes WHERE user_id = :u"), {"u": uid})]
    assert secret not in row["secret_enc"] and row["key_id"] == "k1"
    cipher = MfaCipher(s)
    assert cipher.decrypt(row["key_id"], row["secret_enc"], uid) == secret
    with pytest.raises(CryptoError):
        cipher.decrypt(row["key_id"], row["secret_enc"], uid + 1)                    # gắn với đúng user
    from app.core.crypto import BankCipher
    with pytest.raises(CryptoError):
        BankCipher(s).decrypt(row["key_id"], row["secret_enc"], uid)                 # không dùng nhầm như số tài khoản
    assert len(hashes) == 8 and not set(hashes) & set(recovery) and all(len(x) == 64 for x in hashes)
    blob = json.dumps(audit(pg, uid), default=str) + client.get("/api/v1/auth/mfa/status", headers=h).text
    dump = "\n".join(r.getMessage() + json.dumps({k: str(v) for k, v in r.__dict__.items() if k not in ("msg", "args")}) for r in caplog.records)
    for leak in (secret, *recovery, code(secret, clock), code(secret, clock, 1)):
        assert leak not in blob and leak not in dump, leak
    actions = [a["action"] for a in audit(pg, uid)]
    assert actions[:3] == ["auth.register", "mfa.setup", "mfa.enable"] and "mfa.verify" in actions and "mfa.verify_failed" in actions


def test_failed_attempts_are_audited_and_rate_limited(make, pg):
    client, clock, _ = make(rl_enabled=True, rl_mfa_per_minute=3)
    uid, h, _, _ = user(client, pg)
    client.post("/api/v1/auth/mfa/setup", headers=h)
    codes = [client.post("/api/v1/auth/mfa/enable", headers=h, json={"code": "000000"}).status_code for _ in range(5)]
    assert codes == [401, 401, 429, 429, 429], codes                              # 3 lần/phút/user tính cả lần /setup, rồi chặn
    failed = [a for a in audit(pg, uid) if a["action"] == "mfa.enable_failed"]
    assert len(failed) == 2 and all(a["detail"] == {"kind": "totp"} for a in failed)


def test_verify_body_requires_exactly_one_of_code_or_recovery(api, pg):
    client, clock, _ = api
    uid, h, _, _ = user(client, pg)
    for body in ({}, {"code": "123456", "recovery_code": "aaaaa-bbbbb"}, {"code": "12"}, {"code": None}):
        assert client.post("/api/v1/auth/mfa/verify", headers=h, json=body).status_code == 422, body
    assert client.post("/api/v1/auth/mfa/verify", headers=h, json={"code": "123456"}).status_code == 409      # chưa bật
    assert client.post("/api/v1/auth/mfa/setup").status_code == 401                                          # cần đăng nhập


def test_missing_encryption_key_returns_503_not_a_crash(make, pg):
    client, _, _ = make(bank_enc_key="")
    uid, h, _, _ = user(client, pg)
    r = client.post("/api/v1/auth/mfa/setup", headers=h)
    assert r.status_code == 503 and r.json()["error"]["code"] == "not_configured"


def test_advance_step_is_atomic_and_monotonic(pg):
    """Chống phát lại ở tầng DB: kể cả khi hai request cùng đọc last_step cũ, chỉ MỘT lần ghi bước thành công."""
    from app.modules.auth import repository
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    with pg.begin() as c:
        uid = c.execute(text("INSERT INTO users(email, password_hash, status) VALUES (:e, 'x', 'active') RETURNING id"), {"e": email}).scalar_one()
        assert repository.put_pending_mfa(c, uid, "enc", "k1")
        assert repository.advance_step(c, uid, 100, enabling=True)                  # kích hoạt
        assert repository.advance_step(c, uid, 101) is True
        assert repository.advance_step(c, uid, 101) is False                        # cùng bước: từ chối
        assert repository.advance_step(c, uid, 100) is False                        # bước cũ hơn: từ chối
        assert repository.advance_step(c, uid, 102) is True
        assert repository.advance_step(c, uid, 150, enabling=True) is False         # đã kích hoạt: enabling không áp dụng lại
        assert c.execute(text("SELECT last_step FROM user_mfa WHERE user_id = :u"), {"u": uid}).scalar_one() == 102


def test_verify_before_enabling_is_a_state_error_and_never_issues_tokens(api, pg):
    client, clock, _ = api
    uid, h, _, _ = user(client, pg)
    secret = client.post("/api/v1/auth/mfa/setup", headers=h).json()["secret"]       # chờ kích hoạt, chưa enable
    clock.advance(seconds=30)
    r = client.post("/api/v1/auth/mfa/verify", headers=h, json={"code": code(secret, clock)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "mfa_state" and "access_token" not in r.text
    assert admin_get(client, h).status_code == 403
