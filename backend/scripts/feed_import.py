#!/usr/bin/env python3
"""Đổi file Product Feed (CSV Shopee export) -> feed.csv chuẩn.

    python3 backend/scripts/feed_import.py feed_goc.csv [-o data/feed.csv --min-rate 5 --min-sales 50 --dry-run]
Sau đó thêm vào .env:  FEED_FILE=./feed.csv
"""
import _bootstrap  # noqa: F401
import argparse
import json
import sys
from pathlib import Path

from app.modules.products.feed_import import convert


def main() -> int:
    ap = argparse.ArgumentParser(description="Chuẩn hoá Product Feed Shopee -> feed.csv")
    ap.add_argument("src", help="file CSV feed tải từ dashboard affiliate")
    ap.add_argument("-o", "--out", default="feed.csv")
    ap.add_argument("--min-rate", type=float, default=0.0, help="bỏ sản phẩm có %% hoa hồng thấp hơn")
    ap.add_argument("--min-sales", type=int, default=0, help="bỏ sản phẩm bán ít hơn N")
    ap.add_argument("--drop-zero-rate", action="store_true", help="bỏ luôn sản phẩm rate = 0")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in thống kê, không ghi file")
    ap.add_argument("--json", action="store_true", help="in JSON cho máy đọc")
    a = ap.parse_args()

    if not Path(a.src).exists():
        print(f"không thấy file: {a.src}", file=sys.stderr)
        return 1
    res = convert(a.src, a.out, a.min_rate, a.min_sales, keep_zero_rate=not a.drop_zero_rate, dry_run=a.dry_run)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1

    print(f"encoding={res.get('encoding')}  delimiter={res.get('delimiter')!r}  header_row={res.get('header_row')}")
    print(f"cột nhận ra: {res.get('columns_detected')}")
    print(f"dòng đọc: {res.get('rows_total')}  ->  giữ: {res.get('rows_kept')}  bỏ: {res.get('dropped')}")
    for r in res.get("top5", []):
        print(f"  {r['rate']:>5}%  {r['price']:>10,}đ  bán {r['sold']:>6}  ~{r['est_vnd_per_sale']:>7,}đ/đơn  {r['name']}")
    if res.get("ok"):
        print(f"xong -> {res.get('output') or '(dry-run)'}")
        if not a.dry_run:
            print(f"thêm vào .env:  FEED_FILE={res.get('output')}")
        return 0
    print(f"LỖI: {res.get('error')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
