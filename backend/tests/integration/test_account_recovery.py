"""T-011: xác minh email, quên và đặt lại mật khẩu. Token một lần, chỉ lưu hash, không lộ email nào tồn tại."""
import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main_api import create_app
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
PW = "mat-khau-hop-le-1"
NEW_PW = "mat-khau-moi-9876"


class Spy:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))
        return True


class Boom:
    def send(self, to, subject, body):
        raise RuntimeError("smtp down")


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text(f"DELETE FROM email_tokens WHERE user_id IN {users}"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
        c.execute(text("DELETE FROM rate_limits WHERE key ~ '^(forgot_|resend_|verify_ip|reset_ip|register_ip|login_)'"))
    eng.dispose()


def make(make_settings, pg, **kw):
    s = make_settings(database_url=DB_URL, jwt_secret="j" * 40, ip_salt="i" * 24, web_origin="https://app.test", require_email_verify=True, **kw)
    api = TestClient(create_app(s, engine=pg), raise_server_exceptions=False)
    api.app.state.mailer = Spy()
    return api


@pytest.fixture
def api(make_settings, pg):
    return make(make_settings, pg)


def token_of(mail):
    return re.search(r"token=([A-Za-z0-9_-]+)", mail[2]).group(1)


def register(api, status=None, pg=None):
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    r = api.post("/api/v1/auth/register", json={"email": email, "password": PW})
    assert r.status_code == 201
    if status and pg:
        with pg.begin() as c:
            c.execute(text("UPDATE users SET status = :s WHERE email = :e"), {"s": status, "e": email})
    return email, r.json()["id"]


def login(api, email, pw=PW):
    return api.post("/api/v1/auth/login", json={"email": email, "password": pw})


def test_register_sends_a_verification_link_and_verifying_activates(api, pg):
    email, uid = register(api)
    assert login(api, email).json()["error"]["code"] == "email_unverified"
    (mail,) = api.app.state.mailer.sent
    assert mail[0] == email and mail[2].count("https://app.test/verify-email?token=") == 1 and "24 giờ" in mail[2]
    tok = token_of(mail)
    with pg.connect() as c:
        stored = c.execute(text("SELECT token_hash FROM email_tokens WHERE user_id = :u"), {"u": uid}).scalar_one()
    assert tok not in stored and len(stored) == 64                                   # chỉ lưu SHA-256
    assert api.post("/api/v1/auth/verify", json={"token": tok}).status_code == 204
    assert login(api, email).status_code == 200
    again = api.post("/api/v1/auth/verify", json={"token": tok})
    assert again.status_code == 400 and again.json()["error"]["code"] == "invalid_token"      # dùng một lần


def test_bad_expired_wrong_purpose_and_malformed_tokens_are_rejected(api, pg):
    email, uid = register(api)
    tok = token_of(api.app.state.mailer.sent[0])
    for bad in (tok[:-1] + ("A" if tok[-1] != "A" else "B"), "x" * 43, tok + "x"):
        assert api.post("/api/v1/auth/verify", json={"token": bad}).status_code == 400, bad
    for malformed in ("", "short", "a" * 101, None):
        assert api.post("/api/v1/auth/verify", json={"token": malformed}).status_code == 422, malformed
    with pg.begin() as c:
        c.execute(text("UPDATE email_tokens SET expires_at = now() - interval '1 second' WHERE user_id = :u"), {"u": uid})
    assert api.post("/api/v1/auth/verify", json={"token": tok}).status_code == 400            # hết hạn
    assert login(api, email).json()["error"]["code"] == "email_unverified"
    api.post("/api/v1/auth/forgot", json={"email": email})
    reset_tok = token_of(api.app.state.mailer.sent[-1])
    assert api.post("/api/v1/auth/verify", json={"token": reset_tok}).status_code == 400      # token đặt lại không dùng để xác minh


def test_resend_replaces_the_old_token_and_only_sends_to_unverified(api, pg):
    email, uid = register(api, pg=pg)
    first = token_of(api.app.state.mailer.sent[0])
    assert api.post("/api/v1/auth/verify/resend", json={"email": email}).status_code == 202
    second = token_of(api.app.state.mailer.sent[1])
    assert first != second
    assert api.post("/api/v1/auth/verify", json={"token": first}).status_code == 400          # token cũ vô hiệu
    assert api.post("/api/v1/auth/verify", json={"token": second}).status_code == 204
    n = len(api.app.state.mailer.sent)
    r = api.post("/api/v1/auth/verify/resend", json={"email": email})                          # đã xác minh: 202 nhưng không gửi
    assert r.status_code == 202 and len(api.app.state.mailer.sent) == n
    r2 = api.post("/api/v1/auth/verify/resend", json={"email": "khong-ton-tai@example.test"})
    assert (r2.status_code, r2.json()) == (r.status_code, r.json()) and len(api.app.state.mailer.sent) == n


def test_forgot_is_identical_for_existing_missing_and_locked_emails(api, pg):
    active, _ = register(api, "active", pg)
    locked, _ = register(api, "locked", pg)
    base = len(api.app.state.mailer.sent)
    answers = [api.post("/api/v1/auth/forgot", json={"email": e}) for e in (active, "khong-ton-tai@example.test", locked, active.upper())]
    assert {(r.status_code, json.dumps(r.json())) for r in answers} == {(202, '{"ok": true}')}
    sent = api.app.state.mailer.sent[base:]
    assert [m[0] for m in sent] == [active, active] and all("1 giờ" in m[2] and "reset-password?token=" in m[2] for m in sent)   # active (và chữ hoa) có thư; còn lại thì không


def test_reset_changes_password_logs_out_everywhere_and_is_single_use(api, pg):
    email, uid = register(api, "active", pg)
    tokens = login(api, email).json()
    other = login(api, email).json()
    api.post("/api/v1/auth/forgot", json={"email": email})
    t1 = token_of(api.app.state.mailer.sent[-1])
    api.post("/api/v1/auth/forgot", json={"email": f"{email}"})                                   # yêu cầu mới: token cũ vô hiệu
    t2 = token_of(api.app.state.mailer.sent[-1])
    assert t1 != t2 and api.post("/api/v1/auth/reset", json={"token": t1, "password": NEW_PW}).status_code == 400
    assert api.post("/api/v1/auth/reset", json={"token": t2, "password": "ngan"}).status_code == 422       # mật khẩu yếu: token chưa bị tiêu hao
    assert api.post("/api/v1/auth/reset", json={"token": t2, "password": NEW_PW}).status_code == 204
    assert login(api, email).json()["error"]["code"] == "invalid_credentials"                        # mật khẩu cũ hết hiệu lực
    assert login(api, email, NEW_PW).status_code == 200
    for rt in (tokens["refresh_token"], other["refresh_token"]):
        assert api.post("/api/v1/auth/refresh", json={"refresh_token": rt}).status_code == 401      # mọi phiên cũ bị đăng xuất
    assert api.post("/api/v1/auth/reset", json={"token": t2, "password": "mat-khau-khac-123"}).status_code == 400
    with pg.connect() as c:
        acts = [r[0] for r in c.execute(text("SELECT action FROM audit_logs WHERE actor_id = :u AND action LIKE 'auth.%' ORDER BY id"), {"u": uid})]
        blob = json.dumps([dict(r) for r in c.execute(text("SELECT * FROM audit_logs WHERE actor_id = :u"), {"u": uid}).mappings()], default=str)
    assert "auth.password_reset" in acts and t2 not in blob and t1 not in blob and NEW_PW not in blob


def test_reset_proves_email_ownership_but_never_unlocks(api, pg):
    email, uid = register(api)                                                                    # unverified
    api.post("/api/v1/auth/forgot", json={"email": email})
    tok = token_of(api.app.state.mailer.sent[-1])
    assert api.post("/api/v1/auth/reset", json={"token": tok, "password": NEW_PW}).status_code == 204
    assert login(api, email, NEW_PW).status_code == 200                                           # đã active nhờ chứng minh được email
    api.post("/api/v1/auth/forgot", json={"email": email})
    tok2 = token_of(api.app.state.mailer.sent[-1])
    with pg.begin() as c:
        c.execute(text("UPDATE users SET status = 'locked' WHERE id = :u"), {"u": uid})           # bị khóa SAU khi đã phát token
    assert api.post("/api/v1/auth/reset", json={"token": tok2, "password": "mat-khau-moi-5555"}).status_code == 204
    assert login(api, email, "mat-khau-moi-5555").json()["error"]["code"] == "account_locked"     # không mở khóa được bằng đặt lại mật khẩu
    with pg.connect() as c:
        assert c.execute(text("SELECT status FROM users WHERE id = :u"), {"u": uid}).scalar_one() == "locked"


def test_rate_limits_forgot_per_email(make_settings, pg):
    api = make(make_settings, pg, rl_enabled=True, rl_forgot_per_hour=100)
    e = f"itest-{uuid.uuid4().hex[:8]}@example.test"
    codes = [api.post("/api/v1/auth/forgot", json={"email": e}).status_code for _ in range(5)]
    assert codes == [202, 202, 202, 429, 429]                                                     # 3 lần/giờ/email


def test_rate_limits_forgot_per_ip(make_settings, pg):
    api2 = make(make_settings, pg, rl_enabled=True, rl_forgot_per_hour=2)
    codes = [api2.post("/api/v1/auth/forgot", json={"email": f"itest-{uuid.uuid4().hex[:8]}@example.test"}).status_code for _ in range(4)]
    assert codes == [202, 202, 429, 429]                                                          # theo IP (mỗi email khác nhau)


def test_mail_failures_and_missing_config_never_change_the_response(make_settings, pg):
    api = make(make_settings, pg)
    api.app.state.mailer = Boom()
    email, _ = register(api, "active", pg)
    assert api.post("/api/v1/auth/forgot", json={"email": email}).status_code == 202            # SMTP hỏng: vẫn 202
    api = make(make_settings, pg)
    api.app.state.settings = api.app.state.settings.model_copy(update={"web_origin": ""})
    email, _ = register(api, "active", pg)
    api.post("/api/v1/auth/forgot", json={"email": email})
    assert api.app.state.mailer.sent == []                                                        # không có WEB_ORIGIN: không gửi liên kết


def test_verification_is_not_requested_when_the_flag_is_off(make_settings, pg):
    s = make_settings(database_url=DB_URL, jwt_secret="j" * 40, web_origin="https://app.test", require_email_verify=False)
    api = TestClient(create_app(s, engine=pg), raise_server_exceptions=False)
    api.app.state.mailer = Spy()
    email, _ = register(api)
    assert api.app.state.mailer.sent == [] and login(api, email).status_code == 200
