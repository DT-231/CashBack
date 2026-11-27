"""API user links trên Postgres thật; mọi sản phẩm dùng shop_id trong dải test riêng."""
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.subid import decode
from app.main_api import create_app
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
SECRET = "j" * 40
SUBID_SECRET = "s" * 32
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
    settings = make_settings(database_url=DB_URL, jwt_secret=SECRET, subid_secret=SUBID_SECRET,
                             public_base="https://x.test")
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
    token = parse_qs(urlsplit(data["direct_url"]).query)["utm_content"][0]
    decoded = decode(token, SUBID_SECRET)
    assert decoded.status == "ok" and decoded.type == "l" and decoded.owner > 0 and decoded.ref > 0
    settings = api.app.state.settings
    query = parse_qs(urlsplit(data["direct_url"]).query)
    assert query["utm_source"] == [f"an_{settings.shopee_aff_id}"]
    assert query["utm_medium"] == ["affiliates"]
    mine = api.get("/api/v1/me/links", headers=a)
    theirs = api.get("/api/v1/me/links", headers=b)
    assert len(mine.json()) == len(theirs.json()) == 1
    assert mine.json()[0]["clicks"] == 0
    assert api.get("/api/v1/me/links").json()["error"]["code"] == "unauthorized"


def test_bad_host_missing_product_and_public_base_empty(make_settings, pg):
    api = TestClient(create_app(make_settings(database_url=DB_URL, jwt_secret=SECRET,
                                             subid_secret=SUBID_SECRET, public_base=""), engine=pg),
                     raise_server_exceptions=False)
    headers = new_user(api)
    assert api.post("/api/v1/links", headers=headers, json={"url": "https://evil.com/product/1/2"}).status_code == 400
    assert api.post("/api/v1/links", headers=headers, json={"url": "https://shopee.vn/khong-co-id"}).status_code == 400
    result = api.post("/api/v1/links", headers=headers,
                      json={"url": "https://shopee.vn/product/990002/100002"})
    assert result.status_code == 200 and result.json()["go_url"] is None


@pytest.mark.parametrize("url, message", [
    ("https://evil.com/product/1/2", None),
    ("https://shopee.vn.evil.com/product/1/2", None),
    ("https://shopee.vn@evil.com/product/1/2", None),
    ("https://s.shopee.vn/abc", "chưa hỗ trợ link rút gọn"),
    ("ftp://shopee.vn/product/1/2", None),
    ("javascript:alert(1)", None),
])
def test_rejects_unsupported_urls(api, url, message):
    headers = new_user(api)
    response = api.post("/api/v1/links", headers=headers, json={"url": url})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_input"
    if message:
        assert message in response.json()["error"]["message"]


@pytest.mark.parametrize("headers", [None, {"Authorization": "Bearer invalid-token"}])
def test_create_requires_valid_token(api, headers):
    response = api.post("/api/v1/links", headers=headers, json={"url": "https://shopee.vn/product/990003/100003"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_url_over_2000_chars_is_validation_error(api):
    response = api.post("/api/v1/links", headers=new_user(api), json={"url": "x" * 2001})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_list_limit_and_offset(api):
    headers = new_user(api)
    for shop_id in (990003, 990004, 990005):
        response = api.post("/api/v1/links", headers=headers,
                            json={"url": f"https://shopee.vn/product/{shop_id}/{shop_id + 100000}"})
        assert response.status_code == 200
    assert len(api.get("/api/v1/me/links?limit=2", headers=headers).json()) == 2
    assert len(api.get("/api/v1/me/links?limit=2&offset=2", headers=headers).json()) == 1
    invalid = api.get("/api/v1/me/links?limit=0", headers=headers)
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "validation_error"


def test_empty_subid_secret_is_not_configured(make_settings, pg):
    settings = make_settings(database_url=DB_URL, jwt_secret=SECRET, subid_secret="", public_base="https://x.test")
    api = TestClient(create_app(settings, engine=pg), raise_server_exceptions=False)
    response = api.post("/api/v1/links", headers=new_user(api),
                        json={"url": "https://shopee.vn/product/990006/100006"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "not_configured"
