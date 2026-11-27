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
