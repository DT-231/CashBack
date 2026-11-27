"""SQL của audit_logs. Chỉ module này được ghi bảng (test kiến trúc). Chỉ thêm, không sửa/xóa (trigger DB)."""
from __future__ import annotations

import json

from sqlalchemy import Connection, text


def insert(conn: Connection, *, actor_id: int | None, actor_role: str, action: str, target_type: str | None,
           target_id: str | None, detail: dict | None, ip_hash: str | None, request_id: str | None) -> int:
    return conn.execute(text("""
        INSERT INTO audit_logs (actor_id, actor_role, action, target_type, target_id, detail, ip_hash, request_id)
        VALUES (:actor_id, :actor_role, :action, :target_type, :target_id, CAST(:detail AS jsonb), :ip_hash, :request_id)
        RETURNING id"""), {"actor_id": actor_id, "actor_role": actor_role, "action": action, "target_type": target_type,
                           "target_id": target_id, "detail": json.dumps(detail, ensure_ascii=False) if detail is not None else None,
                           "ip_hash": ip_hash, "request_id": request_id}).scalar_one()


def list_recent(conn: Connection, *, limit: int = 50, actor_id: int | None = None, action: str | None = None):
    sql = "SELECT id, actor_id, actor_role, action, target_type, target_id, detail, ip_hash, request_id, at FROM audit_logs WHERE true"
    params: dict = {"limit": limit}
    if actor_id is not None:
        sql += " AND actor_id = :actor_id"
        params["actor_id"] = actor_id
    if action is not None:
        sql += " AND action = :action"
        params["action"] = action
    return conn.execute(text(sql + " ORDER BY id DESC LIMIT :limit"), params).mappings().all()
