"""Lớp tương thích cho code cũ (server.py, verify_link.py). Logic đã chuyển sang
backend/app/modules/links/affiliate_link.py. Sẽ bị xóa ở bước 10 của refactor."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.modules.links import affiliate_link as _al  # noqa: E402

DEFAULT_TEMPLATE = _al.DEFAULT_TEMPLATE
SUB_ID_SLOTS = _al.SUB_ID_SLOTS
product_url = _al.product_url
parse_product_url = _al.parse_product_url


def aff_id():
    return os.environ.get("SHOPEE_AFF_ID", "").strip()


def _cfg():
    return _al.LinkConfig(
        aff_id=aff_id(),
        campaign=os.environ.get("AFF_CAMPAIGN", "-"),
        template=os.environ.get("LINK_TEMPLATE", ""),
        pad=os.environ.get("SUB_ID_PAD", "1") != "0",
    )


def normalize_sub_id(sub_id):
    return _al.normalize_sub_id(sub_id, _cfg().pad)


def make_link(url, sub_id="0", campaign=None, template=None):
    return _al.make_link(url, sub_id, _cfg(), campaign=campaign, template=template)


def link_for_item(item_id, shop_id, sub_id="0"):
    return _al.link_for_item(item_id, shop_id, sub_id, _cfg())
