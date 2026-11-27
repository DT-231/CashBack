#!/usr/bin/env python3
"""Shopee Link API — microservice cho AI của bạn gọi: tên sản phẩm -> link affiliate.

Chạy:  python3 server.py --port 8080
Test:  curl "http://127.0.0.1:8080/api/search?keyword=noi%20chien&limit=5&sub=fb01"

Endpoints
  GET  /health
  GET  /api/search?keyword=..&limit=..&sort=relevancy|sales&sub=..
  POST /api/link          {"url": "..."} hoặc {"item_id":1,"shop_id":2,"sub":"x"}
  GET  /go/<sub_id>       -> 302 sang link affiliate + ghi click
  GET  /api/stats?days=7
  GET  /api/revenue?days=7   (cần cookie; đọc dashboard Shopee)
"""
import argparse
import hashlib
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent


def load_env():
    """Nạp .env cạnh file này. Biến môi trường thật vẫn thắng nếu .env không có key."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

import affiliate  # noqa: E402
import browser_search  # noqa: E402
import feed_search  # noqa: E402
import revenue  # noqa: E402
import shopee_search  # noqa: E402
import store  # noqa: E402

ENGINES = {"api": shopee_search.search, "feed": feed_search.search, "browser": browser_search.search}


def do_search(keyword, limit, sort, engine="auto"):
    """auto: feed (nếu có file) -> API Shopee -> browser. Trả về kèm engine đã dùng."""
    if engine == "auto":
        engine = os.environ.get("SEARCH_ENGINE", "auto").strip().lower()
    order = [engine] if engine in ENGINES else ["feed", "api", "browser"]
    tried = []
    for name in order:
        if name == "feed" and not os.environ.get("FEED_FILE"):
            tried.append("feed:bỏ qua (chưa đặt FEED_FILE)")
            continue
        if name == "api":
            res = shopee_search.search(keyword, limit=limit, sort=sort)
        else:
            res = ENGINES[name](keyword, limit=limit)
        tried.append(f"{name}:{'ok' if res.get('ok') else (res.get('error') or 'fail')}")
        if res.get("ok"):
            res["engine"] = name
            res["tried"] = tried
            return res
        if engine in ENGINES:  # chỉ định cứng 1 nguồn thì không fallback
            res["engine"] = name
            res["tried"] = tried
            return res
    return {"ok": False, "items": [], "error": "mọi nguồn đều fail", "engine": None, "tried": tried}

PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "").rstrip("/")


def _ip_hash(addr):
    salt = os.environ.get("IP_SALT", "zaka")
    return hashlib.sha256((salt + (addr or "")).encode()).hexdigest()[:16]


class Handler(BaseHTTPRequestHandler):
    server_version = "ShopeeLinkAPI/1.0"

    # ---------- helpers ----------
    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, url):
        self.send_response(302)
        self.send_header("Location", url)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            return json.loads(self.rfile.read(n).decode("utf-8", "ignore") or "{}")
        except Exception:  # noqa: BLE001
            return {}

    def log_message(self, fmt, *args):  # bớt ồn
        if os.environ.get("VERBOSE") == "1":
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---------- routes ----------
    def do_OPTIONS(self):
        self._send({}, 204)

    def do_GET(self):
        p = urlparse(self.path)
        q = parse_qs(p.query)

        if p.path == "/health":
            return self._send({
                "ok": True,
                "mock": os.environ.get("MOCK") == "1",
                "aff_id_set": bool(os.environ.get("SHOPEE_AFF_ID")),
                "cookie_set": bool(os.environ.get("SHOPEE_COOKIE")),
                "engine": os.environ.get("SEARCH_ENGINE", "auto"),
                "feed_file": os.environ.get("FEED_FILE") or None,
            })

        if p.path == "/api/search":
            keyword = (q.get("keyword") or [""])[0].strip()
            if not keyword:
                return self._send({"ok": False, "error": "thiếu keyword"}, 400)
            limit = int((q.get("limit") or ["10"])[0])
            sort = (q.get("sort") or ["relevancy"])[0]
            sub = (q.get("sub") or [""])[0].strip()
            engine = (q.get("engine") or ["auto"])[0].strip().lower()

            res = do_search(keyword, limit=limit, sort=sort, engine=engine)
            items = res["items"]
            out = []
            for i, it in enumerate(items, 1):
                rec = dict(it)
                sid = f"{sub}-{i}" if sub else f"{keyword[:12]}-{i}"
                sid = sid.replace(" ", "_")
                rec["sub_id"] = sid
                if not it.get("item_id") or not it.get("shop_id"):
                    rec["product_url"] = None
                    rec["aff_link"] = None
                    rec["link_error"] = "nguồn dữ liệu thiếu item_id/shop_id"
                    out.append(rec)
                    continue
                try:
                    link = affiliate.link_for_item(it["item_id"], it["shop_id"], sid)
                    rec["product_url"] = link["product_url"]
                    rec["aff_link"] = link["aff_link"]
                    store.save_link(sid, link["aff_link"], link["product_url"],
                                    it["item_id"], it["shop_id"], it.get("name"), keyword)
                except ValueError as e:
                    rec["product_url"] = affiliate.product_url(it["shop_id"], it["item_id"])
                    rec["aff_link"] = None
                    rec["link_error"] = str(e)
                out.append(rec)
            return self._send({
                "ok": res["ok"], "keyword": keyword, "count": len(out),
                "engine": res.get("engine"), "tried": res.get("tried"),
                "source": res.get("source"), "error": res.get("error"), "items": out,
            })

        if p.path == "/api/stats":
            days = int((q.get("days") or ["7"])[0])
            return self._send({"ok": True, **store.stats(days)})

        # Số liệu THẬT từ dashboard Shopee (click/đơn/hoa hồng theo sub_id).
        # Khác /api/stats: /api/stats đếm click trên /go/ của mình,
        # /api/revenue đọc số Shopee ghi nhận. Cần SHOPEE_COOKIE trong .env.
        if p.path == "/api/revenue":
            days = int((q.get("days") or ["7"])[0])
            try:
                data = revenue.summary(days)
            except revenue.RevenueError as e:
                return self._send({"ok": False, "error": str(e)}, 502)
            return self._send({"ok": True, **data})

        if p.path.startswith("/go/"):
            sub = p.path[4:].strip("/")
            row = store.get_target(sub)
            if not row:
                return self._send({"ok": False, "error": "sub_id không tồn tại"}, 404)
            store.log_click(sub, _ip_hash(self.client_address[0]),
                            self.headers.get("User-Agent", ""),
                            self.headers.get("Referer", ""))
            return self._redirect(row["target"])

        if p.path == "/":
            guide = {
                "service": "Shopee Link API",
                "for": "AI của bạn gọi vào đây để lấy link sản phẩm",
                "endpoints": {
                    "GET /api/search?keyword=&limit=&sort=&sub=": "tìm sản phẩm + link aff",
                    "POST /api/link": "{url} hoặc {item_id,shop_id,sub}",
                    "GET /go/<sub_id>": "redirect + đếm click",
                    "GET /api/stats?days=7": "thống kê click trên /go của mình",
                    "GET /api/revenue?days=7": "số liệu thật từ dashboard Shopee: click/đơn/hoa hồng theo sub_id",
                },
            }
            return self._send(guide)

        return self._send({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path)
        if p.path != "/api/link":
            return self._send({"ok": False, "error": "not found"}, 404)

        data = self._body()
        url = (data.get("url") or "").strip()
        sub = str(data.get("sub") or data.get("sub_id") or "api")
        item_id = data.get("item_id")
        shop_id = data.get("shop_id")

        parsed = affiliate.parse_product_url(url) if url else None
        if parsed:
            shop_id, item_id = parsed
        if not (item_id and shop_id):
            return self._send({"ok": False, "error": "cần url hoặc item_id + shop_id"}, 400)

        try:
            link = affiliate.link_for_item(int(item_id), int(shop_id), sub)
        except ValueError as e:
            return self._send({"ok": False, "error": str(e)}, 500)

        store.save_link(sub, link["aff_link"], link["product_url"],
                        int(item_id), int(shop_id), data.get("name"), data.get("keyword"))
        out = {"ok": True, **link}
        if PUBLIC_BASE:
            out["click_url"] = f"{PUBLIC_BASE}/go/{sub}"
        return self._send(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    a = ap.parse_args()

    store.init()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"Shopee Link API chạy tại http://{a.host}:{a.port}")
    print(f"MOCK={'1' if os.environ.get('MOCK') == '1' else '0'}  "
          f"AFF_ID={'có' if os.environ.get('SHOPEE_AFF_ID') else 'CHƯA CÓ'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
