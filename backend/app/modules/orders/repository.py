"""SQL của orders. Nhận Connection đang trong transaction; không commit. Chỉ đụng bảng của chính orders."""
from __future__ import annotations

import json

from sqlalchemy import Connection, text


LOCK_KEY = 74_121_001   # khóa advisory: chỉ một tiến trình đồng bộ đơn tại một thời điểm


def try_lock(conn: Connection) -> bool:
    return bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar())


def unlock(conn: Connection) -> None:
    conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})


def get_status(conn: Connection, order_sn: str):
    return conn.execute(text("SELECT id, status, completed_at, user_id, post_id FROM shopee_orders "
                             "WHERE order_sn = :s"), {"s": order_sn}).mappings().first()


def insert_order(conn: Connection, o, attr, status: str, completed_at) -> int | None:
    """None nếu `order_sn` đã tồn tại (chạy chồng/đua): caller đọc lại rồi đi đường cập nhật."""
    return conn.execute(text(
        "INSERT INTO shopee_orders(order_sn, raw_status, status, utm_content, source_type, user_id, click_id, post_id, "
        "commission_micro, purchase_time, completed_at, raw) "
        "VALUES (:sn, :rs, :st, :utm, :src, :u, :c, :p, :com, :pt, :ca, CAST(:raw AS jsonb)) "
        "ON CONFLICT (order_sn) DO NOTHING RETURNING id"),
        {"sn": o.order_sn, "rs": o.raw_status, "st": status, "utm": o.utm_content, "src": attr.source_type,
         "u": attr.user_id, "c": attr.click_id, "p": attr.post_id, "com": o.commission_micro, "pt": o.purchase_time,
         "ca": completed_at, "raw": json.dumps(o.raw, ensure_ascii=False, default=str)}).scalar_one_or_none()


def update_order(conn: Connection, order_id: int, o, status: str, completed_at) -> None:
    """Chỉ cập nhật phần Shopee quyết định. KHÔNG đụng user_id/click_id/post_id/source_type/utm_content:
    staff có thể đã gán tay đơn mồ côi (T-044) và không được bị sync ghi đè."""
    conn.execute(text(
        "UPDATE shopee_orders SET raw_status = :rs, status = :st, commission_micro = :com, "
        "purchase_time = COALESCE(:pt, purchase_time), completed_at = :ca, raw = CAST(:raw AS jsonb), "
        "updated_at = now() WHERE id = :i"),
        {"rs": o.raw_status, "st": status, "com": o.commission_micro, "pt": o.purchase_time, "ca": completed_at,
         "raw": json.dumps(o.raw, ensure_ascii=False, default=str), "i": order_id})


def set_attribution(conn: Connection, order_id: int, utm_content: str, attr) -> None:
    """Chỉ dùng cho đơn CHƯA ai nhận (user_id và post_id còn NULL): đơn mồ côi nay đã khớp được."""
    conn.execute(text("UPDATE shopee_orders SET utm_content = :utm, source_type = :src, user_id = :u, click_id = :c, "
                      "post_id = :p WHERE id = :i AND user_id IS NULL AND post_id IS NULL"),
                 {"utm": utm_content, "src": attr.source_type, "u": attr.user_id, "c": attr.click_id,
                  "p": attr.post_id, "i": order_id})


def delete_orphan(conn: Connection, order_id: int) -> None:
    conn.execute(text("DELETE FROM orphan_orders WHERE order_id = :i"), {"i": order_id})


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


def attributed_orders(conn: Connection, after_id: int, limit: int, recent_days: int):
    """Đơn đã gán cho user mà ví còn có thể phải xử lý: chưa chốt (PENDING/COMPLETED) hoặc mới đổi gần đây."""
    return conn.execute(text(
        "SELECT id, user_id, status, commission_micro, completed_at FROM shopee_orders "
        "WHERE user_id IS NOT NULL AND id > :a AND (status IN ('PENDING', 'COMPLETED') "
        "OR updated_at > now() - make_interval(days => :d)) ORDER BY id LIMIT :l"),
        {"a": after_id, "d": recent_days, "l": limit}).mappings().all()


def user_orders(conn: Connection, user_id: int, limit: int, offset: int):
    """Đơn của MỘT user (mới nhất trước). Không bao giờ trả đơn của người khác hay đơn mồ côi (user_id NULL)."""
    return conn.execute(text(
        "SELECT id, order_sn, status, purchase_time, completed_at FROM shopee_orders WHERE user_id = :u "
        "ORDER BY COALESCE(purchase_time, created_at) DESC, id DESC LIMIT :l OFFSET :o"),
        {"u": user_id, "l": limit, "o": offset}).mappings().all()


def latest_finished_run(conn: Connection):
    return conn.execute(text("SELECT result, finished_at FROM sync_runs WHERE kind = 'orders' "
                             "AND finished_at IS NOT NULL ORDER BY id DESC LIMIT 1")).mappings().first()


def list_orphans(conn: Connection, limit: int, offset: int):
    """Đơn mồ côi CHƯA ai nhận (staff/admin gán tay được), mới nhất trước."""
    return conn.execute(text(
        "SELECT o.id, o.order_sn, o.status, o.commission_micro, o.purchase_time, o.utm_content, oo.reason "
        "FROM orphan_orders oo JOIN shopee_orders o ON o.id = oo.order_id "
        "WHERE oo.assigned_to_user IS NULL AND o.user_id IS NULL AND o.post_id IS NULL "
        "ORDER BY o.id DESC LIMIT :l OFFSET :o"), {"l": limit, "o": offset}).mappings().all()


def lock_order(conn: Connection, order_id: int):
    return conn.execute(text("SELECT id, user_id, post_id FROM shopee_orders WHERE id = :i FOR UPDATE"),
                        {"i": order_id}).mappings().first()


def has_open_orphan(conn: Connection, order_id: int) -> bool:
    return conn.execute(text("SELECT 1 FROM orphan_orders WHERE order_id = :i AND assigned_to_user IS NULL"),
                        {"i": order_id}).first() is not None


def assign_orphan(conn: Connection, order_id: int, user_id: int, admin_id: int) -> bool:
    """Gán đơn cho user (chỉ khi còn mồ côi). Dòng orphan_orders được giữ lại làm lịch sử với assigned_to_user/assigned_by."""
    won = conn.execute(text("UPDATE shopee_orders SET user_id = :u, source_type = 'user', updated_at = now() "
                            "WHERE id = :i AND user_id IS NULL AND post_id IS NULL RETURNING 1"), {"u": user_id, "i": order_id}).first()
    if won is None:
        return False
    conn.execute(text("UPDATE orphan_orders SET assigned_to_user = :u, assigned_by = :a WHERE order_id = :i"),
                 {"u": user_id, "a": admin_id, "i": order_id})
    return True
