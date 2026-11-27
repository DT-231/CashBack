"""Đường dẫn cũ /api/search, /api/link, /health, / — giữ để Muse AI hiện tại không vỡ (docs/08 "Tool API hiện có").

Hình dạng JSON và lỗi giữ nguyên như server.py cũ. Đã BỎ: /go/<sub_id> (chuyển sang Cloudflare Worker),
/api/stats và /api/revenue (thay bằng /agent/insights, /admin/overview và scripts/revenue_report.py).
Sẽ xóa khi mọi client chuyển sang /api/v1/agent/*.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.modules.agent_auth.api import require_agent_if_configured
from app.modules.links import service as links
from app.modules.links.affiliate_link import LinkConfig, LinkError, link_for_item, parse_product_url

router = APIRouter(tags=["legacy"])
guard = [Depends(require_agent_if_configured)]   # bắt buộc khóa khi đã cấu hình / lắng nghe ngoài localhost


def _err(msg: str, code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=code)


@router.get("/health")
def health(request: Request):
    s = request.app.state.settings
    return {"ok": True, "mock": s.mock, "aff_id_set": bool(s.aff_id),
            "cookie_set": bool(s.shopee_cookie.get_secret_value()), "engine": s.search_engine,
            "feed_configured": bool(s.feed_file)}


@router.get("/")
def guide():
    return {"service": "Shopee Link API", "for": "AI của bạn gọi vào đây để lấy link sản phẩm",
            "endpoints": {"GET /api/search?keyword=&limit=&sort=&sub=": "tìm sản phẩm + link aff",
                          "POST /api/link": "{url} hoặc {item_id,shop_id,sub}",
                          "GET /api/v1/agent/*": "Tool API mới (Bearer key)"}}


@router.get("/api/search", dependencies=guard)
def search(request: Request):
    q = request.query_params
    keyword = (q.get("keyword") or "").strip()
    if not keyword:
        return _err("thiếu keyword", 400)
    try:
        limit = int(q.get("limit") or "10")
    except ValueError:
        return _err("limit phải là số nguyên", 400)
    sort = q.get("sort") or "relevancy"
    sub = (q.get("sub") or "").strip()
    engine = (q.get("engine") or "auto").strip().lower()

    res = request.app.state.search.search(keyword, limit, sort, engine)
    items = links.enrich_items(request.app.state.settings, res["items"], sub)
    return {"ok": res["ok"], "keyword": keyword, "count": len(items), "engine": res.get("engine"),
            "tried": res.get("tried"), "source": res.get("source"), "error": res.get("error"), "items": items}


@router.post("/api/link", dependencies=guard)
async def link(request: Request):
    try:
        raw = await request.body()
        data = json.loads(raw.decode("utf-8", "ignore") or "{}") if raw else {}
        if not isinstance(data, dict):
            data = {}
    except ValueError:
        data = {}
    url = (data.get("url") or "").strip()
    sub = str(data.get("sub") or data.get("sub_id") or "api")
    item_id, shop_id = data.get("item_id"), data.get("shop_id")
    parsed = parse_product_url(url) if url else None
    if parsed:
        shop_id, item_id = parsed
    if not (item_id and shop_id):
        return _err("cần url hoặc item_id + shop_id", 400)
    try:
        item_id, shop_id = int(item_id), int(shop_id)
    except (TypeError, ValueError):
        return _err("item_id và shop_id phải là số nguyên", 400)
    try:
        out = link_for_item(item_id, shop_id, sub, LinkConfig.from_settings(request.app.state.settings))
    except LinkError as e:
        return _err(str(e), 500)
    return {"ok": True, **out}
