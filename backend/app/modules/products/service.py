"""Tìm sản phẩm qua nhiều nguồn sau một giao diện: feed -> API Shopee -> browser."""
from __future__ import annotations

from app.core.config import Settings
from app.integrations.shopee import browser
from app.modules.products.feed import FeedStore, search_feed

ENGINES = ("api", "feed", "browser")


class ProductSearch:
    def __init__(self, settings: Settings, shopee, feed: FeedStore | None = None):
        self.s, self.shopee, self.feed = settings, shopee, feed or FeedStore()

    def _run(self, name: str, keyword: str, limit: int, sort: str) -> dict:
        if name == "api":
            return self.shopee.search(keyword, limit=limit, sort=sort)
        if name == "feed":
            return search_feed(self.feed, self.s.feed_file, keyword, limit)
        if self.s.mock:   # MOCK=1: tuyệt đối không mở browser thật
            return {"ok": False, "items": [], "source": "browser", "error": "browser bị tắt khi MOCK=1"}
        return browser.search(self.s, keyword, limit)

    def search(self, keyword: str, limit: int = 10, sort: str = "relevancy", engine: str = "auto") -> dict:
        """auto: feed (nếu có file) -> API Shopee -> browser. Trả kèm engine đã dùng và nhật ký `tried`."""
        if engine == "auto":
            engine = self.s.search_engine.strip().lower()
        hard = engine in ENGINES   # chỉ định cứng 1 nguồn thì không fallback
        order = [engine] if hard else ["feed", "api", "browser"]
        tried = []
        for name in order:
            if name == "feed" and not self.s.feed_file:
                tried.append("feed:bỏ qua (chưa đặt FEED_FILE)")
                continue
            res = self._run(name, keyword, limit, sort)
            tried.append(f"{name}:{'ok' if res.get('ok') else (res.get('error') or 'fail')}")
            if res.get("ok") or hard:
                res["engine"], res["tried"] = name, tried
                return res
        return {"ok": False, "items": [], "error": "mọi nguồn đều fail", "engine": None, "tried": tried}
