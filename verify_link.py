#!/usr/bin/env python3
"""Kiểm tra link affiliate sinh ra có thật sự vào hệ thống tracking của Shopee không.

Cách dùng:
  python3 verify_link.py                                  # tự test 1 sản phẩm mẫu
  python3 verify_link.py --shop 1020310358 --item 24088489429 --sub fb01
  python3 verify_link.py --url "https://shopee.vn/..." --sub tiktok-01

Nó in ra: link sinh ra, HTTP status, Location sau 301, và 3 dấu hiệu quyết định:
  utm_source=an_<aff_id>   -> đúng affiliate id của bạn
  utm_content=<sub_id>     -> sub_id còn nguyên (để lọc báo cáo)
  uls_trackid=...           -> Shopee ĐÃ nhận link vào tracking (dấu hiệu quan trọng nhất)

Thiếu uls_trackid = link không được tracking, dù vẫn mở ra sản phẩm.
"""
import argparse
import os
import sys
from urllib.error import HTTPError
from urllib.parse import urlparse, parse_qs
from urllib.request import HTTPRedirectHandler, Request, build_opener

import affiliate

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check(link, timeout=20):
    opener = build_opener(_NoRedirect)
    req = Request(link, headers={
        "User-Agent": UA,
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    status, location = None, None
    try:
        r = opener.open(req, timeout=timeout)
        status = r.status
    except HTTPError as e:
        status = e.code
        location = e.headers.get("Location")

    target = location or link
    q = parse_qs(urlparse(target).query)
    return {
        "status": status,
        "redirect": location,
        "tracked": bool(q.get("uls_trackid")),
        "utm_source": (q.get("utm_source") or [None])[0],
        "utm_medium": (q.get("utm_medium") or [None])[0],
        "utm_content": (q.get("utm_content") or [None])[0],
        "final_host": urlparse(target).netloc,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shop", default="1020310358")
    ap.add_argument("--item", default="24088489429")
    ap.add_argument("--sub", default="verify01")
    ap.add_argument("--url", default="")
    a = ap.parse_args()

    if not affiliate.aff_id():
        print("THIẾU SHOPEE_AFF_ID — điền vào .env trước (hoặc export SHOPEE_AFF_ID=...)")
        return 2

    src = a.url or affiliate.product_url(a.shop, a.item)
    link = affiliate.make_link(src, a.sub)
    print("AFF_ID :", affiliate.aff_id())
    print("LINK   :", link)
    print("-" * 70)

    res = check(link)
    for k, v in res.items():
        print(f"{k:12}: {v}")

    print("-" * 70)
    ok = (res["tracked"]
          and (res["utm_source"] or "").startswith("an_")
          and bool(res["utm_content"]))
    if ok:
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
