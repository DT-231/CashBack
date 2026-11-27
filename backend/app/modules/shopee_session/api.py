"""HTTP quản trị cookie Shopee (admin + TOTP). Cố ý KHÔNG có endpoint đọc cookie."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.modules.audit.deps import admin_audit_context
from app.modules.audit.service import AuditContext
from app.modules.auth.api import require_admin
from app.modules.auth.schemas import UserOut
from app.modules.shopee_session.service import ShopeeSessionService

router = APIRouter(prefix="/api/v1/admin/shopee-session", tags=["shopee-session"])


class CookieIn(BaseModel):
    cookie: str = Field(min_length=3, max_length=9000, repr=False)


class SessionStatusOut(BaseModel):
    has_cookie: bool
    status: str
    last_ok_at: str | None
    failure_count: int
    updated_at: str | None


def _svc(request: Request) -> ShopeeSessionService:
    st = request.app.state
    return ShopeeSessionService(st.settings, st.get_engine())


@router.put("", status_code=204)
def put_cookie(body: CookieIn, request: Request, audit: AuditContext = Depends(admin_audit_context)):
    _svc(request).set_cookie(body.cookie, audit=audit)


@router.get("/status", response_model=SessionStatusOut)
def get_status(request: Request, _: UserOut = Depends(require_admin)):
    s = _svc(request).status()
    return {**s, "last_ok_at": s["last_ok_at"].isoformat() if s["last_ok_at"] else None,
            "updated_at": s["updated_at"].isoformat() if s["updated_at"] else None}
