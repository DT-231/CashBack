"""Đăng ký / đăng nhập / refresh / logout trên Postgres thật (skip nếu không có DB)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main_api import create_app
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
SECRET = "j" * 40
PW = "mat-khau-hop-le-1"


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        ids = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {ids}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
    eng.dispose()


@pytest.fixture
def make_api(make_settings, pg):
    def make(**kw):
        s = make_settings(database_url=DB_URL, jwt_secret=SECRET, **kw)
        return TestClient(create_app(s, engine=pg), raise_server_exceptions=False)
    return make


@pytest.fixture
def api(make_api):
    return make_api()


def email():
    return f"itest-{uuid.uuid4().hex[:10]}@example.test"


def register(api, e=None, pw=PW):
    e = e or email()
    return e, api.post("/api/v1/auth/register", json={"email": e, "password": pw})


def login(api, e, pw=PW):
    return api.post("/api/v1/auth/login", json={"email": e, "password": pw})


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_register_creates_active_member_and_stores_only_argon2_hash(api, pg):
    e, r = register(api, "  ITest-Case@Example.Test ".replace("ITest-Case", f"itest-{uuid.uuid4().hex[:8]}"))
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["role"] == "member" and j["status"] == "active" and "password" not in str(j) and "hash" not in str(j)
    with pg.connect() as c:
        stored = c.execute(text("SELECT password_hash FROM users WHERE id = :u"), {"u": j["id"]}).scalar_one()
    assert stored.startswith("$argon2id$") and PW not in stored


def test_register_validation_and_duplicate(api):
    assert api.post("/api/v1/auth/register", json={"email": "khong-phai-email", "password": PW}).status_code == 422
    r = api.post("/api/v1/auth/register", json={"email": email(), "password": "ngan"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    e, first = register(api)
    assert first.status_code == 201
    dup = api.post("/api/v1/auth/register", json={"email": e.upper(), "password": PW})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "email_taken"


def test_login_me_and_wrong_credentials_are_indistinguishable(api):
    e, _ = register(api)
    ok = login(api, e)
    assert ok.status_code == 200
    t = ok.json()
    assert t["token_type"] == "bearer" and t["expires_in"] == 900
    me = api.get("/api/v1/auth/me", headers=auth(t["access_token"]))
    assert me.status_code == 200 and me.json()["email"] == e
    bad_pw, no_user = login(api, e, "sai-mat-khau-xyz"), login(api, email())
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json()["error"]["code"] == no_user.json()["error"]["code"] == "invalid_credentials"
    assert bad_pw.json()["error"]["message"] == no_user.json()["error"]["message"]


def test_me_requires_valid_token(api):
    assert api.get("/api/v1/auth/me").status_code == 401
    assert api.get("/api/v1/auth/me", headers=auth("rac")).status_code == 401
    assert api.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401


def age_revoked(pg, e, seconds=60):
    """Lùi thời điểm thu hồi để vượt khoảng ân hạn, giả lập 'đã xoay vòng từ lâu'."""
    with pg.begin() as c:
        c.execute(text("UPDATE refresh_tokens SET revoked_at = revoked_at - make_interval(secs => :s) "
                       "WHERE revoked_at IS NOT NULL AND user_id = (SELECT id FROM users WHERE email = :e)"),
                  {"s": seconds, "e": e})


def test_refresh_rotates_and_old_reuse_revokes_everything(api, pg):
    e, _ = register(api)
    t1 = login(api, e).json()
    t2 = api.post("/api/v1/auth/refresh", json={"refresh_token": t1["refresh_token"]})
    assert t2.status_code == 200 and t2.json()["refresh_token"] != t1["refresh_token"]
    age_revoked(pg, e)
    # dùng lại token cũ đã xoay vòng từ lâu: bị từ chối VÀ phiên mới cũng bị thu hồi
    reuse = api.post("/api/v1/auth/refresh", json={"refresh_token": t1["refresh_token"]})
    assert reuse.status_code == 401 and reuse.json()["error"]["code"] == "invalid_refresh"
    after = api.post("/api/v1/auth/refresh", json={"refresh_token": t2.json()["refresh_token"]})
    assert after.status_code == 401


def test_double_refresh_race_does_not_kill_the_session(api):
    """Hai tab/retry dùng cùng một token gần như đồng thời: người thua nhận 401 nhưng phiên thắng vẫn sống."""
    e, _ = register(api)
    t1 = login(api, e).json()
    winner = api.post("/api/v1/auth/refresh", json={"refresh_token": t1["refresh_token"]})
    loser = api.post("/api/v1/auth/refresh", json={"refresh_token": t1["refresh_token"]})
    assert winner.status_code == 200 and loser.status_code == 401
    assert api.post("/api/v1/auth/refresh", json={"refresh_token": winner.json()["refresh_token"]}).status_code == 200


def test_stale_token_after_logout_does_not_kill_new_login(api, pg):
    e, _ = register(api)
    old = login(api, e).json()
    assert api.post("/api/v1/auth/logout", headers=auth(old["access_token"])).status_code == 204
    fresh = login(api, e).json()
    assert api.post("/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]}).status_code == 401
    assert api.post("/api/v1/auth/refresh", json={"refresh_token": fresh["refresh_token"]}).status_code == 200


def test_login_prunes_long_dead_tokens(api, pg):
    e, _ = register(api)
    login(api, e)
    with pg.begin() as c:
        c.execute(text("UPDATE refresh_tokens SET expires_at = now() - interval '40 days'"
                       " WHERE user_id = (SELECT id FROM users WHERE email = :e)"), {"e": e})
    login(api, e)
    with pg.connect() as c:
        n = c.execute(text("SELECT count(*) FROM refresh_tokens WHERE user_id = (SELECT id FROM users WHERE email = :e)"),
                      {"e": e}).scalar_one()
    assert n == 1


def test_refresh_expired_or_unknown_is_rejected(api, pg):
    e, _ = register(api)
    t = login(api, e).json()
    with pg.begin() as c:
        c.execute(text("UPDATE refresh_tokens SET expires_at = now() - interval '1 minute'"
                       " WHERE user_id = (SELECT id FROM users WHERE email = :e)"), {"e": e})
    assert api.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401
    assert api.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 43}).status_code == 401


def test_logout_revokes_refresh_tokens(api):
    e, _ = register(api)
    t = login(api, e).json()
    assert api.post("/api/v1/auth/logout", headers=auth(t["access_token"])).status_code == 204
    assert api.post("/api/v1/auth/refresh", json={"refresh_token": t["refresh_token"]}).status_code == 401
    assert api.post("/api/v1/auth/logout").status_code == 401


def test_locked_and_unverified_accounts_cannot_login(make_api, api, pg):
    e, _ = register(api)
    with pg.begin() as c:
        c.execute(text("UPDATE users SET status = 'locked' WHERE email = :e"), {"e": e})
    r = login(api, e)
    assert r.status_code == 403 and r.json()["error"]["code"] == "account_locked"
    strict = make_api(require_email_verify=True)
    e2, reg = register(strict)
    assert reg.json()["status"] == "unverified"
    r = login(strict, e2)
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_unverified"


def test_locked_user_access_token_stops_working(api, pg):
    e, _ = register(api)
    t = login(api, e).json()
    with pg.begin() as c:
        c.execute(text("UPDATE users SET status = 'locked' WHERE email = :e"), {"e": e})
    assert api.get("/api/v1/auth/me", headers=auth(t["access_token"])).status_code == 401


def test_without_jwt_secret_login_is_503_not_500(make_settings, pg):
    s = make_settings(database_url=DB_URL)     # không đặt jwt_secret
    app = TestClient(create_app(s, engine=pg), raise_server_exceptions=False)
    e = email()
    assert app.post("/api/v1/auth/register", json={"email": e, "password": PW}).status_code == 201
    r = app.post("/api/v1/auth/login", json={"email": e, "password": PW})
    assert r.status_code == 503 and r.json()["error"]["code"] == "not_configured"
