"""Client giả cho MOCK=1 và test: cùng giao diện ShopeeClient, dữ liệu từ fixtures/ (ẩn danh), không đụng mạng."""
from __future__ import annotations

import json
from pathlib import Path

from app.integrations.shopee.client import DashboardSnapshot, window

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeShopeeClient:
    def search(self, keyword: str, limit: int = 10, sort: str = "relevancy") -> dict:
        limit = max(1, min(int(limit), 60))
        return {"ok": True, "items": _load("mock_items.json")[:limit], "error": None, "source": "mock"}

    def dashboard_snapshot(self, days: int = 7) -> DashboardSnapshot:
        return DashboardSnapshot(window(days), _load("revenue_dashboard.json")["data"],
                                 _load("revenue_clicks.json")["data"]["list"],
                                 _load("revenue_orders.json")["data"]["list"])

    def check_link(self, link: str, timeout: int = 20) -> dict:
        return {"status": 301, "redirect": link + "&uls_trackid=mock", "tracked": True,
                "utm_source": None, "utm_medium": None, "utm_content": None, "final_host": "shopee.vn"}
