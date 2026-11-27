"""Quyết định một đơn thuộc về ai từ `utm_content` (sub_id v1). HÀM THUẦN + một hàm tra DB được truyền vào."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.core import subid


@dataclass(frozen=True)
class Attribution:
    source_type: str                 # user | post | legacy | unknown
    user_id: int | None = None
    click_id: int | None = None
    post_id: int | None = None
    orphan_reason: str | None = None  # có giá trị = đơn mồ côi (thuộc admin, staff gán tay được)


Lookup = Callable[[str, int, int], bool]   # (kind, owner, ref) -> có tồn tại và khớp không


def attribute(utm_content: str, secret, exists: Lookup) -> Attribution:
    d = subid.decode(utm_content, secret)
    if d.status == "empty":
        return Attribution("unknown", orphan_reason="no_sub_id")
    if d.status == "legacy":
        return Attribution("legacy", orphan_reason="legacy_sub_id")
    if d.status == "invalid":
        return Attribution("unknown", orphan_reason=f"invalid_sub_id: {d.reason}")
    if d.type == "x":
        return Attribution("unknown", orphan_reason="other_source")
    if d.type == "u":
        if not exists("click", d.owner, d.ref):
            return Attribution("unknown", orphan_reason="click_not_found")
        return Attribution("user", user_id=d.owner, click_id=d.ref)
    if d.type == "l":
        if not exists("link", d.owner, d.ref):
            return Attribution("unknown", orphan_reason="link_not_found")
        return Attribution("user", user_id=d.owner)
    if d.type == "p":
        if not exists("post", d.owner, d.ref):
            return Attribution("unknown", orphan_reason="post_not_found")
        return Attribution("post", post_id=d.owner)
    return Attribution("unknown", orphan_reason="unsupported_type")
