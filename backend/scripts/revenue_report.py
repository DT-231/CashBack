#!/usr/bin/env python3
"""Báo cáo doanh thu THẬT từ dashboard affiliate (cần SHOPEE_COOKIE). MOCK=1 dùng dữ liệu mẫu.

    python3 backend/scripts/revenue_report.py [--days 30] [--json]
"""
import _bootstrap  # noqa: F401  (phải import trước app.*)
import argparse
import json
import sys
from datetime import datetime

from app.core.config import load_settings
from app.core.money import format_vnd, micro_to_vnd_round
from app.integrations.shopee import build_client
from app.integrations.shopee.client import VN_TZ
from app.integrations.shopee.errors import ShopeeError
from app.modules.reports.service import build_summary


def vnd(micro) -> str:
    return format_vnd(micro_to_vnd_round(micro))


def print_human(s: dict) -> None:
    t = s["totals"]
    print(f"\n== {s['days']} ngày ({s['window'][0]} → {s['window'][1]}) ==")
    print(f"Click: {t['clicks']} | Đơn: {t['orders']} | Giá trị đơn: {vnd(t['order_amount_micro'])}đ | "
          f"Hoa hồng: {vnd(t['commission_micro'])}đ | Thực nhận: {vnd(t['income_micro'])}đ")
    if t["last_update"]:
        print("Số liệu cập nhật tới:", datetime.fromtimestamp(int(t["last_update"]), VN_TZ).strftime("%Y-%m-%d %H:%M"))
    if s["by_sub"]:
        print("\n-- Theo sub_id --")
        print(f"{'sub_id':<22}{'click':>7}{'đơn':>6}{'CVR':>8}{'hoa hồng':>14}")
        for r in s["by_sub"]:
            print(f"{r['sub_id'][:21]:<22}{r['clicks']:>7}{r['orders']:>6}{r['cvr_pct']:>7}%"
                  f"{vnd(r['commission_micro']):>14}")
    if s["top_items"]:
        print("\n-- Sản phẩm ra tiền --")
        for it in s["top_items"][:8]:
            print(f"  {vnd(it['commission_micro']):>9}đ  {it['qty']}x  "
                  f"[{it['platform_rate_bp'] / 100}%/{it['brand_rate_bp'] / 100}%]  {it['name']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        s = build_summary(build_client(load_settings()).dashboard_snapshot(max(1, a.days)), max(1, a.days))
    except ShopeeError as e:
        print(f"[!] {e}", file=sys.stderr)
        return 2
    print(json.dumps(s, ensure_ascii=False, indent=2, default=str) if a.json else "", end="")
    if not a.json:
        print_human(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
