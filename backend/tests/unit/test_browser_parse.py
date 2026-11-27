from app.integrations.shopee.browser import parse_links, search
from app.core.config import Settings


def test_parse_links_dedups_and_reads_price():
    raw = [{"href": "https://shopee.vn/a-i.7.9", "text": "Nồi A\n₫ 690.000"},
           {"href": "https://shopee.vn/a-i.7.9", "text": "dup"},
           {"href": "https://shopee.vn/other", "text": "x"},
           {"href": "https://shopee.vn/b-i.8.10", "text": ""}]
    items = parse_links(raw, 10)
    assert [i["item_id"] for i in items] == [9, 10]
    assert items[0]["price"] == 690000 and items[1]["name"] == "item 10"
    assert len(parse_links(raw, 1)) == 1


def test_search_without_playwright_reports_error(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("playwright"):
            raise ImportError
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    r = search(Settings(), "x")
    assert not r["ok"] and "playwright" in r["error"]
