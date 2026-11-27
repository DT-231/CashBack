"""Truy cập DB: CHỈ ở đây mới có SQL. Nhận Connection đang trong transaction; không commit, không biết HTTP."""
from __future__ import annotations

from sqlalchemy import Connection, text


def get(conn: Connection, thing_id: int):
    return conn.execute(text("SELECT id, name FROM things WHERE id = :i"), {"i": thing_id}).mappings().first()
