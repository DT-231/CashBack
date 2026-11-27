"""Ghi nhật ký kiểm toán: ai (user/staff/admin/agent/system), làm gì, với đối tượng nào, lúc nào, từ IP băm nào.

- `record(conn, ...)` chạy TRONG transaction của thao tác cần ghi (admin/tiền): lỗi ghi log thì cả thao tác hủy.
- `record_best_effort(engine, ...)` cho sự kiện thông tin (đăng ký, đăng xuất): lỗi chỉ log, không làm hỏng yêu cầu.
- IP chỉ lưu dạng HMAC (`core.clientip.keyed_hash`, cần IP_SALT); không có IP_SALT thì ip_hash = NULL.
- `detail` luôn đi qua `sanitize_detail`: không mật khẩu, token, cookie, số tài khoản.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import Connection, Engine

from app.core.clientip import keyed_hash
from app.core.config import Settings
from app.core.logging import get_request_id
from app.modules.audit import repository
from app.modules.audit.errors import InvalidAudit
from app.modules.audit.sanitize import sanitize_detail

log = logging.getLogger("app.audit")
ROLES = ("user", "staff", "admin", "agent", "system")
_ACTION = re.compile(r"^[a-z][a-z_]*\.[a-z][a-z_]*$")     # <nhóm>.<hành động>, ví dụ settings.set, auth.register


@dataclass(frozen=True)
class Actor:
    id: int | None
    role: str

    def __post_init__(self):
        if self.role not in ROLES:
            raise InvalidAudit(f"vai trò không hợp lệ: {self.role}")


SYSTEM = Actor(None, "system")


@dataclass(frozen=True)
class AuditContext:
    """Gói "ai, từ đâu" mà endpoint admin truyền xuống service để service ghi log TRONG cùng transaction với thao tác."""
    settings: Settings
    actor: Actor
    ip: str | None = None


def record(conn: Connection, settings: Settings, actor: Actor, action: str, *, target_type: str | None = None,
           target_id: int | str | None = None, detail: dict | None = None, ip: str | None = None) -> int:
    if not _ACTION.match(action):
        raise InvalidAudit(f"action phải có dạng nhóm.hành_động: {action!r}")
    return repository.insert(
        conn, actor_id=actor.id, actor_role=actor.role, action=action, target_type=target_type,
        target_id=None if target_id is None else str(target_id)[:100], detail=sanitize_detail(detail),
        ip_hash=keyed_hash(settings, ip), request_id=get_request_id())


def record_best_effort(engine: Engine, settings: Settings, actor: Actor, action: str, **kw) -> None:
    try:
        with engine.begin() as conn:
            record(conn, settings, actor, action, **kw)
    except Exception:  # noqa: BLE001 - sự kiện thông tin không được làm hỏng yêu cầu của người dùng
        log.exception("không ghi được audit log", extra={"action": action})
