from __future__ import annotations

from sqlalchemy import Connection, text


def upsert_product(conn: Connection, shop_id: int, item_id: int):
    conn.execute(text(
        "INSERT INTO products(shop_id, item_id) VALUES (:s, :i) "
        "ON CONFLICT (shop_id, item_id) DO NOTHING"), {"s": shop_id, "i": item_id})
    return conn.execute(text(
        "SELECT id, shop_id, item_id, name FROM products WHERE shop_id=:s AND item_id=:i"),
        {"s": shop_id, "i": item_id}).mappings().one()


def get_user_link(conn: Connection, user_id: int, product_id: int):
    return conn.execute(text(
        "SELECT id, code, created_at FROM links WHERE user_id=:u AND product_id=:p"),
        {"u": user_id, "p": product_id}).mappings().first()


def insert_user_link(conn: Connection, user_id: int, product_id: int, code: str) -> bool:
    return conn.execute(text(
        "INSERT INTO links(user_id, product_id, code) VALUES (:u, :p, :c) "
        "ON CONFLICT DO NOTHING RETURNING id"), {"u": user_id, "p": product_id, "c": code}).scalar_one_or_none() is not None


def list_user_links(conn: Connection, user_id: int, limit: int, offset: int):
    return conn.execute(text(
        "SELECT l.code, l.created_at, p.shop_id, p.item_id, p.name, "
        "(SELECT count(*) FROM clicks c WHERE c.link_id=l.id) AS clicks "
        "FROM links l JOIN products p ON p.id=l.product_id WHERE l.user_id=:u "
        "ORDER BY l.created_at DESC, l.id DESC LIMIT :lim OFFSET :off"),
        {"u": user_id, "lim": limit, "off": offset}).mappings().all()


def get_by_code(conn: Connection, code: str):
    return conn.execute(text(
        "SELECT l.id AS link_id, l.user_id, p.shop_id, p.item_id FROM links l "
        "JOIN products p ON p.id = l.product_id WHERE l.code = :c"), {"c": code}).mappings().first()
