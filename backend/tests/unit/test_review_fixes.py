"""Hồi quy cho các điểm từ code review (docs/refactor/04-ket-qua.md)."""
import pytest
from fastapi.testclient import TestClient

from app.core import logging as clog
from app.core.cache import TTLCache
from app.main_api import create_app
from app.modules.links.affiliate_link import LinkConfig, LinkError, make_link
from app.modules.products.feed import FeedStore, search_feed
from tests.unit.test_shopee_client import Resp, make, patch_get

BAD_DB = "postgresql+psycopg://x:y@127.0.0.1:1/z"


def test_broken_or_jsonl_feed_is_error_not_exception(tmp_path):
    bad = tmp_path / "f.json"
    bad.write_text("{trunc", encoding="utf-8")
    assert "không đọc được" in search_feed(FeedStore(), str(bad), "x")["error"]
    jl = tmp_path / "f.jsonl"
    jl.write_text('{"item_id":1,"shop_id":2,"name":"Ghế"}\n{"item_id":3,"shop_id":4,"name":"Bàn"}\n', encoding="utf-8")
    assert search_feed(FeedStore(), str(jl), "ban")["items"][0]["item_id"] == 3


def test_cache_is_bounded():
    c = TTLCache(100, max_entries=3)
    for i in range(10):
        c.get_or_set(i, lambda i=i: i)
    assert len(c._data) <= 3


def test_short_subid_secret_is_503(make_settings):
    app = TestClient(create_app(make_settings(subid_secret="short", agent_api_key="k" * 32, database_url=BAD_DB)),
                     raise_server_exceptions=False)
    r = app.post("/api/v1/agent/links", headers={"Authorization": "Bearer " + "k" * 32},
                 json={"shop_id": 1, "item_id": 2, "post_key": "a", "page_code": "p1"})
    assert r.status_code == 503 and "SUBID_SECRET" in r.json()["error"]["message"]


def test_retry_success_clears_previous_error(monkeypatch):
    seq = [Resp(429), Resp(200, {"data": {"items": [{"itemid": 1, "shopid": 2, "name": "A"}]}})]
    patch_get(monkeypatch, lambda *a, **k: seq.pop(0))
    r = make().search("x")
    assert r["ok"] and r["error"] is None


def test_db_outage_during_auth_is_503(make_settings):
    app = TestClient(create_app(make_settings(database_url=BAD_DB)), raise_server_exceptions=False)
    r = app.get("/api/v1/agent/health", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "auth_unavailable"


@pytest.mark.parametrize("body", [{"url": 123}, {"item_id": -5, "shop_id": 1}, {"item_id": 0, "shop_id": 1}])
def test_legacy_link_rejects_bad_types_and_signs(client, body):
    assert client.post("/api/link", json=body).status_code == 400


def test_bad_template_is_link_error():
    cfg = LinkConfig(aff_id="1", template="https://x/{shop_id}/{item_id}/{nope}")
    with pytest.raises(LinkError, match="LINK_TEMPLATE"):
        make_link("https://shopee.vn/product/1/2", "x", cfg)


def test_request_id_from_client_is_validated(client):
    assert client.get("/health", headers={"x-request-id": "ok-1.2_3"}).headers["x-request-id"] == "ok-1.2_3"
    got = client.get("/health", headers={"x-request-id": "bad id" + "x" * 100}).headers["x-request-id"]
    assert clog._RID_OK.fullmatch(got) and len(got) <= 64
