"""HTTP rút tiền. Người dùng: tài khoản ngân hàng + yêu cầu rút. Admin: duyệt/từ chối/chi trả/xem số tài khoản.
Mọi endpoint ghi dữ liệu có dependency `audit_context` (test contract kiểm); route admin có thêm `require_admin`."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from app.core.clientip import request_ip
from app.core.ratelimit import enforce_rate_limits
from app.modules.audit.service import Actor, AuditContext
from app.modules.auth.api import current_user, require_admin
from app.modules.auth.schemas import UserOut
from app.modules.payout.schemas import (AdminWithdrawalOut, BankAccountIn, BankAccountOut, IdemKey, MarkPaidIn,
                                        PayoutAccountOut, ReasonIn, WithdrawalIn, WithdrawalOut)
from app.modules.payout.service import PayoutService

me_router = APIRouter(prefix="/api/v1/me", tags=["payout"])
admin_router = APIRouter(prefix="/api/v1/admin/withdrawals", tags=["payout-admin"])


def _service(request: Request) -> PayoutService:
    st = request.app.state
    return PayoutService(st.settings, st.get_engine())


def _actor_role(user: UserOut) -> str:
    return {"member": "user", "staff": "staff", "admin": "admin"}.get(user.role, "user")


def audit_context(request: Request, user: UserOut = Depends(current_user)) -> AuditContext:
    st = request.app.state
    return AuditContext(st.settings, Actor(user.id, _actor_role(user)), request_ip(request, st.settings))


def admin_audit_context(request: Request, user: UserOut = Depends(require_admin)) -> AuditContext:
    st = request.app.state
    return AuditContext(st.settings, Actor(user.id, "admin"), request_ip(request, st.settings))


def _limit(request: Request, scope: str, user: UserOut, per_hour: int) -> None:
    enforce_rate_limits(request, [(f"{scope}_user", str(user.id), per_hour, 3600),
                                  (f"{scope}_ip", request_ip(request, request.app.state.settings), per_hour * 4, 3600)])


@me_router.post("/bank-accounts", status_code=201, response_model=BankAccountOut)
def add_bank_account(body: BankAccountIn, request: Request, user: UserOut = Depends(current_user),
                     audit: AuditContext = Depends(audit_context)):
    _limit(request, "bank_add", user, request.app.state.settings.rl_bank_add_per_hour)
    return _service(request).add_bank_account(user.id, body, audit=audit)


@me_router.get("/bank-accounts", response_model=list[BankAccountOut])
def my_bank_accounts(request: Request, user: UserOut = Depends(current_user)):
    return _service(request).list_bank_accounts(user.id)


@me_router.post("/withdrawals", status_code=201, response_model=WithdrawalOut)
def request_withdrawal(body: WithdrawalIn, request: Request, idempotency_key: IdemKey = Header(alias="Idempotency-Key"),
                       user: UserOut = Depends(current_user), audit: AuditContext = Depends(audit_context)):
    _limit(request, "withdraw", user, request.app.state.settings.rl_withdraw_per_hour)
    return _service(request).request_withdrawal(user.id, body.amount_vnd, body.bank_account_id, idempotency_key, audit=audit)


@me_router.get("/withdrawals", response_model=list[WithdrawalOut])
def my_withdrawals(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                   user: UserOut = Depends(current_user)):
    return _service(request).list_my_withdrawals(user.id, limit, offset)


@admin_router.get("", response_model=list[AdminWithdrawalOut])
def admin_list(request: Request, status: str | None = Query(None, pattern="^(requested|approved|rejected|processing|paid|failed)$"),
               limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: UserOut = Depends(require_admin)):
    return _service(request).admin_list(status, limit, offset)


@admin_router.post("/{wid}/approve", response_model=AdminWithdrawalOut)
def approve(wid: int, request: Request, audit: AuditContext = Depends(admin_audit_context)):
    return _service(request).approve(wid, audit=audit)


@admin_router.post("/{wid}/reject", response_model=AdminWithdrawalOut)
def reject(wid: int, body: ReasonIn, request: Request, audit: AuditContext = Depends(admin_audit_context)):
    return _service(request).reject(wid, body.reason, audit=audit)


@admin_router.post("/{wid}/fail", response_model=AdminWithdrawalOut)
def fail(wid: int, body: ReasonIn, request: Request, audit: AuditContext = Depends(admin_audit_context)):
    return _service(request).fail(wid, body.reason, audit=audit)


@admin_router.post("/{wid}/mark-paid", response_model=AdminWithdrawalOut)
def mark_paid(wid: int, body: MarkPaidIn, request: Request, audit: AuditContext = Depends(admin_audit_context)):
    return _service(request).mark_paid(wid, body.provider_ref, audit=audit)


@admin_router.get("/{wid}/payout-account", response_model=PayoutAccountOut)
def payout_account(wid: int, request: Request, audit: AuditContext = Depends(admin_audit_context)):
    """Giải mã số tài khoản (ghi audit `payout.view_account` mỗi lần). Không cache."""
    data = _service(request).view_account(wid, audit=audit)
    return JSONResponse(data.model_dump(), headers={"Cache-Control": "no-store"})
