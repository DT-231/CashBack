from __future__ import annotations

from fastapi import Request

from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import AppError, Unauthorized
from app.modules.agent_auth.service import AgentAuth, AgentIdentity


def bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def require_agent(request: Request) -> AgentIdentity:
    """Dependency: bắt buộc Bearer key hợp lệ."""
    st = request.app.state
    # engine được tạo lười: phải gọi get_engine() thì khóa trong bảng agent_keys mới được kiểm tra
    engine = st.get_engine() if st.settings.database_url else None
    try:
        ident = AgentAuth(st.settings, engine).authenticate(bearer(request))
    except SQLAlchemyError as e:
        raise AppError("không kiểm tra được API key (DB không sẵn sàng)", code="auth_unavailable", status=503) from e
    if ident is None:
        raise Unauthorized("thiếu hoặc sai API key")
    return ident


def require_agent_if_configured(request: Request) -> AgentIdentity | None:
    """Dành cho đường dẫn cũ /api/*: chỉ bắt buộc khi đã đặt AGENT_API_KEY hoặc server lắng nghe ngoài localhost."""
    if not request.app.state.settings.auth_required:
        return None
    return require_agent(request)
