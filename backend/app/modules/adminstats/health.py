"""Sức khỏe hệ thống cho admin: DB, đồng bộ đơn, cookie Shopee, sao lưu. Chỉ trạng thái và con số, KHÔNG có đường dẫn, DSN hay bí mật.
Mỗi thành phần: status ∈ ok | warn | down | unknown | not_configured. overall: down > warn > ok (not_configured của sao lưu là warn)."""
from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, text

from app.core.config import Settings
from app.modules.orders.service import OrderReader
from app.modules.shopee_session.service import ShopeeSessionService


def _age_hours(then: datetime, now: datetime) -> float:
    return round((now - then).total_seconds() / 3600, 1)


def backup_status(settings: Settings, now: datetime) -> dict:
    if not settings.backup_dir.strip():
        return {"status": "not_configured"}
    files = sorted(Path(settings.backup_dir).expanduser().glob("backup-*.dump.enc"), key=lambda p: p.stat().st_mtime) \
        if Path(settings.backup_dir).expanduser().is_dir() else []
    if not files:
        return {"status": "down", "count": 0}
    age = _age_hours(datetime.fromtimestamp(files[-1].stat().st_mtime, UTC), now)
    return {"status": "ok" if age <= settings.backup_max_age_hours else "warn", "latest_age_hours": age, "count": len(files)}


def build_health(settings: Settings, engine: Engine, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    t0 = time.perf_counter()
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        db = {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception:  # noqa: BLE001 - mọi lỗi kết nối đều là "down"; chi tiết lỗi có thể chứa DSN nên không trả ra
        return {"overall": "down", "db": {"status": "down"}, "sync": {"status": "unknown"}, "shopee_session": {"status": "unknown"},
                "backup": backup_status(settings, now), "warnings": settings.startup_warnings()}
    h = OrderReader(engine).sync_health()
    if h is None:
        sync = {"status": "unknown"}
    else:
        age = _age_hours(h.finished_at, now)
        sync = {"status": "ok" if h.result == "ok" and age <= settings.sync_max_age_hours else "warn", "result": h.result, "age_hours": age}
    s = ShopeeSessionService(settings, engine).status()
    session = {"status": {"healthy": "ok", "unknown": "unknown", "degraded": "warn", "blocked": "down", "expired": "down"}[s["status"]],
               "failure_count": s["failure_count"], "has_cookie": s["has_cookie"]}
    if not s["has_cookie"]:
        session["status"] = "not_configured"
    out = {"db": db, "sync": sync, "shopee_session": session, "backup": backup_status(settings, now), "warnings": settings.startup_warnings()}
    statuses = [v["status"] for k, v in out.items() if isinstance(v, dict)]
    out["overall"] = "down" if "down" in statuses else "warn" if ("warn" in statuses or out["backup"]["status"] == "not_configured" or out["warnings"]) else "ok"
    return out
