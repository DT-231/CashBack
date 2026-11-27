"""Băm mật khẩu (argon2id), access token JWT, refresh token ngẫu nhiên. Không biết HTTP, không biết DB."""
from __future__ import annotations

import hashlib
import secrets
import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import ConfigError, Settings

_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("khong-phai-mat-khau-that")   # để user không tồn tại tốn thời gian như user có tồn tại


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Luôn chạy một phép băm argon2 kể cả khi `stored_hash` là None (chống dò email qua thời gian phản hồi)."""
    try:
        ok = _ph.verify(stored_hash or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return ok and stored_hash is not None


def _secret(settings: Settings) -> str:
    s = settings.jwt_secret.get_secret_value()
    if len(s) < 32:
        raise ConfigError("JWT_SECRET phải có ít nhất 32 ký tự")
    return s


def make_access_token(settings: Settings, user_id: int, role: str, mfa_at: int | None = None) -> str:
    """`mfa_at`: epoch giây của lần nhập mã TOTP/mã khôi phục gần nhất của phiên này (None = chưa xác minh hai lớp)."""
    now = int(time.time())
    claims = {"sub": str(user_id), "role": role, "typ": "access", "iat": now,
              "exp": now + settings.access_ttl_min * 60}
    if mfa_at is not None:
        claims["mfa_at"] = int(mfa_at)
    return jwt.encode(claims, _secret(settings), algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> dict | None:
    try:
        claims = jwt.decode(token, _secret(settings), algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == "access" else None


def new_refresh_token() -> tuple[str, str]:
    """(token gốc gửi cho client, hash lưu DB). DB không bao giờ giữ token gốc."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
