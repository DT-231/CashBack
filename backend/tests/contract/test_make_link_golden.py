"""Khóa hành vi sinh link affiliate (đã verify thật với Shopee ngày 2026-11-26). KHÔNG được đổi."""
import pytest

from app.modules.links.affiliate_link import LinkConfig, LinkError, link_for_item, make_link, normalize_sub_id, \
    parse_product_url

CFG = LinkConfig(aff_id="17300000000")
BASE = ("https://shopee.vn/universal-link/product/{s}/{i}?utm_source=an_17300000000"
        "&utm_medium=affiliates&utm_campaign=-&utm_content={c}")

GOLDEN = [
    ("https://shopee.vn/product/1020310358/24088489429", "fb01", "fb01----", 1020310358, 24088489429),
    ("https://shopee.vn/Ten-SP-i.5501.100001?sp_atk=abc", "fb01-3", "fb01-3---", 5501, 100001),
    ("https://shopee.vn/product/5502/100002", "tt09", "tt09----", 5502, 100002),
    ("https://shopee.vn/product/7/8", "1u-3f-23zt-a7q-", "1u-3f-23zt-a7q-", 7, 8),
    ("https://shopee.vn/product/7/8", "", "0----", 7, 8),
]


@pytest.mark.parametrize("url,sub,content,s,i", GOLDEN)
def test_golden_links(url, sub, content, s, i):
    assert make_link(url, sub, CFG) == BASE.format(s=s, i=i, c=content)


def test_parse_product_url():
    assert parse_product_url("https://shopee.vn/product/1/2") == (1, 2)
    assert parse_product_url("https://shopee.vn/x-y-i.3.4?z=1") == (3, 4)
    assert parse_product_url("https://example.com/abc") is None
    assert parse_product_url("") is None


def test_missing_aff_id_and_url():
    with pytest.raises(LinkError):
        make_link("https://shopee.vn/product/1/2", "x", LinkConfig(aff_id=""))
    with pytest.raises(LinkError):
        make_link("", "x", CFG)


def test_pad_disabled_keeps_sub_verbatim():
    assert normalize_sub_id("a b_c", pad=False) == "a-b-c"
    assert normalize_sub_id("fb01-1-2-3-4") == "fb01-1-2-3-4"
    assert normalize_sub_id(None) == "0----"


def test_campaign_override_and_url_quoting():
    link = make_link("https://shopee.vn/product/1/2", "x", LinkConfig(aff_id="1", campaign="sale 11/11"))
    assert "utm_campaign=sale%2011%2F11" in link


def test_origin_template_and_passthrough_template():
    cfg = LinkConfig(aff_id="9", template="https://go.example/?u={origin}&s={sub_id}&a={aff_id}")
    assert make_link("https://shopee.vn/product/1/2", "k", cfg) == \
        "https://go.example/?u=https%3A%2F%2Fshopee.vn%2Fproduct%2F1%2F2&s=k----&a=9"
    cfg = LinkConfig(aff_id="9", template="https://x.example/{plain}")
    out = make_link("https://shopee.vn/p?a=1", "k", cfg)
    assert out.startswith("https://shopee.vn/p?a=1&utm_source=an_9&utm_medium=affiliates")


def test_template_needing_ids_rejects_unparsable_url():
    with pytest.raises(LinkError, match="shop_id"):
        make_link("https://example.com/x", "k", CFG)


def test_link_for_item():
    r = link_for_item(2, 1, "fb01-1", CFG)
    assert r["product_url"] == "https://shopee.vn/product/1/2" and r["sub_id"] == "fb01-1---"
    assert r["aff_link"].endswith("utm_content=fb01-1---")
