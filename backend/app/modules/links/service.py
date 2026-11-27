"""Dựng link cho kết quả tìm kiếm (đường dẫn cũ /api/search).

sub_id ở đây là nhãn do CALLER đặt (`sub`) + số thứ tự, KHÔNG phải sub_id v1: đơn về từ các link này sẽ được
giải mã là `legacy`. Link có chữ ký, truy ngược được: dùng POST /api/v1/agent/links.
"""
from __future__ import annotations

from app.core.config import Settings
from app.modules.links.affiliate_link import LinkConfig, LinkError, link_for_item, product_url


def enrich_items(settings: Settings, items: list[dict], sub: str) -> list[dict]:
    """Gắn product_url/aff_link/sub_id cho từng item. Không có `sub` thì dùng tiền tố 'api' (không đưa keyword người dùng vào sub_id)."""
    cfg = LinkConfig.from_settings(settings)
    out = []
    for i, it in enumerate(items, 1):
        rec = dict(it)
        sid = f"{sub or 'api'}-{i}".replace(" ", "_")
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
