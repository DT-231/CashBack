"""Rate limit dùng bảng Postgres `rate_limits`, fail-open khi bộ đếm lỗi."""
from __future__ import annotations

import logging
import random

from fastapi import Request
from sqlalchemy import text

from app.core.clientip import request_ip, limiter_key
from app.core.errors import RateLimited

log = logging.getLogger(__name__)

_INCREMENT = text("""
    INSERT INTO rate_limits (key, count, window_start) VALUES (:key, 1, now())
    ON CONFLICT (key) DO UPDATE SET
      count = CASE WHEN rate_limits.window_start <= now() - make_interval(secs => :window)
                   THEN 1 ELSE rate_limits.count + 1 END,
      window_start = CASE WHEN rate_limits.window_start <= now() - make_interval(secs => :window)
                          THEN now() ELSE rate_limits.window_start END
    RETURNING count,
      GREATEST(1, CEIL(EXTRACT(EPOCH FROM
        (window_start + make_interval(secs => :window) - now())))::int) AS retry_after
""")


def _record(request: Request, scope: str, value: str | None, limit: int, window: int) -> int | None:
    settings = request.app.state.settings
    key = f"{scope}:{limiter_key(settings, value)}"
    try:
        engine = request.app.state.get_engine()
        with engine.begin() as conn:
            row = conn.execute(_INCREMENT, {"key": key, "window": window}).one()
        if random.random() < 0.01:
            try:
                with engine.begin() as conn:
                    conn.execute(text("DELETE FROM rate_limits WHERE window_start < now() - interval '1 day'"))
            except Exception:
                log.exception("rate limit cleanup failed")
    except Exception:
        log.exception("rate limit check failed", extra={"scope": scope})
        return None

    return row.retry_after if row.count > limit else None


def enforce_rate_limits(request: Request, limits: list[tuple[str, str | None, int, int]]) -> None:
    if not request.app.state.settings.rl_enabled:
        return
    retry_after = None
    for scope, value, limit, window in limits:
        blocked_for = _record(request, scope, value, limit, window)
        if blocked_for is not None:
            retry_after = max(retry_after or 0, blocked_for)
    if retry_after is not None:
        raise RateLimited("Bạn gửi yêu cầu quá nhanh. Vui lòng thử lại sau.",
                          headers={"Retry-After": str(retry_after)})


def enforce_rate_limit(request: Request, scope: str, value: str | None, limit: int, window: int) -> None:
    enforce_rate_limits(request, [(scope, value, limit, window)])


def enforce_ip_limit(request: Request, scope: str, limit: int, window: int) -> None:
    settings = request.app.state.settings
    enforce_rate_limit(request, scope, request_ip(request, settings), limit, window)
