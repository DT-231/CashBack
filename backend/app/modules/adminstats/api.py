"""HTTP tổng quan và tra cứu cho admin (chỉ đọc). Cần admin + TOTP. Không có endpoint ghi ở đây."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request

from app.core.money import micro_to_vnd
from app.modules.adminstats import repository
from app.modules.adminstats.health import build_health
from app.modules.auth.api import require_admin
from app.modules.auth.schemas import UserOut

router = APIRouter(prefix="/api/v1/admin", tags=["admin-stats"])
_SOURCES = "^(user|post|legacy|unknown)$"
_STATUSES = "^(PENDING|COMPLETED|CANCELLED|RETURNED)$"


def _iso(rows):
    return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(r).items()} for r in rows]


@router.get("/overview")
def overview(request: Request, days: int = Query(30, ge=1, le=365), _: UserOut = Depends(require_admin)):
    with request.app.state.get_engine().connect() as conn:
        d = repository.overview(conn, days)
    for v in d["orders"].values():
        v["commission_vnd"] = micro_to_vnd(v["commission_micro"])            # UI chỉ hiển thị VND do backend quy đổi (làm tròn xuống)
    if d["last_sync"]:
        d["last_sync"] = {"result": d["last_sync"]["result"], "finished_at": d["last_sync"]["finished_at"].isoformat()}
    return d


@router.get("/users")
def users(request: Request, q: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=100),
          offset: int = Query(0, ge=0), _: UserOut = Depends(require_admin)):
    with request.app.state.get_engine().connect() as conn:
        return _iso(repository.users(conn, q, limit, offset))


@router.get("/orders")
def orders(request: Request, status: str | None = Query(None, pattern=_STATUSES), source: str | None = Query(None, pattern=_SOURCES),
           limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), _: UserOut = Depends(require_admin)):
    with request.app.state.get_engine().connect() as conn:
        rows = repository.orders(conn, status, source, limit, offset)
    return [{**r, "commission_vnd": micro_to_vnd(r["commission_micro"])} for r in _iso(rows)]


@router.get("/health")
def health(request: Request, _: UserOut = Depends(require_admin)):
    st = request.app.state
    return build_health(st.settings, st.get_engine())


def _month_bounds(month: str):
    y, m = int(month[:4]), int(month[5:7])
    return datetime(y, m, 1, tzinfo=UTC), (datetime(y + 1, 1, 1, tzinfo=UTC) if m == 12 else datetime(y, m + 1, 1, tzinfo=UTC))


@router.get("/reconciliation")
def reconciliation(request: Request, month: str = Query(..., pattern=r"^20[0-9]{2}-(0[1-9]|1[0-2])$"), _: UserOut = Depends(require_admin)):
    """Đối soát theo tháng: hoa hồng Shopee ghi nhận − phần chia user = biên của nền tảng (ước tính, làm tròn xuống phần của user)."""
    start, end = _month_bounds(month)
    with request.app.state.get_engine().connect() as conn:
        raw = repository.reconciliation(conn, start, end)
    by_status: dict[str, dict] = {}
    for r in raw["orders"]:
        d = by_status.setdefault(r["status"], {"count": 0, "commission_micro": 0, "attributed_micro": 0})
        d["count"] += r["n"]
        d["commission_micro"] += int(r["micro"])
        d["attributed_micro"] += int(r["micro"]) if r["attributed"] else 0
    for d in by_status.values():
        d["commission_vnd"], d["attributed_vnd"] = micro_to_vnd(d["commission_micro"]), micro_to_vnd(d["attributed_micro"])
    led: dict[str, dict[str, int]] = {}
    for r in raw["ledger"]:
        led.setdefault(r["status"], {})[r["kind"]] = int(r["vnd"])

    def net(st):
        return led.get(st, {}).get("accrual", 0) - led.get(st, {}).get("cancel", 0)
    completed = by_status.get("COMPLETED", {"commission_vnd": 0, "attributed_vnd": 0})
    return {
        "month": month, "orders": by_status, "ledger_by_order_status": led,
        "completed": {"shopee_commission_vnd": completed["commission_vnd"], "attributed_commission_vnd": completed["attributed_vnd"],
                      "user_share_accrued_vnd": net("COMPLETED"),
                      "platform_margin_vnd": completed["commission_vnd"] - net("COMPLETED")},   # gồm cả đơn mồ côi (không chia cho ai)
        "paid_out_vnd": raw["payout_vnd"],
        "admin_loss_vnd": sum(v.get("adjust", 0) for v in led.values()),
        "note": "Hoa hồng cộng ở dạng micro rồi quy đổi xuống VND; phần user làm tròn xuống từng đơn nên tổng phần user luôn <= 60% tổng hoa hồng.",
    }


@router.get("/ledger-integrity")
def ledger_integrity(request: Request, _: UserOut = Depends(require_admin)):
    """Số dư lưu trong `wallets` phải bằng số suy ra từ sổ cái. `mismatches` > 0 là sự cố: dừng rút tiền, xem docs/runbooks/wallet.md."""
    with request.app.state.get_engine().connect() as conn:
        return repository.ledger_integrity(conn)
