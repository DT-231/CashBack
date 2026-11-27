"""Entrypoint job nền. Hiện có: `python -m app.main_worker sync-once` (đồng bộ đơn một lần, MOCK=1 dùng fixture)."""
from __future__ import annotations

import argparse
import json
import sys

from app.core.config import load_settings
from app.core.db import make_engine
from app.core.logging import configure_logging
from app.integrations.shopee import build_client
from app.modules.orders.service import OrderSync


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.main_worker")
    ap.add_argument("command", choices=["sync-once"])
    ap.add_argument("--days", type=int, default=None)
    a = ap.parse_args(argv)
    s = load_settings()
    configure_logging(s.log_level)
    res = OrderSync(s, make_engine(s), build_client(s)).run(a.days)
    print(json.dumps(res.__dict__, ensure_ascii=False, default=str))
    return 0 if res.result == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
