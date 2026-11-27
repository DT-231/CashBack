import pytest

import feed_search as fs


@pytest.mark.parametrize("raw,expected", [
    ("690.000", 690000), ("259,000", 259000), ("8%", 8), ("0,08", 0.08),
    ("1.250.000", 1250000), ("1,250,000", 1250000), ("259,5", 259.5),
    ("", 0), (None, 0), ("abc", 0),
])
def test_num_vn_and_us_formats(raw, expected):
    assert fs._num(raw) == expected


def test_strip_accents_and_tokens():
    assert fs._strip_accents("Đồ Nồi Chiên") == "do noi chien"
    assert fs._tokens("a Nồi-chiên 6L") == ["noi", "chien", "6l"]   # bỏ token 1 ký tự


def test_pick_matches_columns_loosely():
    row = {"Commission Rate (%)": "8", "ID Sản phẩm": "9"}
    assert fs._pick(row, fs.COLS["comm_rate"]) == "8"
    assert fs._pick(row, fs.COLS["item_id"]) == "9"
    assert fs._pick({"x": "1"}, fs.COLS["name"]) is None


def test_record_extracts_ids_from_url():
    r = fs._record({"product_name": "A", "product_link": "https://shopee.vn/a-i.7001.900001"})
    assert (r["shop_id"], r["item_id"]) == (7001, 900001)
    assert fs._record({"price": "1"}) is None   # thiếu tên


def test_record_comm_rate_fraction_is_scaled_to_percent():
    """Audit #8: <1 được coi là phân số. 0,5% thật sẽ thành 50%. Khóa hành vi hiện tại."""
    assert fs._record({"product_name": "A", "commission_rate": "0,08"})["comm_rate"] == 8.0
    assert fs._record({"product_name": "A", "commission_rate": "0,5"})["comm_rate"] == 50.0
    assert fs._record({"product_name": "A", "commission_rate": "8%"})["comm_rate"] == 8.0


def test_search_ranks_exact_substring_first_then_sales(feed_file):
    r = fs.search("noi chien")
    assert r["ok"] and r["items"][0]["name"].startswith("Nồi chiên")
    assert r["items"][0]["match_score"] == 1.0


def test_search_no_match(feed_file):
    r = fs.search("zzzzzz qqqqq")
    assert not r["ok"] and "không có sản phẩm" in r["error"]


def test_search_without_feed_file_env(monkeypatch):
    monkeypatch.delenv("FEED_FILE", raising=False)
    assert "FEED_FILE" in fs.search("x")["error"]


def test_search_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("FEED_FILE", str(tmp_path / "nope.csv"))
    assert "feed rỗng" in fs.search("x")["error"]


def test_json_feed_and_cache_invalidation(tmp_path, monkeypatch):
    p = tmp_path / "f.json"
    p.write_text('{"items":[{"item_id":1,"shop_id":2,"name":"Ghế gaming","price":"1.000"}]}', encoding="utf-8")
    monkeypatch.setenv("FEED_FILE", str(p))
    assert fs.search("ghe gaming")["items"][0]["price"] == 1000
    p.write_text('[{"item_id":3,"shop_id":4,"name":"Bàn học"}]', encoding="utf-8")
    import os
    os.utime(p, (p.stat().st_atime + 5, p.stat().st_mtime + 5))
    assert fs.search("ban hoc")["items"][0]["item_id"] == 3


def test_limit_is_clamped(feed_file):
    assert len(fs.search("inox chao noi", limit=0)["items"]) == 1
