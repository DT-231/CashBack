#!/usr/bin/env python3
"""Ví dụ: AI của bạn gọi tool này thế nào (OpenAI-compatible function calling).

Chạy server trước:  python3 server.py --port 8080
Rồi:                python3 example_agent.py "tìm cho tao 3 nồi chiên dưới 800k"

Phần quan trọng không phải LLM — mà là mapping tool_call -> HTTP request.
Copy đúng 3 nhánh dưới đây vào agent của bạn là xong.
"""
import json
import os
import sys

import requests

BASE = os.environ.get("BASE", "http://127.0.0.1:8080").rstrip("/")


def shopee_find_links(keyword, limit=10, sort="relevancy", sub=""):
    r = requests.get(f"{BASE}/api/search",
                     params={"keyword": keyword, "limit": limit, "sort": sort, "sub": sub},
                     timeout=90)
    return r.json()


def shopee_link_from_url(url, sub="api"):
    r = requests.post(f"{BASE}/api/link", json={"url": url, "sub": sub}, timeout=30)
    return r.json()


def shopee_click_stats(days=7):
    r = requests.get(f"{BASE}/api/stats", params={"days": days}, timeout=10)
    return r.json()


DISPATCH = {
    "shopee_find_links": lambda a: shopee_find_links(**a),
    "shopee_link_from_url": lambda a: shopee_link_from_url(**a),
    "shopee_click_stats": lambda a: shopee_click_stats(**a),
}


def run_tool_call(name, args):
    fn = DISPATCH.get(name)
    if not fn:
        return {"error": f"tool lạ: {name}"}
    return fn(args)


def demo(keyword):
    """Không cần LLM: gọi thẳng để thấy dữ liệu AI sẽ nhận."""
    print(f"\n[AI gọi shopee_find_links(keyword={keyword!r}, limit=3)]")
    res = shopee_find_links(keyword, limit=3, sub="demo01")
    print(f"engine dùng: {res.get('engine')} | thử: {res.get('tried')}")
    if not res.get("ok"):
        print("Không lấy được:", res.get("error"))
        return
    for it in res["items"]:
        print(f"\n- {it['name']}")
        print(f"  giá      : {it.get('price'):,}đ".replace(",", "."))
        print(f"  hoa hồng : {it.get('comm_rate', 'chưa rõ')}%")
        print(f"  sub_id   : {it['sub_id']}")
        print(f"  aff_link : {it['aff_link']}")

    # đây là phần AI KHÔNG được tự bịa: chỉ dùng data thật trả về
    print("\n-> Prompt cho LLM viết caption phải chứa đúng tên + giá + aff_link ở trên.")


if __name__ == "__main__":
    if not sys.argv[1:]:
        print(__doc__)
        sys.exit(0)
    demo(" ".join(sys.argv[1:]))
