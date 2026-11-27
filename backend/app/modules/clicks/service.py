"""Nghiệp vụ /go/{code}: tra link, ghi click, dựng link affiliate có sub_id ký. KHÔNG biết HTTP, KHÔNG có SQL."""
from __future__ import annotations

import hashlib
import hmac
import logging
import re

from sqlalchemy import Engine

from app.core import subid
from app.core.config import ConfigError, Settings
from app.modules.clicks import repository
from app.modules.clicks.errors import LinkNotFound
from app.modules.links.service import UserLinkService

log = logging.getLogger("app.clicks")
_CODE = re.compile(r"[0-9a-z]{8}")
# Crawler xem trước link (Facebook, Zalo...), bot: vẫn chuyển hướng nhưng KHÔNG ghi click.
_BOT = re.compile(r"bot|crawl|spider|preview|facebookexternalhit|slurp", re.I)


def hash_value(settings: Settings, value: str | None) -> str | None:
    """HMAC-SHA256(IP_SALT, value), 16 ký tự hex đầu. Không có IP_SALT hoặc value rỗng thì không lưu gì."""
    key = settings.ip_salt.get_secret_value()
    if not key or not value:
        return None
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]


class ClickService:
    def __init__(self, settings: Settings, engine: Engine):
        self.s, self.engine = settings, engine
        self.links = UserLinkService(settings, engine)

    def go(self, code: str, ip: str | None, user_agent: str | None) -> str:
        """Trả URL Shopee để chuyển hướng. Mọi lỗi khi ghi click đều KHÔNG chặn chuyển hướng (không mất đơn)."""
        if not _CODE.fullmatch(code):
            raise LinkNotFound("Link không tồn tại")
        secret = self.s.subid_secret.get_secret_value()
        if len(secret.encode()) < 16:
            raise ConfigError("SUBID_SECRET phải có ít nhất 16 byte")
        self.s.require("shopee_aff_id")       # kiểm tra cấu hình TRƯỚC khi ghi gì vào DB (không để lại click ma)
        link = self.links.resolve(code)
        if link is None:
            raise LinkNotFound("Link không tồn tại")
        sub = self._attribute(link, ip, user_agent, secret)
        return self.links.affiliate_url(link.shop_id, link.item_id, sub)

    def _attribute(self, link, ip, user_agent, secret) -> str:
        if not link.user_active:   # chủ link bị khóa: người mua vẫn được chuyển hướng, hoa hồng không gán cho ai
            return subid.encode("x", 0, link.link_id, secret)
        link_level = subid.encode("l", link.user_id, link.link_id, secret)
        if _BOT.search(user_agent or ""):
            return link_level
        try:
            with self.engine.begin() as conn:
                click_id = repository.next_click_id(conn)
                sub = subid.encode("u", link.user_id, click_id, secret)
                repository.insert_click(conn, click_id, link.link_id, sub,
                                        hash_value(self.s, ip), hash_value(self.s, user_agent))
            return sub
        except Exception:   # noqa: BLE001 - bất kỳ lỗi ghi click nào cũng phải rơi về link mức link; có log đầy đủ
            log.exception("không ghi được click, chuyển hướng bằng sub_id mức link", extra={"link_id": link.link_id})
            return link_level
