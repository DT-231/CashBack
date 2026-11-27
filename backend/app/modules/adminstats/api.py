"""HTTP tổng quan và tra cứu cho admin (chỉ đọc). Cần admin + TOTP. Không có endpoint ghi ở đây."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.core.money import micro_to_vnd
from app.modules.adminstats import repository
from app.modules.auth.api import require_admin
from app.modules.auth.schemas import UserOut

router = APIRouter(prefix="/api/v1/admin", tags=["admin-stats"])
_SOURCES = "^(user|post|legacy|unknown)$"
_STATUSES = "^(PENDING|COMPLETED|CANCELLED|RETURNED)$"


def _iso(rows):
    return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items()} for r in rows]


@router.get("/overview")
def overview(request: Request, days: int = Query(30, ge=1, le=365), _: UserOut = Depends(require_admin)):
    with request.app.state.get_engine().connect() as conn:
        d = repository.overview(conn, days)
    for v in d["orders"].values():
        v["commission_vnd"] = micro_to_vnd(v["commission_micro"])            # UI chỉ hiển thị VND do backend quy đổi (làm tròn xuống)
    if d["last_sync"]:
        d["last_sync"] = {"result": d["last_sync"]["result"], "finished_at": d["last_sync"]["finished_at"].isoformat()}
    return d


@router.get("/users")
def users(request: Request, q: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=100),
          offset: int = Query(0, ge=0), _: UserOut = Depends(require_admin)):
    with request.app.state.get_engine().connect() as conn:
        return _iso(repository.users(conn, q, limit, offset))


@router.get("/orders")
def orders(request: Request, status: str | None = Query(None, pattern=_STATUSES), source: str | None = Query(None, pattern=_SOURCES),
           limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: UserOut = Depends(require_admin)):
    with request.app.state.get_engine().connect() as conn:
        rows = repository.orders(conn, status, source, limit, offset)
    return [{**r, "commission_vnd": micro_to_vnd(r["commission_micro"])} for r in _iso(rows)]
