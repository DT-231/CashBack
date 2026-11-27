"""Tool API cho Muse AI (docs/08): /api/v1/agent/*"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.modules.agent_auth.api import require_agent
from app.modules.agent_auth.service import AgentIdentity
from app.modules.ai_posts.schemas import LinkRequest, LinkResponse
from app.modules.ai_posts.service import AiPostService

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/links", response_model=LinkResponse)
def create_link(req: LinkRequest, request: Request, who: AgentIdentity = Depends(require_agent)):
    return AiPostService(request.app.state.settings, request.app.state.get_engine()).create_link(who, req)


@router.get("/search")
def search(request: Request, keyword: str = Query(min_length=1, max_length=200), limit: int = Query(10, ge=1, le=60),
           sort: str = Query("relevancy", pattern="^(relevancy|sales)$"), min_rate: float = Query(0, ge=0),
           min_sold: int = Query(0, ge=0), engine: str = "auto", _: AgentIdentity = Depends(require_agent)):
    """Tìm sản phẩm. KHÔNG trả link (tránh tạo link thừa); lấy link qua POST /agent/links."""
    res = request.app.state.search.search(keyword.strip(), limit, sort, engine.strip().lower())
    items = [i for i in res["items"] if i.get("comm_rate", min_rate) >= min_rate and (i.get("sold") or 0) >= min_sold]
    return {"ok": res["ok"], "engine": res.get("engine"), "tried": res.get("tried"), "source": res.get("source"),
            "error": res.get("error"), "count": len(items), "items": items}


@router.get("/health")
def health(request: Request, _: AgentIdentity = Depends(require_agent)):
    s = request.app.state.settings
    return {"ok": True, "mock": s.mock, "engine": s.search_engine, "feed_configured": bool(s.feed_file),
            "cookie_set": bool(s.shopee_cookie.get_secret_value()), "aff_id_set": bool(s.aff_id)}
