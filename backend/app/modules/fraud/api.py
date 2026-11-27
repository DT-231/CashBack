"""HTTP cờ gian lận (admin + TOTP). Xem và xử lý cờ; việc khóa user dùng PATCH /admin/users/{id} (T-043) kèm lý do."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.modules.audit.deps import admin_audit_context
from app.modules.audit.service import AuditContext
from app.modules.auth.api import require_admin
from app.modules.auth.schemas import UserOut
from app.modules.fraud.service import FraudService

router = APIRouter(prefix="/api/v1/admin/fraud-flags", tags=["fraud"])


class ResolveIn(BaseModel):
    status: str = Field(pattern="^(dismissed|confirmed)$")
    note: str = Field(min_length=3, max_length=300)


def _svc(request: Request) -> FraudService:
    st = request.app.state
    return FraudService(st.settings, st.get_engine())


@router.get("")
def list_flags(request: Request, status: str | None = Query(None, pattern="^(open|dismissed|confirmed)$"), limit: int = Query(50, ge=1, le=100),
               offset: int = Query(0, ge=0), _: UserOut = Depends(require_admin)):
    return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in f.items()} for f in _svc(request).list_flags(status, limit, offset)]


@router.post("/{flag_id}/resolve", status_code=204)
def resolve(flag_id: int, body: ResolveIn, request: Request, audit: AuditContext = Depends(admin_audit_context)):
    _svc(request).resolve(flag_id, body.status, body.note, audit=audit)
