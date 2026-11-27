#!/usr/bin/env python3
"""Kiểm tra link affiliate sinh ra có vào tracking của Shopee không (GỌI LIVE; MOCK=1 thì giả).

  python3 backend/scripts/verify_link.py [--shop S --item I --sub fb01 | --url URL]

Dấu hiệu: utm_source=an_<aff_id> (đúng id), utm_content=<sub_id> còn nguyên, uls_trackid (Shopee đã nhận
link vào tracking — quan trọng nhất). Thiếu uls_trackid = không được tracking dù vẫn mở ra sản phẩm.
"""
import _bootstrap  # noqa: F401
import argparse
import sys

from app.core.config import load_settings
from app.integrations.shopee import build_client
from app.integrations.shopee.errors import ShopeeError
from app.modules.links.affiliate_link import LinkConfig, make_link, product_url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shop", default="1020310358")
    ap.add_argument("--item", default="24088489429")
    ap.add_argument("--sub", default="verify01")
    ap.add_argument("--url", default="")
    a = ap.parse_args()

    st = load_settings()
    if not st.aff_id:
        print("THIẾU SHOPEE_AFF_ID — điền vào .env trước (hoặc export SHOPEE_AFF_ID=...)")
        return 2
    link = make_link(a.url or product_url(a.shop, a.item), a.sub, LinkConfig.from_settings(st))
    print("AFF_ID :", st.aff_id)
    print("LINK   :", link)
    print("-" * 70)
    try:
        res = build_client(st).check_link(link)
    except ShopeeError as e:
        print(f"[!] {e}")
        return 2
    for k, v in res.items():
        print(f"{k:12}: {v}")
    print("-" * 70)
    if res["tracked"] and (res["utm_source"] or "").startswith("an_") and bool(res["utm_content"]):
        print("KẾT LUẬN: OK — link vào tracking, sub_id còn nguyên. Dùng được.")
        print("Bước cuối: nhờ 1 người máy/IP khác bấm link, mua món rẻ nhất,")
        print("24-48h sau xem Báo cáo -> Clicks phải > 0. Có click = chắc chắn đúng.")
        return 0
    print("KẾT LUẬN: CHƯA ỔN — xem dòng nào sai ở trên.")
    if not res["tracked"]:
        print("  Không thấy uls_trackid: Shopee chưa nhận link. Kiểm tra lại template/aff_id.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
