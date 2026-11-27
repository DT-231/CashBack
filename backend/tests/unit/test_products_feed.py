import os

from app.modules.products import feed as fs
from app.modules.products.feed import FeedStore, search_feed


def S(path, kw, limit=10):
    return search_feed(FeedStore(), str(path) if path else "", kw, limit)


def test_strip_accents_and_tokens():
    assert fs.strip_accents("Đồ Nồi Chiên") == "do noi chien"
    assert fs.tokens("a Nồi-chiên 6L") == ["noi", "chien", "6l"]   # bỏ token 1 ký tự


def test_pick_matches_columns_loosely():
    row = {"Commission Rate (%)": "8", "ID Sản phẩm": "9"}
    assert fs.pick(row, fs.COLS["comm_rate"]) == "8"
    assert fs.pick(row, fs.COLS["item_id"]) == "9"
    assert fs.pick({"x": "1"}, fs.COLS["name"]) is None


def test_record_extracts_ids_from_url():
    r = fs.to_record({"product_name": "A", "product_link": "https://shopee.vn/a-i.7001.900001"})
    assert (r.shop_id, r.item_id) == (7001, 900001)
    assert fs.to_record({"price": "1"}) is None   # thiếu tên


def test_record_comm_rate_fraction_is_scaled_to_percent():
    """Audit #8: <1 được coi là phân số. 0,5% thật sẽ thành 50%. Khóa hành vi hiện tại."""
    rate = lambda v: fs.to_record({"product_name": "A", "commission_rate": v}).comm_rate  # noqa: E731
    assert rate("0,08") == 8.0 and rate("0,5") == 50.0 and rate("8%") == 8.0


def test_search_ranks_exact_substring_first(feed_file):
    r = S(feed_file, "noi chien")
    assert r["ok"] and r["items"][0]["name"].startswith("Nồi chiên") and r["items"][0]["match_score"] == 1.0


def test_search_no_match_missing_env_and_file(feed_file, tmp_path):
    assert "không có sản phẩm" in S(feed_file, "zzzzzz qqqqq")["error"]
    assert "FEED_FILE" in S("", "x")["error"]
    assert "feed rỗng" in S(tmp_path / "nope.csv", "x")["error"]


def test_json_feed_and_cache_invalidation(tmp_path):
    p = tmp_path / "f.json"
    p.write_text('{"items":[{"item_id":1,"shop_id":2,"name":"Ghế gaming","price":"1.000"}]}', encoding="utf-8")
    store = FeedStore()
    assert search_feed(store, str(p), "ghe gaming")["items"][0]["price"] == 1000
    p.write_text('[{"item_id":3,"shop_id":4,"name":"Bàn học"}]', encoding="utf-8")
    os.utime(p, (p.stat().st_atime + 5, p.stat().st_mtime + 5))
    assert search_feed(store, str(p), "ban hoc")["items"][0]["item_id"] == 3


def test_cache_reuses_rows_when_unchanged(feed_file):
    store = FeedStore()
    a = store.load(str(feed_file))
    assert store.load(str(feed_file)) is a


def test_limit_is_clamped(feed_file):
    assert len(S(feed_file, "inox chao noi", limit=0)["items"]) == 1
