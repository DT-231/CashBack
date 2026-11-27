"""Dựng link cho kết quả tìm kiếm (đường dẫn cũ /api/search).

sub_id ở đây là nhãn do CALLER đặt (`sub`) + số thứ tự, KHÔNG phải sub_id v1: đơn về từ các link này sẽ được
giải mã là `legacy`. Link có chữ ký, truy ngược được: dùng POST /api/v1/agent/links.
"""
from __future__ import annotations

import secrets
import string
from urllib.parse import urlsplit

from sqlalchemy import Engine

from app.core import subid
from app.core.config import ConfigError, Settings
from app.core.errors import AppError
from app.modules.links import repository
from app.modules.links.affiliate_link import (
    LinkConfig,
    LinkError,
    link_for_item,
    make_link,
    parse_product_url,
    product_url,
)
from app.modules.links.errors import InvalidLink
from app.modules.links.schemas import LinkOut, ProductOut, ResolvedLink, UserLinkOut

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


_CODE_ALPHABET = string.ascii_lowercase + string.digits


class UserLinkService:
    def __init__(self, settings: Settings, engine: Engine):
        self.settings, self.engine = settings, engine

    @staticmethod
    def _parse_url(url: str) -> tuple[int, int]:
        try:
            parsed = urlsplit(url)
        except ValueError as exc:
            raise InvalidLink("URL Shopee không hợp lệ") from exc
        host = (parsed.hostname or "").lower()
        if host == "s.shopee.vn":
            raise InvalidLink("chưa hỗ trợ link rút gọn")
        if parsed.scheme.lower() not in {"http", "https"} or host not in {"shopee.vn", "www.shopee.vn"} or parsed.username or parsed.password:
            raise InvalidLink("Chỉ nhận link sản phẩm shopee.vn")
        ids = parse_product_url(url)
        if ids is None:
            raise InvalidLink("URL không có shop_id/item_id sản phẩm")
        return ids

    def _go_url(self, code: str) -> str | None:
        base = self.settings.public_base.rstrip("/")
        return f"{base}/go/{code}" if base else None

    def create(self, user_id: int, url: str) -> LinkOut:
        shop_id, item_id = self._parse_url(url)
        self.settings.require("shopee_aff_id")
        secret = self.settings.subid_secret.get_secret_value()
        if len(secret.encode()) < 16:
            raise ConfigError("SUBID_SECRET phải có ít nhất 16 byte")
        with self.engine.begin() as conn:
            product = repository.upsert_product(conn, shop_id, item_id)
            row = repository.get_user_link(conn, user_id, product["id"])
            if row is None:
                for _ in range(5):
                    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
                    if repository.insert_user_link(conn, user_id, product["id"], code):
                        row = repository.get_user_link(conn, user_id, product["id"])
                        break
                    row = repository.get_user_link(conn, user_id, product["id"])
                    if row is not None:
                        break
                if row is None:
                    raise AppError("Không thể tạo mã link, vui lòng thử lại", code="link_code_unavailable", status=503)
            signed_sub_id = subid.encode("l", user_id, row["id"], secret)
        direct_url = make_link(product_url(shop_id, item_id), signed_sub_id, LinkConfig.from_settings(self.settings))
        return LinkOut(code=row["code"], go_url=self._go_url(row["code"]), direct_url=direct_url,
                       product=ProductOut(shop_id=shop_id, item_id=item_id, name=product["name"]))

    def list_for_user(self, user_id: int, limit: int, offset: int) -> list[UserLinkOut]:
        with self.engine.connect() as conn:
            rows = repository.list_user_links(conn, user_id, limit, offset)
        return [UserLinkOut(code=r["code"], go_url=self._go_url(r["code"]),
                            product=ProductOut(shop_id=r["shop_id"], item_id=r["item_id"], name=r["name"]),
                            created_at=r["created_at"], clicks=r["clicks"]) for r in rows]

    def resolve(self, code: str) -> ResolvedLink | None:
        """Tra link theo mã công khai (dùng cho /go/{code}). Không có thì trả None."""
        with self.engine.connect() as conn:
            row = repository.get_by_code(conn, code)
        return ResolvedLink(**row) if row else None

    def affiliate_url(self, shop_id: int, item_id: int, sub_id: str) -> str:
        """Link affiliate cho sản phẩm với sub_id đã ký (do caller dựng bằng app.core.subid)."""
        self.settings.require("shopee_aff_id")
        return make_link(product_url(shop_id, item_id), sub_id, LinkConfig.from_settings(self.settings))
