from app.integrations.shopee.fake import FakeShopeeClient
from app.modules.reports.service import build_summary


def summary():
    return build_summary(FakeShopeeClient().dashboard_snapshot(7), 7)


def test_totals_and_by_day_are_integer_micro():
    s = summary()
    t = s["totals"]
    assert t["clicks"] == 14 and t["orders"] == 1
    assert t["commission_micro"] == 403_750_000 and t["order_amount_micro"] == 19_000_000_000
    assert all(isinstance(v, int) for v in (t["commission_micro"], t["income_micro"], t["est_commission_micro"]))
    assert [d["date"] for d in s["by_day"]] == ["2026-11-26", "2026-11-27"]


def test_groups_by_sub_id_and_cvr():
    by = {r["sub_id"]: r for r in summary()["by_sub"]}
    fb = by["fb01-1"]                          # dấu '-' hai đầu bị cắt
    assert fb["clicks"] == 2 and fb["orders"] == 1 and fb["cvr_pct"] == 50.0
    assert fb["commission_micro"] == 403_750_000 and fb["items"] == 2
    none = by["(không sub_id)"]                # click rỗng + đơn rỗng gộp chung
    assert none["clicks"] == 1 and none["orders"] == 1 and none["commission_micro"] == 100_000_000
    assert summary()["by_sub"][0]["sub_id"] == "fb01-1"


def test_top_items_and_rates_in_basis_points():
    it = summary()["top_items"][0]
    assert it["price_micro"] == 9_500_000_000 and it["qty"] == 2 and it["commission_micro"] == 403_750_000
    assert it["platform_rate_bp"] == 250 and it["name"] == "Nồi chiên mẫu"


def test_empty_snapshot():
    from app.integrations.shopee.client import DashboardSnapshot
    s = build_summary(DashboardSnapshot((0, 86399)), 1)
    assert s["totals"]["clicks"] == 0 and s["by_sub"] == [] and s["top_items"] == []
