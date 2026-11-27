"""Xác thực Tool API bằng Bearer key. Khóa lưu dạng SHA-256 (khóa đủ dài, ngẫu nhiên nên không cần salt)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from sqlalchemy import Engine

from app.core.config import Settings
from app.modules.agent_auth import repository


@dataclass(frozen=True)
class AgentIdentity:
    key_id: int | None     # None = khóa khởi tạo từ AGENT_API_KEY (chưa nằm trong bảng agent_keys)
    name: str


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return "mk_" + secrets.token_urlsafe(32)


class AgentAuth:
    def __init__(self, settings: Settings, engine: Engine | None):
        self.s, self.engine = settings, engine

    def authenticate(self, token: str | None) -> AgentIdentity | None:
        if not token:
            return None
        env_key = self.s.agent_api_key.get_secret_value()
        if env_key and hmac.compare_digest(token.encode(), env_key.encode()):
            return AgentIdentity(None, "env")
        if self.engine is None:
            return None
        with self.engine.connect() as conn:
            row = repository.find_active(conn, hash_key(token))
        return AgentIdentity(row["id"], row["name"]) if row else None

    def issue(self, name: str) -> str:
        """Tạo khóa mới; trả khóa gốc DUY NHẤT một lần (DB chỉ giữ hash)."""
        key = new_key()
        with self.engine.begin() as conn:
            repository.create(conn, name, hash_key(key))
        return key
