import pytest
from starlette.requests import Request

from app.core.clientip import client_ip, keyed_hash, limiter_key


def req(headers=None, host="203.0.113.5"):
    scope = {"type": "http", "method": "GET", "path": "/", "query_string": b"",
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
             "client": (host, 1234) if host else None}
    return Request(scope)


def test_header_ignored_unless_proxy_is_trusted():
    r = req({"CF-Connecting-IP": "198.51.100.7"})
    assert client_ip(r, trust_proxy_headers=False) == "203.0.113.5"
    assert client_ip(r, trust_proxy_headers=True) == "198.51.100.7"


@pytest.mark.parametrize("bad", ["khong-phai-ip", "", "1.2.3", "1.2.3.4, 5.6.7.8", "<script>", "999.1.1.1"])
def test_invalid_header_falls_back_to_the_connection_ip(bad):
    assert client_ip(req({"CF-Connecting-IP": bad}), True) == "203.0.113.5"


def test_ipv6_is_normalised_and_missing_info_is_none():
    assert client_ip(req({"CF-Connecting-IP": "2001:0DB8:0000:0000:0000:0000:0000:0001"}), True) == "2001:db8::1"
    assert client_ip(req(host=None), True) is None
    assert client_ip(req({"CF-Connecting-IP": " 198.51.100.7 "}), True) == "198.51.100.7"


def test_keyed_hash_needs_a_salt_and_hides_the_value(make_settings):
    assert keyed_hash(make_settings(), "1.2.3.4") is None
    s = make_settings(ip_salt="i" * 32)
    h = keyed_hash(s, "1.2.3.4")
    assert len(h) == 16 and "1.2.3.4" not in h and h == keyed_hash(s, "1.2.3.4")
    assert h != keyed_hash(make_settings(ip_salt="j" * 32), "1.2.3.4")


def test_limiter_key_always_returns_a_key_without_the_raw_value(make_settings):
    for s in (make_settings(), make_settings(ip_salt="i" * 32)):
        k = limiter_key(s, "1.2.3.4")
        assert "1.2.3.4" not in k and k == limiter_key(s, "1.2.3.4") and k != limiter_key(s, "1.2.3.5")
        assert limiter_key(s, None) and limiter_key(s, None) == limiter_key(s, "")


# --- T-017: X-Visitor-IP chỉ được tin khi kèm bí mật chung đúng ---
SECRET = "bff-shared-secret-0123456789"


def bff(ip="198.51.100.9", secret=SECRET, **extra):
    h = {"X-Visitor-IP": ip}
    if secret is not None:
        h["X-BFF-Secret"] = secret
    return req({**h, **extra})


def test_visitor_ip_trusted_with_correct_secret_even_without_proxy_trust():
    assert client_ip(bff(), False, SECRET) == "198.51.100.9"
    assert client_ip(bff("2001:0DB8:0:0:0:0:0:1"), False, SECRET) == "2001:db8::1"


@pytest.mark.parametrize("given", ["wrong-secret", SECRET + "x", SECRET[:-1], "", None])
def test_visitor_ip_ignored_when_secret_wrong_or_missing(given):
    assert client_ip(bff(secret=given), False, SECRET) == "203.0.113.5"        # IP kết nối
    assert client_ip(bff(secret=given), True, SECRET) == "203.0.113.5"         # trust_proxy nhưng không có CF header
    r = bff(secret=given, **{"CF-Connecting-IP": "198.51.100.77"})
    assert client_ip(r, True, SECRET) == "198.51.100.77"                       # rơi về CF-Connecting-IP, KHÔNG phải header giả


def test_visitor_ip_never_trusted_when_secret_not_configured():
    assert client_ip(bff(secret=SECRET), False, "") == "203.0.113.5"
    assert client_ip(bff(secret=""), False, "") == "203.0.113.5"               # secret rỗng cả hai phía không phải là "khớp"
    assert client_ip(bff(secret=None), False) == "203.0.113.5"


def test_visitor_ip_invalid_value_falls_back_even_with_correct_secret():
    for bad in ["not-an-ip", "1.2.3.4, 5.6.7.8", "999.1.1.1", ""]:
        assert client_ip(bff(bad), False, SECRET) == "203.0.113.5", bad


def test_secret_with_non_ascii_header_does_not_raise():
    r = Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "client": ("203.0.113.5", 1),
                 "headers": [(b"x-visitor-ip", b"198.51.100.9"), (b"x-bff-secret", "bí-mật-ñ".encode("utf-8"))]})
    assert client_ip(r, False, SECRET) == "203.0.113.5"


def test_secret_is_compared_in_constant_time(monkeypatch):
    import hmac
    from app.core import clientip
    seen = []
    real = hmac.compare_digest
    monkeypatch.setattr(clientip.hmac, "compare_digest", lambda a, b: seen.append((len(a), len(b))) or real(a, b))
    client_ip(bff(secret="short"), False, SECRET)
    assert seen and seen[0][0] == seen[0][1]       # so sánh hai digest cùng độ dài, qua hmac.compare_digest


def test_bff_secret_too_short_refuses_to_serve():
    from app.core.config import ConfigError, Settings
    with pytest.raises(ConfigError, match="BFF_SHARED_SECRET"):
        Settings(bff_shared_secret="short").validate_for_serving()
    Settings(bff_shared_secret="x" * 16).validate_for_serving()
    Settings().validate_for_serving()
