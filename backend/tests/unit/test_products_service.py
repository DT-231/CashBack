from app.core.config import Settings
from app.integrations.shopee.fake import FakeShopeeClient
from app.modules.products.service import ProductSearch


class Boom:
    def search(self, *a, **k):
        return {"ok": False, "items": [], "error": "HTTP 403", "source": "shopee"}


def ps(shopee=None, **kw):
    return ProductSearch(Settings(mock=True, **kw), shopee or FakeShopeeClient())


def test_auto_without_feed_skips_feed_and_uses_api():
    r = ps().search("x", 2)
    assert r["engine"] == "api" and r["source"] == "mock" and len(r["items"]) == 2
    assert r["tried"] == ["feed:bỏ qua (chưa đặt FEED_FILE)", "api:ok"]


def test_auto_prefers_feed(feed_file):
    r = ps(feed_file=str(feed_file)).search("ke chen", 3)
    assert r["engine"] == "feed" and r["items"][0]["name"] == "Kệ chén inox 2 tầng"


def test_falls_back_when_feed_has_no_match(feed_file):
    r = ps(feed_file=str(feed_file)).search("zzzzzz", 3)
    assert r["engine"] == "api" and r["tried"][0].startswith("feed:feed không có")


def test_hard_engine_does_not_fall_back():
    r = ps(Boom()).search("x", engine="api")
    assert not r["ok"] and r["engine"] == "api" and r["tried"] == ["api:HTTP 403"]


def test_hard_engine_feed_without_file_reports_all_failed():
    r = ps().search("x", engine="feed")
    assert not r["ok"] and r["engine"] is None and r["error"] == "mọi nguồn đều fail"


def test_all_sources_fail_message():
    r = ps(Boom()).search("x")
    assert r["error"] == "mọi nguồn đều fail" and r["tried"][-1].startswith("browser:")


def test_engine_from_settings_and_unknown_engine_falls_back():
    assert ps(search_engine="API").search("x")["engine"] == "api"
    assert ps().search("x", engine="weird")["engine"] == "api"


def test_browser_is_disabled_under_mock():
    r = ps().search("x", engine="browser")
    assert not r["ok"] and "MOCK" in r["error"]
