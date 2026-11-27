"""Khóa hình dạng các endpoint cũ còn giữ (/health, /api/search, /api/link) trên app FastAPI mới.

Golden file chụp từ service cũ ở bước 2. `link_tt09.json` chỉ khác bản gốc ở chỗ bỏ `click_url`
(/go chuyển sang Cloudflare Worker, xem docs/refactor/02-target.md Q2).
"""
import json
from pathlib import Path

GOLDEN = Path(__file__).parent / "golden"


def golden(name):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def test_health(client):
    r = client.get("/health").json()
    assert r["ok"] is True and r["mock"] is True and r["aff_id_set"] is True
    assert "feed_file" not in r and r["feed_configured"] is False   # audit #18: không lộ đường dẫn


def test_search_mock_shape_and_links(client):
    r = client.get("/api/search", params={"keyword": "nồi chiên không dầu", "limit": 3, "sub": "fb01"}).json()
    assert r["count"] == 3 and r["ok"] is True
    first = r["items"][0]
    assert first["name"] and first["price"] > 0 and "utm_source=an_" in first["aff_link"]
    assert first["sub_id"].startswith("fb01-")


def test_search_golden(client):
    r = client.get("/api/search", params={"keyword": "nồi chiên", "limit": 5, "sub": "fb01"}).json()
    assert r == golden("search_mock.json")


def test_link_golden(client):
    r = client.post("/api/link", json={"url": "https://shopee.vn/product/5502/100002", "sub": "tt09"}).json()
    assert r == golden("link_tt09.json")


def test_link_from_url_forms_and_ids(client):
    r = client.post("/api/link", json={"url": "https://shopee.vn/Ten-San-Pham-i.5501.100001?sp_atk=abc",
                                       "sub": "x1"}).json()
    assert r["ok"] and r["product_url"].endswith("/5501/100001")
    r = client.post("/api/link", json={"item_id": 100001, "shop_id": 5501, "sub": "x2"}).json()
    assert r["ok"] and r["aff_link"].endswith("utm_content=x2----")


def test_link_default_sub_is_api(client):
    assert client.post("/api/link", json={"url": "https://shopee.vn/product/1/1"}).json()["sub_id"] == "api----"


def test_link_needs_url_or_ids(client):
    assert client.post("/api/link", json={}).status_code == 400


def test_invalid_json_body_is_reported_as_missing_ids(client):
    """Hành vi hiện tại (audit #15): JSON hỏng bị nuốt, client thấy lỗi sai nguyên nhân."""
    r = client.post("/api/link", content="{not json")
    assert r.status_code == 400 and "url" in r.json()["error"]


def test_feed_engine_accent_insensitive(make_settings, feed_file):
    from fastapi.testclient import TestClient
    from app.main_api import create_app
    c = TestClient(create_app(make_settings(feed_file=str(feed_file))))
    r = c.get("/api/search", params={"keyword": "noi chien khong dau", "limit": 5, "sub": "f1", "engine": "feed"}).json()
    assert r["ok"] and r["engine"] == "feed"
    assert r["items"][0]["comm_rate"] == 8 and "utm_source=an_" in r["items"][0]["aff_link"]
    r2 = c.get("/api/search", params={"keyword": "ke chen", "limit": 3, "sub": "a1"}).json()
    assert r2["engine"] == "feed"


def test_auto_without_feed_uses_api_mock(client):
    r = client.get("/api/search", params={"keyword": "noi chien", "limit": 2, "sub": "a1"}).json()
    assert r["engine"] == "api" and r["source"] == "mock" and r["tried"][0].startswith("feed:bỏ qua")


def test_missing_keyword_is_400(client):
    assert client.get("/api/search").status_code == 400


def test_item_without_ids_has_no_link(client):
    from app.modules.links.service import enrich_items
    out = enrich_items(client.app.state.settings, [{"name": "x"}], "")
    assert out[0]["aff_link"] is None and "item_id/shop_id" in out[0]["link_error"]


def test_missing_aff_id_reports_link_error(make_settings):
    from fastapi.testclient import TestClient
    from app.main_api import create_app
    r = TestClient(create_app(make_settings(shopee_aff_id=""))).get("/api/search", params={"keyword": "x", "limit": 1}).json()
    assert r["items"][0]["aff_link"] is None and "SHOPEE_AFF_ID" in r["items"][0]["link_error"]


def test_removed_endpoints_are_gone(client):
    """/go, /api/stats, /api/revenue đã bỏ (docs/08)."""
    for path in ("/go/abc", "/api/stats", "/api/revenue", "/nope"):
        assert client.get(path).status_code == 404


def test_request_id_header_roundtrip(client):
    assert client.get("/health", headers={"x-request-id": "abc123"}).headers["x-request-id"] == "abc123"
    assert client.get("/health").headers["x-request-id"]
