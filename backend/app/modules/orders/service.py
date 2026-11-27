"""Đồng bộ đơn từ Shopee vào DB: upsert idempotent, khớp sub_id, đưa đơn lạ vào hàng mồ côi. KHÔNG biết HTTP.

Chưa chuyển tiền: việc đổi trạng thái đơn -> ví là của module `wallet` (T-031), đọc `sync_runs` để biết dữ liệu có đủ không.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import Engine

from app.core.config import ConfigError, Settings
from app.integrations.shopee.errors import ShopeeError
from app.modules.orders import repository
from app.modules.orders.attribution import attribute
from app.modules.orders.normalize import normalize_row

log = logging.getLogger("app.orders")


@dataclass
class SyncResult:
    result: str                      # ok | partial | failed
    rows: int = 0
    created: int = 0
    updated: int = 0
    orphans: int = 0
    status_changes: list[tuple[str, str, str]] = field(default_factory=list)   # (order_sn, từ, sang)
    error: str | None = None


class OrderSync:
    def __init__(self, settings: Settings, engine: Engine, client):
        self.s, self.engine, self.client = settings, engine, client

    def run(self, days: int | None = None) -> SyncResult:
        secret = self.s.subid_secret.get_secret_value()
        if len(secret.encode()) < 16:
            raise ConfigError("SUBID_SECRET phải có ít nhất 16 byte")
        with self.engine.begin() as conn:
            run_id = repository.start_run(conn, "orders")
        try:
            batch = self.client.order_batch(days or self.s.sync_days)
        except ShopeeError as e:           # cookie chết/403/mạng: ghi 'failed', KHÔNG đụng dữ liệu hiện có
            with self.engine.begin() as conn:
                repository.finish_run(conn, run_id, "failed", 0)
            log.error("đồng bộ đơn thất bại", extra={"error": str(e)})
            return SyncResult("failed", error=str(e))
        res = SyncResult("ok" if batch.complete else "partial")
        with self.engine.begin() as conn:
            for row in batch.rows:
                for o in normalize_row(row):
                    self._upsert(conn, o, secret, res)
            repository.finish_run(conn, run_id, res.result, res.rows)
        return res

    def _upsert(self, conn, o, secret, res: SyncResult) -> None:
        res.rows += 1
        cur = repository.get_status(conn, o.order_sn)
        if cur is None:
            attr = attribute(o.utm_content, secret, lambda k, ow, rf: repository.exists(conn, k, ow, rf))
            completed = o.completed_at if o.status == "COMPLETED" else None
            oid = repository.insert_order(conn, o, attr, o.status, completed)
            repository.replace_items(conn, oid, o.items)
            res.created += 1
            if attr.orphan_reason:
                repository.add_orphan(conn, oid, attr.orphan_reason)
                res.orphans += 1
            return
        completed = cur["completed_at"] or (o.completed_at if o.status == "COMPLETED" else None)
        if o.status != "COMPLETED":
            completed = None if o.status in ("CANCELLED", "RETURNED") else cur["completed_at"]
        repository.update_order(conn, cur["id"], o, o.status, completed)
        repository.replace_items(conn, cur["id"], o.items)
        res.updated += 1
        if cur["status"] != o.status:
            res.status_changes.append((o.order_sn, cur["status"], o.status))
