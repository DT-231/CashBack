import time

import jwt
import pytest

from app.core import security
from app.core.config import ConfigError

SECRET = "k" * 40


def test_password_hash_and_verify():
    h = security.hash_password("mat-khau-dai-123")
    assert h.startswith("$argon2id$") and "mat-khau" not in h
    assert security.verify_password("mat-khau-dai-123", h) is True
    assert security.verify_password("sai-mat-khau-xx", h) is False


def test_verify_without_user_is_false_but_still_hashes():
    assert security.verify_password("bat-ky-mat-khau", None) is False
    assert security.verify_password("bat-ky-mat-khau", "khong-phai-hash") is False


def test_access_token_roundtrip(make_settings):
    s = make_settings(jwt_secret=SECRET)
    c = security.decode_access_token(s, security.make_access_token(s, 42, "member"))
    assert c["sub"] == "42" and c["role"] == "member" and c["typ"] == "access"


def test_access_token_rejects_tamper_expired_wrong_type_and_alg_none(make_settings):
    s = make_settings(jwt_secret=SECRET)
    good = security.make_access_token(s, 1, "member")
    assert security.decode_access_token(s, good + "x") is None
    assert security.decode_access_token(make_settings(jwt_secret="z" * 40), good) is None
    now = int(time.time())
    expired = jwt.encode({"sub": "1", "typ": "access", "exp": now - 5}, SECRET, algorithm="HS256")
    other_type = jwt.encode({"sub": "1", "typ": "refresh", "exp": now + 99}, SECRET, algorithm="HS256")
    none_alg = jwt.encode({"sub": "1", "typ": "access", "exp": now + 99}, None, algorithm="none")
    for bad in (expired, other_type, none_alg, "", "abc.def.ghi"):
        assert security.decode_access_token(s, bad) is None


def test_weak_or_missing_secret_is_config_error(make_settings):
    for secret in ("", "ngan"):
        with pytest.raises(ConfigError):
            security.make_access_token(make_settings(jwt_secret=secret), 1, "member")


def test_refresh_token_only_hash_is_stored():
    raw, hashed = security.new_refresh_token()
    assert raw != hashed and security.hash_refresh_token(raw) == hashed and len(raw) >= 40
    assert security.new_refresh_token()[0] != raw
