"""Khóa hành vi HTTP của service cũ (port từ test_offline.py, không còn ghi đè samples/).

Đây là lưới an toàn cho bước 8 (chuyển sang FastAPI): shape JSON và aff_link phải giữ nguyên.
"""
import json
from pathlib import Path

import requests

import server

GOLDEN = Path(__file__).parent / "golden"


def get(base, path, **kw):
    return requests.get(base + path, timeout=10, **kw)


def test_health(base_url):
    r = get(base_url, "/health").json()
    assert r["ok"] is True and r["mock"] is True and r["aff_id_set"] is True


def test_search_mock_shape_and_links(base_url):
    r = get(base_url, "/api/search", params={"keyword": "nồi chiên không dầu", "limit": 3, "sub": "fb01"}).json()
    assert r["count"] == 3 and r["ok"] is True
    first = r["items"][0]
    assert first["name"] and first["price"] > 0
    assert "utm_source=an_" in first["aff_link"]
    assert first["sub_id"].startswith("fb01-")


def test_search_golden(base_url):
    """Chụp nguyên văn output MOCK; bước 8 phải cho kết quả giống hệt (trừ phần được ghi chú)."""
    r = get(base_url, "/api/search", params={"keyword": "nồi chiên", "limit": 5, "sub": "fb01"}).json()
    assert r == json.loads((GOLDEN / "search_mock.json").read_text(encoding="utf-8"))


def test_link_golden(base_url):
    r = requests.post(base_url + "/api/link",
                      json={"url": "https://shopee.vn/product/5502/100002", "sub": "tt09"}, timeout=10).json()
    assert r == json.loads((GOLDEN / "link_tt09.json").read_text(encoding="utf-8"))


def test_link_from_url_forms(base_url):
    r = requests.post(base_url + "/api/link", json={"url": "https://shopee.vn/product/5502/100002", "sub": "tt09"},
                      timeout=10).json()
    assert r["ok"] and "tt09" in r["aff_link"] and r["click_url"].endswith("/go/tt09")
    r = requests.post(base_url + "/api/link",
                      json={"url": "https://shopee.vn/Ten-San-Pham-i.5501.100001?sp_atk=abc", "sub": "x1"},
                      timeout=10).json()
    assert r["ok"] and r["product_url"].endswith("/5501/100001")


def test_link_needs_url_or_ids(base_url):
    r = requests.post(base_url + "/api/link", json={}, timeout=10)
    assert r.status_code == 400


def test_go_redirect_and_stats(base_url):
    requests.post(base_url + "/api/link", json={"url": "https://shopee.vn/product/5502/100002", "sub": "tt09"},
                  timeout=10)
    for _ in range(2):
        rr = get(base_url, "/go/tt09", allow_redirects=False)
        assert rr.status_code == 302 and "utm_source=an_" in rr.headers["Location"]
    st = get(base_url, "/api/stats", params={"days": 7}).json()
    assert st["clicks_total"] == 2 and st["links_issued"] == 1
    top = st["by_link"][0]
    assert top["sub_id"] == "tt09" and top["clicks"] == 2


def test_go_unknown_is_404(base_url):
    assert get(base_url, "/go/khong_ton_tai", allow_redirects=False).status_code == 404


def test_unknown_path_is_404(base_url):
    assert get(base_url, "/nope").status_code == 404


def test_feed_engine_accent_insensitive(base_url, feed_file):
    r = get(base_url, "/api/search",
            params={"keyword": "noi chien khong dau", "limit": 5, "sub": "f1", "engine": "feed"}).json()
    assert r["ok"] and r["engine"] == "feed"
    it = r["items"][0]
    assert it["comm_rate"] == 8 and "utm_source=an_" in it["aff_link"]


def test_auto_prefers_feed(base_url, feed_file):
    r = get(base_url, "/api/search", params={"keyword": "ke chen", "limit": 3, "sub": "a1"}).json()
    assert r["engine"] == "feed"


def test_auto_without_feed_uses_api_mock(base_url):
    r = get(base_url, "/api/search", params={"keyword": "noi chien", "limit": 2, "sub": "a1"}).json()
    assert r["engine"] == "api" and r["source"] == "mock"
    assert r["tried"][0].startswith("feed:bỏ qua")


def test_missing_keyword_is_400(base_url):
    assert get(base_url, "/api/search").status_code == 400


def test_item_without_ids_has_no_link(base_url, monkeypatch):
    monkeypatch.setattr(server, "do_search", lambda *a, **k: {"ok": True, "items": [{"name": "x"}], "source": "t"})
    r = get(base_url, "/api/search", params={"keyword": "x"}).json()
    it = r["items"][0]
    assert it["aff_link"] is None and "item_id/shop_id" in it["link_error"]


def test_missing_aff_id_reports_link_error(base_url, monkeypatch):
    monkeypatch.delenv("SHOPEE_AFF_ID")
    r = get(base_url, "/api/search", params={"keyword": "x", "limit": 1}).json()
    assert r["items"][0]["aff_link"] is None and "SHOPEE_AFF_ID" in r["items"][0]["link_error"]


def test_revenue_error_maps_to_502(base_url):
    # không có cookie -> RevenueError, không gọi mạng
    r = get(base_url, "/api/revenue")
    assert r.status_code == 502 and r.json()["ok"] is False


def test_invalid_json_body_is_reported_as_missing_ids(base_url):
    """Hành vi hiện tại (audit #15): JSON hỏng bị nuốt, client thấy lỗi sai nguyên nhân."""
    r = requests.post(base_url + "/api/link", data="{not json", timeout=10)
    assert r.status_code == 400 and "url" in r.json()["error"]
