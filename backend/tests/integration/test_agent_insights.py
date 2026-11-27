"""T-051: insights cho Muse AI. Chỉ đơn từ BÀI ĐĂNG; không lộ người dùng; hoa hồng VND nguyên."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main_api import create_app
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
KEY = "e" * 32
TAG = "itest-ins-"


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    yield eng
    with eng.begin() as c:
        c.execute(text("DELETE FROM shopee_orders WHERE order_sn LIKE 'ITEST-I-%'"))
        c.execute(text(f"DELETE FROM posts WHERE post_key LIKE '{TAG}%'"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-ins-%@example.test'"))
    eng.dispose()


@pytest.fixture
def api(make_settings, pg):
    s = make_settings(database_url=DB_URL, agent_api_key=KEY, subid_secret="s" * 32)
    return TestClient(create_app(s, engine=pg), raise_server_exceptions=False)


H = {"Authorization": f"Bearer {KEY}"}


def post(pg, category, page, hour, days_ago=1):
    """Tạo bài với giờ đăng (giờ Việt Nam) cố định: hour giờ VN của ngày cách đây `days_ago` ngày."""
    with pg.begin() as c:
        return c.execute(text(
            "INSERT INTO posts(post_key, page_code, category, issued_at) VALUES (:k, :p, :c, "
            "((date_trunc('day', now() AT TIME ZONE 'Asia/Ho_Chi_Minh') - make_interval(days => :d) + make_interval(hours => :h)) AT TIME ZONE 'Asia/Ho_Chi_Minh')) RETURNING id"),
            {"k": f"{TAG}{uuid.uuid4().hex[:8]}", "p": page, "c": category, "h": hour, "d": days_ago}).scalar_one()


def order(pg, post_id, status, micro, source="post"):
    with pg.begin() as c:
        c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, post_id, commission_micro) VALUES (:s, :st, :src, :p, :m)"),
                  {"s": f"ITEST-I-{uuid.uuid4().hex[:8]}", "st": status, "src": source, "p": post_id, "m": micro})


def get(api, **p):
    r = api.get("/api/v1/agent/insights", params=p, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_requires_agent_key_and_validates_parameters(api):
    assert api.get("/api/v1/agent/insights", params={"group": "post"}).status_code == 401
    assert api.get("/api/v1/agent/insights", params={"group": "post"}, headers={"Authorization": "Bearer wrong"}).status_code == 401
    for bad in ({"group": "user"}, {"group": "post; DROP TABLE posts"}, {}, {"group": "post", "days": 0}, {"group": "post", "days": 366},
                {"group": "post", "limit": 0}, {"group": "post", "limit": 201}):
        assert api.get("/api/v1/agent/insights", params=bad, headers=H).status_code == 422, bad


def test_group_by_post_counts_orders_and_hides_cancelled_commission(api, pg):
    p1 = post(pg, "gia-dung", "pg1", 9)
    post(pg, "gia-dung", "pg1", 20)
    order(pg, p1, "COMPLETED", 4_037_500_000)            # 40.375đ
    order(pg, p1, "PENDING", 1_000_000_000)              # 10.000đ
    order(pg, p1, "CANCELLED", 9_000_000_000)            # không tính hoa hồng
    order(pg, p1, "RETURNED", 9_000_000_000)
    rows = {r["key"]: r for r in get(api, group="post")["rows"] if r["key"].startswith(TAG)}
    a, b = [rows[k] for k in sorted(rows, key=lambda k: -rows[k]["orders"])]
    assert a["orders"] == 4 and a["completed_orders"] == 1 and a["commission_vnd"] == 50_375 and a["posts"] == 1       # 40.375 + 10.000 (làm tròn xuống tổng micro)
    assert (b["orders"], b["commission_vnd"]) == (0, 0)                                                                # bài chưa có đơn vẫn hiện
    assert {"page_code", "category", "issued_at"} <= set(a) and "commission_micro" not in a


def test_group_by_category_page_and_hour(api, pg):
    c = f"{TAG}cat-{uuid.uuid4().hex[:4]}"
    pg_code = f"{TAG}pg-{uuid.uuid4().hex[:4]}"
    p1, p2, p3 = post(pg, c, pg_code, 9), post(pg, c, pg_code, 9), post(pg, "khac", "khac", 21)
    order(pg, p1, "COMPLETED", 2_000_000_000)
    order(pg, p2, "PENDING", 3_000_000_000)
    order(pg, p3, "COMPLETED", 4_000_000_000)
    cat = {r["key"]: r for r in get(api, group="category")["rows"]}[c]
    assert (cat["posts"], cat["orders"], cat["completed_orders"], cat["commission_vnd"]) == (2, 2, 1, 50_000)
    page = {r["key"]: r for r in get(api, group="page")["rows"]}[pg_code]
    assert (page["posts"], page["orders"], page["commission_vnd"]) == (2, 2, 50_000)
    hours = {r["key"]: r for r in get(api, group="hour")["rows"]}
    assert 9 in hours and 21 in hours and hours[9]["posts"] >= 2 and hours[9]["orders"] >= 2 and hours[21]["orders"] >= 1       # giờ VN, 0 đến 23
    assert all(0 <= r["key"] <= 23 for r in hours.values()) and [r["key"] for r in hours.values()] == sorted(r["key"] for r in hours.values())


def test_empty_category_and_page_are_grouped_as_unknown(api, pg):
    p = post(pg, "", "", 10)
    order(pg, p, "COMPLETED", 1_000_000_000)
    assert any(r["key"] == "unknown" and r["orders"] >= 1 for r in get(api, group="category")["rows"])
    assert any(r["key"] == "unknown" and r["orders"] >= 1 for r in get(api, group="page")["rows"])


def test_only_post_orders_count_and_no_user_data_ever_leaks(api, pg):
    with pg.begin() as c:
        uid = c.execute(text("INSERT INTO users(email, password_hash, status) VALUES ('itest-ins-leak@example.test', 'x', 'active') RETURNING id")).scalar_one()
        oid = c.execute(text("INSERT INTO shopee_orders(order_sn, status, source_type, user_id, commission_micro) VALUES ('ITEST-I-USER', 'COMPLETED', 'user', :u, 7777000000) RETURNING id"), {"u": uid}).scalar_one()
    p = post(pg, "gia-dung", "pg9", 9)
    with pg.begin() as c:                                                           # đơn của NGƯỜI DÙNG nhưng cố tình gắn nhầm post_id: không được tính vì source_type != 'post'
        c.execute(text("UPDATE shopee_orders SET post_id = :p WHERE id = :o"), {"p": p, "o": oid})
    order(pg, p, "COMPLETED", 1_000_000_000)
    for group in ("post", "category", "page", "hour"):
        text_ = json.dumps(get(api, group=group))
        for leak in ("itest-ins-leak", "ITEST-I-", "user_id", "email", "order_sn", "ip_hash", "7777"):
            assert leak not in text_, (group, leak)
    row = [r for r in get(api, group="post")["rows"] if r["posts"] == 1 and r["key"].startswith(TAG) and r["page_code"] == "pg9"][0]
    assert row["orders"] == 1 and row["commission_vnd"] == 10_000                    # chỉ đơn từ bài; đơn người dùng (77.770đ) không lọt vào


def test_window_and_limit(api, pg):
    old = post(pg, "gia-dung", "pgold", 9, days_ago=40)
    order(pg, old, "COMPLETED", 1_000_000_000)
    keys30 = {r["key"] for r in get(api, group="post", days=30, limit=200)["rows"]}
    keys60 = {r["key"] for r in get(api, group="post", days=60, limit=200)["rows"]}
    with pg.connect() as c:
        old_key = c.execute(text("SELECT post_key FROM posts WHERE id = :i"), {"i": old}).scalar_one()
    assert old_key not in keys30 and old_key in keys60                              # ngoài cửa sổ 30 ngày thì không có
    for i in range(3):
        post(pg, "gia-dung", "pgl", 9)
    assert len(get(api, group="post", limit=2)["rows"]) == 2
