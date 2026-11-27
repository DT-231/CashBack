from types import SimpleNamespace


from app.core.clientip import limiter_key
from app.core.errors import RateLimited
from app.core.ratelimit import enforce_rate_limit


def request(settings, engine):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings, get_engine=lambda: engine)))


def test_limiter_key_never_contains_raw_ip_or_email(make_settings):
    values = ("198.51.100.42", "person@example.test")
    for salt in ("salt" * 8, ""):
        settings = make_settings(ip_salt=salt)
        for value in values:
            key = limiter_key(settings, value)
            assert value not in key
            assert len(key) <= 16


def test_disabled_limiter_never_opens_database(make_settings):
    enforce_rate_limit(request(make_settings(rl_enabled=False), None), "login_ip", "127.0.0.1", 1, 60)


def test_limit_error_has_retry_after_header():
    error = RateLimited("Thử lại sau", headers={"Retry-After": "7"})
    assert (error.status, error.code, error.headers["Retry-After"]) == (429, "rate_limited", "7")


def test_database_failure_is_fail_open(make_settings):
    def broken():
        raise RuntimeError("database unavailable")

    req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=make_settings(rl_enabled=True), get_engine=broken)))
    enforce_rate_limit(req, "go", "198.51.100.42", 1, 60)
