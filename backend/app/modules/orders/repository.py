"""SQL của orders. Nhận Connection đang trong transaction; không commit.

Lưu ý: `exists` đọc (chỉ đọc) bảng clicks/links/posts của module khác để xác minh `sub_id` — không ghi gì ở đó.
"""
from __future__ import annotations

import json

from sqlalchemy import Connection, text


def exists(conn: Connection, kind: str, owner: int, ref: int) -> bool:
    """`sub_id` đã có chữ ký hợp lệ, nhưng vẫn phải khớp dữ liệu: click thuộc đúng user, link thuộc đúng user, post có thật."""
    sql = {
        "click": "SELECT 1 FROM clicks c JOIN links l ON l.id = c.link_id WHERE c.id = :r AND l.user_id = :o",
        "link": "SELECT 1 FROM links WHERE id = :r AND user_id = :o",
        "post": "SELECT 1 FROM posts WHERE id = :o",
    }[kind]
    return conn.execute(text(sql), {"o": owner, "r": ref}).first() is not None


def get_status(conn: Connection, order_sn: str):
    return conn.execute(text("SELECT id, status, completed_at FROM shopee_orders WHERE order_sn = :s"),
                        {"s": order_sn}).mappings().first()


def insert_order(conn: Connection, o, attr, status: str, completed_at) -> int:
    return conn.execute(text(
        "INSERT INTO shopee_orders(order_sn, raw_status, status, utm_content, source_type, user_id, click_id, post_id, "
        "commission_micro, purchase_time, completed_at, raw) "
        "VALUES (:sn, :rs, :st, :utm, :src, :u, :c, :p, :com, :pt, :ca, CAST(:raw AS jsonb)) RETURNING id"),
        {"sn": o.order_sn, "rs": o.raw_status, "st": status, "utm": o.utm_content, "src": attr.source_type,
         "u": attr.user_id, "c": attr.click_id, "p": attr.post_id, "com": o.commission_micro, "pt": o.purchase_time,
         "ca": completed_at, "raw": json.dumps(o.raw, ensure_ascii=False, default=str)}).scalar_one()


def update_order(conn: Connection, order_id: int, o, status: str, completed_at) -> None:
    """Chỉ cập nhật phần Shopee quyết định. KHÔNG đụng user_id/click_id/post_id/source_type/utm_content:
    staff có thể đã gán tay đơn mồ côi (T-044) và không được bị sync ghi đè."""
    conn.execute(text(
        "UPDATE shopee_orders SET raw_status = :rs, status = :st, commission_micro = :com, "
        "purchase_time = COALESCE(:pt, purchase_time), completed_at = :ca, raw = CAST(:raw AS jsonb), "
        "updated_at = now() WHERE id = :i"),
        {"rs": o.raw_status, "st": status, "com": o.commission_micro, "pt": o.purchase_time, "ca": completed_at,
         "raw": json.dumps(o.raw, ensure_ascii=False, default=str), "i": order_id})


def replace_items(conn: Connection, order_id: int, items) -> None:
    conn.execute(text("DELETE FROM shopee_order_items WHERE order_id = :i"), {"i": order_id})
    for it in items:
        conn.execute(text(
            "INSERT INTO shopee_order_items(order_id, item_id, shop_id, qty, price_micro, commission_micro, "
            "platform_rate_bp, brand_rate_bp, category_lv1) VALUES (:o, :it, :sh, :q, :p, :c, :pr, :br, :cat)"),
            {"o": order_id, "it": it.item_id, "sh": it.shop_id, "q": it.qty, "p": it.price_micro,
             "c": it.commission_micro, "pr": it.platform_rate_bp, "br": it.brand_rate_bp, "cat": it.category_lv1})


def add_orphan(conn: Connection, order_id: int, reason: str) -> None:
    conn.execute(text("INSERT INTO orphan_orders(order_id, reason) VALUES (:i, :r) ON CONFLICT (order_id) DO NOTHING"),
                 {"i": order_id, "r": reason[:200]})


def start_run(conn: Connection, kind: str) -> int:
    return conn.execute(text("INSERT INTO sync_runs(kind) VALUES (:k) RETURNING id"), {"k": kind}).scalar_one()


def finish_run(conn: Connection, run_id: int, result: str, rows: int) -> None:
    conn.execute(text("UPDATE sync_runs SET finished_at = now(), result = :r, rows = :n WHERE id = :i"),
                 {"r": result, "n": rows, "i": run_id})
