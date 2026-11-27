#!/usr/bin/env python3
"""Test offline: bật MOCK=1, chạy server in-process, gọi đủ 4 endpoint.
Chạy: python3 test_offline.py
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["MOCK"] = "1"
os.environ["SHOPEE_AFF_ID"] = "17399999999"
os.environ["DB_PATH"] = str(ROOT / "data" / "test.db")
os.environ["PUBLIC_BASE"] = "http://127.0.0.1:8931"

import requests  # noqa: E402

sys.path.insert(0, str(ROOT))
import server  # noqa: E402
import store  # noqa: E402

PORT = 8931
BASE = f"http://127.0.0.1:{PORT}"
fails = []


def check(name, cond, extra=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  <- {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def main():
    if (ROOT / "data" / "test.db").exists():
        (ROOT / "data" / "test.db").unlink()
    store.init()
    srv = server.ThreadingHTTPServer(("127.0.0.1", PORT), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.4)
    try:
        r = requests.get(BASE + "/health", timeout=5).json()
        check("health trả ok + mock=1", r.get("ok") and r.get("mock") is True)

        r = requests.get(BASE + "/api/search",
                         params={"keyword": "nồi chiên không dầu", "limit": 3, "sub": "fb01"},
                         timeout=10).json()
        check("search trả 3 item", r.get("count") == 3, str(r)[:200])
        first = (r.get("items") or [{}])[0]
        check("item có tên + giá + link aff",
              bool(first.get("name")) and first.get("price", 0) > 0 and "utm_source=an_" in (first.get("aff_link") or ""),
              json.dumps(first, ensure_ascii=False)[:200])
        check("sub_id gắn đúng prefix", first.get("sub_id", "").startswith("fb01-"),
              first.get("sub_id"))

        r = requests.post(BASE + "/api/link",
                          json={"url": "https://shopee.vn/product/5502/100002", "sub": "tt09"},
                          timeout=10).json()
        check("link từ URL -> có aff_link", r.get("ok") and "tt09" in (r.get("aff_link") or ""), str(r)[:200])
        check("link từ URL -> click_url", r.get("click_url", "").endswith("/go/tt09"))

        r = requests.post(BASE + "/api/link",
                          json={"url": "https://shopee.vn/Ten-San-Pham-i.5501.100001?sp_atk=abc", "sub": "x1"},
                          timeout=10).json()
        check("parse dạng -i.shop.item", r.get("ok") and r.get("product_url", "").endswith("/5501/100001"),
              str(r)[:200])

        rr = requests.get(BASE + "/go/tt09", allow_redirects=False, timeout=5)
        check("go/<sub> trả 302", rr.status_code == 302, str(rr.status_code))
        check("302 trỏ về link aff", "utm_source=an_" in rr.headers.get("Location", ""))

        requests.get(BASE + "/go/tt09", allow_redirects=False, timeout=5)
        st = requests.get(BASE + "/api/stats", params={"days": 7}, timeout=5).json()
        check("stats đếm được 2 click", st.get("clicks_total") == 2, str(st)[:200])
        top = (st.get("by_link") or [{}])[0]
        check("stats gộp theo sub_id", top.get("sub_id") == "tt09" and top.get("clicks") == 2,
              json.dumps(top, ensure_ascii=False))

        rr = requests.get(BASE + "/go/khong_ton_tai", allow_redirects=False, timeout=5)
        check("sub sai -> 404", rr.status_code == 404)

        # ---- nguồn feed CSV ----
        feed = ROOT / "samples" / "sample_feed.csv"
        feed.parent.mkdir(parents=True, exist_ok=True)
        feed.write_text(
            "itemid,shopid,product_name,price,commission_rate,sales,product_link\n"
            "900001,7001,Nồi chiên không dầu 6L,690000,8,1200,https://shopee.vn/product/7001/900001\n"
            "900002,7002,Kệ chén inox 2 tầng,159000,6,5100,https://shopee.vn/product/7002/900002\n"
            "900003,7003,Chảo chống dính 28cm,259000,5,2300,https://shopee.vn/product/7003/900003\n",
            encoding="utf-8",
        )
        os.environ["FEED_FILE"] = str(feed)
        r = requests.get(BASE + "/api/search",
                         params={"keyword": "noi chien khong dau", "limit": 5,
                                 "sub": "f1", "engine": "feed"}, timeout=10).json()
        check("feed engine tìm được theo tên không dấu",
              r.get("ok") and r.get("engine") == "feed", str(r)[:300])
        it = (r.get("items") or [{}])[0]
        check("feed giữ nguyên %hoa hồng", it.get("comm_rate") == 8,
              json.dumps(it, ensure_ascii=False)[:200])
        check("feed vẫn gắn aff_link", "utm_source=an_" in (it.get("aff_link") or ""))

        r2 = requests.get(BASE + "/api/search",
                          params={"keyword": "ke chen", "limit": 3, "sub": "a1"}, timeout=60).json()
        check("auto chọn feed trước", r2.get("engine") == "feed", str(r2.get("tried")))
    finally:
        srv.shutdown()

    print()
    if fails:
        print(f"{len(fails)} test FAIL: {fails}")
        sys.exit(1)
    print("TẤT CẢ TEST PASS — service chạy được, endpoint trả đúng shape.")


if __name__ == "__main__":
    main()
