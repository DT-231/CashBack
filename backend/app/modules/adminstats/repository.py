"""Thống kê cho admin: CHỈ ĐỌC (SELECT) nhiều bảng. Không có INSERT/UPDATE/DELETE (test kiến trúc kiểm). Tiền là số nguyên (micro Shopee hoặc VND)."""
from __future__ import annotations

from sqlalchemy import Connection, text


def _one(conn: Connection, sql: str, **p):
    return conn.execute(text(sql), p).scalar_one()


def overview(conn: Connection, days: int) -> dict:
    d = {"d": days}
    users = conn.execute(text("SELECT count(*) AS total, count(*) FILTER (WHERE created_at > now() - make_interval(days => :d)) AS new, "
                              "count(*) FILTER (WHERE status = 'locked') AS locked FROM users"), d).mappings().one()
    orders = conn.execute(text(
        "SELECT status, count(*) AS n, COALESCE(sum(commission_micro), 0) AS micro FROM shopee_orders "
        "WHERE created_at > now() - make_interval(days => :d) GROUP BY status"), d).mappings().all()
    wallets = conn.execute(text("SELECT COALESCE(sum(pending_vnd),0) AS pending, COALESCE(sum(available_vnd),0) AS available, "
                                "COALESCE(sum(held_vnd),0) AS held FROM wallets")).mappings().one()
    wd = conn.execute(text("SELECT status, count(*) AS n, COALESCE(sum(amount_vnd),0) AS vnd FROM withdrawals GROUP BY status")).mappings().all()
    sync = conn.execute(text("SELECT result, finished_at FROM sync_runs WHERE kind = 'orders' AND finished_at IS NOT NULL "
                             "ORDER BY id DESC LIMIT 1")).mappings().first()
    return {
        "days": days,
        "users": dict(users),
        "clicks": _one(conn, "SELECT count(*) FROM clicks WHERE created_at > now() - make_interval(days => :d)", **d),
        "links": _one(conn, "SELECT count(*) FROM links WHERE created_at > now() - make_interval(days => :d)", **d),
        "orders": {r["status"]: {"count": r["n"], "commission_micro": int(r["micro"])} for r in orders},
        "orphans_open": _one(conn, "SELECT count(*) FROM orphan_orders oo JOIN shopee_orders o ON o.id = oo.order_id "
                                   "WHERE oo.assigned_to_user IS NULL AND o.user_id IS NULL AND o.post_id IS NULL"),
        "wallet_totals_vnd": {k: int(v) for k, v in wallets.items()},
        "withdrawals": {r["status"]: {"count": r["n"], "amount_vnd": int(r["vnd"])} for r in wd},
        "last_sync": dict(sync) if sync else None,
    }


def users(conn: Connection, q: str | None, limit: int, offset: int):
    sql = ("SELECT u.id, u.email, u.role, u.status, u.created_at, COALESCE(w.available_vnd, 0) AS available_vnd, "
           "COALESCE(w.pending_vnd, 0) AS pending_vnd, COALESCE(w.held_vnd, 0) AS held_vnd "
           "FROM users u LEFT JOIN wallets w ON w.user_id = u.id")
    p: dict = {"l": limit, "o": offset}
    if q:
        sql += " WHERE u.email LIKE :q ESCAPE '\\'"
        p["q"] = "%" + q.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return conn.execute(text(sql + " ORDER BY u.id DESC LIMIT :l OFFSET :o"), p).mappings().all()


def orders(conn: Connection, status: str | None, source: str | None, limit: int, offset: int):
    sql = "SELECT id, order_sn, status, source_type, user_id, post_id, commission_micro, purchase_time, completed_at FROM shopee_orders WHERE true"
    p: dict = {"l": limit, "o": offset}
    if status:
        sql += " AND status = :s"
        p["s"] = status
    if source:
        sql += " AND source_type = :src"
        p["src"] = source
    return conn.execute(text(sql + " ORDER BY id DESC LIMIT :l OFFSET :o"), p).mappings().all()


# ---------- Đối soát (T-052): chỉ đọc, tiền số nguyên ----------
def reconciliation(conn: Connection, start, end) -> dict:
    """Đơn có `purchase_time` (không có thì `created_at`) trong [start, end). Hoa hồng Shopee ở dạng micro (cộng rồi mới quy đổi, tránh cộng dồn
    sai số làm tròn); các khoản của ví tính theo bút toán của CHÍNH các đơn đó (`wallet_entries.order_id`)."""
    p = {"s": start, "e": end}
    orders = conn.execute(text(
        "SELECT status, source_type = 'user' AS attributed, count(*) AS n, COALESCE(sum(commission_micro), 0) AS micro FROM shopee_orders "
        "WHERE COALESCE(purchase_time, created_at) >= :s AND COALESCE(purchase_time, created_at) < :e GROUP BY 1, 2"), p).mappings().all()
    ledger = conn.execute(text(
        "SELECT o.status, e.kind, COALESCE(sum(e.amount_vnd), 0) AS vnd FROM wallet_entries e JOIN shopee_orders o ON o.id = e.order_id "
        "WHERE COALESCE(o.purchase_time, o.created_at) >= :s AND COALESCE(o.purchase_time, o.created_at) < :e GROUP BY 1, 2"), p).mappings().all()
    payouts = conn.execute(text("SELECT COALESCE(sum(amount_vnd), 0) FROM wallet_entries WHERE kind = 'payout' AND created_at >= :s AND created_at < :e"), p).scalar_one()
    return {"orders": [dict(r) for r in orders], "ledger": [dict(r) for r in ledger], "payout_vnd": int(payouts)}


def ledger_integrity(conn: Connection, limit: int = 50) -> dict:
    """So số dư lưu trong `wallets` với số suy ra từ `wallet_entries` (bất biến của sổ cái). Mọi lệch là sự cố nghiêm trọng."""
    derived = ("SELECT u.user_id, "
               "COALESCE(sum(CASE WHEN kind = 'accrual' THEN amount_vnd WHEN kind IN ('cancel', 'release') THEN -amount_vnd ELSE 0 END), 0) AS pending, "
               "COALESCE(sum(CASE WHEN kind IN ('release', 'refund_hold') THEN amount_vnd WHEN kind IN ('reverse', 'hold') THEN -amount_vnd ELSE 0 END), 0) AS available, "
               "COALESCE(sum(CASE WHEN kind = 'hold' THEN amount_vnd WHEN kind IN ('payout', 'refund_hold') THEN -amount_vnd ELSE 0 END), 0) AS held "
               "FROM (SELECT user_id FROM wallets UNION SELECT user_id FROM wallet_entries) u LEFT JOIN wallet_entries e ON e.user_id = u.user_id GROUP BY u.user_id")
    sql = (f"SELECT d.user_id, COALESCE(w.pending_vnd, 0) AS stored_pending, d.pending AS derived_pending, COALESCE(w.available_vnd, 0) AS stored_available, "
           f"d.available AS derived_available, COALESCE(w.held_vnd, 0) AS stored_held, d.held AS derived_held FROM ({derived}) d "
           "LEFT JOIN wallets w ON w.user_id = d.user_id WHERE COALESCE(w.pending_vnd, 0) <> d.pending OR COALESCE(w.available_vnd, 0) <> d.available "
           "OR COALESCE(w.held_vnd, 0) <> d.held ORDER BY d.user_id")
    rows = conn.execute(text(sql + " LIMIT :l"), {"l": limit}).mappings().all()
    checked = conn.execute(text("SELECT count(*) FROM (SELECT user_id FROM wallets UNION SELECT user_id FROM wallet_entries) x")).scalar_one()
    total = conn.execute(text(f"SELECT count(*) FROM ({sql}) y")).scalar_one()
    return {"wallets_checked": int(checked), "mismatches": int(total), "samples": [dict(r) for r in rows]}
