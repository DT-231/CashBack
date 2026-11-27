"""Lọc `detail` của audit log: KHÔNG bao giờ ghi mật khẩu, token, cookie, số tài khoản. Whitelist theo tên khóa + che giá trị trông như bí mật."""
from __future__ import annotations

import json
import re

REDACTED = "[REDACTED]"
MAX_DEPTH = 4
MAX_JSON_CHARS = 4000

# Khóa chứa các đoạn này bị che hoàn toàn (không phân biệt hoa thường).
_KEY_PARTS = ("password", "passwd", "pwd", "token", "secret", "cookie", "authorization", "api_key", "apikey",
              "jwt", "otp", "cvv", "card", "iban", "stk", "signature", "private", "credential", "session")
_KEY_EXACT = {"pin", "key", "auth", "csrf"}
_JWT = re.compile(r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")      # JWT nằm bất kỳ đâu trong chuỗi
_OPAQUE = re.compile(r"[A-Za-z0-9_-]{32,}")                                          # refresh token, khóa hex/base64 dài
_LONG_DIGITS = re.compile(r"\d{8,}")                    # số tài khoản/thẻ/điện thoại nằm trong chuỗi
_BEARER = re.compile(r"(?i)\bbearer\s+\S+")


def _sensitive_key(k: str) -> bool:
    low = k.lower()
    if low in _KEY_EXACT or any(p in low for p in _KEY_PARTS):
        return True
    return "account" in low and not low.endswith("_id")          # account_number: che; bank_account_id: giữ (chỉ là id)


def _clean_str(s: str) -> str:
    s = _BEARER.sub(REDACTED, s)
    s = _OPAQUE.sub(REDACTED, _JWT.sub(REDACTED, s))
    return _LONG_DIGITS.sub(REDACTED, s)[:500]


def sanitize(obj, depth: int = 0):
    if depth > MAX_DEPTH:
        return REDACTED
    if isinstance(obj, dict):
        return {str(k)[:60]: (REDACTED if _sensitive_key(str(k)) else sanitize(v, depth + 1)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v, depth + 1) for v in list(obj)[:50]]
    if isinstance(obj, str):
        return _clean_str(obj)
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    return _clean_str(str(obj))


def sanitize_detail(detail: dict | None) -> dict | None:
    if detail is None:
        return None
    clean = sanitize(detail)
    if len(json.dumps(clean, ensure_ascii=False, default=str)) > MAX_JSON_CHARS:
        return {"truncated": True}
    return clean
