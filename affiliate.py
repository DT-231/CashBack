"""Ghép link affiliate Shopee VN — format ĐÃ VERIFY từ dashboard thật (2026-11-26).

Lấy từ HAR của affiliate.shopee.vn (API batchCustomLink), link dài thật trả về:

  https://shopee.vn/universal-link/<slug>-i.<shop_id>.<item_id>
      ?utm_source=an_<affiliate_id>
      &utm_medium=affiliates
      &utm_campaign=<ten_chien_dich>
      &utm_content=<sub_id1>-<sub_id2>-<sub_id3>-<sub_id4>-<sub_id5>

Đã test thật: URL dạng dưới trả 301 -> shopee.vn/product/... GIỮ NGUYÊN toàn bộ utm
và Shopee tự thêm uls_trackid (nghĩa là đã vào hệ thống tracking của Shopee Affiliate).

  https://shopee.vn/universal-link/product/{shop_id}/{item_id}?utm_source=an_{aff_id}&utm_medium=affiliates&utm_campaign=-&utm_content=xxx----

Không cần slug sản phẩm, không cần API key. Chỉ cần affiliate_id + shop_id + item_id.
"""
import os
import re
from urllib.parse import quote, urlparse, parse_qsl, urlencode, urlunparse

# Template mặc định — khớp 100% format dashboard VN trả về.
DEFAULT_TEMPLATE = (
    "https://shopee.vn/universal-link/product/{shop_id}/{item_id}"
    "?utm_source=an_{aff_id}"
    "&utm_medium=affiliates"
    "&utm_campaign={campaign}"
    "&utm_content={sub_id}"
)

# Số đoạn sub_id mà Shopee VN tách trong utm_content (sub_id1..sub_id5).
SUB_ID_SLOTS = 5


def aff_id():
    return os.environ.get("SHOPEE_AFF_ID", "").strip()


def product_url(shop_id, item_id):
    return f"https://shopee.vn/product/{shop_id}/{item_id}"


def parse_product_url(url):
    """Nhận mọi dạng link sản phẩm, trả (shop_id, item_id) hoặc None."""
    if not url:
        return None
    path = url.split("?", 1)[0].split("#", 1)[0]
    m = re.search(r"/product/(\d+)/(\d+)", path)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"-i\.(\d+)\.(\d+)", path)  # dạng ...-i.123456.789012
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def normalize_sub_id(sub_id):
    """Đưa sub_id về đúng dạng utm_content: các đoạn ngăn bằng '-', đủ 5 slot.

    "fb01"        -> "fb01----"      (sub_id1=fb01, các slot còn lại rỗng)
    "fb01-1"      -> "fb01-1---"     (sub_id1=fb01, sub_id2=1)
    "fb01-1-2-3-4" -> giữ nguyên
    Đặt SUB_ID_PAD=0 trong .env nếu muốn dùng nguyên văn, không tự bù.
    """
    s = str(sub_id if sub_id not in (None, "") else "0").strip()
    s = re.sub(r"[\s_]+", "-", s)
    if os.environ.get("SUB_ID_PAD", "1") == "0":
        return s
    while s.count("-") < SUB_ID_SLOTS - 1:
        s += "-"
    return s


def _append_utm(url, params):
    """Gắn utm vào URL bất kỳ, ghi đè param trùng tên nếu đã có."""
    p = urlparse(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    q.update(params)
    return urlunparse(p._replace(query=urlencode(q, safe="")))


def make_link(url, sub_id="0", campaign=None, template=None):
    """Sinh link affiliate từ link sản phẩm (hoặc từ shop_id/item_id qua link_for_item)."""
    aid = aff_id()
    if not aid:
        raise ValueError("Thiếu SHOPEE_AFF_ID trong .env")
    if not url:
        raise ValueError("Thiếu URL sản phẩm")

    camp = campaign if campaign is not None else os.environ.get("AFF_CAMPAIGN", "-")
    tmpl = template or os.environ.get("LINK_TEMPLATE") or DEFAULT_TEMPLATE
    sub = normalize_sub_id(sub_id)

    if "{shop_id}" in tmpl and "{item_id}" in tmpl:
        ids = parse_product_url(url)
        if not ids:
            raise ValueError("Không tách được shop_id/item_id từ URL, dùng template {origin} thay thế")
        shop_id, item_id = ids
        return tmpl.format(
            shop_id=shop_id,
            item_id=item_id,
            aff_id=quote(aid, safe=""),
            sub_id=quote(sub, safe=""),
            campaign=quote(str(camp), safe=""),
        )

    # Template cũ / tuỳ biến dạng {origin}
    if "{origin}" in tmpl:
        return tmpl.format(
            origin=quote(url, safe=""),
            aff_id=quote(aid, safe=""),
            sub_id=quote(sub, safe=""),
            campaign=quote(str(camp), safe=""),
        )

    # Template trỏ thẳng vào link gốc: giữ nguyên URL rồi gắn utm
    return _append_utm(url, {
        "utm_source": f"an_{aid}",
        "utm_medium": "affiliates",
        "utm_campaign": str(camp),
        "utm_content": sub,
    })


def link_for_item(item_id, shop_id, sub_id="0"):
    url = product_url(shop_id, item_id)
    return {
        "product_url": url,
        "aff_link": make_link(url, sub_id),
        "sub_id": normalize_sub_id(sub_id),
    }


def explain():
    """In ra format đang dùng — để đối chiếu tay với dashboard."""
    return {
        "affiliate_id": aff_id() or None,
        "template": os.environ.get("LINK_TEMPLATE") or DEFAULT_TEMPLATE,
        "campaign": os.environ.get("AFF_CAMPAIGN", "-"),
        "sub_id_pad": os.environ.get("SUB_ID_PAD", "1") != "0",
        "example": make_link(product_url("1020310358", "24088489429"), "fb01")
        if aff_id() else None,
    }
