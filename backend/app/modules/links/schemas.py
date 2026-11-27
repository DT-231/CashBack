from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateLinkRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class ProductOut(BaseModel):
    shop_id: int
    item_id: int
    name: str | None = None


class LinkOut(BaseModel):
    code: str
    go_url: str | None
    direct_url: str
    product: ProductOut


class UserLinkOut(BaseModel):
    code: str
    go_url: str | None
    product: ProductOut
    created_at: datetime
    clicks: int


class ResolvedLink(BaseModel):
    """Kết quả tra mã /go/{code}: đủ để dựng link affiliate và ghi click."""
    link_id: int
    user_id: int
    shop_id: int
    item_id: int
    user_active: bool   # chủ link còn hoạt động; bị khóa/chưa xác minh thì không được gán click/đơn
