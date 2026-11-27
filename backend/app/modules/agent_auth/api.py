from __future__ import annotations

from fastapi import Request

from app.core.errors import Unauthorized
from app.modules.agent_auth.service import AgentAuth, AgentIdentity


def bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def require_agent(request: Request) -> AgentIdentity:
    """Dependency: bắt buộc Bearer key hợp lệ."""
    ident = AgentAuth(request.app.state.settings, request.app.state.engine).authenticate(bearer(request))
    if ident is None:
        raise Unauthorized("thiếu hoặc sai API key")
    return ident


def require_agent_if_configured(request: Request) -> AgentIdentity | None:
    """Dành cho đường dẫn cũ /api/*: chỉ bắt buộc khi đã đặt AGENT_API_KEY hoặc server lắng nghe ngoài localhost."""
    if not request.app.state.settings.auth_required:
        return None
    return require_agent(request)
