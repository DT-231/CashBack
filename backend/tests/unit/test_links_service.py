from app.modules.links.service import UserLinkService
from app.modules.links.errors import InvalidLink
import pytest


@pytest.mark.parametrize("url", [
    "https://evil.com/product/1/2", "https://shopee.vn.evil.com/product/1/2",
    "https://shopee.vn@evil.com/product/1/2", "https://s.shopee.vn/abc",
])
def test_rejects_unsupported_hosts(url):
    with pytest.raises(InvalidLink):
        UserLinkService._parse_url(url)


def test_parses_supported_product_url_forms():
    assert UserLinkService._parse_url("https://shopee.vn/Ten-SP-i.5501.100001?sp_atk=abc") == (5501, 100001)
    assert UserLinkService._parse_url("http://www.shopee.vn/product/5501/100001") == (5501, 100001)


def test_create_uses_repository_and_reuses_existing_link(make_settings, monkeypatch):
    from contextlib import contextmanager
    from app.modules.links import service

    class Engine:
        @contextmanager
        def begin(self):
            yield object()

    state = {"link": None, "insertions": 0}
    monkeypatch.setattr(service.repository, "upsert_product", lambda *_: {"id": 9, "shop_id": 5501,
                                                                             "item_id": 100001, "name": None})
    monkeypatch.setattr(service.repository, "get_user_link", lambda *_: state["link"])

    def insert(_conn, user_id, product_id, code):
        state["insertions"] += 1
        state["link"] = {"id": 7, "code": code, "created_at": None}
        return True

    monkeypatch.setattr(service.repository, "insert_user_link", insert)
    svc = UserLinkService(make_settings(), Engine())
    first = svc.create(42, "https://shopee.vn/product/5501/100001")
    again = svc.create(42, "https://shopee.vn/any-i.5501.100001")
    assert first.code == again.code and state["insertions"] == 1
    assert "utm_source=an_17399999999" in first.direct_url
