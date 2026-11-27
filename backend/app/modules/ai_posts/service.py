"""Cấp link cho bài đăng của Muse AI. Idempotent theo post_key: gọi lại trả đúng link cũ, KHÔNG ghi đè đích."""
from __future__ import annotations

from sqlalchemy import Engine

from app.core import subid
from app.core.config import Settings
from app.core.errors import Conflict
from app.modules.agent_auth.service import AgentIdentity
from app.modules.ai_posts import repository
from app.modules.ai_posts.schemas import LinkRequest, LinkResponse
from app.modules.links.affiliate_link import LinkConfig, make_link, product_url


class AiPostService:
    def __init__(self, settings: Settings, engine: Engine):
        self.s, self.engine = settings, engine

    def _response(self, post_id: int, sub_id: str, shop_id: int, item_id: int) -> LinkResponse:
        url = product_url(shop_id, item_id)
        return LinkResponse(post_id=post_id, sub_id=sub_id, product_url=url,
                            aff_link=make_link(url, sub_id, LinkConfig.from_settings(self.s)))

    def create_link(self, who: AgentIdentity, req: LinkRequest) -> LinkResponse:
        self.s.require("shopee_aff_id", "subid_secret")
        secret = self.s.subid_secret.get_secret_value()
        with self.engine.begin() as conn:
            product_id = repository.upsert_product(conn, req.shop_id, req.item_id)
            post_id = repository.insert_post(conn, req.post_key, product_id, who.key_id, req.page_code, req.category)
            if post_id is None:   # post_key đã có
                row = repository.get_by_key(conn, req.post_key)
                if (row["shop_id"], row["item_id"], row["page_code"]) != (req.shop_id, req.item_id, req.page_code):
                    raise Conflict("post_key đã được dùng cho sản phẩm/fanpage khác", code="post_key_conflict")
                return self._response(row["id"], row["sub_id"], req.shop_id, req.item_id)
            sub_id = subid.encode("p", post_id, int(req.page_code, 36), secret)
            repository.set_sub_id(conn, post_id, sub_id)
        return self._response(post_id, sub_id, req.shop_id, req.item_id)
