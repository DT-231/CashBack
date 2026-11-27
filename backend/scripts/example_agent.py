#!/usr/bin/env python3
"""Ví dụ: AI của bạn gọi tool này thế nào (OpenAI-compatible function calling).

Chạy server trước:  MOCK=1 python3 -m app.main_api      (trong thư mục backend/)
Rồi:                python3 backend/scripts/example_agent.py "tìm cho tao 3 nồi chiên dưới 800k"
Nếu đặt AGENT_API_KEY ở server, đặt cùng biến đó khi chạy ví dụ này.

Phần quan trọng không phải LLM — mà là mapping tool_call -> HTTP request.
Copy đúng 2 nhánh dưới đây vào agent của bạn là xong.
"""
import os
import sys

import requests

BASE = os.environ.get("BASE", "http://127.0.0.1:8080").rstrip("/")
KEY = os.environ.get("AGENT_API_KEY", "")
HEADERS = {"Authorization": f"Bearer {KEY}"} if KEY else {}


def shopee_find_links(keyword, limit=10, sort="relevancy", sub=""):
    r = requests.get(f"{BASE}/api/search",
                     params={"keyword": keyword, "limit": limit, "sort": sort, "sub": sub},
                     headers=HEADERS, timeout=90)
    return r.json()


def shopee_link_from_url(url, sub="api"):
    r = requests.post(f"{BASE}/api/link", json={"url": url, "sub": sub}, headers=HEADERS, timeout=30)
    return r.json()


DISPATCH = {
    "shopee_find_links": lambda a: shopee_find_links(**a),
    "shopee_link_from_url": lambda a: shopee_link_from_url(**a),
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
