"""HTTP quản trị người dùng (admin + TOTP): khóa/mở. Role KHÔNG đổi qua API (chủ DB làm tay, xem docs/runbooks/admin-mfa.md)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.audit.deps import admin_audit_context
from app.modules.audit.service import AuditContext
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/v1/admin/users", tags=["auth-admin"])


class StatusIn(BaseModel):
    status: str = Field(pattern="^(active|locked)$")
    reason: str = Field(min_length=3, max_length=300)


@router.patch("/{user_id}", status_code=204)
def set_user_status(user_id: int, body: StatusIn, request: Request, audit: AuditContext = Depends(admin_audit_context)):
    st = request.app.state
    AuthService(st.settings, st.get_engine()).set_user_status(user_id, body.status, body.reason, audit=audit)
