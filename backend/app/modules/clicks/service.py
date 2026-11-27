"""Nghiệp vụ /go/{code}: tra link, ghi click, dựng link affiliate có sub_id ký. KHÔNG biết HTTP, KHÔNG có SQL."""
from __future__ import annotations

import hashlib
import hmac
import logging
import re

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.core import subid
from app.core.config import ConfigError, Settings
from app.modules.clicks import repository
from app.modules.clicks.errors import LinkNotFound
from app.modules.links.service import UserLinkService

log = logging.getLogger("app.clicks")
_CODE = re.compile(r"^[0-9a-z]{8}$")


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
        """Trả URL Shopee để chuyển hướng. Ghi click lỗi thì VẪN chuyển hướng (bằng sub_id mức link) để không mất đơn."""
        if not _CODE.match(code):
            raise LinkNotFound("Link không tồn tại")
        secret = self.s.subid_secret.get_secret_value()
        if len(secret.encode()) < 16:
            raise ConfigError("SUBID_SECRET phải có ít nhất 16 byte")
        link = self.links.resolve(code)
        if link is None:
            raise LinkNotFound("Link không tồn tại")
        try:
            with self.engine.begin() as conn:
                click_id = repository.next_click_id(conn)
                sub = subid.encode("u", link.user_id, click_id, secret)
                repository.insert_click(conn, click_id, link.link_id, sub,
                                        hash_value(self.s, ip), hash_value(self.s, user_agent))
        except SQLAlchemyError:
            log.exception("không ghi được click, chuyển hướng bằng sub_id mức link", extra={"link_id": link.link_id})
            sub = subid.encode("l", link.user_id, link.link_id, secret)
        return self.links.affiliate_url(link.shop_id, link.item_id, sub)
