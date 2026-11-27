"""Cấu hình nghiệp vụ có hiệu lực theo thời gian (tỷ lệ chia, số ngày giữ, ngưỡng rút). Đổi cấu hình KHÔNG đổi hồi tố:
nơi dùng phải lưu snapshot giá trị tại thời điểm phát sinh (ví lưu `share_bp` trên từng bút toán)."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from collections.abc import Callable

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from app.modules.audit import service as audit
from app.modules.platform_settings import repository
from app.modules.platform_settings.errors import InvalidSetting

DEFAULTS = {"user_share_bp": 6000, "hold_days": 7, "min_withdraw_vnd": 100_000, "bank_change_cooldown_hours": 48}   # quyết định PO: 60/40, giữ 7 ngày
LIMITS = {"user_share_bp": (0, 10_000), "hold_days": (0, 120), "min_withdraw_vnd": (0, 100_000_000),
          "bank_change_cooldown_hours": (0, 720)}


def _valid(key: str, v) -> bool:
    lo, hi = LIMITS[key]
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


class PlatformSettings:
    def __init__(self, engine: Engine, clock=lambda: datetime.now(UTC)):
        self.engine, self.clock = engine, clock

    def get_int(self, key: str, at: datetime | None = None) -> int:
        if key not in DEFAULTS:
            raise InvalidSetting(f"không có cấu hình {key}")
        with self.engine.connect() as conn:
            v = repository.get_effective(conn, key, at or self.clock())
        return v if _valid(key, v) else DEFAULTS[key]

    def resolver(self, key: str) -> Callable[[datetime], int]:
        """Đọc lịch sử MỘT lần, trả hàm `giá trị có hiệu lực tại thời điểm t` (dùng khi tra cho nhiều đơn)."""
        if key not in DEFAULTS:
            raise InvalidSetting(f"không có cấu hình {key}")
        with self.engine.connect() as conn:
            rows = [(t, v) for t, v in repository.history(conn, key)]

        def at(t: datetime) -> int:
            value = DEFAULTS[key]
            for eff, v in rows:
                if eff > t:
                    break
                value = v if _valid(key, v) else DEFAULTS[key]
            return value
        return at

    def set_int(self, key: str, value: int, effective_from: datetime | None = None, *,
                audit_ctx: audit.AuditContext | None = None) -> None:
        """Chỉ nối thêm bản ghi mới có hiệu lực từ bây giờ trở đi; không được sửa quá khứ hay ghi đè một mốc đã có.
        Thao tác admin (endpoint) PHẢI truyền `audit_ctx`: log `settings.set` được ghi trong cùng transaction (lỗi log thì không đổi cấu hình)."""
        if key not in DEFAULTS:
            raise InvalidSetting(f"không có cấu hình {key}")
        if not _valid(key, value):
            lo, hi = LIMITS[key]
            raise InvalidSetting(f"{key} phải là số nguyên trong [{lo}, {hi}]")
        now = self.clock()
        eff = effective_from or now
        if eff < now:
            raise InvalidSetting("effective_from không được ở quá khứ (cấu hình không đổi hồi tố)")
        try:
            with self.engine.begin() as conn:
                repository.put(conn, key, json.dumps(value), eff)
                if audit_ctx is not None:
                    audit.record(conn, audit_ctx.settings, audit_ctx.actor, "settings.set", target_type="setting", target_id=key,
                                 detail={"key": key, "value": value, "effective_from": eff.isoformat()}, ip=audit_ctx.ip)
        except IntegrityError:
            raise InvalidSetting("đã có cấu hình tại đúng thời điểm này; chọn mốc khác") from None
