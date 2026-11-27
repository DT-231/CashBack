"""Đồng bộ đơn trên Postgres thật: idempotent, đổi trạng thái, mồ côi, không ghi đè gán tay, dữ liệu dở dang."""
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core import subid
from app.core.config import ConfigError
from app.modules.orders import repository as orders_repo
from app.integrations.shopee.client import OrderBatch
from app.integrations.shopee.errors import ShopeeBlockedError
from app.main_api import create_app
from app.modules.orders.service import OrderSync
from tests.integration.pg import DB_URL, pg_available

pytestmark = pytest.mark.skipif(not pg_available(), reason="không có Postgres (make db-up)")
SECRET = "s" * 32
PW = "mat-khau-hop-le-1"


class FakeClient:
    def __init__(self, rows=(), complete=True, error=None):
        self.rows, self.complete, self.error = list(rows), complete, error

    def order_batch(self, days=60):
        if self.error:
            raise self.error
        return OrderBatch((0, 0), self.rows, self.complete)


@pytest.fixture
def pg():
    eng = create_engine(DB_URL)
    with eng.connect() as c:
        last_run = c.execute(text("SELECT coalesce(max(id), 0) FROM sync_runs")).scalar_one()
    yield eng
    users = "(SELECT id FROM users WHERE email LIKE 'itest-%@example.test')"
    with eng.begin() as c:
        c.execute(text("DELETE FROM orphan_orders WHERE order_id IN (SELECT id FROM shopee_orders WHERE order_sn LIKE 'ITEST-%')"))
        c.execute(text("DELETE FROM shopee_order_items WHERE order_id IN (SELECT id FROM shopee_orders WHERE order_sn LIKE 'ITEST-%')"))
        c.execute(text("DELETE FROM shopee_orders WHERE order_sn LIKE 'ITEST-%'"))
        c.execute(text("DELETE FROM sync_runs WHERE id > :i"), {"i": last_run})
        c.execute(text(f"DELETE FROM clicks WHERE link_id IN (SELECT id FROM links WHERE user_id IN {users})"))
        c.execute(text(f"DELETE FROM links WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM posts WHERE post_key LIKE 'itest-%'"))
        c.execute(text("DELETE FROM products WHERE shop_id BETWEEN 990001 AND 990009"))
        c.execute(text(f"DELETE FROM refresh_tokens WHERE user_id IN {users}"))
        c.execute(text("DELETE FROM users WHERE email LIKE 'itest-%@example.test'"))
    eng.dispose()


@pytest.fixture
def settings(make_settings):
    return make_settings(database_url=DB_URL, jwt_secret="j" * 40, subid_secret=SECRET)


@pytest.fixture
def api(settings, pg):
    return TestClient(create_app(settings, engine=pg), raise_server_exceptions=False, follow_redirects=False)


def user_with_click(api):
    """User thật + link + một click thật qua /go; trả (user_id, link_code, click_id, utm_content)."""
    email = f"itest-{uuid.uuid4().hex[:10]}@example.test"
    uid = api.post("/api/v1/auth/register", json={"email": email, "password": PW}).json()["id"]
    tok = api.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    code = api.post("/api/v1/links", headers={"Authorization": f"Bearer {tok}"},
                    json={"url": "https://shopee.vn/product/990004/100004"}).json()["code"]
    utm = parse_qs(urlsplit(api.get(f"/go/{code}").headers["location"]).query)["utm_content"][0]
    d = subid.decode(utm, SECRET)
    return uid, code, d.ref, utm


def order_row(sn=None, utm="", commission=403_750_000, **extra):
    sn = sn or f"ITEST-{uuid.uuid4().hex[:8]}"
    return {"utm_content": utm, "capped_commission": commission,
            "orders": [{"order_sn": sn, "items": [{"item_id": 100004, "shop_id": 990004, "item_price": 9_500_000_000,
                                                    "qty": 2, "item_commission": commission,
                                                    "platform_commission_rate": 250,
                                                    "global_category_lv1_name": "Nhà cửa"}], **extra}]}, sn


def sync(settings, pg, rows, **kw):
    return OrderSync(settings, pg, FakeClient(rows, **kw)).run(60)


def fetch(pg, sn):
    with pg.connect() as c:
        return c.execute(text("SELECT * FROM shopee_orders WHERE order_sn = :s"), {"s": sn}).mappings().one()


def orphan(pg, sn):
    with pg.connect() as c:
        return c.execute(text("SELECT reason FROM orphan_orders WHERE order_id = (SELECT id FROM shopee_orders "
                              "WHERE order_sn = :s)"), {"s": sn}).scalar_one_or_none()


def test_click_order_is_attributed_to_the_right_user_and_click(api, settings, pg):
    uid, _, click_id, utm = user_with_click(api)
    row, sn = order_row(utm=utm)
    res = sync(settings, pg, [row])
    assert (res.result, res.created, res.orphans) == ("ok", 1, 0)
    o = fetch(pg, sn)
    assert (o["user_id"], o["click_id"], o["source_type"], o["commission_micro"], o["status"]) == (
        uid, click_id, "user", 403_750_000, "PENDING")
    assert orphan(pg, sn) is None
    with pg.connect() as c:
        items = c.execute(text("SELECT qty, price_micro, platform_rate_bp FROM shopee_order_items WHERE order_id = :i"),
                          {"i": o["id"]}).all()
    assert [tuple(i) for i in items] == [(2, 9_500_000_000, 250)]


def test_sync_is_idempotent(api, settings, pg):
    _, _, _, utm = user_with_click(api)
    row, sn = order_row(utm=utm)
    a, b = sync(settings, pg, [row]), sync(settings, pg, [row])
    assert (a.created, a.updated, b.created, b.updated) == (1, 0, 0, 1)
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM shopee_orders WHERE order_sn = :s"), {"s": sn}).scalar_one() == 1
        assert c.execute(text("SELECT count(*) FROM shopee_order_items WHERE order_id = :i"),
                         {"i": fetch(pg, sn)["id"]}).scalar_one() == 1


def test_status_transitions_are_reported_and_completed_at_is_kept(api, settings, pg):
    _, _, _, utm = user_with_click(api)
    row, sn = order_row(utm=utm)
    sync(settings, pg, [row])
    row["orders"][0].update(order_status="COMPLETED", complete_time=1_760_000_000)
    res = sync(settings, pg, [row])
    assert res.status_changes == [(sn, "PENDING", "COMPLETED")]
    done = fetch(pg, sn)["completed_at"]
    assert fetch(pg, sn)["status"] == "COMPLETED" and done is not None
    row["orders"][0]["complete_time"] = 1_770_000_000      # Shopee đổi mốc: giữ mốc hoàn tất đầu tiên
    assert sync(settings, pg, [row]).status_changes == [] and fetch(pg, sn)["completed_at"] == done
    row["orders"][0]["order_status"] = "RETURNED"
    assert sync(settings, pg, [row]).status_changes == [(sn, "COMPLETED", "RETURNED")]
    assert fetch(pg, sn)["status"] == "RETURNED" and fetch(pg, sn)["completed_at"] == done   # giữ lịch sử hoàn tất


def test_commission_change_is_applied_but_attribution_is_not_recomputed(api, settings, pg):
    uid, _, _, utm = user_with_click(api)
    row, sn = order_row(utm=utm)
    sync(settings, pg, [row])
    row["capped_commission"] = 100_000_000
    row["orders"][0]["items"][0]["item_commission"] = 100_000_000
    row["utm_content"] = "doi-sub-id---"
    sync(settings, pg, [row])
    o = fetch(pg, sn)
    assert o["commission_micro"] == 100_000_000 and o["user_id"] == uid and o["utm_content"] == utm


@pytest.mark.parametrize("utm,reason", [("", "no_sub_id"), ("fb01-1---", "legacy_sub_id")])
def test_unattributable_orders_go_to_the_orphan_queue(settings, pg, utm, reason):
    row, sn = order_row(utm=utm)
    res = sync(settings, pg, [row])
    o = fetch(pg, sn)
    assert res.orphans == 1 and orphan(pg, sn) == reason and o["user_id"] is None


def test_forged_sub_id_pointing_at_a_real_user_is_an_orphan(api, settings, pg):
    uid, _, click_id, utm = user_with_click(api)
    forged = utm.replace("-" + subid.to_base36(uid) + "-", "-" + subid.to_base36(uid + 1) + "-")
    row, sn = order_row(utm=forged)
    sync(settings, pg, [row])
    o = fetch(pg, sn)
    assert o["user_id"] is None and orphan(pg, sn).startswith("invalid_sub_id")


def test_validly_signed_sub_id_with_a_click_of_another_user_is_an_orphan(api, settings, pg):
    uid_a, _, click_a, _ = user_with_click(api)
    uid_b, _, _, _ = user_with_click(api)
    mixed = subid.encode("u", uid_b, click_a, SECRET)         # chữ ký đúng nhưng click không thuộc B
    row, sn = order_row(utm=mixed)
    sync(settings, pg, [row])
    assert fetch(pg, sn)["user_id"] is None and orphan(pg, sn) == "click_not_found"


def test_link_level_and_post_and_other_sources(api, settings, pg):
    uid, code, _, _ = user_with_click(api)
    with pg.connect() as c:
        link_id = c.execute(text("SELECT id FROM links WHERE code = :c"), {"c": code}).scalar_one()
    with pg.begin() as c:
        post_id = c.execute(text("INSERT INTO posts(post_key) VALUES (:k) RETURNING id"),
                            {"k": f"itest-{uuid.uuid4().hex[:8]}"}).scalar_one()
    r1, s1 = order_row(utm=subid.encode("l", uid, link_id, SECRET))
    r2, s2 = order_row(utm=subid.encode("p", post_id, 1, SECRET))
    r3, s3 = order_row(utm=subid.encode("x", 0, link_id, SECRET))
    sync(settings, pg, [r1, r2, r3])
    a, b, c3 = fetch(pg, s1), fetch(pg, s2), fetch(pg, s3)
    assert (a["user_id"], a["click_id"], a["source_type"]) == (uid, None, "user")
    assert (b["post_id"], b["user_id"], b["source_type"]) == (post_id, None, "post") and orphan(pg, s2) is None
    assert c3["user_id"] is None and orphan(pg, s3) == "other_source"


def test_manual_assignment_of_an_orphan_survives_resync(api, settings, pg):
    uid, _, _, _ = user_with_click(api)
    row, sn = order_row(utm="")
    sync(settings, pg, [row])
    with pg.begin() as c:
        c.execute(text("UPDATE shopee_orders SET user_id = :u, source_type = 'user' WHERE order_sn = :s"),
                  {"u": uid, "s": sn})
    sync(settings, pg, [row])
    o = fetch(pg, sn)
    assert o["user_id"] == uid and o["source_type"] == "user"


def test_partial_batch_is_saved_but_marked_partial(settings, pg):
    row, sn = order_row()
    res = sync(settings, pg, [row], complete=False)
    assert res.result == "partial" and fetch(pg, sn)["order_sn"] == sn
    with pg.connect() as c:
        last = c.execute(text("SELECT result, rows FROM sync_runs WHERE kind = 'orders' ORDER BY id DESC LIMIT 1")).one()
    assert tuple(last) == ("partial", 1)


def test_shopee_error_marks_run_failed_and_touches_nothing(settings, pg):
    row, sn = order_row()
    sync(settings, pg, [row])
    res = OrderSync(settings, pg, FakeClient(error=ShopeeBlockedError("HTTP 403 — cookie hết hạn"))).run(60)
    assert res.result == "failed" and "403" in res.error
    assert fetch(pg, sn)["commission_micro"] == 403_750_000
    with pg.connect() as c:
        assert c.execute(text("SELECT result FROM sync_runs WHERE kind = 'orders' ORDER BY id DESC LIMIT 1")).scalar_one() == "failed"


def test_weak_subid_secret_refuses_to_sync(make_settings, pg):
    with pytest.raises(ConfigError):
        OrderSync(make_settings(database_url=DB_URL, subid_secret=""), pg, FakeClient()).run()


def test_capped_zero_commission_is_stored_as_zero(settings, pg):
    row, sn = order_row(commission=403_750_000)
    row["capped_commission"] = 0
    row["gross_commission"] = 100_000_000
    sync(settings, pg, [row])
    assert fetch(pg, sn)["commission_micro"] == 0


def test_unknown_or_missing_status_never_downgrades_a_completed_order(api, settings, pg):
    _, _, _, utm = user_with_click(api)
    row, sn = order_row(utm=utm)
    row["orders"][0]["order_status"] = "COMPLETED"
    sync(settings, pg, [row])
    del row["orders"][0]["order_status"]                    # Shopee đổi tên trường: map về PENDING
    res = sync(settings, pg, [row])
    assert fetch(pg, sn)["status"] == "COMPLETED" and res.status_changes == []
    assert res.status_conflicts == [(sn, "COMPLETED", "PENDING")]
    row["orders"][0]["order_status"] = "CANCELLED"
    sync(settings, pg, [row])
    assert fetch(pg, sn)["status"] == "COMPLETED"


def test_cancelled_order_is_terminal(api, settings, pg):
    _, _, _, utm = user_with_click(api)
    row, sn = order_row(utm=utm, order_status="CANCELLED")
    sync(settings, pg, [row])
    row["orders"][0]["order_status"] = "COMPLETED"
    res = sync(settings, pg, [row])
    assert fetch(pg, sn)["status"] == "CANCELLED" and res.status_conflicts == [(sn, "CANCELLED", "COMPLETED")]


def test_completed_without_a_time_gets_first_seen_time_and_keeps_it(api, settings, pg):
    from datetime import UTC, datetime
    t1, t2 = datetime(2026, 12, 1, tzinfo=UTC), datetime(2026, 12, 9, tzinfo=UTC)
    _, _, _, utm = user_with_click(api)
    row, sn = order_row(utm=utm, order_status="COMPLETED")
    OrderSync(settings, pg, FakeClient([row]), clock=lambda: t1).run(60)
    OrderSync(settings, pg, FakeClient([row]), clock=lambda: t2).run(60)
    assert fetch(pg, sn)["completed_at"] == t1


def test_rows_with_the_same_order_sn_are_merged_not_overwritten(api, settings, pg):
    uid, _, _, utm = user_with_click(api)
    r1, sn = order_row(utm=utm, commission=100_000_000)
    r2, _ = order_row(sn=sn, utm="", commission=50_000_000)
    res = sync(settings, pg, [r1, r2])
    o = fetch(pg, sn)
    assert res.rows == 1 and res.created == 1 and o["commission_micro"] == 150_000_000 and o["user_id"] == uid
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM shopee_order_items WHERE order_id = :i"), {"i": o["id"]}).scalar_one() == 2


def test_orphan_is_reattributed_when_the_data_arrives_late(api, settings, pg):
    uid, _, click_id, utm = user_with_click(api)
    row, sn = order_row(utm=subid.encode("u", uid, click_id + 10_000_000, SECRET))   # click chưa tồn tại lúc này
    sync(settings, pg, [row])
    assert fetch(pg, sn)["user_id"] is None and orphan(pg, sn) == "click_not_found"
    row["utm_content"] = utm                                 # Shopee trả lại utm đúng ở lần sync sau
    res = sync(settings, pg, [row])
    o = fetch(pg, sn)
    assert res.reattributed == 1 and o["user_id"] == uid and o["click_id"] == click_id and orphan(pg, sn) is None


def test_one_bad_order_does_not_sink_the_batch_and_marks_partial(api, settings, pg):
    _, _, _, utm = user_with_click(api)
    good, sg = order_row(utm=utm)
    bad, sb = order_row(utm="")
    bad["orders"][0]["items"][0]["item_name"] = "x"
    bad["junk"] = "\u0000"                                  # jsonb từ chối NUL: lỗi DB riêng của đơn này
    res = sync(settings, pg, [bad, good])
    assert res.errors == 1 and res.result == "partial" and fetch(pg, sg)["order_sn"] == sg
    with pg.connect() as c:
        assert c.execute(text("SELECT count(*) FROM shopee_orders WHERE order_sn = :s"), {"s": sb}).scalar_one() == 0
        assert c.execute(text("SELECT result FROM sync_runs WHERE kind = 'orders' ORDER BY id DESC LIMIT 1")).scalar_one() == "partial"


def test_concurrent_sync_is_skipped_without_a_run_row(settings, pg):
    holder = pg.connect()
    try:
        assert orders_repo.try_lock(holder)
        with pg.connect() as c:
            before = c.execute(text("SELECT count(*) FROM sync_runs")).scalar_one()
        res = sync(settings, pg, [order_row()[0]])
        with pg.connect() as c:
            after = c.execute(text("SELECT count(*) FROM sync_runs")).scalar_one()
        assert res.result == "skipped" and before == after
    finally:
        orders_repo.unlock(holder)
        holder.close()
    assert sync(settings, pg, []).result == "ok"             # khóa đã nhả: chạy được lại


def test_unexpected_client_error_marks_run_failed_and_propagates(settings, pg):
    with pytest.raises(RuntimeError):
        OrderSync(settings, pg, FakeClient(error=RuntimeError("boom"))).run(60)
    with pg.connect() as c:
        assert c.execute(text("SELECT result FROM sync_runs WHERE kind = 'orders' ORDER BY id DESC LIMIT 1")).scalar_one() == "failed"


@pytest.mark.parametrize("days", [0, -5, 367, 100000])
def test_days_out_of_range_is_rejected(settings, pg, days):
    with pytest.raises(ConfigError):
        sync_days = OrderSync(settings, pg, FakeClient())
        sync_days.run(days)


def test_worker_cli_reports_config_errors_cleanly(monkeypatch, capsys):
    from app import main_worker
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("SUBID_SECRET", "")
    assert main_worker.main(["sync-once"]) == 2
    assert "SUBID_SECRET" in capsys.readouterr().err
    monkeypatch.setenv("SUBID_SECRET", SECRET)
    assert main_worker.main(["sync-once", "--days", "0"]) == 2
    assert "days" in capsys.readouterr().err
