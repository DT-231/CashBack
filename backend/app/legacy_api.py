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
from app.modules.links.affiliate_link import LinkConfig, LinkError, LinkInputError, link_for_item, normalize_sub_id, parse_product_url

router = APIRouter(tags=["legacy"])
guard = [Depends(require_agent_if_configured)]   # bắt buộc khóa khi đã cấu hình / lắng nghe ngoài localhost


def _err(msg: str, code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=code)


@router.get("/health")
def health(request: Request):
    s = request.app.state.settings
    return {"ok": True, "mock": s.mock, "aff_id_set": bool(s.aff_id),
            "cookie_set": bool(s.shopee_cookie.get_secret_value()),
            "web_cookie_set": bool(s.shopee_web_cookie.get_secret_value()), "engine": s.search_engine,
            "feed_configured": bool(s.feed_file),
            "bff_enabled": s.bff_enabled, "visitor_ip": s.visitor_ip_status,
            "degraded": bool(s.startup_warnings()), "warnings": s.startup_warnings()}


@router.get("/")
def guide():
    return {"service": "Shopee Link API", "for": "AI của bạn gọi vào đây để lấy link sản phẩm",
            "endpoints": {"GET /api/search?keyword=&limit=&sort=&sub=": "tìm sản phẩm + link aff",
                          "POST /api/link": "{url} hoặc {item_id,shop_id,sub}",
                          "GET /api/v1/agent/*": "Tool API mới (Bearer key)"}}


ENGINES = ("auto", "feed", "api", "browser")
SORTS = ("relevancy", "sales")


@router.get("/api/search", dependencies=guard)
def search(request: Request):
    q = request.query_params
    raw_keyword = q.get("keyword") or ""
    if "\r" in raw_keyword or "\n" in raw_keyword:   # keyword đi vào header Referer: chặn header injection
        return _err("keyword không được chứa xuống dòng", 400)
    keyword = raw_keyword.strip()
    if not keyword:
        return _err("thiếu keyword", 400)
    if len(keyword) > 200:
        return _err("keyword tối đa 200 ký tự", 400)
    try:
        limit = int(q.get("limit") or "10")
    except ValueError:
        return _err("limit phải là số nguyên", 400)
    limit = max(1, min(limit, 60))
    sort = q.get("sort") or "relevancy"
    if sort not in SORTS:
        return _err("sort chỉ nhận: " + "|".join(SORTS), 400)
    engine = (q.get("engine") or "auto").strip().lower()
    if engine not in ENGINES:
        return _err("engine chỉ nhận: " + "|".join(ENGINES), 400)
    sub = (q.get("sub") or "").strip()
    try:
        normalize_sub_id(f"{sub or 'api'}-{limit}")   # sub + số thứ tự phải vẫn ≤5 slot hợp lệ
    except LinkInputError as e:
        return _err(str(e), 400)

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
    url = data.get("url") or ""
    if not isinstance(url, str):
        return _err("url phải là chuỗi", 400)
    url = url.strip()
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
    if item_id <= 0 or shop_id <= 0:
        return _err("item_id và shop_id phải dương", 400)
    try:
        out = link_for_item(item_id, shop_id, sub, LinkConfig.from_settings(request.app.state.settings))
    except LinkInputError as e:
        return _err(str(e), 400)
    except LinkError as e:
        return _err(str(e), 500)
    return {"ok": True, **out}
