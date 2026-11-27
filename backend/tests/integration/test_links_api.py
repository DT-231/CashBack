"""API user links trên Postgres thật; mọi sản phẩm dùng shop_id trong dải test riêng."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.subid import decode
from app.main_api import create_app
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
SECRET = "j" * 40
PW = "mat-khau-hop-le-1"


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        c.execute(text("DELETE FROM clicks WHERE link_id IN (SELECT id FROM links WHERE user_id IN "
                       "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test'))"))
        c.execute(text("DELETE FROM links WHERE user_id IN (SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"))
        c.execute(text("DELETE FROM products WHERE shop_id BETWEEN 990001 AND 990009"))
        ids = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {ids}"))
        c.execute(text(f"DELETE FROM users WHERE id IN {ids}"))
    eng.dispose()


@pytest.fixture
def api(make_settings, pg):
    settings = make_settings(database_url=DB_URL, jwt_secret=SECRET, public_base="https://x.test")
    return TestClient(create_app(settings, engine=pg), raise_server_exceptions=False)


def new_user(api):
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    api.post("/api/v1/auth/register", json={"email": email, "password": PW})
    token = api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_reuses_link_and_lists_only_own_user(api):
    a, b = new_user(api), new_user(api)
    url = "https://shopee.vn/Ten-SP-i.990001.100001?sp_atk=abc"
    first = api.post("/api/v1/links", headers=a, json={"url": url})
    again = api.post("/api/v1/links", headers=a, json={"url": "http://www.shopee.vn/product/990001/100001"})
    other = api.post("/api/v1/links", headers=b, json={"url": url})
    assert first.status_code == again.status_code == other.status_code == 200
    assert first.json()["code"] == again.json()["code"] != other.json()["code"]
    data = first.json()
    assert data["go_url"] == f"https://x.test/go/{data['code']}"
    assert data["product"] == {"shop_id": 990001, "item_id": 100001, "name": None}
    from urllib.parse import parse_qs, urlsplit
    token = parse_qs(urlsplit(data["direct_url"]).query)["utm_content"][0]
    decoded = decode(token, SECRET)
    assert decoded.status == "ok" and decoded.type == "l" and decoded.owner > 0 and decoded.ref > 0
    mine = api.get("/api/v1/me/links", headers=a)
    theirs = api.get("/api/v1/me/links", headers=b)
    assert len(mine.json()) == len(theirs.json()) == 1
    assert mine.json()[0]["clicks"] == 0
    assert api.get("/api/v1/me/links").json()["error"]["code"] == "unauthorized"


def test_bad_host_missing_product_and_public_base_empty(make_settings, pg):
    api = TestClient(create_app(make_settings(database_url=DB_URL, jwt_secret=SECRET, public_base=""), engine=pg),
                     raise_server_exceptions=False)
    headers = new_user(api)
    assert api.post("/api/v1/links", headers=headers, json={"url": "https://evil.com/product/1/2"}).status_code == 400
    assert api.post("/api/v1/links", headers=headers, json={"url": "https://shopee.vn/khong-co-id"}).status_code == 400
    result = api.post("/api/v1/links", headers=headers,
                      json={"url": "https://shopee.vn/product/990002/100002"})
    assert result.status_code == 200 and result.json()["go_url"] is None
