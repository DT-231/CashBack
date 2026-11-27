"""P1-7: min_rate chỉ lọc được khi nguồn là feed; các nguồn khác phải báo filter_applied.min_rate = False."""
from fastapi.testclient import TestClient

from app.integrations.shopee.fake import FakeShopeeClient
from app.main_api import create_app

KEY = "k" * 32
H = {"Authorization": f"Bearer {KEY}"}


def app_with(make_settings, **kw):
    return TestClient(create_app(make_settings(agent_api_key=KEY, **kw), shopee=FakeShopeeClient()))


def test_api_engine_cannot_filter_rate_and_says_so(make_settings):
    r = app_with(make_settings).get("/api/v1/agent/search", params={"keyword": "x", "limit": 3, "min_rate": 8},
                                    headers=H).json()
    assert r["engine"] == "api" and r["count"] == 3 and r["filter_applied"] == {"min_rate": False, "min_sold": False}


def test_feed_engine_filters_by_rate(make_settings, feed_file):
    c = app_with(make_settings, feed_file=str(feed_file))
    r = c.get("/api/v1/agent/search", params={"keyword": "inox chao noi", "min_rate": 6}, headers=H).json()
    assert r["engine"] == "feed" and r["filter_applied"]["min_rate"] is True
    assert r["items"] and all(i["comm_rate"] >= 6 for i in r["items"])      # chảo 5% bị loại
    r0 = c.get("/api/v1/agent/search", params={"keyword": "inox chao noi"}, headers=H).json()
    assert r0["count"] > r["count"] and r0["filter_applied"]["min_rate"] is False   # không đặt min_rate


def test_min_sold_always_filters(make_settings):
    r = app_with(make_settings).get("/api/v1/agent/search", params={"keyword": "x", "limit": 5, "min_sold": 3000},
                                    headers=H).json()
    assert r["count"] == 2 and all(i["sold"] >= 3000 for i in r["items"]) and r["filter_applied"]["min_sold"] is True
