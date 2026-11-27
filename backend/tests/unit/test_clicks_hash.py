from app.modules.clicks.service import hash_value


def test_no_salt_or_no_value_stores_nothing(make_settings):
    assert hash_value(make_settings(), "1.2.3.4") is None
    assert hash_value(make_settings(ip_salt="s" * 32), None) is None
    assert hash_value(make_settings(ip_salt="s" * 32), "") is None


def test_hash_is_keyed_stable_and_hides_the_ip(make_settings):
    a, b = make_settings(ip_salt="a" * 32), make_settings(ip_salt="b" * 32)
    h = hash_value(a, "203.0.113.9")
    assert h == hash_value(a, "203.0.113.9") and len(h) == 16 and "203" not in h
    assert h != hash_value(b, "203.0.113.9") and h != hash_value(a, "203.0.113.10")
