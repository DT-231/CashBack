"""Phát hiện gian lận (T-053). CHỈ tạo cờ cho admin xem và xử lý; KHÔNG tự khóa, giữ hay trừ tiền ai (sai dương tính rất dễ xảy ra:
hai người chung wifi/nhà). Cờ có ngưỡng cấu hình; quét lại là idempotent (cập nhật cờ đang mở, không tạo trùng); cờ bị bỏ qua không
tạo lại trong FRAUD_DISMISS_COOLDOWN_DAYS ngày. Admin xử lý cờ (dismissed/confirmed) có audit; khóa user là hành động riêng (T-043)."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.errors import AppError, Forbidden
from app.modules.audit import service as audit_service
from app.modules.audit.service import AuditContext, audited
from app.modules.fraud import repository


class FlagNotFound(AppError):
    status, code = 404, "flag_not_found"


class FlagClosed(AppError):
    status, code = 409, "flag_closed"


@dataclass
class ScanResult:
    created: int = 0
    updated: int = 0
    suppressed: int = 0
    by_rule: dict[str, int] = field(default_factory=dict)


class FraudService:
    READ_ONLY = frozenset({"scan", "list_flags"})     # scan ghi cờ nhưng là việc của worker (không có tác nhân con người), xem docstring

    def __init__(self, settings: Settings, engine: Engine):
        self.s, self.engine = settings, engine

    def scan(self) -> ScanResult:
        """Chạy các luật và ghi cờ. Gọi từ worker (`fraud-scan`)."""
        s, res = self.s, ScanResult()
        with self.engine.begin() as conn:
            found = (
                [(r["user_id"], "shared_ip", r["n"], {"distinct_users": r["n"]}) for r in repository.shared_ip_users(conn, s.fraud_shared_ip_users)]
                + [(r["user_id"], "high_cancel_rate", int(r["bad"] * 100 // r["total"]), {"orders": r["total"], "cancelled_or_returned": r["bad"]})
                   for r in repository.high_cancel_users(conn, s.fraud_cancel_min_orders, s.fraud_cancel_rate_pct)]
                + [(r["user_id"], "click_burst", int(r["n"]), {"max_clicks_per_hour": int(r["n"])})
                   for r in repository.click_bursts(conn, s.fraud_burst_clicks_per_hour)])
            for user_id, rule, score, detail in found:
                out = repository.upsert_flag(conn, user_id, rule, score, detail, s.fraud_dismiss_cooldown_days)
                setattr(res, out, getattr(res, out) + 1)
                res.by_rule[rule] = res.by_rule.get(rule, 0) + 1
        return res

    def list_flags(self, status: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        with self.engine.connect() as conn:
            return [dict(r) for r in repository.list_flags(conn, status, limit, offset)]

    @audited
    def resolve(self, flag_id: int, status: str, note: str, *, audit: AuditContext) -> None:
        if audit.actor.role != "admin":
            raise Forbidden("Chỉ admin được xử lý cờ gian lận")
        if status not in ("dismissed", "confirmed"):
            raise AppError("status phải là dismissed hoặc confirmed", code="invalid_status", status=422)
        with self.engine.begin() as conn:
            row = repository.resolve(conn, flag_id, status, audit.actor.id, note)
            if row is None:
                if not repository.exists(conn, flag_id):
                    raise FlagNotFound("Không có cờ này")
                raise FlagClosed("Cờ này đã được xử lý")
            audit_service.record(conn, audit.settings, audit.actor, "fraud.resolve", target_type="fraud_flag", target_id=flag_id,
                                 detail={"user_id": row["user_id"], "rule": row["rule"], "status": status, "note": note}, ip=audit.ip)
