"""Kết nối Postgres. Repository nhận `Connection` đang trong transaction; service quyết định ranh giới."""
from __future__ import annotations

from sqlalchemy import Engine, create_engine

from app.core.config import ConfigError, Settings


def make_engine(settings: Settings) -> Engine:
    if not settings.database_url:
        raise ConfigError("Thiếu biến môi trường: DATABASE_URL")
    return create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
