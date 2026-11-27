from __future__ import annotations

from sqlalchemy import Connection, text


def upsert_product(conn: Connection, shop_id: int, item_id: int) -> int:
    return conn.execute(text(
        "INSERT INTO products(shop_id, item_id) VALUES (:s, :i) "
        "ON CONFLICT (shop_id, item_id) DO UPDATE SET shop_id = EXCLUDED.shop_id RETURNING id"),
        {"s": shop_id, "i": item_id}).scalar_one()


def insert_post(conn: Connection, post_key: str, product_id: int, agent_key_id: int | None,
                page_code: str, category: str | None) -> int | None:
    """None nếu post_key đã tồn tại (không ghi đè)."""
    return conn.execute(text(
        "INSERT INTO posts(post_key, product_id, agent_key_id, page_code, category) "
        "VALUES (:k, :p, :a, :pc, :c) ON CONFLICT (post_key) DO NOTHING RETURNING id"),
        {"k": post_key, "p": product_id, "a": agent_key_id, "pc": page_code, "c": category}).scalar_one_or_none()


def get_by_key(conn: Connection, post_key: str):
    return conn.execute(text(
        "SELECT po.id, po.sub_id, po.page_code, pr.shop_id, pr.item_id FROM posts po "
        "JOIN products pr ON pr.id = po.product_id WHERE po.post_key = :k"), {"k": post_key}).mappings().first()


def set_sub_id(conn: Connection, post_id: int, sub_id: str) -> None:
    conn.execute(text("UPDATE posts SET sub_id = :s WHERE id = :i"), {"s": sub_id, "i": post_id})
