"""Entrypoint job nền: `sync-once` (đồng bộ đơn), `settle-once` (chốt ví), `run-once` (cả hai, theo thứ tự đó)."""
from __future__ import annotations

import argparse
import json
import sys

from pydantic import SecretStr

from app.core.config import ConfigError, load_settings
from app.core.db import make_engine
from app.integrations.telegram import build_notifier
from app.core.logging import configure_logging
from app.integrations.shopee import build_client
from app.modules.orders.service import OrderSync
from app.modules.shopee_session.service import ShopeeSessionService
from app.modules.wallet.service import WalletService


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.main_worker")
    ap.add_argument("command", choices=["sync-once", "settle-once", "run-once"])
    ap.add_argument("--days", type=int, default=None, help="1..366 (mặc định SYNC_DAYS)")
    a = ap.parse_args(argv)
    engine = None
    try:
        s = load_settings()
        configure_logging(s.log_level)
        engine = make_engine(s)
        out = {}
        if a.command in ("sync-once", "run-once"):
            sessions = ShopeeSessionService(s, engine)
            cookie = None if s.mock else sessions.load_cookie()      # cookie admin dán (mã hóa trong DB) thắng biến môi trường
            live = s.model_copy(update={"shopee_cookie": SecretStr(cookie)}) if cookie else s
            sync = OrderSync(s, engine, build_client(live)).run(a.days)
            if cookie:
                sessions.record_result(sync.result, sync.blocked, build_notifier(s))
            out["sync"] = sync.__dict__
        if a.command in ("settle-once", "run-once"):
            out["settle"] = WalletService(s, engine).settle().__dict__
    except ConfigError as e:
        print(f"Lỗi cấu hình: {e}", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(out, ensure_ascii=False, default=str))
    ok = out.get("sync", {}).get("result", "ok") == "ok" and out.get("settle", {}).get("errors", 0) == 0
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
