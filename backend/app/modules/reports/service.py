"""Tổng hợp số liệu dashboard Shopee thành báo cáo theo ngày / sub_id / sản phẩm.

Hàm thuần trên DashboardSnapshot. Tiền giữ dạng micro-VND (số nguyên); chỉ lớp hiển thị mới đổi sang đồng.
"""
from __future__ import annotations

from datetime import datetime

from app.integrations.shopee.client import VN_TZ, DashboardSnapshot


def _i(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def build_summary(snap: DashboardSnapshot, days: int) -> dict:
    d = snap.daily or {}

    by_day = [{
        "date": row.get("ymd"), "clicks": row.get("clicks") or 0, "orders": row.get("cv_by_order") or 0,
        "order_amount_micro": _i(row.get("order_amount")), "commission_micro": _i(row.get("total_commission")),
        "income_micro": _i(row.get("total_income")),
    } for row in d.get("list") or []]

    by_sub: dict[str, dict] = {}

    def slot(sid) -> dict:
        k = (sid or "").strip("-") or "(không sub_id)"
        return by_sub.setdefault(k, {"sub_id": k, "clicks": 0, "orders": 0, "commission_micro": 0,
                                     "items": 0, "cvr_pct": 0.0})

    for c in snap.clicks:
        slot(c.get("sub_id"))["clicks"] += 1

    items: list[dict] = []
    for o in snap.orders:
        rec = slot(o.get("utm_content"))
        rec["orders"] += 1
        rec["commission_micro"] += _i(o.get("capped_commission")) or _i(o.get("gross_commission"))
        for it in o.get("orders") or []:
            for line in it.get("items") or []:
                rec["items"] += _i(line.get("qty"))
                items.append({
                    "order_sn": it.get("order_sn"), "item_id": line.get("item_id"), "shop_id": line.get("shop_id"),
                    "shop": line.get("shop_name"), "name": (line.get("item_name") or "")[:70],
                    "price_micro": _i(line.get("item_price")), "qty": line.get("qty") or 0,
                    "commission_micro": _i(line.get("item_commission")),
                    "brand_rate_bp": _i(line.get("brand_commission_rate")),
                    "platform_rate_bp": _i(line.get("platform_commission_rate")),
                    "cat1": line.get("global_category_lv1_name"), "cat3": line.get("global_category_lv3_name"),
                })

    for s in by_sub.values():
        s["cvr_pct"] = round(100.0 * s["orders"] / s["clicks"], 2) if s["clicks"] else 0.0

    items.sort(key=lambda x: -x["commission_micro"])
    subs = sorted(by_sub.values(), key=lambda x: (-x["commission_micro"], -x["clicks"]))
    fmt = lambda ts: datetime.fromtimestamp(ts, VN_TZ).strftime("%Y-%m-%d %H:%M")  # noqa: E731

    return {
        "days": days,
        "window": [fmt(snap.window[0]), fmt(snap.window[1])],
        "totals": {
            "clicks": d.get("clicks_sum") or sum(x["clicks"] for x in by_day),
            "orders": d.get("cv_by_order_sum") or sum(x["orders"] for x in by_day),
            "order_amount_micro": _i(d.get("order_amount_sum")),
            "commission_micro": _i(d.get("total_commission_sum")),
            "income_micro": _i(d.get("total_income_sum")),
            "est_commission_micro": _i(d.get("est_commission_sum")),
            "last_update": d.get("last_update_time"),
        },
        "by_day": by_day, "by_sub": subs, "top_items": items[:15],
    }
