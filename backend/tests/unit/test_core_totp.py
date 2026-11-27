"""TOTP RFC 6238: vector kiểm thử chính thức (SHA1), cửa sổ, chống phát lại, định dạng."""
import base64

import pytest

from app.core import totp

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")     # bí mật dùng trong RFC 6238 (SHA1)
# (thời điểm, mã 8 chữ số của RFC; mã 6 chữ số là 6 ký tự cuối)
RFC_VECTORS = [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"), (1234567890, "89005924"),
               (2000000000, "69279037"), (20000000000, "65353130")]


@pytest.mark.parametrize("t,code8", RFC_VECTORS)
def test_rfc6238_vectors(t, code8):
    assert totp.code_at(RFC_SECRET, t // 30, digits=8) == code8
    assert totp.code_at(RFC_SECRET, t // 30) == code8[-6:]


def test_verify_accepts_current_and_adjacent_steps_only():
    now = 1_700_000_000.0
    s = totp.current_step(now)
    for d in (-1, 0, 1):
        assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, s + d), now) == s + d
    for d in (-2, 2, 5):
        assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, s + d), now) is None


def test_a_code_cannot_be_replayed_and_older_steps_are_refused():
    now = 1_700_000_000.0
    s = totp.current_step(now)
    code = totp.code_at(RFC_SECRET, s)
    assert totp.verify(RFC_SECRET, code, now, last_step=0) == s
    assert totp.verify(RFC_SECRET, code, now, last_step=s) is None                       # cùng bước: đã dùng
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, s - 1), now, last_step=s) is None   # bước cũ hơn bước đã dùng
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, s + 1), now, last_step=s) == s + 1  # bước mới hơn thì được


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "12 34 5", "１２３４５６", None, "00000a", "-12345"])
def test_malformed_codes_are_rejected(bad):
    assert totp.verify(RFC_SECRET, bad, 1_700_000_000.0) is None


def test_spaces_inside_a_valid_code_are_tolerated_as_authenticator_apps_display_them():
    now = 1_700_000_000.0
    code = totp.code_at(RFC_SECRET, totp.current_step(now))
    assert totp.verify(RFC_SECRET, f"{code[:3]} {code[3:]}", now) is not None


def test_secret_and_uri():
    a, b = totp.generate_secret(), totp.generate_secret()
    assert a != b and len(a) == 32 and set(a) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
    assert len(base64.b32decode(a)) == 20
    uri = totp.provisioning_uri(a, "admin@example.test", "Cash Back")
    assert uri.startswith("otpauth://totp/Cash%20Back:admin%40example.test?secret=" + a) and "period=30" in uri and "digits=6" in uri
