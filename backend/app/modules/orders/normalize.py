"""Chuẩn hóa một dòng báo cáo đơn của Shopee (`/api/v3/report/list`) thành đơn nội bộ. HÀM THUẦN, không DB.

ĐÃ XÁC NHẬN từ HAR thật (docs/legacy): `utm_content`, `capped_commission`, `gross_commission`, và trong
`orders[].items[]`: `item_id, shop_id, item_price, qty, item_commission, platform_commission_rate,
brand_commission_rate, global_category_lv1_name`. Tiền là micro-VND (×1e5).

CHƯA XÁC NHẬN (cần HAR thật có đơn đủ trạng thái; hiện chỉ biết có giá trị `COMPLETED`): tên trường trạng thái
đơn và thời gian mua. Ta đọc kiểu dung thứ ở `STATUS_KEYS`/`TIME_KEYS` MỘT chỗ; không đọc được thì coi là
PENDING (không chuyển tiền) và giữ nguyên `raw_status` để người vận hành thấy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

STATUS_KEYS = ("order_status", "status", "purchase_status", "conversion_status")
TIME_KEYS = ("purchase_time", "order_time", "create_time")
COMPLETED_AT_KEYS = ("complete_time", "completed_time", "completed_at")

_STATUS = {
    "COMPLETED": "COMPLETED", "COMPLETE": "COMPLETED",
    "CANCELLED": "CANCELLED", "CANCELED": "CANCELLED",
    "RETURNED": "RETURNED", "REFUNDED": "RETURNED", "RETURN_REFUND": "RETURNED",
}


@dataclass(frozen=True)
class NormalizedItem:
    item_id: int | None
    shop_id: int | None
    qty: int
    price_micro: int
    commission_micro: int
    platform_rate_bp: int | None
    brand_rate_bp: int | None
    category_lv1: str | None


@dataclass(frozen=True)
class NormalizedOrder:
    order_sn: str
    raw_status: str | None
    status: str                      # PENDING | COMPLETED | CANCELLED | RETURNED
    utm_content: str
    commission_micro: int
    purchase_time: datetime | None
    completed_at: datetime | None
    items: list[NormalizedItem] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _opt_int(v) -> int | None:
    try:
        return None if v is None else int(v)
    except (TypeError, ValueError):
        return None


def _first(d: dict, keys):
    return next((d[k] for k in keys if d.get(k) not in (None, "")), None)


def _ts(v) -> datetime | None:
    n = _opt_int(v)
    if not n or n <= 0:
        return None
    if n > 10**12:           # mili-giây
        n //= 1000
    try:
        return datetime.fromtimestamp(n, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def map_status(raw) -> str:
    return _STATUS.get(str(raw or "").strip().upper().replace(" ", "_"), "PENDING")


def normalize_row(row: dict) -> list[NormalizedOrder]:
    """Một dòng báo cáo = một lượt chuyển đổi, chứa `orders[]` (thường 1 đơn). Trả mỗi `order_sn` một NormalizedOrder."""
    nested = [o for o in (row.get("orders") or []) if o.get("order_sn")]
    capped = _opt_int(row.get("capped_commission")) if row.get("capped_commission") is not None else None
    out = []
    for o in nested:
        items = [NormalizedItem(
            item_id=_opt_int(it.get("item_id")), shop_id=_opt_int(it.get("shop_id")), qty=_int(it.get("qty")) or 1,
            price_micro=_int(it.get("item_price")), commission_micro=_int(it.get("item_commission")),
            platform_rate_bp=_opt_int(it.get("platform_commission_rate")),
            brand_rate_bp=_opt_int(it.get("brand_commission_rate")),
            category_lv1=it.get("global_category_lv1_name")) for it in (o.get("items") or [])]
        commission = sum(i.commission_micro for i in items)
        if len(nested) == 1 and capped is not None:
            # An toàn về tiền: không bao giờ trả nhiều hơn mức Shopee đã giới hạn. capped=0 là 0 thật, KHÔNG rơi về gross.
            commission = min(commission, capped)
        # trạng thái/thời gian có thể nằm ở đơn con hoặc ở dòng ngoài
        raw_status = _first(o, STATUS_KEYS) or _first(row, STATUS_KEYS)
        out.append(NormalizedOrder(
            order_sn=str(o["order_sn"]), raw_status=None if raw_status is None else str(raw_status),
            status=map_status(raw_status), utm_content=str(row.get("utm_content") or ""),
            commission_micro=max(commission, 0),
            purchase_time=_ts(_first(o, TIME_KEYS) or _first(row, TIME_KEYS)),
            completed_at=_ts(_first(o, COMPLETED_AT_KEYS) or _first(row, COMPLETED_AT_KEYS)),
            items=items, raw=row))
    return out
