"""store.py (SQLite cũ). Sẽ bị thay bằng repository Postgres ở bước 8."""
import store


def test_save_and_get_target(db):
    db.save_link("a1", "http://t/1", "http://p/1", 1, 2, "n", "kw")
    row = db.get_target("a1")
    assert row["target"] == "http://t/1" and row["item_id"] == 1 and row["keyword"] == "kw"
    assert db.get_target("nope") is None


def test_same_sub_id_overwrites_target(db):
    """Audit #1: sub_id trùng ghi đè đích. Đây là hành vi HIỆN TẠI, sẽ đổi ở bước 9."""
    db.save_link("api", "http://t/first")
    db.save_link("api", "http://t/second")
    assert db.get_target("api")["target"] == "http://t/second"


def test_click_log_truncates_ua_and_referer(db):
    db.save_link("a1", "http://t")
    db.log_click("a1", "iphash", "u" * 500, "r" * 500)
    with store._conn() as c:
        row = c.execute("SELECT ua, referer FROM clicks").fetchone()
    assert len(row["ua"]) == 300 and len(row["referer"]) == 300


def test_stats_counts_window_and_orders_by_clicks(db):
    db.save_link("a", "t"); db.save_link("b", "t")
    for _ in range(3):
        db.log_click("a")
    db.log_click("b")
    st = db.stats(7)
    assert st["links_issued"] == 2 and st["clicks_total"] == 4
    assert [r["sub_id"] for r in st["by_link"]] == ["a", "b"]
    assert st["by_link"][0]["clicks"] == 3


def test_stats_excludes_old_clicks(db):
    db.save_link("a", "t")
    db.log_click("a")
    with store._conn() as c:
        c.execute("UPDATE clicks SET ts = ts - 10*86400")
    st = db.stats(7)
    assert st["clicks_total"] == 0 and st["by_link"][0]["clicks"] == 0


def test_link_without_clicks_is_listed(db):
    db.save_link("lonely", "t")
    assert db.stats(7)["by_link"][0]["last_click"] is None
