from datetime import UTC, datetime

import pytest

from app.modules.orders.normalize import map_status, normalize_row


def row(**kw):
    base = {"utm_content": "1u-a-b-xyz-", "capped_commission": 403_750_000, "gross_commission": 0,
            "orders": [{"order_sn": "SN1", "items": [{"item_id": 1, "shop_id": 2, "item_price": 9_500_000_000, "qty": 2,
                                                       "item_commission": 403_750_000,
                                                       "platform_commission_rate": 250,
                                                       "brand_commission_rate": 0,
                                                       "global_category_lv1_name": "Nhà cửa"}]}]}
    base.update(kw)
    return base


def test_matches_the_verified_real_order_amounts():
    [o] = normalize_row(row())
    assert o.order_sn == "SN1" and o.commission_micro == 403_750_000 and o.utm_content == "1u-a-b-xyz-"
    assert o.items[0].qty == 2 and o.items[0].price_micro == 9_500_000_000 and o.items[0].platform_rate_bp == 250
    assert o.status == "PENDING" and o.raw_status is None     # chưa biết trạng thái -> không bao giờ coi là hoàn tất


def test_capped_zero_is_zero_not_gross():
    [o] = normalize_row(row(capped_commission=0, gross_commission=100_000_000))
    assert o.commission_micro == 0


def test_capped_never_exceeded_and_missing_capped_uses_items():
    assert normalize_row(row(capped_commission=100))[0].commission_micro == 100
    r = row()
    del r["capped_commission"]
    assert normalize_row(r)[0].commission_micro == 403_750_000


def test_multi_order_row_sums_items_and_ignores_row_level_cap():
    two = {"order_sn": "SN2", "items": [{"item_commission": 5, "qty": 1}]}
    one = {"order_sn": "SN3", "items": [{"item_commission": 7, "qty": 1}]}
    got = {o.order_sn: o.commission_micro for o in normalize_row(row(capped_commission=1, orders=[two, one]))}
    assert got == {"SN2": 5, "SN3": 7}


@pytest.mark.parametrize("raw,expected", [("COMPLETED", "COMPLETED"), ("completed", "COMPLETED"), ("Cancelled", "CANCELLED"),
                                          ("CANCELED", "CANCELLED"), ("return refund", "RETURNED"),
                                          ("REFUNDED", "RETURNED"), ("PENDING", "PENDING"), ("ĐANG XỬ LÝ", "PENDING"),
                                          (None, "PENDING"), ("", "PENDING")])
def test_status_mapping_is_conservative(raw, expected):
    assert map_status(raw) == expected


def test_unknown_status_keeps_raw_text_and_stays_pending():
    r = row()
    r["orders"][0]["order_status"] = "SOMETHING_NEW"
    [o] = normalize_row(r)
    assert o.status == "PENDING" and o.raw_status == "SOMETHING_NEW"


def test_status_may_live_on_row_or_nested_order():
    assert normalize_row(row(status="COMPLETED"))[0].status == "COMPLETED"
    r = row()
    r["orders"][0]["status"] = "CANCELLED"
    assert normalize_row(r)[0].status == "CANCELLED"


def test_times_seconds_and_millis():
    r = row(purchase_time=1_760_000_000, complete_time=1_760_000_000_000)
    [o] = normalize_row(r)
    want = datetime.fromtimestamp(1_760_000_000, UTC)
    assert o.purchase_time == want and o.completed_at == want
    assert normalize_row(row(purchase_time="rác"))[0].purchase_time is None


def test_garbage_is_safe():
    assert normalize_row({}) == [] and normalize_row({"orders": [{"items": []}]}) == []
    [o] = normalize_row({"orders": [{"order_sn": "S", "items": [{"item_commission": "abc", "qty": None}]}]})
    assert o.commission_micro == 0 and o.items[0].qty == 1 and o.utm_content == ""
