"""revenue.py với dữ liệu giả (không gọi Shopee). Fixture là dữ liệu tổng hợp theo cấu trúc HAR đã verify."""
import json
from pathlib import Path

import pytest

import revenue

FX = Path(__file__).resolve().parents[2] / "app" / "integrations" / "shopee" / "fixtures"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


@pytest.fixture
def fake_dashboard(monkeypatch):
    def fake_get(path, params):
        if path.endswith("dashboard/detail"):
            return load("revenue_dashboard.json")
        if "click_report" in path:
            return load("revenue_clicks.json")
        if "report/list" in path:
            return load("revenue_orders.json")
        raise AssertionError(path)
    monkeypatch.setattr(revenue, "_get", fake_get)


def test_vnd_converts_micro_and_tolerates_junk():
    assert revenue.vnd(403750000) == 4037.5
    assert revenue.vnd(None) == 0.0 and revenue.vnd("x") == 0.0


def test_window_covers_whole_days_in_vn_time():
    s, e = revenue.window(1)
    assert 0 < e - s <= 86399
    s7, _ = revenue.window(7)
    assert 6 * 86400 <= e - s7 <= 7 * 86400 - 1


def test_summary_totals_and_by_day(fake_dashboard):
    s = revenue.summary(7)
    assert s["totals"]["clicks"] == 14 and s["totals"]["orders"] == 1
    assert s["totals"]["commission_vnd"] == 4037.5 and s["totals"]["order_amount_vnd"] == 190000.0
    assert [d["date"] for d in s["by_day"]] == ["2026-11-26", "2026-11-27"]


def test_summary_groups_by_sub_id_and_cvr(fake_dashboard):
    s = revenue.summary(7)
    by = {r["sub_id"]: r for r in s["by_sub"]}
    fb = by["fb01-1"]                     # dấu '-' ở hai đầu bị cắt
    assert fb["clicks"] == 2 and fb["orders"] == 1 and fb["cvr_pct"] == 50.0
    assert fb["commission_vnd"] == 4037.5 and fb["items"] == 2
    none = by["(không sub_id)"]           # click rỗng + đơn rỗng gộp chung
    assert none["clicks"] == 1 and none["orders"] == 1 and none["commission_vnd"] == 1000.0
    assert s["by_sub"][0]["sub_id"] == "fb01-1"   # xếp theo hoa hồng giảm dần


def test_summary_top_items_and_rates(fake_dashboard):
    it = revenue.summary(7)["top_items"][0]
    assert it["price_vnd"] == 95000.0 and it["qty"] == 2 and it["commission_vnd"] == 4037.5
    assert it["platform_rate_pct"] == 2.5 and it["name"] == "Nồi chiên mẫu"


def test_paged_stops_at_total_count(monkeypatch):
    pages = []
    def fake_get(path, params):
        pages.append(params["page_num"])
        return {"code": 0, "data": {"total_count": 150, "list": [{"i": 1}] * (100 if params["page_num"] == 1 else 50)}}
    monkeypatch.setattr(revenue, "_get", fake_get)
    assert len(revenue._paged("/x", {}, "t")) == 150 and pages == [1, 2]


def test_paged_stops_on_empty_and_respects_max_pages(monkeypatch):
    monkeypatch.setattr(revenue, "_get", lambda p, q: {"data": {"total_count": 10**9, "list": [{"i": 1}]}})
    assert len(revenue._paged("/x", {}, "t", max_pages=3)) == 3
    monkeypatch.setattr(revenue, "_get", lambda p, q: {"data": {"list": []}})
    assert revenue._paged("/x", {}, "t") == []


def test_get_requires_cookie():
    with pytest.raises(revenue.RevenueError, match="SHOPEE_COOKIE"):
        revenue._get("/x", {})


class _R:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._b, self.text = status, body, text

    def json(self):
        if self._b is None:
            raise ValueError("html")
        return self._b


@pytest.fixture
def with_cookie(monkeypatch):
    monkeypatch.setenv("SHOPEE_COOKIE", "fake=1")
    monkeypatch.setattr(revenue.time, "sleep", lambda s: None)


@pytest.mark.parametrize("resp,match", [
    (_R(403), "403"),
    (_R(500, text="boom"), "HTTP 500"),
    (_R(200, None, "<html>"), "HTML"),
    (_R(200, {"code": 7, "msg": "bad"}), "code=7"),
])
def test_get_error_mapping(with_cookie, monkeypatch, resp, match):
    monkeypatch.setattr(revenue.requests.Session, "get", lambda self, *a, **k: resp)
    with pytest.raises(revenue.RevenueError, match=match):
        revenue._get("/x", {})


def test_get_retries_network_error_once(with_cookie, monkeypatch):
    n = []
    def flaky(self, *a, **k):
        n.append(1)
        if len(n) == 1:
            raise revenue.requests.ConnectionError("down")
        return _R(200, {"code": 0, "data": {"ok": 1}})
    monkeypatch.setattr(revenue.requests.Session, "get", flaky)
    assert revenue._get("/x", {})["data"] == {"ok": 1} and len(n) == 2


def test_cookie_is_not_in_error_text(with_cookie, monkeypatch):
    monkeypatch.setattr(revenue.requests.Session, "get", lambda self, *a, **k: _R(403))
    with pytest.raises(revenue.RevenueError) as ei:
        revenue._get("/x", {})
    assert "fake=1" not in str(ei.value)
