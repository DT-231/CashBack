"""HTTP quản trị đơn mồ côi (admin + TOTP)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, StrictInt

from app.core.money import micro_to_vnd
from app.modules.audit.deps import admin_audit_context
from app.modules.audit.service import AuditContext
from app.modules.auth.api import require_admin
from app.modules.auth.schemas import UserOut
from app.modules.orders.admin_service import OrphanAdmin

router = APIRouter(prefix="/api/v1/admin/orphans", tags=["orders-admin"])


class AssignIn(BaseModel):
    user_id: StrictInt = Field(gt=0)
    reason: str = Field(min_length=3, max_length=300)


class OrphanOut(BaseModel):
    id: int
    order_sn: str
    status: str
    commission_micro: int
    commission_vnd: int
    purchase_time: str | None
    utm_content: str | None
    reason: str


def _svc(request: Request) -> OrphanAdmin:
    st = request.app.state
    return OrphanAdmin(st.settings, st.get_engine())


@router.get("", response_model=list[OrphanOut])
def list_orphans(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: UserOut = Depends(require_admin)):
    return [{**r, "commission_vnd": micro_to_vnd(r["commission_micro"]),
             "purchase_time": r["purchase_time"].isoformat() if r["purchase_time"] else None} for r in _svc(request).list(limit, offset)]


@router.post("/{order_id}/assign", status_code=204)
def assign(order_id: int, body: AssignIn, request: Request, audit: AuditContext = Depends(admin_audit_context)):
    _svc(request).assign(order_id, body.user_id, body.reason, audit=audit)
