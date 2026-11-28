"""Thống kê cho Muse AI học bài nào ra tiền. CHỈ ĐỌC. CHỈ đơn có nguồn là BÀI ĐĂNG (`source_type = 'post'`): tuyệt đối không đụng tới đơn,
click hay danh tính của người dùng cashback. Không trả email, user_id, mã đơn hay IP."""
from __future__ import annotations

from sqlalchemy import Connection, text

# Hoa hồng chỉ tính đơn chưa bị hủy/trả: PENDING + COMPLETED (số thật cuối cùng còn phụ thuộc Shopee duyệt)
_LIVE = "o.status IN ('PENDING', 'COMPLETED')"
_TZ = "Asia/Ho_Chi_Minh"
_GROUPS = {
    "post": ("p.post_key AS key, p.page_code, p.category, p.issued_at", "p.id, p.post_key, p.page_code, p.category, p.issued_at", "p.issued_at DESC"),
    "category": ("COALESCE(NULLIF(p.category, ''), 'unknown') AS key", "COALESCE(NULLIF(p.category, ''), 'unknown')", "orders DESC"),
    "page": ("COALESCE(NULLIF(p.page_code, ''), 'unknown') AS key", "COALESCE(NULLIF(p.page_code, ''), 'unknown')", "orders DESC"),
    "hour": (f"EXTRACT(HOUR FROM p.issued_at AT TIME ZONE '{_TZ}')::int AS key", f"EXTRACT(HOUR FROM p.issued_at AT TIME ZONE '{_TZ}')::int", "key"),
}


def insights(conn: Connection, group: str, days: int, limit: int):
    select, group_by, order = _GROUPS[group]
    sql = (f"SELECT {select}, count(DISTINCT p.id) AS posts, count(o.id) AS orders, "
           f"count(o.id) FILTER (WHERE o.status = 'COMPLETED') AS completed_orders, "
           f"COALESCE(sum(o.commission_micro) FILTER (WHERE {_LIVE}), 0) AS commission_micro "
           "FROM posts p LEFT JOIN shopee_orders o ON o.post_id = p.id AND o.source_type = 'post' "
           "WHERE p.issued_at > now() - make_interval(days => :d) "
           f"GROUP BY {group_by} ORDER BY {order} LIMIT :l")
    return conn.execute(text(sql), {"d": days, "l": limit}).mappings().all()
