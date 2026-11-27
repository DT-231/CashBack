"""Rate limit Postgres thật, bao gồm race giữa nhiều request."""
from concurrent.futures import ThreadPoolExecutor

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
    yield engine, settings
    values = [("login_ip", f"198.51.100.{n}") for n in [13, *range(20, 31), 40, 41, 42, 43]] + [
        ("login_ip", "198.51.100.15"), ("login_ip", "198.51.100.16"),
        ("login_ip", "testclient"),
        ("login_email", "itest-ratelimit@example.test"),
        ("login_email", "itest-parallel@example.test"),
    ]
    keys = [f"{scope}:{limiter_key(settings, value)}" for scope, value in values]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM rate_limits WHERE key = ANY(:keys)"), {"keys": keys})
    engine.dispose()


def api(pg, make_settings, **overrides):
    engine, _ = pg
    settings = make_settings(database_url=DB_URL, ip_salt=SALT, rl_enabled=True,
                             jwt_secret="j" * 40, **overrides)
    return TestClient(create_app(settings, engine=engine), raise_server_exceptions=False)


def login(client, address="198.51.100.13", email="itest-ratelimit@example.test"):
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
    for _ in range(3):
        assert client.post("/api/v1/auth/login", headers={"cf-connecting-ip": "198.51.100.13"},
                           json={"email": "invalid", "password": "x"}).status_code == 422
    with pg[0].connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM rate_limits WHERE key LIKE 'login_email:%'")).scalar_one() == 0


def test_proxy_header_is_used_only_when_trusted(pg, make_settings):
    trusted = api(pg, make_settings, trust_proxy_headers=True, rl_login_per_minute=1)
    assert login(trusted, "198.51.100.40").status_code == 401
    assert login(trusted, "198.51.100.41").status_code == 401

    untrusted = api(pg, make_settings, trust_proxy_headers=False, rl_login_per_minute=1)
    assert login(untrusted, "198.51.100.42").status_code == 401
    assert login(untrusted, "198.51.100.43").status_code == 429
