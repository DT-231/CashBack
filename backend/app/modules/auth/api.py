"""HTTP của auth. Dependency `current_user` dùng chung cho các module khác cần đăng nhập."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.clientip import request_ip
from app.core import security
from app.core.errors import Forbidden, Unauthorized
from app.modules.audit.service import Actor, record_best_effort
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


def token_claims(request: Request) -> dict:
    token = _bearer(request)
    return (security.decode_access_token(request.app.state.settings, token) if token else None) or {}


def require_admin(request: Request, user: UserOut = Depends(current_user)) -> UserOut:
    """Chỉ role admin (staff KHÔNG đủ) VÀ đã đăng nhập hai lớp (TOTP) gần đây khi `ADMIN_MFA_REQUIRED` (mặc định bật).
    `current_user` đọc role từ DB mỗi request nên hạ quyền có hiệu lực ngay; trạng thái TOTP cũng kiểm DB mỗi lần."""
    if user.role != "admin":
        raise Forbidden("Chỉ admin được thực hiện thao tác này")
    st = request.app.state
    if st.settings.admin_mfa_required:
        from app.modules.auth.mfa_service import MfaService      # import muộn: mfa_service dùng AuthService
        clock = getattr(st, "mfa_clock", None)
        MfaService(st.settings, st.get_engine(), **({"clock": clock} if clock else {})).require_fresh(user.id, token_claims(request))
    return user


@router.post("/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn, request: Request):
    enforce_ip_limit(request, "register_ip", request.app.state.settings.rl_register_per_hour, 3600)
    user = _service(request).register(body.email, body.password)
    st = request.app.state
    record_best_effort(st.get_engine(), st.settings, Actor(user.id, "user"), "auth.register",
                       target_type="user", target_id=user.id, ip=request_ip(request, st.settings))
    return user


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
    st = request.app.state
    record_best_effort(st.get_engine(), st.settings, Actor(user.id, user.role if user.role in ("user", "staff", "admin") else "user"),
                       "auth.logout", target_type="user", target_id=user.id, ip=request_ip(request, st.settings))


@router.get("/me", response_model=UserOut)
def me(user: UserOut = Depends(current_user)):
    return user
