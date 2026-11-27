"""Log không được chứa cookie, token, mật khẩu, khóa, URL có mật khẩu, mã OTP... (T-065)."""
import json
import logging

import pytest

from app.core import logging as clog

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4fwpMeJf36"


def emit(msg="m", args=(), **extra):
    rec = logging.LogRecord("t", logging.INFO, "f", 1, msg, args, None)
    rec.__dict__.update(extra)
    return clog.JsonFormatter().format(rec)


@pytest.mark.parametrize("key", ["cookie", "Cookie", "set-cookie", "authorization", "Authorization", "password", "new_password", "token",
                                 "access_token", "refresh_token", "api_key", "x-api-key", "BANK_ENC_KEY", "bank_enc_key", "x-bff-secret",
                                 "bff_shared_secret", "cookie_enc", "secret_enc", "idempotency-key", "recovery_code", "otp", "csrf",
                                 "x-csrf-token", "account_no", "account_number", "bank_account_number", "session_id", "private_key"])
def test_sensitive_keys_in_extra_are_masked_whatever_their_spelling(key):
    out = json.loads(emit(**{key.replace("-", "_"): "VALUE-THAT-MUST-NOT-APPEAR"}))
    assert "VALUE-THAT-MUST-NOT-APPEAR" not in json.dumps(out)
    assert clog.redact({key: "VALUE-THAT-MUST-NOT-APPEAR"}) == {key: "***"}


def test_nested_and_list_structures_are_masked():
    out = clog.redact({"req": {"headers": {"Authorization": "Bearer abc", "X-Request-Id": "r1"}, "items": [{"refresh_token": "t"}, {"id": 5}]}})
    assert out == {"req": {"headers": {"Authorization": "***", "X-Request-Id": "r1"}, "items": [{"refresh_token": "***"}, {"id": 5}]}}


def test_secret_shaped_text_in_the_message_is_masked():
    for text in (f"Authorization: Bearer {JWT}", f"got header bearer {JWT}", f"token={JWT}", f"jwt {JWT} end",
                 "cookie=SPC_ST=abc123; other", "password: hunter2hunter2", "api_key = k-123456789",
                 "connect postgresql+psycopg://cashback:Sup3rSecret@127.0.0.1:5433/cashback failed",
                 "mysql://root:pw123@db/x and redis://:onlypass@h", "sent Bearer opaque-token-abc123xyz987 to upstream"):
        out = json.loads(emit(text))["msg"]
        for leak in (JWT, "abc123", "hunter2", "k-123456789", "Sup3rSecret", "pw123", "opaque-token-abc123xyz987"):
            assert leak not in out, (text, out)
    assert "cashback" in json.loads(emit("connect postgresql://cashback:Sup3rSecret@h/db"))["msg"]      # tên user còn để chẩn đoán


def test_format_args_and_exceptions_are_masked():
    out = json.loads(emit("login with %s", (f"Bearer {JWT}",)))
    assert JWT not in out["msg"]
    try:
        raise RuntimeError(f"upstream said token={JWT}")
    except RuntimeError:
        import sys
        rec = logging.LogRecord("t", logging.ERROR, "f", 1, "boom", (), sys.exc_info())
        assert JWT not in clog.JsonFormatter().format(rec)


def test_ordinary_fields_survive():
    out = json.loads(emit("request", method="GET", path="/health", status=200, ms=1.5, order_id=7, user_id=3))
    assert (out["method"], out["path"], out["status"], out["ms"], out["order_id"], out["user_id"]) == ("GET", "/health", 200, 1.5, 7, 3)
    assert out["msg"] == "request" and out["level"] == "INFO" and "request_id" in out
