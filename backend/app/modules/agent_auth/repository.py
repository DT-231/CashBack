from __future__ import annotations

from sqlalchemy import Connection, text


def find_active(conn: Connection, key_hash: str):
    return conn.execute(text("SELECT id, name FROM agent_keys WHERE key_hash = :h AND revoked_at IS NULL"),
                        {"h": key_hash}).mappings().first()


def create(conn: Connection, name: str, key_hash: str) -> int:
    return conn.execute(text("INSERT INTO agent_keys(name, key_hash) VALUES (:n, :h) RETURNING id"),
                        {"n": name, "h": key_hash}).scalar_one()


def revoke(conn: Connection, key_id: int) -> None:
    conn.execute(text("UPDATE agent_keys SET revoked_at = now() WHERE id = :i AND revoked_at IS NULL"), {"i": key_id})
