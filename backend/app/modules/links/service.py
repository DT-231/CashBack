"""Dựng link cho kết quả tìm kiếm / URL sản phẩm (dùng cho đường dẫn cũ /api/search, /api/link)."""
from __future__ import annotations

from app.core.config import Settings
from app.modules.links.affiliate_link import LinkConfig, LinkError, link_for_item, product_url


def enrich_items(settings: Settings, items: list[dict], keyword: str, sub: str) -> list[dict]:
    """Gắn product_url/aff_link/sub_id cho từng item. Kiểu sub_id cũ: '<sub>-<i>' (xem audit #4)."""
    cfg = LinkConfig.from_settings(settings)
    out = []
    for i, it in enumerate(items, 1):
        rec = dict(it)
        sid = (f"{sub}-{i}" if sub else f"{keyword[:12]}-{i}").replace(" ", "_")
        rec["sub_id"] = sid
        if not it.get("item_id") or not it.get("shop_id"):
            rec.update(product_url=None, aff_link=None, link_error="nguồn dữ liệu thiếu item_id/shop_id")
        else:
            try:
                link = link_for_item(it["item_id"], it["shop_id"], sid, cfg)
                rec.update(product_url=link["product_url"], aff_link=link["aff_link"])
            except LinkError as e:
                rec.update(product_url=product_url(it["shop_id"], it["item_id"]), aff_link=None, link_error=str(e))
        out.append(rec)
    return out
