"""HTTP của /go/{code}: chỉ lấy IP/User-Agent, gọi service, trả 302."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.modules.clicks.service import ClickService

router = APIRouter(tags=["clicks"])


def _client_ip(request: Request) -> str | None:
    if request.app.state.settings.trust_proxy_headers:
        ip = request.headers.get("cf-connecting-ip")
        if ip:
            return ip.strip()
    return request.client.host if request.client else None


@router.get("/go/{code}", include_in_schema=False)
def go(code: str, request: Request):
    st = request.app.state
    url = ClickService(st.settings, st.get_engine()).go(code, _client_ip(request), request.headers.get("user-agent"))
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})
