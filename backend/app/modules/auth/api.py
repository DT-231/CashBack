"""HTTP của auth. Dependency `current_user` dùng chung cho các module khác cần đăng nhập."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.clientip import request_ip
from app.core.errors import Unauthorized
from app.core.ratelimit import enforce_ip_limit, enforce_rate_limits
from app.modules.auth.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _service(request: Request) -> AuthService:
    st = request.app.state
    return AuthService(st.settings, st.get_engine())


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def current_user(request: Request) -> UserOut:
    user = _service(request).user_from_token(_bearer(request))
    if user is None:
        raise Unauthorized("Chưa đăng nhập hoặc phiên đã hết hạn")
    return user


@router.post("/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn, request: Request):
    enforce_ip_limit(request, "register_ip", request.app.state.settings.rl_register_per_hour, 3600)
    return _service(request).register(body.email, body.password)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request):
    settings = request.app.state.settings
    enforce_rate_limits(request, [
        ("login_ip", request_ip(request, settings), settings.rl_login_per_minute, 60),
        ("login_email", body.email, settings.rl_login_per_email_15min, 900),
    ])
    return _service(request).login(body.email, body.password)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, request: Request):
    enforce_ip_limit(request, "refresh_ip", request.app.state.settings.rl_refresh_per_minute, 60)
    return _service(request).refresh(body.refresh_token)


@router.post("/logout", status_code=204)
def logout(request: Request, user: UserOut = Depends(current_user)):
    _service(request).logout_all(user.id)


@router.get("/me", response_model=UserOut)
def me(user: UserOut = Depends(current_user)):
    return user
