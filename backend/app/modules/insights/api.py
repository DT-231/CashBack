"""GET /api/v1/agent/insights: Muse AI xem bài/ngành/giờ/fanpage nào ra đơn và hoa hồng (T-051)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.core.money import micro_to_vnd
from app.modules.agent_auth.api import require_agent
from app.modules.agent_auth.service import AgentIdentity
from app.modules.insights import repository

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.get("/insights")
def get_insights(request: Request, group: str = Query(pattern="^(post|category|page|hour)$"), days: int = Query(30, ge=1, le=365),
                 limit: int = Query(100, ge=1, le=200), _: AgentIdentity = Depends(require_agent)):
    with request.app.state.get_engine().connect() as conn:
        rows = repository.insights(conn, group, days, limit)
    out = []
    for r in rows:
        d = dict(r)
        d["commission_vnd"] = micro_to_vnd(int(d.pop("commission_micro")))          # làm tròn xuống; micro không trả ra ngoài
        if hasattr(d.get("issued_at"), "isoformat"):
            d["issued_at"] = d["issued_at"].isoformat()
        out.append(d)
    return {"group": group, "days": days, "note": "Chỉ tính đơn từ bài đăng (không gồm người dùng cashback); hoa hồng gồm đơn PENDING và COMPLETED, trừ đơn hủy/trả; "
                                                  "số cuối cùng do Shopee duyệt. Click của bài không có (Shopee không báo theo bài ở đây).", "rows": out}
