"""Kéo số liệu THẬT từ dashboard affiliate (khỏi cần export CSV).

3 endpoint này lấy trực tiếp từ HAR thật của bạn (26-27/11/2026), đã xác nhận
là trang report gọi đúng như vậy:

  GET /api/v3/dashboard/detail?start_time=&end_time=
      -> clicks, cv_by_order, order_amount, total_commission theo từng ngày
  GET /api/v1/click_report/list?click_time_s=&click_time_e=&page_num=&page_size=
      -> từng click, có sub_id  => biết bài nào / link nào ra click
  GET /api/v3/report/list?purchase_time_s=&purchase_time_e=&page_num=&page_size=&version=1
      -> từng đơn: shop, item, category, % hoa hồng, utm_content (sub_id), tiền hoa hồng

Chỉ cần SHOPEE_COOKIE (cookie phiên affiliate.shopee.vn) trong .env.
Đây là đường KHÔNG cần API engine, không captcha, không feed CSV.

Đơn vị tiền: Shopee trả số nguyên × 1e5 (micro-VND). 403750000 = 4.037,5 đ.
Đã đối chiếu: item_price 9.500.000.000/1e5 = 95.000đ, qty 2, platform rate 2,5%
-> 161.500 × 2,5% = 4.037,5đ = item_commission. Khớp.

Dùng:
    python3 revenue.py                 # 7 ngày gần nhất
    python3 revenue.py --days 30
    python3 revenue.py --days 30 --json
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

BASE = "https://affiliate.shopee.vn"
VN_TZ = timezone(timedelta(hours=7))
MICRO = 100_000.0
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36")


class RevenueError(RuntimeError):
    pass


def cookie() -> str:
    return (os.environ.get("SHOPEE_COOKIE") or os.environ.get("AFF_COOKIE") or "").strip()


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "accept": "application/json, text/plain, */*",
        "accept-language": "vi-VN,vi;q=0.9,en;q=0.8",
        "affiliate-program-type": "1",
        "referer": f"{BASE}/dashboard",
        "user-agent": UA,
    })
    ck = cookie()
    if ck:
        s.headers["cookie"] = ck
    proxy = (os.environ.get("SHOPEE_PROXY") or "").strip()
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


def _get(path: str, params: dict) -> dict:
    """GET json, tự phân biệt cookie hết hạn / bị chặn IP / lỗi thật."""
    if not cookie():
        raise RevenueError(
            "Thiếu SHOPEE_COOKIE trong .env.\n"
            "Lấy: Chrome -> login affiliate.shopee.vn -> F12 -> Network -> F5 ->\n"
            "      bấm 1 request bất kỳ -> Request Headers -> copy nguyên dòng Cookie: ...\n"
            "Chỉ dán vào .env trên máy bạn. Cookie sống 7-15 ngày."
        )
    s = _session()
    for attempt in (1, 2):
        try:
            r = s.get(f"{BASE}{path}", params=params, timeout=25)
        except requests.RequestException as e:
            if attempt == 2:
                raise RevenueError(f"Không gọi được dashboard: {e}") from e
            time.sleep(2)
            continue
        if r.status_code in (401, 403):
            raise RevenueError(
                f"HTTP {r.status_code} — cookie hết hạn hoặc IP bị chặn.\n"
                "  • Lấy lại SHOPEE_COOKIE (F12 -> Network -> Request Headers -> Cookie)\n"
                "  • Nếu vẫn 403: đặt SHOPEE_PROXY = proxy IP nhà (datacenter IP hay bị chặn)"
            )
        if r.status_code >= 400:
            raise RevenueError(f"HTTP {r.status_code}: {r.text[:200]}")
        try:
            j = r.json()
        except ValueError as e:
            raise RevenueError(f"Dashboard trả HTML thay vì JSON (bị chặn?): {r.text[:160]}") from e
        if j.get("code") not in (0, None):
            raise RevenueError(f"API code={j.get('code')} msg={j.get('msg')}")
        return j
    raise RevenueError("unreachable")


def window(days: int) -> tuple[int, int]:
    """[đầu ngày (days-1) ngày trước .. hết hôm nay] theo giờ VN, ra epoch giây."""
    now = datetime.now(VN_TZ)
    start = (now - timedelta(days=max(days, 1) - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return int(start.timestamp()), int(end.timestamp())


def _paged(path: str, params: dict, key_time: str, max_pages: int = 40) -> list[dict]:
    out: list[dict] = []
    page = 1
    while page <= max_pages:
        q = dict(params, page_num=page, page_size=100)
        j = _get(path, q)
        data = j.get("data") or {}
        rows = data.get("list") or []
        out.extend(rows)
        total = int(data.get("total_count") or 0)
        if not rows or len(out) >= total:
            break
        page += 1
    return out


def daily(days: int = 7) -> dict:
    s, e = window(days)
    j = _get("/api/v3/dashboard/detail", {"start_time": s, "end_time": e})
    return j.get("data") or {}


def click_rows(days: int = 7) -> list[dict]:
    s, e = window(days)
    return _paged("/api/v1/click_report/list", {"click_time_s": s, "click_time_e": e}, "click_time")


def order_rows(days: int = 7) -> list[dict]:
    s, e = window(days)
    return _paged("/api/v3/report/list",
                  {"purchase_time_s": s, "purchase_time_e": e, "version": 1}, "purchase_time")


def vnd(micro) -> float:
    try:
        return float(micro or 0) / MICRO
    except (TypeError, ValueError):
        return 0.0


def summary(days: int = 7) -> dict:
    """Gộp 3 nguồn lại thành 1 cục: theo ngày, theo sub_id, top sản phẩm."""
    d = daily(days)
    clicks = click_rows(days)
    orders = order_rows(days)

    by_day = []
    for row in d.get("list") or []:
        by_day.append({
            "date": row.get("ymd"),
            "clicks": row.get("clicks") or 0,
            "orders": row.get("cv_by_order") or 0,
            "order_amount_vnd": vnd(row.get("order_amount")),
            "commission_vnd": vnd(row.get("total_commission")),
            "income_vnd": vnd(row.get("total_income")),
        })

    by_sub: dict[str, dict] = {}

    def slot(sid: str) -> dict:
        k = (sid or "").strip("-") or "(không sub_id)"
        return by_sub.setdefault(k, {"sub_id": k, "clicks": 0, "orders": 0,
                                     "commission_vnd": 0.0, "items": 0, "cvr_pct": 0.0})

    for c in clicks:
        rec = slot(c.get("sub_id"))
        rec["clicks"] += 1

    items: list[dict] = []
    for o in orders:
        rec = slot(o.get("utm_content"))
        rec["orders"] += 1
        rec["commission_vnd"] += vnd(o.get("capped_commission")) or vnd(o.get("gross_commission"))
        for it in o.get("orders") or []:
            for line in it.get("items") or []:
                rec["items"] += int(line.get("qty") or 0)
                items.append({
                    "order_sn": it.get("order_sn"),
                    "item_id": line.get("item_id"),
                    "shop_id": line.get("shop_id"),
                    "shop": line.get("shop_name"),
                    "name": (line.get("item_name") or "")[:70],
                    "price_vnd": vnd(line.get("item_price")),
                    "qty": line.get("qty") or 0,
                    "commission_vnd": vnd(line.get("item_commission")),
                    "brand_rate_pct": (line.get("brand_commission_rate") or 0) / 100.0,
                    "platform_rate_pct": (line.get("platform_commission_rate") or 0) / 100.0,
                    "cat1": line.get("global_category_lv1_name"),
                    "cat3": line.get("global_category_lv3_name"),
                })

    for s in by_sub.values():
        s["cvr_pct"] = round(100.0 * s["orders"] / s["clicks"], 2) if s["clicks"] else 0.0

    items.sort(key=lambda x: -x["commission_vnd"])
    subs = sorted(by_sub.values(), key=lambda x: (-x["commission_vnd"], -x["clicks"]))

    return {
        "days": days,
        "window": [datetime.fromtimestamp(window(days)[0], VN_TZ).strftime("%Y-%m-%d %H:%M"),
                   datetime.fromtimestamp(window(days)[1], VN_TZ).strftime("%Y-%m-%d %H:%M")],
        "totals": {
            "clicks": d.get("clicks_sum") or sum(x["clicks"] for x in by_day),
            "orders": d.get("cv_by_order_sum") or sum(x["orders"] for x in by_day),
            "order_amount_vnd": vnd(d.get("order_amount_sum")),
            "commission_vnd": vnd(d.get("total_commission_sum")),
            "income_vnd": vnd(d.get("total_income_sum")),
            "est_commission_vnd": vnd(d.get("est_commission_sum")),
            "last_update": d.get("last_update_time"),
        },
        "by_day": by_day,
        "by_sub": subs,
        "top_items": items[:15],
    }


def _fmt_money(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def _print_human(s: dict) -> None:
    t = s["totals"]
    print(f"\n== {s['days']} ngày ({s['window'][0]} → {s['window'][1]}) ==")
    print(f"Click: {t['clicks']} | Đơn: {t['orders']} | "
          f"Giá trị đơn: {_fmt_money(t['order_amount_vnd'])}đ | "
          f"Hoa hồng: {_fmt_money(t['commission_vnd'])}đ | "
          f"Thực nhận: {_fmt_money(t['income_vnd'])}đ")
    if t["last_update"]:
        print("Số liệu cập nhật tới:",
              datetime.fromtimestamp(int(t["last_update"]), VN_TZ).strftime("%Y-%m-%d %H:%M"))

    if s["by_sub"]:
        print("\n-- Theo sub_id --")
        print(f"{'sub_id':<22}{'click':>7}{'đơn':>6}{'CVR':>8}{'hoa hồng':>14}")
        for r in s["by_sub"]:
            print(f"{r['sub_id'][:21]:<22}{r['clicks']:>7}{r['orders']:>6}"
                  f"{r['cvr_pct']:>7}%{_fmt_money(r['commission_vnd']):>14}")

    if s["top_items"]:
        print("\n-- Sản phẩm ra tiền --")
        for it in s["top_items"][:8]:
            print(f"  {it['commission_vnd']:>9,.0f}đ  {it['qty']}x  "
                  f"[{it['platform_rate_pct']}%/{it['brand_rate_pct']}%]  {it['name']}")
        print("  (id để map lại: " + ", ".join(
            f"{i['shop_id']}.{i['item_id']}" for i in s['top_items'][:5]) + ")")


def main() -> int:
    days = 7
    as_json = "--json" in sys.argv
    for i, a in enumerate(sys.argv):
        if a == "--days" and i + 1 < len(sys.argv):
            try:
                days = max(1, int(sys.argv[i + 1]))
            except ValueError:
                pass
            break
    try:
        s = summary(days)
    except RevenueError as e:
        print(f"[!] {e}", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(s, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
