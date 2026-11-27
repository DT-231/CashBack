"""Hoàn tiền: biến đơn Shopee đã gán cho user thành bút toán ví. KHÔNG biết HTTP, KHÔNG có SQL.

Quy tắc cho từng đơn (idempotent, quyết định theo TRẠNG THÁI hiện tại chứ không theo lịch sử lần chạy):
  PENDING/COMPLETED, chưa có bút toán   -> accrual = floor(hoa hồng x tỷ lệ lúc này); lưu `share_bp` làm snapshot
  hoa hồng đổi khi còn chờ              -> điều chỉnh (accrual/cancel phần chênh) theo snapshot cũ; sau khi đã release thì kệ
  COMPLETED + hold_days đã qua + sync khỏe -> release toàn bộ phần đang chờ của đơn
  CANCELLED/RETURNED khi còn chờ        -> cancel phần đang chờ
  RETURNED/CANCELLED sau khi đã release -> reverse phần còn "rút được"; phần user đã rút mất -> adjust (lỗ của admin)
  số ngày giữ lấy theo cấu hình có hiệu lực LÚC ĐƠN HOÀN TẤT; tỷ lệ chia lấy lúc accrual đầu (snapshot)
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
    orders: int = 0                  # số đơn thật sự được xử lý (đơn đã chốt bị bỏ qua, không tính)
    accrued: int = 0
    released: int = 0
    cancelled: int = 0
    reversed: int = 0
    losses: int = 0
    release_blocked: int = 0         # đủ điều kiện nhưng sync không khỏe
    sync_healthy: bool = False
    errors: int = 0

    def merge(self, other: "SettleResult") -> None:
        self.orders += 1
        for f in ("accrued", "released", "cancelled", "reversed", "losses", "release_blocked"):
            setattr(self, f, getattr(self, f) + getattr(other, f))


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
        now = self.clock()
        share_at, hold_at = self.platform.resolver("user_share_bp"), self.platform.resolver("hold_days")   # đọc MỘT lần
        after = 0
        while True:
            batch = self.orders.attributed_orders(after_id=after)
            if not batch:
                return res
            with self.engine.connect() as conn:
                totals = repository.order_totals_many(conn, [o.order_id for o in batch])
            for o in batch:
                after = max(after, o.order_id)
                # Kiểm tra trước, KHÔNG khóa: đơn đã chốt (đa số theo thời gian) không tốn khóa ví hay truy vấn thêm
                if not self._needs_action(o, totals.get(o.order_id, {}), now, share_at, hold_at):
                    continue
                local = SettleResult(sync_healthy=res.sync_healthy)
                try:
                    with self.engine.begin() as conn:       # một giao dịch cho mỗi đơn: lỗi một đơn không chặn các đơn khác
                        self._settle_order(conn, o, local, now, share_at, hold_at)
                except Exception:   # noqa: BLE001 - có log đầy đủ; lần chạy sau thử lại (idempotent)
                    res.errors += 1
                    log.exception("không chốt được đơn", extra={"order_id": o.order_id})
                    continue
                res.merge(local)            # chỉ cộng bộ đếm SAU KHI giao dịch đã commit

    def _hold_due(self, o: AttributedOrder, now: datetime, hold_at) -> bool:
        """Đã hết hạn giữ chưa? Số ngày giữ lấy theo cấu hình có hiệu lực LÚC ĐƠN HOÀN TẤT (không đổi hồi tố)."""
        return o.completed_at is not None and o.completed_at + timedelta(days=hold_at(o.completed_at)) <= now

    def _needs_action(self, o: AttributedOrder, t: dict, now: datetime, share_at, hold_at) -> bool:
        """Bảo thủ: True nếu CÓ THỂ cần ghi gì đó. Chỉ dùng để bỏ qua sớm các đơn đã chốt; quyết định thật nằm trong khóa."""
        released = t.get("release", 0)
        pending = t.get("accrual", 0) - t.get("cancel", 0) - released
        if released > 0:
            return o.status in ("RETURNED", "CANCELLED") and t.get("reverse", 0) + t.get("adjust", 0) == 0
        if o.status in ("CANCELLED", "RETURNED"):
            return pending > 0
        target = micro_share_floor(max(o.commission_micro, 0), t.get("_share") or share_at(now))
        return target != pending or (o.status == "COMPLETED" and pending > 0 and self._hold_due(o, now, hold_at))

    def _settle_order(self, conn, o: AttributedOrder, res: SettleResult, now: datetime, share_at, hold_at) -> None:
        user, oid = o.user_id, o.order_id
        repository.ensure_wallet(conn, user)
        repository.lock_wallet(conn, user)                  # xếp hàng mọi thay đổi của user này; đọc tổng SAU khi có khóa
        t = repository.order_totals(conn, oid)
        released = t.get("release", 0)
        pending = t.get("accrual", 0) - t.get("cancel", 0) - released
        n = repository.count_for_order(conn, oid)

        def key(kind: str) -> str:
            return f"{kind}:{oid}:{n}"                     # n tăng theo từng bút toán của đơn: không đụng khóa cũ

        def post(kind: str, state: str, amount: int, **kw) -> bool:
            return ledger.post(conn, user, kind, state, amount, key(kind), order_id=oid, locked=True, **kw)

        if released == 0:
            if o.status in ("CANCELLED", "RETURNED"):
                if pending > 0 and post("cancel", "cancelled", pending):
                    res.cancelled += 1
                return
            share = repository.first_accrual_share(conn, oid)
            if share is None:
                share = share_at(now)
            target = micro_share_floor(max(o.commission_micro, 0), share)
            if target > pending:
                if post("accrual", "pending", target - pending, share_bp=share):
                    res.accrued += 1
                    pending = target
            elif target < pending:                          # Shopee giảm hoa hồng khi còn chờ
                if post("cancel", "cancelled", pending - target):
                    res.cancelled += 1
                    pending = target
            if o.status == "COMPLETED" and pending > 0 and self._hold_due(o, now, hold_at):
                if res.sync_healthy:
                    if post("release", "available", pending):
                        res.released += 1
                else:
                    res.release_blocked += 1
            return
        # đã release: Shopee trả hàng hoặc thu hồi (hủy) sau khi hoàn tất
        if o.status in ("RETURNED", "CANCELLED") and t.get("reverse", 0) + t.get("adjust", 0) == 0:
            available = repository.lock_wallet(conn, user)["available_vnd"]
            cover = min(released, available)
            if cover > 0 and post("reverse", "reversed", cover):
                res.reversed += 1
            if released - cover > 0 and post("adjust", "reversed", released - cover):
                res.losses += 1
                log.warning("user đã rút trước khi đơn bị thu hồi: ghi nhận lỗ của admin",
                            extra={"order_id": oid, "loss_vnd": released - cover})
