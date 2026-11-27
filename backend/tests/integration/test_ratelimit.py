"""Rate limit Postgres thật, bao gồm race giữa nhiều request."""
from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.clientip import limiter_key
from app.main_api import create_app
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
SALT = "ratelimit-itest-salt-0123456789"


@pytest.fixture
def pg(make_settings):
    engine = create_engine(DB_URL)
    settings = make_settings(ip_salt=SALT)
    keys = set()
    yield engine, settings, keys
    with engine.begin() as conn:
        if keys:
            conn.execute(text("DELETE FROM rate_limits WHERE key = ANY(:keys)"), {"keys": list(keys)})
        test_users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        conn.execute(text(f"DELETE FROM clicks WHERE link_id IN (SELECT id FROM links WHERE user_id IN {test_users})"))
        conn.execute(text(f"DELETE FROM links WHERE user_id IN {test_users}"))
        conn.execute(text("DELETE FROM products WHERE shop_id BETWEEN 990001 AND 990009"))
        conn.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {test_users}"))
        conn.execute(text(f"DELETE FROM users WHERE id IN {test_users}"))
    engine.dispose()


def api(pg, make_settings, **overrides):
    engine = pg[0]
    settings = make_settings(database_url=DB_URL, ip_salt=SALT, rl_enabled=True,
                             jwt_secret="j" * 40, **overrides)
    app = create_app(settings, engine=engine)
    app.state.rl_test_keys = pg[2]
    return TestClient(app, raise_server_exceptions=False, follow_redirects=False)


def track(client, scope, value):
    client.app.state.rl_test_keys.add(f"{scope}:{limiter_key(client.app.state.settings, value)}")


def login(client, address="198.51.100.13", email="itest-ratelimit@example.test"):
    actual_ip = address if client.app.state.settings.trust_proxy_headers else "testclient"
    track(client, "login_ip", actual_ip)
    track(client, "login_email", email.strip().lower())
    return client.post("/api/v1/auth/login", headers={"cf-connecting-ip": address},
                       json={"email": email, "password": "sai-mat-khau"})


def test_login_limit_returns_429_and_retry_after(pg, make_settings):
    client = api(pg, make_settings, trust_proxy_headers=True, rl_login_per_minute=3)
    results = [login(client) for _ in range(4)]
    assert [r.status_code for r in results] == [401, 401, 401, 429]
    blocked = results[-1]
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) >= 1


def test_email_limit_spans_ips_and_email_key_is_hashed(pg, make_settings):
    client = api(pg, make_settings, trust_proxy_headers=True, rl_login_per_minute=100,
                 rl_login_per_email_15min=10)
    addresses = [f"198.51.100.{n}" for n in range(20, 31)]
    results = [login(client, address, "itest-ratelimit@example.test") for address in addresses]
    assert [r.status_code for r in results].count(429) == 1
    email_key = f"login_email:{limiter_key(pg[1], 'itest-ratelimit@example.test')}"
    with pg[0].connect() as conn:
        row = conn.execute(text("SELECT key, count FROM rate_limits WHERE key = :key"), {"key": email_key}).one()
    assert row.count == 11
    assert "itest-ratelimit@example.test" not in row.key


def test_concurrent_requests_are_counted_atomically(pg, make_settings):
    client = api(pg, make_settings, trust_proxy_headers=True, rl_login_per_minute=5,
                 rl_login_per_email_15min=100)
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: login(client, "198.51.100.15", "itest-parallel@example.test"), range(20)))
    assert [r.status_code for r in results].count(401) == 5
    assert [r.status_code for r in results].count(429) == 15


def test_expired_window_resets_count(pg, make_settings):
    client = api(pg, make_settings, trust_proxy_headers=True, rl_login_per_minute=1)
    assert login(client, "198.51.100.16").status_code == 401
    key = f"login_ip:{limiter_key(pg[1], '198.51.100.16')}"
    with pg[0].begin() as conn:
        conn.execute(text("UPDATE rate_limits SET window_start = now() - interval '2 minutes' WHERE key = :key"),
                     {"key": key})
    assert login(client, "198.51.100.16").status_code == 401
    with pg[0].connect() as conn:
        assert conn.execute(text("SELECT count FROM rate_limits WHERE key = :key"), {"key": key}).scalar_one() == 1


def test_invalid_email_is_not_counted_by_email_limit(pg, make_settings):
    client = api(pg, make_settings, trust_proxy_headers=True, rl_login_per_minute=100)
    invalid_email = "not-valid"
    email_key = f"login_email:{limiter_key(pg[1], invalid_email)}"
    for _ in range(3):
        track(client, "login_ip", "198.51.100.13")
        assert client.post("/api/v1/auth/login", headers={"cf-connecting-ip": "198.51.100.13"},
                           json={"email": invalid_email, "password": "x"}).status_code == 422
    with pg[0].connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM rate_limits WHERE key = :key"),
                            {"key": email_key}).scalar_one() == 0


def test_proxy_header_is_used_only_when_trusted(pg, make_settings):
    trusted = api(pg, make_settings, trust_proxy_headers=True, rl_login_per_minute=1)
    assert login(trusted, "198.51.100.40").status_code == 401
    assert login(trusted, "198.51.100.41").status_code == 401

    untrusted = api(pg, make_settings, trust_proxy_headers=False, rl_login_per_minute=1)
    assert login(untrusted, "198.51.100.42").status_code == 401
    assert login(untrusted, "198.51.100.43").status_code == 429


def test_register_endpoint_is_limited(pg, make_settings):
    client = api(pg, make_settings, trust_proxy_headers=True, rl_register_per_hour=2)
    results = []
    for _ in range(3):
        track(client, "register_ip", "198.51.100.50")
        results.append(client.post("/api/v1/auth/register", headers={"cf-connecting-ip": "198.51.100.50"},
                                   json={"email": f"itest-ratelimit-reg-{uuid.uuid4().hex}@example.test",
                                         "password": "mat-khau-hop-le"}))
    assert [r.status_code for r in results] == [201, 201, 429]
    assert results[-1].json()["error"]["code"] == "rate_limited"
    assert int(results[-1].headers["retry-after"]) >= 1


def test_refresh_endpoint_is_limited(pg, make_settings):
    client = api(pg, make_settings, trust_proxy_headers=True, rl_refresh_per_minute=2)
    results = []
    for _ in range(3):
        track(client, "refresh_ip", "198.51.100.51")
        results.append(client.post("/api/v1/auth/refresh", headers={"cf-connecting-ip": "198.51.100.51"},
                                   json={"refresh_token": "x" * 20}))
    assert [r.status_code for r in results[:2]] == [401, 401]
    assert results[-1].status_code == 429
    assert results[-1].json()["error"]["code"] == "rate_limited"
    assert int(results[-1].headers["retry-after"]) >= 1


def test_go_endpoint_is_limited_even_for_unknown_code(pg, make_settings):
    client = api(pg, make_settings, trust_proxy_headers=True, rl_go_per_minute=2)
    results = []
    for _ in range(3):
        track(client, "go", "198.51.100.52")
        results.append(client.get("/go/no-such-link", headers={"cf-connecting-ip": "198.51.100.52"}))
    assert [r.status_code for r in results] == [404, 404, 429]
    assert results[-1].json()["error"]["code"] == "rate_limited"
    assert int(results[-1].headers["retry-after"]) >= 1


def test_go_and_login_fail_open_when_limiter_query_fails(pg, make_settings, monkeypatch):
    import app.core.ratelimit as ratelimit

    client = api(pg, make_settings, trust_proxy_headers=True, rl_register_per_hour=100,
                 rl_login_per_minute=100, rl_login_per_email_15min=100, rl_go_per_minute=100)
    email = f"itest-ratelimit-reg-{uuid.uuid4().hex}@example.test"
    track(client, "register_ip", "testclient")
    registered = client.post("/api/v1/auth/register", json={"email": email, "password": "mat-khau-hop-le"})
    assert registered.status_code == 201
    track(client, "login_ip", "testclient")
    track(client, "login_email", email)
    logged_in = client.post("/api/v1/auth/login", json={"email": email, "password": "mat-khau-hop-le"})
    assert logged_in.status_code == 200
    link = client.post("/api/v1/links", headers={"Authorization": f"Bearer {logged_in.json()['access_token']}"},
                       json={"url": "https://shopee.vn/product/990003/100003"})
    assert link.status_code == 200

    monkeypatch.setattr(ratelimit, "_INCREMENT", text("SELECT * FROM definitely_missing_rate_limits_table"))
    track(client, "go", "testclient")
    assert client.get(f"/go/{link.json()['code']}").status_code == 302
    track(client, "login_ip", "testclient")
    track(client, "login_email", email)
    failed_login = client.post("/api/v1/auth/login", json={"email": email, "password": "sai-mat-khau"})
    assert failed_login.status_code == 401


BFF = "bff-itest-secret-0123456789"


def bff_login(client, visitor_ip, secret=BFF, email=None):
    """Đăng nhập sai như BFF làm: kết nối từ 127.0.0.1 (testclient), IP thật trong X-Visitor-IP."""
    email = email or f"itest-bff-{visitor_ip.replace('.', '-')}@example.test"
    track(client, "login_ip", visitor_ip)
    track(client, "login_ip", "testclient")
    track(client, "login_email", email)
    headers = {"x-visitor-ip": visitor_ip}
    if secret is not None:
        headers["x-bff-secret"] = secret
    return client.post("/api/v1/auth/login", headers=headers, json={"email": email, "password": "sai-mat-khau"})


def test_bff_visitors_have_separate_counters(pg, make_settings):
    client = api(pg, make_settings, bff_shared_secret=BFF, rl_login_per_minute=2)
    a = [bff_login(client, "198.51.100.41").status_code for _ in range(3)]
    b = [bff_login(client, "198.51.100.42").status_code for _ in range(3)]
    assert a == [401, 401, 429]
    assert b == [401, 401, 429]        # khách B không bị tính chung với khách A; mỗi người có bộ đếm riêng


def test_forged_visitor_ip_cannot_dodge_the_limit(pg, make_settings):
    client = api(pg, make_settings, bff_shared_secret=BFF, rl_login_per_minute=2)
    # Sai secret: mọi "IP khác nhau" đều bị tính theo IP kết nối thật => vẫn bị chặn ở lần thứ 3
    codes = [bff_login(client, f"198.51.100.{50 + n}", secret="forged").status_code for n in range(3)]
    assert codes == [401, 401, 429]


def test_visitor_ip_ignored_when_no_secret_configured(pg, make_settings):
    client = api(pg, make_settings, rl_login_per_minute=2)       # bff_shared_secret để trống
    codes = [bff_login(client, f"198.51.100.{60 + n}", secret=BFF).status_code for n in range(3)]
    assert codes == [401, 401, 429]
