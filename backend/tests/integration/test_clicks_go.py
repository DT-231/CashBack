"""/go/{code} trên Postgres thật: ghi click, sub_id ký, dự phòng khi ghi click lỗi."""
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.subid import decode
from app.main_api import create_app
from app.modules.clicks import repository
from app.modules.clicks.service import hash_value
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
SUBID_SECRET = "s" * 32
IP_SALT = "i" * 32
PW = "mat-khau-hop-le-1"
SHOPEE_URL = "https://shopee.vn/product/990003/100003"


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
    with eng.begin() as c:
        c.execute(text(f"DELETE FROM clicks WHERE link_id IN (SELECT id FROM links WHERE user_id IN {users})"))
        c.execute(text(f"DELETE FROM links WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM products WHERE shop_id BETWEEN 990001 AND 990009"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
    eng.dispose()


@pytest.fixture
def make_api(make_settings, pg):
    def make(**kw):
        s = make_settings(database_url=DB_URL, jwt_secret="j" * 40, subid_secret=SUBID_SECRET, **kw)
        return TestClient(create_app(s, engine=pg), raise_server_exceptions=False, follow_redirects=False), s
    return make


@pytest.fixture
def api(make_api):
    return make_api()[0]


def new_link(api):
    """Tạo user + link qua API thật; trả (user_id, code)."""
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    tok = api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    code = api.post("/api/v1/links", headers={"Authorization": f"Bearer {tok}"}, json={"url": SHOPEE_URL}).json()["code"]
    return uid, code


def utm(resp):
    return parse_qs(urlsplit(resp.headers["location"]).query)["utm_content"][0]


def test_go_records_click_and_redirects_with_signed_click_level_sub_id(api, pg):
    uid, code = new_link(api)
    r = api.get(f"/go/{code}")
    assert r.status_code == 302 and r.headers["cache-control"] == "no-store"
    loc = urlsplit(r.headers["location"])
    assert loc.netloc == "shopee.vn" and loc.path == "/universal-link/product/990003/100003"
    q = parse_qs(loc.query)
    assert q["utm_source"] == ["an_17399999999"] and q["utm_medium"] == ["affiliates"]
    d = decode(utm(r), SUBID_SECRET)
    assert d.status == "ok" and d.type == "u" and d.owner == uid
    with pg.connect() as c:
        row = c.execute(text("SELECT id, sub_id, link_id FROM clicks WHERE id = :i"), {"i": d.ref}).one()
        link_id = c.execute(text("SELECT id FROM links WHERE code = :c"), {"c": code}).scalar_one()
    assert row.sub_id == utm(r) and row.link_id == link_id


def test_every_click_gets_its_own_sub_id(api, pg):
    _, code = new_link(api)
    subs = {utm(api.get(f"/go/{code}")) for _ in range(3)}
    assert len(subs) == 3
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM clicks WHERE sub_id = ANY(:s)"), {"s": list(subs)}).scalar_one() == 3


def test_unknown_or_malformed_code_is_404_and_records_nothing(api, pg):
    with pg.connect() as c:
        before = c.execute(text("SELECT count(*) FROM clicks")).scalar_one()
    for bad in ("zzzzzzzz", "ABCDEFGH", "short", "a" * 9, "a-b-c-d-"):
        r = api.get(f"/go/{bad}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "link_not_found", bad
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM clicks")).scalar_one() == before


def test_click_log_failure_still_redirects_with_link_level_sub_id(api, pg, monkeypatch):
    uid, code = new_link(api)

    def boom(*a, **kw):
        raise OperationalError("INSERT", {}, Exception("db down"))
    monkeypatch.setattr(repository, "insert_click", boom)
    r = api.get(f"/go/{code}")
    assert r.status_code == 302
    d = decode(utm(r), SUBID_SECRET)
    assert d.status == "ok" and d.type == "l" and d.owner == uid
    with pg.connect() as c:   # giao dịch lỗi đã rollback: không để lại click nửa vời
        assert c.execute(text("SELECT count(*) FROM clicks WHERE link_id = (SELECT id FROM links WHERE code = :c)"),
                         {"c": code}).scalar_one() == 0


def test_ip_and_ua_stored_only_as_keyed_hash(make_api, pg):
    api, s = make_api(ip_salt=IP_SALT)
    _, code = new_link(api)
    api.get(f"/go/{code}", headers={"user-agent": "UnitTestAgent/1.0"})
    with pg.connect() as c:
        row = c.execute(text("SELECT ip_hash, ua_hash FROM clicks WHERE link_id = "
                             "(SELECT id FROM links WHERE code = :c)"), {"c": code}).one()
    assert row.ip_hash == hash_value(s, "testclient") and row.ua_hash == hash_value(s, "UnitTestAgent/1.0")
    assert "testclient" not in row.ip_hash and "UnitTest" not in row.ua_hash


def test_without_ip_salt_nothing_personal_is_stored(api, pg):
    _, code = new_link(api)
    api.get(f"/go/{code}")
    with pg.connect() as c:
        row = c.execute(text("SELECT ip_hash, ua_hash FROM clicks WHERE link_id = "
                             "(SELECT id FROM links WHERE code = :c)"), {"c": code}).one()
    assert row.ip_hash is None and row.ua_hash is None


def test_proxy_header_trusted_only_when_enabled(make_api, pg):
    for trust, expect_ip in ((False, "testclient"), (True, "198.51.100.7")):
        api, s = make_api(ip_salt=IP_SALT, trust_proxy_headers=trust)
        _, code = new_link(api)
        api.get(f"/go/{code}", headers={"cf-connecting-ip": "198.51.100.7"})
        with pg.connect() as c:
            h = c.execute(text("SELECT ip_hash FROM clicks WHERE link_id = (SELECT id FROM links WHERE code = :c)"),
                          {"c": code}).scalar_one()
        assert h == hash_value(s, expect_ip), trust


def test_missing_subid_secret_is_503(make_settings, pg):
    s = make_settings(database_url=DB_URL, jwt_secret="j" * 40, subid_secret="")
    api = TestClient(create_app(s, engine=pg), raise_server_exceptions=False, follow_redirects=False)
    r = api.get("/go/abcdefgh")
    assert r.status_code == 503 and r.json()["error"]["code"] == "not_configured"


def test_missing_aff_id_is_503_and_leaves_no_phantom_click(make_settings, pg):
    s = make_settings(database_url=DB_URL, jwt_secret="j" * 40, subid_secret=SUBID_SECRET, shopee_aff_id="")
    api = TestClient(create_app(s, engine=pg), raise_server_exceptions=False, follow_redirects=False)
    with pg.connect() as c:
        before = c.execute(text("SELECT count(*) FROM clicks")).scalar_one()
    assert api.get("/go/abcdefgh").status_code == 503
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM clicks")).scalar_one() == before


def test_locked_owner_still_redirects_but_is_not_attributed(api, pg):
    uid, code = new_link(api)
    with pg.begin() as c:
        c.execute(text("UPDATE users SET status = 'locked' WHERE id = :u"), {"u": uid})
    r = api.get(f"/go/{code}")
    d = decode(utm(r), SUBID_SECRET)
    assert r.status_code == 302 and d.status == "ok" and d.type == "x" and d.owner == 0
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM clicks WHERE link_id = (SELECT id FROM links WHERE code = :c)"),
                         {"c": code}).scalar_one() == 0


@pytest.mark.parametrize("ua", ["facebookexternalhit/1.1", "Mozilla/5.0 (compatible; Googlebot/2.1)",
                                "TelegramBot (like TwitterBot)", "LinkPreview/1.0"])
def test_crawlers_are_redirected_but_not_counted_as_clicks(api, pg, ua):
    uid, code = new_link(api)
    r = api.get(f"/go/{code}", headers={"user-agent": ua})
    d = decode(utm(r), SUBID_SECRET)
    assert r.status_code == 302 and d.type == "l" and d.owner == uid
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM clicks WHERE link_id = (SELECT id FROM links WHERE code = :c)"),
                         {"c": code}).scalar_one() == 0


def test_real_browser_user_agents_are_counted(api, pg):
    _, code = new_link(api)
    for ua in ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 Mobile/15E148 Zalo/23.1",
               "Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile Safari/537.36 [FBAN/FB4A;FBAV/450.0]"):
        api.get(f"/go/{code}", headers={"user-agent": ua})
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM clicks WHERE link_id = (SELECT id FROM links WHERE code = :c)"),
                         {"c": code}).scalar_one() == 2


def test_trailing_newline_code_is_not_accepted(api):
    assert api.get("/go/abcdefgh%0A").status_code == 404


def test_invalid_proxy_ip_header_is_ignored(make_api, pg):
    api, s = make_api(ip_salt=IP_SALT, trust_proxy_headers=True)
    _, code = new_link(api)
    api.get(f"/go/{code}", headers={"cf-connecting-ip": "khong-phai-ip"})
    with pg.connect() as c:
        h = c.execute(text("SELECT ip_hash FROM clicks WHERE link_id = (SELECT id FROM links WHERE code = :c)"),
                      {"c": code}).scalar_one()
    assert h == hash_value(s, "testclient")
