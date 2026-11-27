"""Hồi quy cho lỗi trong docs/refactor/01-audit.md đã sửa ở bước 9 (trước đó là xfail strict).

#1 link ghi đè nhau: giải quyết theo thiết kế (đường dẫn cũ không lưu gì; link AI mới idempotent theo post_key,
   xem tests/integration/test_agent_api.py).
#5 IP_SALT mặc định yếu: biến mất cùng /go (backend không còn băm IP).
"""
import pytest
from fastapi.testclient import TestClient

from app.main_api import create_app


def test_bad_limit_returns_400_not_500(client):          # audit #2
    r = client.get("/api/search", params={"keyword": "x", "limit": "abc"})
    assert r.status_code == 400 and r.json()["ok"] is False


@pytest.mark.parametrize("body", [{"item_id": "abc", "shop_id": 1}, {"item_id": 1, "shop_id": [2]}])
def test_bad_ids_on_link_return_400(client, body):       # audit #2 (POST)
    assert client.post("/api/link", json=body).status_code == 400


def test_legacy_endpoints_require_key_when_configured(make_settings):     # audit #3
    c = TestClient(create_app(make_settings(agent_api_key="k" * 32)))
    assert c.get("/api/search", params={"keyword": "x"}).status_code == 401
    assert c.post("/api/link", json={"item_id": 1, "shop_id": 2}).status_code == 401
    ok = {"Authorization": "Bearer " + "k" * 32}
    assert c.get("/api/search", params={"keyword": "x", "limit": 1}, headers=ok).status_code == 200
    assert c.post("/api/link", json={"item_id": 1, "shop_id": 2}, headers=ok).status_code == 200
    assert c.get("/health").status_code == 200            # health luôn mở


def test_legacy_endpoints_open_on_localhost_without_key(client):
    assert client.get("/api/search", params={"keyword": "x", "limit": 1}).status_code == 200


def test_non_loopback_host_counts_as_auth_required(make_settings):
    c = TestClient(create_app(make_settings(host="0.0.0.0")))
    assert c.get("/api/search", params={"keyword": "x"}).status_code == 401


def test_search_sub_id_does_not_embed_keyword(client):   # audit #4
    items = client.get("/api/search", params={"keyword": "noi chien khong dau", "limit": 2}).json()["items"]
    assert [i["sub_id"] for i in items] == ["api-1", "api-2"]
    assert all("noi" not in i["aff_link"] and "chien" not in i["aff_link"] for i in items)


def test_cors_is_off_by_default_and_opt_in(client, make_settings):
    assert "access-control-allow-origin" not in client.get("/health", headers={"origin": "http://x"}).headers
    c = TestClient(create_app(make_settings(cors_origins="http://app.local")))
    assert c.get("/health", headers={"origin": "http://app.local"}).headers["access-control-allow-origin"] \
        == "http://app.local"
