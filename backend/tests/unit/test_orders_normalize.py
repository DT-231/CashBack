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


def test_multi_order_row_without_cap_pressure_keeps_item_sums():
    two = {"order_sn": "SN2", "items": [{"item_commission": 5, "qty": 1}]}
    one = {"order_sn": "SN3", "items": [{"item_commission": 7, "qty": 1}]}
    got = {o.order_sn: o.commission_micro for o in normalize_row(row(capped_commission=12, orders=[two, one]))}
    assert got == {"SN2": 5, "SN3": 7}


def test_multi_order_row_over_the_cap_is_shared_proportionally_rounded_down():
    a = {"order_sn": "A", "items": [{"item_commission": 600, "qty": 1}]}
    b = {"order_sn": "B", "items": [{"item_commission": 400, "qty": 1}]}
    got = {o.order_sn: o.commission_micro for o in normalize_row(row(capped_commission=500, orders=[a, b]))}
    assert got == {"A": 300, "B": 200} and sum(got.values()) <= 500
    odd = {o.order_sn: o.commission_micro for o in normalize_row(row(capped_commission=1, orders=[a, b]))}
    assert sum(odd.values()) <= 1                      # làm tròn xuống: không bao giờ vượt hạn mức
    zero = normalize_row(row(capped_commission=0, orders=[a, b]))
    assert [o.commission_micro for o in zero] == [0, 0]


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


def test_merge_same_order_sn_rows_adds_commission_and_items():
    from app.modules.orders.normalize import merge_orders
    r1 = row(utm_content="", orders=[{"order_sn": "M", "items": [{"item_commission": 100, "qty": 1}]}], capped_commission=100)
    r2 = row(utm_content="1u-a-b-xyz-", capped_commission=59,
             orders=[{"order_sn": "M", "items": [{"item_commission": 50, "qty": 1}]},
                     {"order_sn": "Z", "items": [{"item_commission": 9, "qty": 1}]}])
    merged = merge_orders([o for r in (r1, r2) for o in normalize_row(r)])
    by = {o.order_sn: o for o in merged}
    assert list(by) == ["M", "Z"] and by["M"].commission_micro == 150 and len(by["M"].items) == 2
    assert by["M"].utm_content == "1u-a-b-xyz-" and by["Z"].commission_micro == 9   # lấy utm không rỗng đầu tiên


def test_merge_status_is_conservative():
    from app.modules.orders.normalize import merge_orders

    def o(status):
        return normalize_row(row(status=status, orders=[{"order_sn": "S", "items": [{"item_commission": 1}]}]))[0]
    assert merge_orders([o("COMPLETED"), o("COMPLETED")])[0].status == "COMPLETED"
    assert merge_orders([o("COMPLETED"), o("PENDING")])[0].status == "PENDING"
    assert merge_orders([o("CANCELLED"), o("RETURNED")])[0].status == "RETURNED"
    assert merge_orders([o("CANCELLED"), o("CANCELLED")])[0].status == "CANCELLED"
    assert merge_orders([o("COMPLETED"), o("CANCELLED")])[0].status == "PENDING"
