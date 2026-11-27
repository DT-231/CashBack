"""Đồng bộ đơn từ Shopee vào DB. KHÔNG biết HTTP, KHÔNG có SQL.

Đảm bảo (đường đi của tiền, nên bảo thủ):
- Idempotent theo `order_sn`; các dòng báo cáo cùng `order_sn` được gộp thành một đơn.
- Trạng thái không bao giờ lùi vì dữ liệu lạ (`status.next_status`).
- Mỗi đơn trong một savepoint: một dòng hỏng không làm hỏng cả lô, lần sync được đánh dấu `partial`.
- Chỉ một tiến trình sync tại một thời điểm (khóa advisory); chạy chồng thì bỏ qua, không ghi `sync_runs`.
- Lô chưa lấy đủ, lô có lỗi, lần sync lỗi đều ghi vào `sync_runs` để module `wallet` (T-031) từ chối chuyển tiền.
Chưa chuyển tiền: việc đổi trạng thái đơn -> ví là của `wallet`.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import Engine

from app.core.config import ConfigError, Settings
from app.integrations.shopee.errors import ShopeeError
from app.modules.ai_posts.service import AiPostService
from app.modules.clicks.service import ClickService
from app.modules.links.service import UserLinkService
from app.modules.orders import repository
from app.modules.orders.attribution import Attribution, attribute
from app.modules.orders.normalize import NormalizedOrder, merge_orders, normalize_row
from app.modules.orders.status import next_status

log = logging.getLogger("app.orders")


@dataclass
class SyncResult:
    result: str                      # ok | partial | failed | skipped
    rows: int = 0
    created: int = 0
    updated: int = 0
    orphans: int = 0
    reattributed: int = 0
    errors: int = 0
    status_changes: list[tuple[str, str, str]] = field(default_factory=list)     # (order_sn, từ, sang)
    status_conflicts: list[tuple[str, str, str]] = field(default_factory=list)   # (order_sn, đang lưu, Shopee báo) bị từ chối
    error: str | None = None


class OrderSync:
    def __init__(self, settings: Settings, engine: Engine, client, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.s, self.engine, self.client, self.clock = settings, engine, client, clock
        self._links, self._clicks, self._posts = (UserLinkService(settings, engine), ClickService(settings, engine),
                                                  AiPostService(settings, engine))

    def run(self, days: int | None = None) -> SyncResult:
        days = self.s.sync_days if days is None else days
        if not 1 <= days <= 366:
            raise ConfigError("days phải trong khoảng 1..366")
        secret = self.s.subid_secret.get_secret_value()
        if len(secret.encode()) < 16:
            raise ConfigError("SUBID_SECRET phải có ít nhất 16 byte")
        lock = self.engine.connect()
        try:
            if not repository.try_lock(lock):
                log.warning("đang có tiến trình đồng bộ đơn khác, bỏ qua")
                return SyncResult("skipped", error="đang có tiến trình đồng bộ khác")
            lock.commit()
            return self._run_locked(days, secret)
        finally:
            try:
                repository.unlock(lock)
                lock.commit()
            finally:
                lock.close()

    def _finish(self, run_id: int, result: str, rows: int) -> None:
        with self.engine.begin() as conn:
            repository.finish_run(conn, run_id, result, rows)

    def _run_locked(self, days: int, secret) -> SyncResult:
        with self.engine.begin() as conn:
            run_id = repository.start_run(conn, "orders")
        try:
            batch = self.client.order_batch(days)
        except ShopeeError as e:           # cookie chết/403/mạng: ghi 'failed', KHÔNG đụng dữ liệu hiện có
            self._finish(run_id, "failed", 0)
            log.error("đồng bộ đơn thất bại", extra={"error": str(e)})
            return SyncResult("failed", error=str(e))
        except Exception:
            self._finish(run_id, "failed", 0)
            raise
        res = SyncResult("ok")
        try:
            orders = merge_orders([o for row in batch.rows for o in normalize_row(row)])
            with self.engine.begin() as conn:
                for o in orders:
                    try:
                        with conn.begin_nested():
                            self._upsert(conn, o, secret, res)
                    except Exception:   # noqa: BLE001 - một đơn hỏng không được làm hỏng cả lô; có log đầy đủ
                        res.errors += 1
                        log.exception("không xử lý được đơn", extra={"order_sn": o.order_sn})
                res.result = "ok" if batch.complete and res.errors == 0 else "partial"
                repository.finish_run(conn, run_id, res.result, res.rows)
        except Exception:
            self._finish(run_id, "failed", 0)
            raise
        return res

    # ---------- một đơn ----------
    def _exists(self, kind: str, owner: int, ref: int) -> bool:
        """Chữ ký đã đúng; vẫn phải khớp dữ liệu thật. Hỏi qua service công khai của module sở hữu dữ liệu."""
        if kind == "click":
            link_id = self._clicks.link_of_click(ref)
            return link_id is not None and self._links.link_belongs_to(owner, link_id)
        if kind == "link":
            return self._links.link_belongs_to(owner, ref)
        return self._posts.post_exists(owner)

    def _attribute(self, o: NormalizedOrder, secret) -> Attribution:
        return attribute(o.utm_content, secret, self._exists)

    def _upsert(self, conn, o: NormalizedOrder, secret, res: SyncResult) -> None:
        res.rows += 1
        cur = repository.get_status(conn, o.order_sn)
        if cur is None:
            attr = self._attribute(o, secret)
            completed = (o.completed_at or self.clock()) if o.status == "COMPLETED" else None
            oid = repository.insert_order(conn, o, attr, o.status, completed)
            if oid is not None:
                repository.replace_items(conn, oid, o.items)
                res.created += 1
                if attr.orphan_reason:
                    repository.add_orphan(conn, oid, attr.orphan_reason)
                    res.orphans += 1
                return
            cur = repository.get_status(conn, o.order_sn)    # có tiến trình khác vừa tạo: đi đường cập nhật
        status, accepted = next_status(cur["status"], o.status)
        if not accepted:
            res.status_conflicts.append((o.order_sn, cur["status"], o.status))
            log.warning("bỏ qua đổi trạng thái không hợp lệ",
                        extra={"order_sn": o.order_sn, "stored": cur["status"], "incoming": o.status})
        completed = cur["completed_at"]            # giữ mốc hoàn tất đầu tiên, kể cả khi sau đó bị trả hàng
        if status == "COMPLETED" and completed is None:
            completed = o.completed_at or self.clock()
        repository.update_order(conn, cur["id"], o, status, completed)
        repository.replace_items(conn, cur["id"], o.items)
        res.updated += 1
        if cur["status"] != status:
            res.status_changes.append((o.order_sn, cur["status"], status))
        # Đơn mồ côi chưa ai nhận (kể cả staff) có thể khớp được khi dữ liệu về muộn
        if cur["user_id"] is None and cur["post_id"] is None and o.utm_content:
            attr = self._attribute(o, secret)
            if attr.orphan_reason is None:
                repository.set_attribution(conn, cur["id"], o.utm_content, attr)
                repository.delete_orphan(conn, cur["id"])
                res.reattributed += 1


@dataclass(frozen=True)
class AttributedOrder:
    order_id: int
    user_id: int
    status: str
    commission_micro: int
    completed_at: datetime | None


@dataclass(frozen=True)
class SyncHealth:
    result: str                      # ok | partial | failed
    finished_at: datetime


class OrderReader:
    """Giao diện đọc công khai của orders cho module khác (wallet). Chỉ đọc."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def attributed_orders(self, after_id: int = 0, limit: int = 500, recent_days: int = 90) -> list[AttributedOrder]:
        with self.engine.connect() as conn:
            rows = repository.attributed_orders(conn, after_id, limit, recent_days)
        return [AttributedOrder(r["id"], r["user_id"], r["status"], r["commission_micro"], r["completed_at"]) for r in rows]

    def sync_health(self) -> SyncHealth | None:
        """Lần đồng bộ đơn đã kết thúc gần nhất (None nếu chưa từng sync)."""
        with self.engine.connect() as conn:
            r = repository.latest_finished_run(conn)
        return SyncHealth(r["result"], r["finished_at"]) if r and r["result"] else None
