"""HTTP của auth. Dependency `current_user` dùng chung cho các module khác cần đăng nhập."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field

from app.core.clientip import request_ip
from app.core import security
from app.core.errors import Forbidden, Unauthorized
from app.modules.audit.service import Actor, record_best_effort
from app.core.ratelimit import enforce_ip_limit, enforce_rate_limits
from app.modules.auth.account_service import AccountService
from app.modules.auth.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_AUDIT_ROLE = {"member": "user", "staff": "staff", "admin": "admin"}


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


def _account(request: Request) -> AccountService:
    st = request.app.state
    return AccountService(st.settings, st.get_engine())


def _send_link(request: Request, issued, purpose: str) -> None:
    """Gửi thư chứa liên kết một lần. Chạy SAU khi đã trả lời (BackgroundTasks). Thiếu WEB_ORIGIN hoặc SMTP thì không gửi gì."""
    st = request.app.state
    origin = st.settings.web_origin.strip().rstrip("/")
    if issued is None or not origin:
        return
    email, token = issued
    page, subject, intro = (("verify-email", "Xác minh email CashBack", "Bấm liên kết để xác minh email (hiệu lực 24 giờ):"),
                            ("reset-password", "Đặt lại mật khẩu CashBack", "Bấm liên kết để đặt mật khẩu mới (hiệu lực 1 giờ):"))[purpose == "reset"]
    getattr(st, "mailer").send(email, subject, f"{intro}\n\n{origin}/{page}?token={token}\n\nNếu bạn không yêu cầu, hãy bỏ qua email này.")


class EmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=100)


class ResetIn(TokenIn):
    password: str = Field(min_length=10, max_length=128)


@router.post("/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn, request: Request, background: BackgroundTasks):
    enforce_ip_limit(request, "register_ip", request.app.state.settings.rl_register_per_hour, 3600)
    user = _service(request).register(body.email, body.password)
    if user.status == "unverified":
        background.add_task(_send_link, request, _account(request).issue_verification_for(user.id, user.email), "verify")
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
    tokens = _service(request).login(body.email, body.password)
    claims = security.decode_access_token(settings, tokens.access_token) or {}     # id/role của người vừa đăng nhập (không lộ email vào audit)
    st = request.app.state
    record_best_effort(st.get_engine(), settings, Actor(int(claims["sub"]), _AUDIT_ROLE.get(claims.get("role"), "user")), "auth.login",
                       target_type="user", target_id=claims["sub"], ip=request_ip(request, settings))
    return tokens


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


def _anti_abuse(request: Request, scope: str, email: str) -> None:
    st = request.app.state.settings
    enforce_rate_limits(request, [(f"{scope}_ip", request_ip(request, st), st.rl_forgot_per_hour, 3600), (f"{scope}_email", email.strip().lower(), 3, 3600)])


@router.post("/verify", status_code=204)
def verify_email(body: TokenIn, request: Request):
    """POST (không GET): token không đi vào URL/nhật ký truy cập/Referer."""
    enforce_ip_limit(request, "verify_ip", request.app.state.settings.rl_login_per_minute, 60)
    _account(request).verify_email(body.token)


@router.post("/verify/resend", status_code=202)
def resend_verification(body: EmailIn, request: Request, background: BackgroundTasks):
    _anti_abuse(request, "resend", body.email)
    background.add_task(_send_link, request, _account(request).request_verification(body.email.strip().lower()), "verify")
    return {"ok": True}


@router.post("/forgot", status_code=202)
def forgot_password(body: EmailIn, request: Request, background: BackgroundTasks):
    """Luôn 202 như nhau dù email có tồn tại hay không."""
    _anti_abuse(request, "forgot", body.email)
    background.add_task(_send_link, request, _account(request).request_reset(body.email.strip().lower()), "reset")
    return {"ok": True}


@router.post("/reset", status_code=204)
def reset_password(body: ResetIn, request: Request):
    enforce_ip_limit(request, "reset_ip", request.app.state.settings.rl_login_per_minute, 60)
    _account(request).reset_password(body.token, body.password, request_ip(request, request.app.state.settings))
