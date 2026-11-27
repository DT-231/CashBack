"""Cấu hình nghiệp vụ có hiệu lực theo thời gian (tỷ lệ chia, số ngày giữ, ngưỡng rút). Đổi cấu hình KHÔNG đổi hồi tố:
nơi dùng phải lưu snapshot giá trị tại thời điểm phát sinh (ví lưu `share_bp` trên từng bút toán)."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import Engine

from app.modules.platform_settings import repository
from app.modules.platform_settings.errors import InvalidSetting

DEFAULTS = {"user_share_bp": 6000, "hold_days": 7, "min_withdraw_vnd": 100_000}   # quyết định PO: 60/40, giữ 7 ngày
LIMITS = {"user_share_bp": (0, 10_000), "hold_days": (0, 120), "min_withdraw_vnd": (0, 100_000_000)}


class PlatformSettings:
    def __init__(self, engine: Engine, clock=lambda: datetime.now(UTC)):
        self.engine, self.clock = engine, clock

    def get_int(self, key: str, at: datetime | None = None) -> int:
        if key not in DEFAULTS:
            raise InvalidSetting(f"không có cấu hình {key}")
        with self.engine.connect() as conn:
            v = repository.get_effective(conn, key, at or self.clock())
        lo, hi = LIMITS[key]
        return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else DEFAULTS[key]

    def set_int(self, key: str, value: int, effective_from: datetime | None = None) -> None:
        if key not in DEFAULTS:
            raise InvalidSetting(f"không có cấu hình {key}")
        lo, hi = LIMITS[key]
        if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
            raise InvalidSetting(f"{key} phải là số nguyên trong [{lo}, {hi}]")
        with self.engine.begin() as conn:
            repository.put(conn, key, json.dumps(value), effective_from or self.clock())
