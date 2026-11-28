"""Log JSON có request_id/job_id; che dữ liệu nhạy cảm. Không bao giờ log cookie, token, số tài khoản."""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import time
import uuid

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

SENSITIVE_KEYS = {"cookie", "authorization", "token", "password", "secret", "api_key", "account_no", "set-cookie"}
# Khóa chứa các đoạn này (không phân biệt hoa thường) bị che hẳn: refresh_token, access_token, bank_enc_key, x-bff-secret, cookie_enc,
# secret_enc, idempotency-key, recovery_code, otp, csrf, account_number, session...
_KEY_PARTS = ("token", "password", "passwd", "secret", "cookie", "authorization", "api_key", "apikey", "bearer", "csrf", "otp", "recovery",
              "enc_key", "_enc", "account_no", "account_number", "idempotency", "session", "credential", "private")
_PATTERN = re.compile(r"(?i)\b(cookie|authorization|token|password|secret|api_key)\b(\s*[=:]\s*)([^\s,;&\"']+)")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")
_URL_CRED = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+):([^\s@/]+)@")      # postgresql://user:MẬT_KHẨU@host


def _sensitive_key(k) -> bool:
    low = str(k).lower().replace("-", "_")
    return low in SENSITIVE_KEYS or str(k).lower() in SENSITIVE_KEYS or any(p in low for p in _KEY_PARTS)


REDACTED = "***"
_RID_OK = re.compile(r"[A-Za-z0-9._-]{1,64}")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str | None = None) -> str:
    rid = value if value and _RID_OK.fullmatch(value) else uuid.uuid4().hex[:12]   # không tin giá trị từ client
    _request_id.set(rid)
    return rid


def redact_text(s: str) -> str:
    s = _URL_CRED.sub(lambda m: f"{m.group(1)}:{REDACTED}@", s)
    s = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", s)
    s = _JWT.sub(REDACTED, s)
    return _PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", s)


def redact(obj):
    if isinstance(obj, dict):
        return {k: (REDACTED if _sensitive_key(k) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


_STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
            "request_id": get_request_id(),
        }
        extra = {k: v for k, v in record.__dict__.items() if k not in _STD}
        out.update(redact(extra))
        if record.exc_info:
            out["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(out, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(level.upper())
