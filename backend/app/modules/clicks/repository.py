"""SQL của clicks. Nhận Connection đang trong transaction; không commit."""
from __future__ import annotations

from sqlalchemy import Connection, text


def next_click_id(conn: Connection) -> int:
    """Cấp trước id để sub_id (chứa click_id) được ghi cùng lúc với dòng click, không cần UPDATE."""
    return conn.execute(text("SELECT nextval(pg_get_serial_sequence('clicks', 'id'))")).scalar_one()


def insert_click(conn: Connection, click_id: int, link_id: int, sub_id: str, ip_hash: str | None,
                 ua_hash: str | None) -> None:
    conn.execute(text("INSERT INTO clicks(id, link_id, sub_id, ip_hash, ua_hash) VALUES (:id, :l, :s, :ip, :ua)"),
                 {"id": click_id, "l": link_id, "s": sub_id, "ip": ip_hash, "ua": ua_hash})


def link_of_click(conn: Connection, click_id: int) -> int | None:
    return conn.execute(text("SELECT link_id FROM clicks WHERE id = :i"), {"i": click_id}).scalar_one_or_none()
