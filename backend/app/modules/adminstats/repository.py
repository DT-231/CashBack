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
