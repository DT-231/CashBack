"""SQL phát hiện gian lận: ĐỌC clicks/links/shopee_orders (không ghi), GHI chỉ `fraud_flags`."""
from __future__ import annotations

import json

from sqlalchemy import Connection, text


def shared_ip_users(conn: Connection, min_users: int):
    """(user_id, số chủ link khác nhau dùng chung ip_hash) cho mọi ip_hash có >= min_users chủ link khác nhau trong 7 ngày."""
    return conn.execute(text(
        "SELECT u AS user_id, n FROM (SELECT c.ip_hash, array_agg(DISTINCT l.user_id) AS users, count(DISTINCT l.user_id) AS n FROM clicks c "
        "JOIN links l ON l.id = c.link_id WHERE c.ip_hash IS NOT NULL AND c.created_at > now() - interval '7 days' "
        "GROUP BY c.ip_hash HAVING count(DISTINCT l.user_id) >= :m) g, unnest(g.users) AS u"), {"m": min_users}).mappings().all()


def high_cancel_users(conn: Connection, min_orders: int, pct: int):
    return conn.execute(text(
        "SELECT user_id, count(*) AS total, count(*) FILTER (WHERE status IN ('CANCELLED', 'RETURNED')) AS bad FROM shopee_orders "
        "WHERE user_id IS NOT NULL AND COALESCE(purchase_time, created_at) > now() - interval '60 days' GROUP BY user_id "
        "HAVING count(*) >= :m AND count(*) FILTER (WHERE status IN ('CANCELLED', 'RETURNED')) * 100 >= :p * count(*)"),
        {"m": min_orders, "p": pct}).mappings().all()


def click_bursts(conn: Connection, per_hour: int):
    """(user_id chủ link, số click lớn nhất trong một giờ từ MỘT ip_hash vào MỘT link) trong 24 giờ."""
    return conn.execute(text(
        "SELECT l.user_id, max(b.n) AS n FROM (SELECT link_id, ip_hash, date_trunc('hour', created_at) AS h, count(*) AS n FROM clicks "
        "WHERE ip_hash IS NOT NULL AND created_at > now() - interval '24 hours' GROUP BY 1, 2, 3 HAVING count(*) >= :m) b "
        "JOIN links l ON l.id = b.link_id GROUP BY l.user_id"), {"m": per_hour}).mappings().all()


def upsert_flag(conn: Connection, user_id: int, rule: str, score: int, detail: dict, cooldown_days: int) -> str:
    """'created' | 'updated' | 'suppressed'. Cờ đang mở thì cập nhật; mới bị bỏ qua gần đây thì không tạo lại."""
    upd = conn.execute(text("UPDATE fraud_flags SET score = :s, detail = CAST(:d AS jsonb), updated_at = now() "
                            "WHERE user_id = :u AND rule = :r AND status = 'open' RETURNING 1"),
                       {"s": score, "d": json.dumps(detail), "u": user_id, "r": rule}).first()
    if upd:
        return "updated"
    ins = conn.execute(text(
        "INSERT INTO fraud_flags(user_id, rule, score, detail) SELECT :u, :r, :s, CAST(:d AS jsonb) WHERE NOT EXISTS "
        "(SELECT 1 FROM fraud_flags WHERE user_id = :u AND rule = :r AND status = 'dismissed' AND resolved_at > now() - make_interval(days => :c)) "
        "ON CONFLICT DO NOTHING RETURNING 1"), {"u": user_id, "r": rule, "s": score, "d": json.dumps(detail), "c": cooldown_days}).first()
    return "created" if ins else "suppressed"


def list_flags(conn: Connection, status: str | None, limit: int, offset: int):
    sql = ("SELECT f.id, f.user_id, u.email, f.rule, f.score, f.status, f.detail, f.created_at, f.updated_at, f.resolved_by, f.resolved_at, "
           "f.resolution_note FROM fraud_flags f JOIN users u ON u.id = f.user_id")
    p: dict = {"l": limit, "o": offset}
    if status:
        sql += " WHERE f.status = :s"
        p["s"] = status
    return conn.execute(text(sql + " ORDER BY f.id DESC LIMIT :l OFFSET :o"), p).mappings().all()


def resolve(conn: Connection, flag_id: int, status: str, admin_id: int, note: str):
    return conn.execute(text(
        "UPDATE fraud_flags SET status = :s, resolved_by = :a, resolved_at = now(), updated_at = now(), resolution_note = :n "
        "WHERE id = :i AND status = 'open' RETURNING id, user_id, rule"), {"s": status, "a": admin_id, "n": note, "i": flag_id}).mappings().first()


def exists(conn: Connection, flag_id: int) -> bool:
    return conn.execute(text("SELECT 1 FROM fraud_flags WHERE id = :i"), {"i": flag_id}).first() is not None
