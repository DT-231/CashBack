import shopee_search as ss


def test_normalize_micro_price_is_divided():
    it = ss._normalize({"itemid": 1, "shopid": 2, "name": "n", "price": 69_000_000_000,
                        "item_rating": {"rating_star": 4.756}, "image": "abc"})
    assert it["price"] == 690000 and it["rating"] == 4.76
    assert it["image"].endswith("/file/abc")


def test_normalize_prefers_price_min_and_keeps_small_price():
    it = ss._normalize({"itemid": 1, "shopid": 2, "price_min": 150000, "price": 1})
    assert it["price"] == 150000


def test_normalize_heuristic_misreads_large_plain_price():
    """Audit #8: giá thật 15.000.000đ (không nhân 1e5) bị chia nhầm thành 150. Khóa hành vi hiện tại."""
    assert ss._normalize({"itemid": 1, "shopid": 2, "price": 15_000_001})["price"] == 150


def test_mock_search_and_limit_clamp():
    r = ss.search("x", limit=2)
    assert r["ok"] and r["source"] == "mock" and len(r["items"]) == 2
    assert len(ss.search("x", limit=0)["items"]) == 1       # tối thiểu 1
    assert len(ss.search("x", limit=999)["items"]) == 5     # chỉ có 5 mock


def test_mock_items_are_copies():
    ss.search("x", limit=1)["items"][0]["name"] = "changed"
    assert ss.search("x", limit=1)["items"][0]["name"] != "changed"


class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._d = status, data or {}

    def json(self):
        return self._d


def test_live_path_403_retries_then_fails(monkeypatch):
    monkeypatch.setenv("MOCK", "0")
    calls = []
    monkeypatch.setattr(ss.requests, "get", lambda *a, **k: calls.append(1) or _Resp(403))
    monkeypatch.setattr(ss.time, "sleep", lambda s: None)
    r = ss.search("x")
    assert not r["ok"] and "403" in r["error"] and len(calls) == 3


def test_live_path_parses_items(monkeypatch):
    monkeypatch.setenv("MOCK", "0")
    data = {"data": {"items": [{"item_basic": {"itemid": 5, "shopid": 6, "name": "A", "price": 1000}}]}}
    monkeypatch.setattr(ss.requests, "get", lambda *a, **k: _Resp(200, data))
    r = ss.search("x")
    assert r["ok"] and r["items"][0]["item_id"] == 5 and r["source"] == "shopee"


def test_live_path_empty_is_failure(monkeypatch):
    monkeypatch.setenv("MOCK", "0")
    monkeypatch.setattr(ss.requests, "get", lambda *a, **k: _Resp(200, {"data": {"items": []}}))
    r = ss.search("x")
    assert not r["ok"] and "schema" in r["error"]


def test_live_path_exception_is_swallowed_into_error(monkeypatch):
    """Audit #16: mọi Exception bị gói thành chuỗi."""
    monkeypatch.setenv("MOCK", "0")
    def boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(ss.requests, "get", boom)
    monkeypatch.setattr(ss.time, "sleep", lambda s: None)
    r = ss.search("x")
    assert not r["ok"] and "RuntimeError: kaboom" in r["error"]
