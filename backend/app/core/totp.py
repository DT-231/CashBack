"""TOTP (RFC 6238, HMAC-SHA1, 30 giây, 6 chữ số) chỉ dùng thư viện chuẩn. Tương thích Google Authenticator, Authy, 1Password.

`verify` chống phát lại: chỉ nhận bước thời gian LỚN HƠN bước đã dùng gần nhất (`last_step`), nên một mã chỉ dùng được một lần.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote

PERIOD = 30
DIGITS = 6
WINDOW = 1          # chấp nhận lệch đồng hồ ±1 bước (±30 giây)


def generate_secret() -> str:
    """20 byte ngẫu nhiên (160 bit, đúng khuyến nghị RFC 4226) dạng base32 không đệm."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret_b32: str) -> bytes:
    return base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8), casefold=True)


def code_at(secret_b32: str, step: int, digits: int = DIGITS) -> str:
    mac = hmac.new(_key(secret_b32), struct.pack(">Q", step), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    value = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(value).zfill(digits)


def current_step(now: float) -> int:
    return int(now // PERIOD)


def verify(secret_b32: str, code: str, now: float, last_step: int = 0) -> int | None:
    """Bước thời gian khớp (để caller lưu làm `last_step`) hoặc None. Kiểm tra TẤT CẢ các bước trong cửa sổ (không thoát sớm)."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isascii() or not code.isdigit():
        return None
    matched = None
    for step in range(current_step(now) - WINDOW, current_step(now) + WINDOW + 1):
        if hmac.compare_digest(code_at(secret_b32, step), code) and step > last_step:
            matched = step if matched is None else max(matched, step)
    return matched


def provisioning_uri(secret_b32: str, account: str, issuer: str) -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret_b32}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}")
