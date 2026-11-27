"""HTTP của ví: chỉ đọc, chỉ ví của chính user đang đăng nhập."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.modules.auth.api import current_user
from app.modules.auth.schemas import UserOut
from app.modules.wallet.schemas import EntryOut, OrderOut, WalletOut
from app.modules.wallet.service import WalletService

router = APIRouter(prefix="/api/v1/me/wallet", tags=["wallet"])
orders_router = APIRouter(prefix="/api/v1/me/orders", tags=["wallet"])


def _service(request: Request) -> WalletService:
    return WalletService(request.app.state.settings, request.app.state.get_engine())


@router.get("", response_model=WalletOut)
def my_wallet(request: Request, user: UserOut = Depends(current_user)):
    return _service(request).wallet(user.id)


@router.get("/entries", response_model=list[EntryOut])
def my_entries(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
               user: UserOut = Depends(current_user)):
    return _service(request).entries(user.id, limit, offset)


@orders_router.get("", response_model=list[OrderOut])
def my_orders(request: Request, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              user: UserOut = Depends(current_user)):
    return _service(request).my_orders(user.id, limit, offset)
