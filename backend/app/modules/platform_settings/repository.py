from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, text


def get_effective(conn: Connection, key: str, at: datetime):
    """Giá trị có hiệu lực tại thời điểm `at` (bản ghi mới nhất có effective_from <= at)."""
    return conn.execute(text("SELECT value FROM settings WHERE key = :k AND effective_from <= :t "
                             "ORDER BY effective_from DESC LIMIT 1"), {"k": key, "t": at}).scalar_one_or_none()


def put(conn: Connection, key: str, value_json: str, effective_from: datetime) -> None:
    conn.execute(text("INSERT INTO settings(key, value, effective_from) VALUES (:k, CAST(:v AS jsonb), :t) "
                      "ON CONFLICT (key, effective_from) DO UPDATE SET value = EXCLUDED.value"),
                 {"k": key, "v": value_json, "t": effective_from})
