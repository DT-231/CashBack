"""Audit log không được chứa mật khẩu, token, cookie, số tài khoản."""
import json

from app.modules.audit.sanitize import REDACTED, sanitize_detail

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.SflKxwRJSMeKKF2QT4fwpMeJf36"


def test_sensitive_keys_are_masked_at_any_depth():
    d = {"password": "p", "new_password": "p", "access_token": "t", "refresh_token": "t", "Authorization": "Bearer abc",
         "cookie": "SPC_ST=x", "api_key": "k", "secret": "s", "otp": "123456", "pin": "1234",
         "bank_account_number": "0123456789", "account": "0123456789", "card_no": "4111", "session_id": "s",
         "nested": {"x": {"token": "t", "ok": 1}}, "rows": [{"password": "p", "id": 5}]}
    out = sanitize_detail(d)
    flat = json.dumps(out)
    for secret in ("SPC_ST", "0123456789", "4111", "Bearer abc", '"t"', '"p"'):
        assert secret not in flat, secret
    assert out["nested"]["x"]["ok"] == 1 and out["rows"][0]["id"] == 5
    assert all(out[k] == REDACTED for k in ("password", "new_password", "access_token", "bank_account_number", "account", "otp", "pin"))


def test_account_keys_are_masked_even_when_the_value_has_no_long_digit_run():
    out = sanitize_detail({"bank_account_number": "12-34-56-78", "account": "VCB 12 34", "account_holder": "NGUYEN VAN A"})
    assert out == {"bank_account_number": REDACTED, "account": REDACTED, "account_holder": REDACTED}


def test_non_secret_fields_are_kept():
    d = {"key": "hold_days", "value": 7, "bank_account_id": 12, "withdrawal_id": 9, "amount_vnd": 100000, "reason": "đơn bị hủy", "ok": True}
    out = sanitize_detail(d)
    assert out["bank_account_id"] == 12 and out["amount_vnd"] == 100000 and out["value"] == 7 and out["reason"] == "đơn bị hủy"
    assert out["key"] == REDACTED          # "key" trần bị che vì hay là khóa API; dùng tên cụ thể như setting_key để giữ


def test_secret_looking_values_are_masked_even_under_innocent_keys():
    out = sanitize_detail({"note": f"token {JWT}", "ref": JWT, "memo": "chuyển khoản STK 0123456789012 Vietcombank",
                           "hdr": "Bearer abc.def.ghi", "phone": "0901234567"})
    flat = json.dumps(out)
    assert JWT not in flat and "0123456789012" not in flat and "abc.def.ghi" not in flat and "0901234567" not in flat
    assert "Vietcombank" in flat


def test_opaque_long_tokens_are_masked_but_short_hashes_kept():
    out = sanitize_detail({"x": "refresh abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG", "ip_hash": "0123abcd4567ef89", "name": "Nguyen Van A"})
    assert "abcdefghijklmnopqrstuvwxyz0123456789" not in json.dumps(out)
    assert out["ip_hash"] == "0123abcd4567ef89" and out["name"] == "Nguyen Van A"


def test_small_numbers_and_ids_survive():
    assert sanitize_detail({"order_ref": "ORD-1234", "n": 1234567}) == {"order_ref": "ORD-1234", "n": 1234567}


def test_oversized_or_deep_detail_is_bounded():
    assert sanitize_detail({"big": ["ab " * 130] * 50}) == {"truncated": True}
    deep = {"a": {"b": {"c": {"d": {"e": {"f": 1}}}}}}
    assert REDACTED in json.dumps(sanitize_detail(deep))
    assert sanitize_detail(None) is None
