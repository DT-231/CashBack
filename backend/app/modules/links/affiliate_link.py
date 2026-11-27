"""Ghép link affiliate Shopee VN — format ĐÃ VERIFY từ dashboard thật (2026-11-26). KHÔNG đổi hành vi.

Link dài thật dashboard trả về:
  https://shopee.vn/universal-link/<slug>-i.<shop_id>.<item_id>
      ?utm_source=an_<affiliate_id>&utm_medium=affiliates&utm_campaign=<chiến dịch>&utm_content=<s1>-<s2>-<s3>-<s4>-<s5>

URL ngắn dưới đây trả 301 -> shopee.vn/product/... giữ nguyên utm và Shopee thêm uls_trackid:
  https://shopee.vn/universal-link/product/{shop_id}/{item_id}?utm_source=an_{aff_id}&utm_medium=affiliates&utm_campaign=-&utm_content=xxx----

Hàm thuần: không đọc env. Cấu hình truyền qua LinkConfig (dựng từ Settings).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

DEFAULT_TEMPLATE = (
    "https://shopee.vn/universal-link/product/{shop_id}/{item_id}"
    "?utm_source=an_{aff_id}"
    "&utm_medium=affiliates"
    "&utm_campaign={campaign}"
    "&utm_content={sub_id}"
)
SUB_ID_SLOTS = 5   # utm_content có 5 slot ngăn bằng '-'


class LinkError(ValueError):
    pass


@dataclass(frozen=True)
class LinkConfig:
    aff_id: str
    campaign: str = "-"
    template: str = ""     # rỗng = DEFAULT_TEMPLATE
    pad: bool = True       # tự bù sub_id đủ 5 slot

    @classmethod
    def from_settings(cls, s) -> "LinkConfig":
        return cls(aff_id=s.aff_id, campaign=s.aff_campaign, template=s.link_template, pad=s.sub_id_pad)


def product_url(shop_id, item_id) -> str:
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


def normalize_sub_id(sub_id, pad: bool = True) -> str:
    """Đưa sub_id về đúng dạng utm_content: đoạn ngăn bằng '-', đủ 5 slot.

    "fb01" -> "fb01----"; "fb01-1" -> "fb01-1---"; "fb01-1-2-3-4" giữ nguyên.
    """
    s = str(sub_id if sub_id not in (None, "") else "0").strip()
    s = re.sub(r"[\s_]+", "-", s)
    if not pad:
        return s
    while s.count("-") < SUB_ID_SLOTS - 1:
        s += "-"
    return s


def _append_utm(url, params):
    p = urlparse(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    q.update(params)
    return urlunparse(p._replace(query=urlencode(q, safe="")))


def make_link(url, sub_id, cfg: LinkConfig, campaign=None, template=None) -> str:
    """Sinh link affiliate từ link sản phẩm."""
    aid = cfg.aff_id.strip()
    if not aid:
        raise LinkError("Thiếu SHOPEE_AFF_ID trong .env")
    if not url:
        raise LinkError("Thiếu URL sản phẩm")

    camp = campaign if campaign is not None else cfg.campaign
    tmpl = template or cfg.template or DEFAULT_TEMPLATE
    sub = normalize_sub_id(sub_id, cfg.pad)

    if "{shop_id}" in tmpl and "{item_id}" in tmpl:
        ids = parse_product_url(url)
        if not ids:
            raise LinkError("Không tách được shop_id/item_id từ URL, dùng template {origin} thay thế")
        shop_id, item_id = ids
        return tmpl.format(shop_id=shop_id, item_id=item_id, aff_id=quote(aid, safe=""),
                           sub_id=quote(sub, safe=""), campaign=quote(str(camp), safe=""))

    if "{origin}" in tmpl:   # template tuỳ biến cũ
        return tmpl.format(origin=quote(url, safe=""), aff_id=quote(aid, safe=""),
                           sub_id=quote(sub, safe=""), campaign=quote(str(camp), safe=""))

    # Template trỏ thẳng vào link gốc: giữ URL rồi gắn utm
    return _append_utm(url, {"utm_source": f"an_{aid}", "utm_medium": "affiliates",
                             "utm_campaign": str(camp), "utm_content": sub})


def link_for_item(item_id, shop_id, sub_id, cfg: LinkConfig) -> dict:
    url = product_url(shop_id, item_id)
    return {"product_url": url, "aff_link": make_link(url, sub_id, cfg),
            "sub_id": normalize_sub_id(sub_id, cfg.pad)}
