"""Tìm sản phẩm Shopee theo keyword -> item_id + shop_id + giá + tên.

Đây là endpoint nội bộ của Shopee mà web/app dùng, KHÔNG phải API công khai.
Nó cần cookie phiên + thường cần IP sạch, và có thể đổi bất kỳ lúc nào.
Mọi chỗ dễ vỡ đều gom về đây, phần còn lại của hệ không phụ thuộc.
"""
import json
import os
import random
import time

import requests

SEARCH_URL = os.environ.get("SHOPEE_SEARCH_URL", "https://shopee.vn/api/v4/search/search_items")

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

MOCK_ITEMS = [
    {"item_id": 100001, "shop_id": 5501, "name": "Nồi chiên không dầu 5.5L",
     "price": 690000, "sold": 1200, "rating": 4.8},
    {"item_id": 100002, "shop_id": 5502, "name": "Bộ dao thớt inox nhà bếp",
     "price": 189000, "sold": 3400, "rating": 4.7},
    {"item_id": 100003, "shop_id": 5503, "name": "Máy hút bụi cầm tay mini",
     "price": 450000, "sold": 820, "rating": 4.6},
    {"item_id": 100004, "shop_id": 5504, "name": "Kệ chén inox 2 tầng",
     "price": 159000, "sold": 5100, "rating": 4.9},
    {"item_id": 100005, "shop_id": 5505, "name": "Chảo chống dính đá hoa cương 28cm",
     "price": 259000, "sold": 2300, "rating": 4.5},
]


def _headers(keyword):
    h = {
        "User-Agent": os.environ.get("SHOPEE_UA", DEFAULT_UA),
        "Accept": "application/json",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Referer": "https://shopee.vn/search?keyword=" + requests.utils.quote(keyword),
        "X-Requested-With": "XMLHttpRequest",
        "X-API-SOURCE": "pc",
        "X-Shopee-Language": "vi",
    }
    cookie = os.environ.get("SHOPEE_COOKIE", "").strip()
    if cookie:
        h["Cookie"] = cookie
    # Header chống bot — giá trị này đổi theo phiên, lấy từ DevTools của bạn
    enc = os.environ.get("SHOPEE_AF_AC_ENC_DAT", "").strip()
    if enc:
        h["af-ac-enc-dat"] = enc
    return h


def _proxies():
    p = os.environ.get("SHOPEE_PROXY", "").strip()
    if not p:
        return None
    return {"http": p, "https": p}


def _normalize(basic):
    price_raw = basic.get("price_min") or basic.get("price") or 0
    # Shopee trả giá đã nhân 100000
    price = price_raw / 100000 if price_raw > 10_000_000 else price_raw
    rating = (basic.get("item_rating") or {}).get("rating_star") or 0
    img = basic.get("image") or ""
    image_url = "https://down-vn.img.susercontent.com/file/" + img if img else ""
    return {
        "item_id": basic.get("itemid"),
        "shop_id": basic.get("shopid"),
        "name": basic.get("name"),
        "price": int(round(price)),
        "sold": basic.get("sold") or 0,
        "rating": round(float(rating), 2),
        "image": image_url,
    }


def search(keyword, limit=10, sort="relevancy", raw=False):
    """Trả {"ok": bool, "items": [...], "error": str|None}"""
    limit = max(1, min(int(limit), 60))

    if os.environ.get("MOCK") == "1":
        items = [dict(i) for i in MOCK_ITEMS[:limit]]
        return {"ok": True, "items": items, "error": None, "source": "mock"}

    params = {
        "by": "sales" if sort == "sales" else "relevancy",
        "keyword": keyword,
        "limit": limit,
        "newest": 0,
        "order": "desc",
        "page_type": "search",
        "scenario": "PAGE_GLOBAL_SEARCH",
        "version": 2,
        "item_card": 2,
    }

    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(
                SEARCH_URL,
                params=params,
                headers=_headers(keyword),
                proxies=_proxies(),
                timeout=20,
            )
            if r.status_code in (403, 429):
                last_err = f"HTTP {r.status_code} (cookie/IP bị chặn — cần cookie mới hoặc proxy)"
                time.sleep(2 + attempt * 2)
                continue
            data = r.json()
            if raw:
                return {"ok": True, "items": data, "error": None, "source": "shopee-raw"}
            block = data.get("error") or data.get("error_msg")
            if block not in (None, 0, ""):
                last_err = f"Shopee trả lỗi: {block}"
                time.sleep(1.5)
                continue
            bucket = (data.get("data") or {}).get("items") or []
            items = []
            for entry in bucket:
                basic = entry.get("item_basic") or entry
                if basic.get("itemid"):
                    items.append(_normalize(basic))
            if not items:
                last_err = "Không parse được item nào (Shopee đổi schema hoặc trả trang login)"
            return {"ok": bool(items), "items": items, "error": last_err, "source": "shopee"}
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(1.5 + attempt + random.random())

    return {"ok": False, "items": [], "error": last_err, "source": "shopee"}
