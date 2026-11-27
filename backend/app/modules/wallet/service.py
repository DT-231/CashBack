"""Hoàn tiền: biến đơn Shopee đã gán cho user thành bút toán ví. KHÔNG biết HTTP, KHÔNG có SQL.

Quy tắc cho từng đơn (idempotent, quyết định theo TRẠNG THÁI hiện tại chứ không theo lịch sử lần chạy):
  PENDING/COMPLETED, chưa có bút toán   -> accrual = floor(hoa hồng x tỷ lệ lúc này); lưu `share_bp` làm snapshot
  hoa hồng đổi khi còn chờ              -> điều chỉnh (accrual/cancel phần chênh) theo snapshot cũ; sau khi đã release thì kệ
  COMPLETED + hold_days đã qua + sync khỏe -> release toàn bộ phần đang chờ của đơn
  CANCELLED/RETURNED khi còn chờ        -> cancel phần đang chờ
  RETURNED sau khi đã release           -> reverse phần còn "rút được"; phần user đã rút mất -> adjust (lỗ của admin)
"Sync khỏe" = lần đồng bộ đơn gần nhất là `ok` và không cũ hơn SYNC_MAX_AGE_HOURS. Không khỏe thì KHÔNG release
(accrual, cancel, reverse chỉ làm giảm hoặc giữ nguyên số tiền rút được nên vẫn chạy).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.money import micro_share_floor
from app.modules.orders.service import AttributedOrder, OrderReader
from app.modules.platform_settings.service import PlatformSettings
from app.modules.wallet import ledger, repository
from app.modules.wallet.schemas import EntryOut, WalletOut

log = logging.getLogger("app.wallet")


@dataclass
class SettleResult:
    orders: int = 0
    accrued: int = 0
    released: int = 0
    cancelled: int = 0
    reversed: int = 0
    losses: int = 0
    release_blocked: int = 0         # đủ điều kiện nhưng sync không khỏe
    sync_healthy: bool = False
    errors: int = 0


class WalletService:
    def __init__(self, settings: Settings, engine: Engine, orders: OrderReader | None = None,
                 platform: PlatformSettings | None = None, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.s, self.engine, self.clock = settings, engine, clock
        self.orders = orders or OrderReader(engine)
        self.platform = platform or PlatformSettings(engine, clock)

    # ---------- đọc ----------
    def wallet(self, user_id: int) -> WalletOut:
        with self.engine.connect() as conn:
            w = repository.get_wallet(conn, user_id)
        w = w or {"pending_vnd": 0, "available_vnd": 0, "held_vnd": 0}
        return WalletOut(**w, share_pct=self.platform.get_int("user_share_bp") / 100)

    def entries(self, user_id: int, limit: int = 50, offset: int = 0) -> list[EntryOut]:
        with self.engine.connect() as conn:
            return [EntryOut(**r) for r in repository.list_entries(conn, user_id, limit, offset)]

    # ---------- chốt sổ ----------
    def sync_is_healthy(self) -> bool:
        h = self.orders.sync_health()
        return bool(h and h.result == "ok" and self.clock() - h.finished_at <= timedelta(hours=self.s.sync_max_age_hours))

    def settle(self) -> SettleResult:
        res = SettleResult(sync_healthy=self.sync_is_healthy())
        after = 0
        while True:
            batch = self.orders.attributed_orders(after_id=after)
            if not batch:
                return res
            for o in batch:
                after = max(after, o.order_id)
                res.orders += 1
                try:
                    with self.engine.begin() as conn:       # một giao dịch cho mỗi đơn: lỗi một đơn không chặn các đơn khác
                        self._settle_order(conn, o, res)
                except Exception:   # noqa: BLE001 - có log đầy đủ; lần chạy sau thử lại (idempotent)
                    res.errors += 1
                    log.exception("không chốt được đơn", extra={"order_id": o.order_id})

    def _settle_order(self, conn, o: AttributedOrder, res: SettleResult) -> None:
        user, oid = o.user_id, o.order_id
        repository.ensure_wallet(conn, user)
        repository.lock_wallet(conn, user)                 # xếp hàng mọi thay đổi của user này; đọc tổng SAU khi có khóa
        t = repository.order_totals(conn, oid)
        released = t.get("release", 0)
        pending = t.get("accrual", 0) - t.get("cancel", 0) - released
        n = repository.count_for_order(conn, oid)

        def key(kind: str) -> str:
            return f"{kind}:{oid}:{n}"                     # n tăng theo từng bút toán của đơn: không đụng khóa cũ

        if released == 0:
            if o.status in ("CANCELLED", "RETURNED"):
                if pending > 0 and ledger.post(conn, user, "cancel", "cancelled", pending, key("cancel"), order_id=oid):
                    res.cancelled += 1
                return
            share = repository.first_accrual_share(conn, oid)
            if share is None:
                share = self.platform.get_int("user_share_bp")
            target = micro_share_floor(o.commission_micro, share)
            if target > pending:
                if ledger.post(conn, user, "accrual", "pending", target - pending, key("accrual"), order_id=oid,
                               share_bp=share):
                    res.accrued += 1
                    pending = target
            elif target < pending:                          # Shopee giảm hoa hồng khi còn chờ
                if ledger.post(conn, user, "cancel", "cancelled", pending - target, key("cancel"), order_id=oid):
                    res.cancelled += 1
                    pending = target
            if o.status == "COMPLETED" and pending > 0 and o.completed_at is not None:
                if o.completed_at + timedelta(days=self.platform.get_int("hold_days")) <= self.clock():
                    if res.sync_healthy:
                        if ledger.post(conn, user, "release", "available", pending, key("release"), order_id=oid):
                            res.released += 1
                    else:
                        res.release_blocked += 1
            return
        # đã release: chỉ còn trường hợp bị trả hàng
        if o.status == "RETURNED" and t.get("reverse", 0) + t.get("adjust", 0) == 0:
            available = repository.lock_wallet(conn, user)["available_vnd"]
            cover = min(released, available)
            if cover > 0 and ledger.post(conn, user, "reverse", "reversed", cover, key("reverse"), order_id=oid):
                res.reversed += 1
            if released - cover > 0 and ledger.post(conn, user, "adjust", "reversed", released - cover,
                                                    key("adjust"), order_id=oid):
                res.losses += 1
                log.warning("user đã rút trước khi đơn bị trả: ghi nhận lỗ của admin",
                            extra={"order_id": oid, "loss_vnd": released - cover})
