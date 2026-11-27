from __future__ import annotations

from pydantic import BaseModel, Field


class LinkRequest(BaseModel):
    shop_id: int = Field(gt=0)
    item_id: int = Field(gt=0)
    post_key: str = Field(min_length=1, max_length=128)
    page_code: str = Field(pattern=r"^[0-9a-z]{1,8}$")   # thành s3 của sub_id v1
    category: str | None = Field(default=None, max_length=64)


class LinkResponse(BaseModel):
    post_id: int
    sub_id: str
    aff_link: str
    product_url: str
