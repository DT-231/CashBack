"""Tool API /api/v1/agent/* trên Postgres thật (skip nếu không có DB). Dọn dữ liệu test sau khi chạy."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core import subid
from app.main_api import create_app
from app.modules.agent_auth.service import AgentAuth, hash_key
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
ENV_KEY = "e" * 32
SECRET = "s" * 32


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        c.execute(text("DELETE FROM posts WHERE post_key LIKE 'itest-%'"))
        c.execute(text("DELETE FROM agent_keys WHERE name LIKE 'itest-%'"))
        c.execute(text("DELETE FROM products WHERE shop_id IN (990001, 990002) AND NOT EXISTS "
                       "(SELECT 1 FROM posts WHERE product_id = products.id)"))
    eng.dispose()


@pytest.fixture
def api(make_settings, pg):
    s = make_settings(database_url=DB_URL, agent_api_key=ENV_KEY, subid_secret=SECRET)
    return TestClient(create_app(s, engine=pg), raise_server_exceptions=False)


def H(key=ENV_KEY):
    return {"Authorization": f"Bearer {key}"}


def body(**kw):
    return {"shop_id": 990001, "item_id": 880001, "post_key": f"itest-{uuid.uuid4().hex[:10]}",
            "page_code": "p1", "category": "gia-dung", **kw}


def test_requires_auth(api):
    assert api.post("/api/v1/agent/links", json=body()).status_code == 401
    r = api.post("/api/v1/agent/links", json=body(), headers=H("wrong"))
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_create_link_uses_v1_signed_sub_id(api):
    r = api.post("/api/v1/agent/links", json=body(), headers=H())
    assert r.status_code == 200, r.text
    j = r.json()
    d = subid.decode(j["sub_id"], SECRET)
    assert d.status == "ok" and d.type == "p" and d.owner == j["post_id"] and d.ref == int("p1", 36)
    assert j["aff_link"].endswith("utm_content=" + j["sub_id"])
    assert j["product_url"] == "https://shopee.vn/product/990001/880001"


def test_idempotent_by_post_key(api):
    b = body()
    first = api.post("/api/v1/agent/links", json=b, headers=H()).json()
    again = api.post("/api/v1/agent/links", json=b, headers=H()).json()
    assert first == again


def test_same_post_key_other_product_is_conflict_and_not_overwritten(api):
    b = body()
    first = api.post("/api/v1/agent/links", json=b, headers=H()).json()
    r = api.post("/api/v1/agent/links", json={**b, "item_id": 880002}, headers=H())
    assert r.status_code == 409 and r.json()["error"]["code"] == "post_key_conflict"
    assert api.post("/api/v1/agent/links", json=b, headers=H()).json() == first


def test_validation_errors_use_error_format(api):
    r = api.post("/api/v1/agent/links", json=body(page_code="BAD-CODE"), headers=H())
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["request_id"]


def test_db_key_lifecycle(api, make_settings, pg):
    auth = AgentAuth(make_settings(database_url=DB_URL), pg)
    key = auth.issue("itest-key")
    with pg.connect() as c:
        stored = c.execute(text("SELECT key_hash FROM agent_keys WHERE name='itest-key'")).scalar_one()
    assert stored == hash_key(key) and key not in stored
    assert api.get("/api/v1/agent/health", headers=H(key)).status_code == 200
    with pg.begin() as c:
        c.execute(text("UPDATE agent_keys SET revoked_at = now() WHERE name='itest-key'"))
    assert api.get("/api/v1/agent/health", headers=H(key)).status_code == 401


def test_posts_reference_agent_key(api, pg, make_settings):
    key = AgentAuth(make_settings(database_url=DB_URL), pg).issue("itest-owner")
    b = body()
    api.post("/api/v1/agent/links", json=b, headers=H(key))
    with pg.connect() as c:
        owner = c.execute(text("SELECT ak.name FROM posts p JOIN agent_keys ak ON ak.id = p.agent_key_id "
                               "WHERE p.post_key = :k"), {"k": b["post_key"]}).scalar_one()
    assert owner == "itest-owner"


def test_agent_search_has_no_links_and_filters(api):
    r = api.get("/api/v1/agent/search", params={"keyword": "noi chien", "limit": 3}, headers=H()).json()
    assert r["ok"] and r["count"] == 3 and all("aff_link" not in i for i in r["items"])
    r = api.get("/api/v1/agent/search", params={"keyword": "x", "min_sold": 3000}, headers=H()).json()
    assert {i["sold"] >= 3000 for i in r["items"]} == {True}
    assert api.get("/api/v1/agent/search", params={"keyword": "x", "limit": 0}, headers=H()).status_code == 422


def test_db_key_works_when_engine_is_created_lazily(make_settings, pg):
    """Hồi quy: app production không truyền engine; khóa trong agent_keys vẫn phải xác thực được."""
    key = AgentAuth(make_settings(database_url=DB_URL), pg).issue("itest-lazy")
    app = TestClient(create_app(make_settings(database_url=DB_URL)), raise_server_exceptions=False)
    assert app.get("/api/v1/agent/health", headers=H(key)).status_code == 200
    assert app.get("/api/v1/agent/health", headers=H("nope")).status_code == 401
