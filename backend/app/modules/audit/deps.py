"""Dependency FastAPI tạo AuditContext (ai, từ đâu) cho endpoint ghi dữ liệu: dùng chung cho payout, orders, ..."""
from __future__ import annotations

from fastapi import Depends, Request

from app.core.clientip import request_ip
from app.modules.audit.service import Actor, AuditContext
from app.modules.auth.api import current_user, require_admin
from app.modules.auth.schemas import UserOut

_ROLE = {"member": "user", "staff": "staff", "admin": "admin"}


def audit_context(request: Request, user: UserOut = Depends(current_user)) -> AuditContext:
    st = request.app.state
    return AuditContext(st.settings, Actor(user.id, _ROLE.get(user.role, "user")), request_ip(request, st.settings))


def admin_audit_context(request: Request, user: UserOut = Depends(require_admin)) -> AuditContext:
    st = request.app.state
    return AuditContext(st.settings, Actor(user.id, "admin"), request_ip(request, st.settings))
