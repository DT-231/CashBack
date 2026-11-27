"""HTTP của /go/{code}: chỉ lấy IP/User-Agent, gọi service, trả 302."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.core.clientip import client_ip
from app.modules.clicks.service import ClickService

router = APIRouter(tags=["clicks"])


@router.get("/go/{code}", include_in_schema=False)
def go(code: str, request: Request):
    st = request.app.state
    url = ClickService(st.settings, st.get_engine()).go(code, client_ip(request, st.settings.trust_proxy_headers),
                                                   request.headers.get("user-agent"))
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
