"""HTTP đăng nhập hai lớp. Mọi endpoint cần đăng nhập; thử mã bị giới hạn tốc độ theo user và IP."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.clientip import request_ip
from app.core.ratelimit import enforce_rate_limits
from app.modules.audit.service import Actor, AuditContext
from app.modules.auth.api import current_user, token_claims
from app.modules.auth.mfa_service import MfaService
from app.modules.auth.schemas import (MfaCodeIn, MfaEnableOut, MfaSetupOut, MfaStatusOut, MfaVerifyIn, TokenOut, UserOut)

router = APIRouter(prefix="/api/v1/auth/mfa", tags=["mfa"])


def _service(request: Request) -> MfaService:
    st = request.app.state
    clock = getattr(st, "mfa_clock", None)                  # chỉ để test điều khiển thời gian (TOTP theo bước 30 giây)
    return MfaService(st.settings, st.get_engine(), **({"clock": clock} if clock else {}))


def mfa_audit_context(request: Request, user: UserOut = Depends(current_user)) -> AuditContext:
    st = request.app.state
    role = {"member": "user", "staff": "staff", "admin": "admin"}.get(user.role, "user")
    return AuditContext(st.settings, Actor(user.id, role), request_ip(request, st.settings))


def _limit(request: Request, user: UserOut) -> None:
    n = request.app.state.settings.rl_mfa_per_minute
    enforce_rate_limits(request, [("mfa_user", str(user.id), n, 60), ("mfa_ip", request_ip(request, request.app.state.settings), n * 4, 60)])


@router.get("/status", response_model=MfaStatusOut)
def status(request: Request, user: UserOut = Depends(current_user)):
    return _service(request).status(user.id, token_claims(request))


@router.post("/setup", response_model=MfaSetupOut)
def setup(request: Request, user: UserOut = Depends(current_user), audit: AuditContext = Depends(mfa_audit_context)):
    _limit(request, user)
    secret, uri = _service(request).setup(user, audit=audit)
    return MfaSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/enable", response_model=MfaEnableOut)
def enable(body: MfaCodeIn, request: Request, user: UserOut = Depends(current_user), audit: AuditContext = Depends(mfa_audit_context)):
    _limit(request, user)
    return MfaEnableOut(recovery_codes=_service(request).enable(user, body.code, audit=audit))


@router.post("/verify", response_model=TokenOut)
def verify(body: MfaVerifyIn, request: Request, user: UserOut = Depends(current_user), audit: AuditContext = Depends(mfa_audit_context)):
    """Trả cặp token MỚI có `mfa_at`; BFF thay cookie bằng cặp này."""
    _limit(request, user)
    return _service(request).verify(user, body.code, body.recovery_code, audit=audit)


@router.post("/disable", status_code=204)
def disable(body: MfaCodeIn, request: Request, user: UserOut = Depends(current_user), audit: AuditContext = Depends(mfa_audit_context)):
    _limit(request, user)
    _service(request).disable(user, body.code, audit=audit)
