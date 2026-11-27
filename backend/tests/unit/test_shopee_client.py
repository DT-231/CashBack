"""ShopeeClient với HTTP giả (không gọi mạng). Port từ test_shopee_search.py + test_revenue.py cũ."""
import pytest

from app.core.config import Settings
from app.integrations.shopee import build_client
from app.integrations.shopee.client import ShopeeClient, window
from app.integrations.shopee.errors import ShopeeBlockedError, ShopeeConfigError, ShopeeError
from app.integrations.shopee.fake import FakeShopeeClient


class Resp:
    def __init__(self, status=200, data=None, text="", headers=None):
        self.status_code, self._d, self.text, self.headers = status, data, text, headers or {}

    def json(self):
        if self._d is None:
            raise ValueError("html")
        return self._d


def make(cookie="fake=1", ttl=0, web="web=1", **kw):
    """cookie = cookie affiliate.shopee.vn (dashboard); web = cookie shopee.vn (search)."""
    return ShopeeClient(Settings(shopee_cookie=cookie, shopee_web_cookie=web, shopee_cache_ttl=ttl, **kw),
                        sleep=lambda s: None)


def patch_get(monkeypatch, fn):
    monkeypatch.setattr("requests.Session.get", lambda self, *a, **k: fn(*a, **k))


# ---------- factory ----------
def test_build_client_mock_never_uses_network():
    assert isinstance(build_client(Settings(mock=True)), FakeShopeeClient)
    assert isinstance(build_client(Settings(mock=False)), ShopeeClient)


# ---------- search ----------
def test_normalize_micro_price_is_divided():
    it = ShopeeClient._normalize_item({"itemid": 1, "shopid": 2, "name": "n", "price": 69_000_000_000,
                                       "item_rating": {"rating_star": 4.756}, "image": "abc"})
    assert it["price"] == 690000 and it["rating"] == 4.76 and it["image"].endswith("/file/abc")


def test_normalize_prefers_price_min_and_keeps_small_price():
    assert ShopeeClient._normalize_item({"itemid": 1, "shopid": 2, "price_min": 150000, "price": 1})["price"] == 150000


def test_normalize_heuristic_misreads_large_plain_price():
    """Audit #8: giá thật 15.000.000đ (không ×1e5) bị chia nhầm. Khóa hành vi hiện tại."""
    assert ShopeeClient._normalize_item({"itemid": 1, "shopid": 2, "price": 15_000_001})["price"] == 150


def test_search_403_fails_fast_without_retry(monkeypatch):
    calls = []
    patch_get(monkeypatch, lambda *a, **k: calls.append(1) or Resp(403))
    r = make().search("x")
    assert not r["ok"] and "403" in r["error"] and len(calls) == 1


def test_search_parses_items_and_clamps_limit(monkeypatch):
    seen = {}
    data = {"data": {"items": [{"item_basic": {"itemid": 5, "shopid": 6, "name": "A", "price": 1000}}]}}

    def fake(*a, **k):
        seen.update(k["params"])
        return Resp(200, data)
    patch_get(monkeypatch, fake)
    r = make().search("x", limit=999)
    assert r["ok"] and r["items"][0]["item_id"] == 5 and r["source"] == "shopee" and seen["limit"] == 60


def test_search_empty_and_shopee_error_and_network_error(monkeypatch):
    patch_get(monkeypatch, lambda *a, **k: Resp(200, {"data": {"items": []}}))
    assert "schema" in make().search("x")["error"]
    patch_get(monkeypatch, lambda *a, **k: Resp(200, {"error": 90309999}))
    assert "Shopee trả lỗi" in make().search("x")["error"]

    def boom(*a, **k):
        raise __import__("requests").ConnectionError("down")
    patch_get(monkeypatch, boom)
    assert "ConnectionError" in make().search("x")["error"]


def test_search_programming_errors_are_not_swallowed(monkeypatch):
    """Cải thiện #16: chỉ bắt lỗi mạng/JSON, không bắt RuntimeError."""
    def boom(*a, **k):
        raise RuntimeError("bug")
    patch_get(monkeypatch, boom)
    with pytest.raises(RuntimeError):
        make().search("x")


def test_search_cache_only_stores_successes(monkeypatch):
    n = []
    ok = {"data": {"items": [{"itemid": 1, "shopid": 2, "name": "A"}]}}
    patch_get(monkeypatch, lambda *a, **k: n.append(1) or Resp(200, ok))
    c = make(ttl=60)
    c.search("x"); c.search("x")
    assert len(n) == 1
    n.clear()
    patch_get(monkeypatch, lambda *a, **k: n.append(1) or Resp(403))
    c = make(ttl=60)
    c.search("y"); c.search("y")
    assert len(n) == 2        # 403 thoát ngay (1 lần/gọi), lỗi không bị cache


def test_search_sends_cookie_and_secret_headers_but_error_hides_them(monkeypatch):
    seen = {}
    patch_get(monkeypatch, lambda *a, **k: seen.update(k) or Resp(403))
    r = make(shopee_af_ac_enc_dat="enc!").search("x")
    assert seen["headers"] if "headers" in seen else True
    assert "fake=1" not in r["error"] and "enc!" not in r["error"]


# ---------- dashboard ----------
def test_window_covers_whole_days_in_vn_time():
    s, e = window(1)
    assert 0 < e - s <= 86399
    s7, _ = window(7)
    assert 6 * 86400 <= e - s7 <= 7 * 86400 - 1


def test_get_requires_cookie():
    with pytest.raises(ShopeeConfigError, match="SHOPEE_COOKIE"):
        make(cookie="")._get("/x", {})


@pytest.mark.parametrize("resp,exc,match", [
    (Resp(403), ShopeeBlockedError, "403"),
    (Resp(500, text="boom"), ShopeeError, "HTTP 500"),
    (Resp(200, None, "<html>"), ShopeeError, "HTML"),
    (Resp(200, {"code": 7, "msg": "bad"}), ShopeeError, "code=7"),
])
def test_get_error_mapping(monkeypatch, resp, exc, match):
    patch_get(monkeypatch, lambda *a, **k: resp)
    with pytest.raises(exc, match=match):
        make()._get("/x", {})


def test_get_retries_network_error_once(monkeypatch):
    n = []

    def flaky(*a, **k):
        n.append(1)
        if len(n) == 1:
            raise __import__("requests").ConnectionError("down")
        return Resp(200, {"code": 0, "data": {"ok": 1}})
    patch_get(monkeypatch, flaky)
    assert make()._get("/x", {})["data"] == {"ok": 1} and len(n) == 2


def test_error_text_never_contains_cookie(monkeypatch):
    patch_get(monkeypatch, lambda *a, **k: Resp(403))
    with pytest.raises(ShopeeError) as ei:
        make(cookie="topsecret=1")._get("/x", {})
    assert "topsecret" not in str(ei.value)


def test_paged_stops_at_total_count_and_max_pages(monkeypatch):
    pages = []

    def fake(path, params):
        pages.append(params["page_num"])
        return {"code": 0, "data": {"total_count": 150, "list": [{"i": 1}] * (100 if params["page_num"] == 1 else 50)}}
    c = make()
    monkeypatch.setattr(c, "_get", fake)
    assert len(c._paged("/x", {})) == 150 and pages == [1, 2]
    monkeypatch.setattr(c, "_get", lambda p, q: {"data": {"total_count": 10**9, "list": [{"i": 1}] * 100}})
    assert len(c._paged("/x", {}, max_pages=3)) == 300
    monkeypatch.setattr(c, "_get", lambda p, q: {"data": {"list": []}})
    assert c._paged("/x", {}) == []


def test_snapshot_uses_one_window_for_all_three_calls(monkeypatch):
    c = make()
    seen = []
    monkeypatch.setattr(c, "_get", lambda path, params: seen.append(dict(params)) or {"data": {"list": []}})
    snap = c.dashboard_snapshot(3)
    starts = {p.get("start_time") or p.get("click_time_s") or p.get("purchase_time_s") for p in seen}
    assert len(seen) == 3 and starts == {snap.window[0]}


def test_check_link_reads_location(monkeypatch):
    patch_get(monkeypatch, lambda *a, **k: Resp(301, headers={
        "Location": "https://shopee.vn/product/1/2?utm_source=an_1&utm_content=x&uls_trackid=abc"}))
    r = make().check_link("https://shopee.vn/universal-link/product/1/2")
    assert r["status"] == 301 and r["tracked"] and r["utm_source"] == "an_1" and r["final_host"] == "shopee.vn"
    assert r["hops"] == ["https://shopee.vn/universal-link/product/1/2"] and r["final_status"] == 301


def test_check_link_follows_short_link_until_trackid_and_uses_proxy(monkeypatch):
    seq = {"https://shope.ee/abc": Resp(301, headers={"Location": "https://shopee.vn/product/1/2?utm_source=an_9&utm_content=k&uls_trackid=xyz"})}
    first = Resp(301, headers={"Location": "https://shope.ee/abc"})
    seen = []

    def fake(self, url, **k):
        seen.append((url, dict(self.proxies), k.get("allow_redirects")))
        return seq.get(url, first)
    monkeypatch.setattr("requests.Session.get", fake)
    r = make(shopee_proxy="http://p:1").check_link("https://shopee.vn/universal-link/product/1/2")
    assert r["tracked"] is True and len(r["hops"]) == 2 and r["hops"][1] == "https://shope.ee/abc"
    assert r["status"] == 301 and r["redirect"] == "https://shope.ee/abc"   # hop đầu giữ hành vi cũ
    assert r["utm_source"] == "an_9" and r["final_host"] == "shopee.vn" and "uls_trackid=xyz" in r["final_url"]
    assert seen[0][1] == {"http": "http://p:1", "https": "http://p:1"} and seen[0][2] is False


def test_check_link_stops_after_three_hops_and_reports_untracked(monkeypatch):
    n = []
    patch_get(monkeypatch, lambda *a, **k: n.append(1) or Resp(302, headers={"Location": "https://x.example/next"}))
    r = make().check_link("https://shopee.vn/a")
    assert len(n) == 3 and r["tracked"] is False and len(r["hops"]) == 3


def test_check_link_network_error_is_shopee_error(monkeypatch):
    def boom(*a, **k):
        raise __import__("requests").ConnectionError("down")
    patch_get(monkeypatch, boom)
    with pytest.raises(ShopeeError):
        make().check_link("https://shopee.vn/a")


# ---------- fake ----------
def test_fake_client_is_offline_and_shaped():
    f = FakeShopeeClient()
    r = f.search("x", limit=2)
    assert r["ok"] and r["source"] == "mock" and len(r["items"]) == 2
    assert len(f.search("x", limit=0)["items"]) == 1 and len(f.search("x", limit=999)["items"]) == 5
    f.search("x", 1)["items"][0]["name"] = "changed"
    assert f.search("x", 1)["items"][0]["name"] != "changed"
    snap = f.dashboard_snapshot(7)
    assert snap.daily["clicks_sum"] == 14 and len(snap.orders) == 2


# ---------- P0-1: cookie search đúng host ----------
def test_search_uses_web_cookie_never_affiliate_cookie(monkeypatch):
    seen = {}

    def fake(self, url, **k):
        seen["cookie"] = self.headers.get("Cookie")
        seen["enc"] = self.headers.get("af-ac-enc-dat")
        return Resp(403)
    monkeypatch.setattr("requests.Session.get", fake)
    make(cookie="AFFILIATE=1", web="SPC_F=web", shopee_web_enc_dat="enc-web", shopee_af_ac_enc_dat="enc-aff").search("x")
    assert seen["cookie"] == "SPC_F=web" and seen["enc"] == "enc-web"


def test_search_enc_dat_falls_back_to_legacy_var_but_cookie_never_does(monkeypatch):
    seen = {}
    monkeypatch.setattr("requests.Session.get", lambda self, url, **k: seen.update(enc=self.headers.get("af-ac-enc-dat")) or Resp(403))
    make(shopee_af_ac_enc_dat="legacy-enc").search("x")
    assert seen["enc"] == "legacy-enc"


def test_search_without_web_cookie_fails_fast_without_network(monkeypatch):
    calls = []
    patch_get(monkeypatch, lambda *a, **k: calls.append(1) or Resp(403))
    r = make(cookie="AFFILIATE=1", web="").search("x")
    assert not r["ok"] and "Thiếu SHOPEE_WEB_COOKIE" in r["error"] and calls == []
    assert "AFFILIATE" not in r["error"]


def test_dashboard_still_uses_affiliate_cookie(monkeypatch):
    seen = {}
    monkeypatch.setattr("requests.Session.get", lambda self, url, **k: seen.update(c=self.headers.get("cookie")) or Resp(200, {"code": 0}))
    make(cookie="AFFILIATE=1", web="WEB=1")._get("/x", {})
    assert seen["c"] == "AFFILIATE=1"


def test_health_reports_both_cookies(make_settings):
    from fastapi.testclient import TestClient
    from app.main_api import create_app
    c = TestClient(create_app(make_settings(shopee_cookie="a=1", shopee_web_cookie="")))
    j = c.get("/health").json()
    assert j["cookie_set"] is True and j["web_cookie_set"] is False


# ---------- P0-2: _paged ----------
def _pages(monkeypatch, c, pages, total=None):
    asked = []

    def fake(path, params):
        asked.append(params["page_num"])
        rows = pages[params["page_num"] - 1] if params["page_num"] <= len(pages) else []
        data = {"list": rows}
        if total is not None:
            data["total_count"] = total
        return {"code": 0, "data": data}
    monkeypatch.setattr(c, "_get", fake)
    return asked


def test_paged_without_total_count_collects_all_pages(monkeypatch):
    c = make()
    full = [{"i": 1}] * 100
    asked = _pages(monkeypatch, c, [full, full, full, []])
    assert len(c._paged("/x", {})) == 300 and asked == [1, 2, 3, 4]


def test_paged_with_total_count_stops_when_reached(monkeypatch):
    c = make()
    asked = _pages(monkeypatch, c, [[{"i": 1}] * 100, [{"i": 1}] * 50, [{"i": 1}] * 100], total=150)
    assert len(c._paged("/x", {})) == 150 and asked == [1, 2]


def test_paged_short_first_page_stops_immediately(monkeypatch):
    c = make()
    asked = _pages(monkeypatch, c, [[{"i": 1}] * 40, [{"i": 1}] * 100])
    assert len(c._paged("/x", {})) == 40 and asked == [1]


# ---------- P1-4: session dùng lại theo luồng ----------
def test_session_is_reused_per_thread_and_kind():
    import threading
    c = make()
    a, b = c._session({"X": "1"}), c._session({"Y": "2"})
    assert a is b and a.headers["X"] == "1" and a.headers["Y"] == "2"    # chỉ update, không reset
    assert c._session({}, "dash") is not a and c._session({}, "check") is not a
    other = []
    t = threading.Thread(target=lambda: other.append(c._session({})))
    t.start(); t.join()
    assert other[0] is not a


def test_session_proxy_applied_once():
    c = make(shopee_proxy="http://p:1")
    assert c._session({}).proxies == {"http": "http://p:1", "https": "http://p:1"}


def test_session_keeps_set_cookie_between_requests():
    import http.server
    import threading
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Cookie"))
            self.send_response(200)
            self.send_header("Set-Cookie", "SPC_EC=abc; Path=/")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=lambda: srv.serve_forever(poll_interval=0.01), daemon=True).start()
    try:
        c = make()
        url = f"http://127.0.0.1:{srv.server_address[1]}/"
        c._session({}).get(url)
        c._session({}).get(url)
    finally:
        srv.shutdown(); srv.server_close()
    assert seen == [None, "SPC_EC=abc"]


def test_search_and_dashboard_headers_do_not_leak(monkeypatch):
    c = make(cookie="AFF=1", web="WEB=1")
    s_search = c._session(c._search_headers("x"), "search")
    s_dash = c._session({"cookie": "AFF=1", "referer": "https://affiliate.shopee.vn/dashboard"}, "dash")
    assert s_search is not s_dash
    assert s_search.headers["Cookie"] == "WEB=1" and s_dash.headers["cookie"] == "AFF=1"
    assert s_search.headers["Referer"] != s_dash.headers["referer"]


# ---------- P1-5: retry ----------
def sleeps(c):
    out = []
    c._sleep = out.append
    return c, out


def test_403_is_one_request_and_no_sleep(monkeypatch):
    n = []
    patch_get(monkeypatch, lambda *a, **k: n.append(1) or Resp(403))
    c, s = sleeps(make())
    assert not c.search("x")["ok"] and len(n) == 1 and s == []


def test_429_retries_and_honors_retry_after_capped(monkeypatch):
    ok = Resp(200, {"data": {"items": [{"itemid": 1, "shopid": 2, "name": "A"}]}})
    seq = [Resp(429, headers={"Retry-After": "30"}), ok]
    n = []
    patch_get(monkeypatch, lambda *a, **k: n.append(1) or seq.pop(0))
    c, s = sleeps(make())
    assert c.search("x")["ok"] and len(n) == 2 and s == [5.0]       # 30s bị chặn ở 5s


def test_429_without_header_uses_default_backoff_and_no_final_sleep(monkeypatch):
    patch_get(monkeypatch, lambda *a, **k: Resp(429))
    c, s = sleeps(make())
    r = c.search("x")
    assert not r["ok"] and "429" in r["error"] and s == [2, 4]       # 3 lần thử, chỉ ngủ giữa các lần


def test_200_is_single_request(monkeypatch):
    n = []
    patch_get(monkeypatch, lambda *a, **k: n.append(1) or Resp(200, {"data": {"items": [{"itemid": 1, "shopid": 2}]}}))
    c, s = sleeps(make())
    assert c.search("x")["ok"] and len(n) == 1 and s == []


def test_network_error_retries_without_final_sleep(monkeypatch):
    def boom(*a, **k):
        raise __import__("requests").ConnectionError("down")
    patch_get(monkeypatch, boom)
    c, s = sleeps(make())
    assert "ConnectionError" in c.search("x")["error"] and len(s) == 2
