"""Chuẩn hoá file Product Feed (CSV Shopee export) -> feed.csv chuẩn cho feed.py.

Feed export thường lệch: BOM, phân cách ';', giá '690.000', rate '8%', item_id chỉ nằm trong link
-i.7001.900001, vài dòng tiêu đề quảng cáo phía trên. Hàm `convert` chuẩn hoá hết và thống kê.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from app.core.money import parse_vn_number
from app.modules.products.feed import COLS, norm_key, pick

OUT_COLS = ["itemid", "shopid", "product_name", "price", "commission_rate", "sales", "product_link", "image_link"]
RE_I = re.compile(r"-i\.(\d+)\.(\d+)")
RE_PRODUCT = re.compile(r"/product/(\d+)/(\d+)")


def sniff_text(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1258", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace"), "utf-8?"


def sniff_delim(line: str) -> str:
    best, best_n = ",", -1
    for d in (",", ";", "\t", "|"):
        n = line.count(d)
        if n > best_n:
            best, best_n = d, n
    return best


def to_int(v, default=0) -> int:
    s = re.sub(r"[^\d\-]", "", str(v).strip()) if v is not None else ""
    try:
        return int(s)
    except ValueError:
        return default


def to_float(v, default=0.0) -> float:
    return float(parse_vn_number(v, default=default))


def ids_from_url(url):
    m = RE_I.search(url or "") or RE_PRODUCT.search(url or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)   # shop_id, item_id


def find_header(rows) -> int:
    """Feed Shopee có thể có vài dòng tiêu đề quảng cáo phía trên -> tìm dòng header thật."""
    best_i, best_score = 0, -1
    keys = {norm_key(k) for v in COLS.values() for k in v}
    for i, row in enumerate(rows[:15]):
        score = sum(1 for c in (norm_key(c) for c in row) if c in keys)
        if score > best_score:
            best_i, best_score = i, score
    return best_i


def convert(src, out_path=None, min_rate=0.0, min_sales=0, keep_zero_rate=True, dry_run=False) -> dict:
    text, enc = sniff_text(src)
    delim = sniff_delim(text.split("\n", 1)[0])
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return {"ok": False, "error": "file rỗng"}

    h_i = find_header(rows)
    header = [str(c or "").strip() for c in rows[h_i]]
    body = [r for r in rows[h_i + 1:] if any(str(c).strip() for c in r)]
    reader_rows = [dict(zip(header, r + [""] * (len(header) - len(r)))) for r in body]

    detected = {}
    for field, cands in COLS.items():
        for c in header:
            if c and pick({c: "x"}, cands) is not None:
                detected[field] = c
                break

    kept, dropped, seen = [], {}, set()

    def drop(why):
        dropped[why] = dropped.get(why, 0) + 1

    for row in reader_rows:
        item_id, shop_id = to_int(pick(row, COLS["item_id"])), to_int(pick(row, COLS["shop_id"]))
        url = (pick(row, COLS["url"]) or "").strip()
        if (not item_id or not shop_id) and url:
            s, i = ids_from_url(url)
            shop_id, item_id = shop_id or (s or 0), item_id or (i or 0)
        name = (pick(row, COLS["name"]) or "").strip()

        if not item_id or not shop_id:
            drop("thiếu item_id/shop_id"); continue  # noqa: E702
        if not name:
            drop("thiếu tên sản phẩm"); continue  # noqa: E702
        if (shop_id, item_id) in seen:
            drop("trùng item"); continue  # noqa: E702
        seen.add((shop_id, item_id))

        rate = to_float(pick(row, COLS["comm_rate"]))
        sales = to_int(pick(row, COLS["sales"]))
        price = to_float(pick(row, COLS["price"]))
        if min_rate and rate < min_rate:
            drop("rate dưới ngưỡng"); continue  # noqa: E702
        if min_sales and sales < min_sales:
            drop("sales dưới ngưỡng"); continue  # noqa: E702
        if not rate and not keep_zero_rate:
            drop("rate = 0"); continue  # noqa: E702

        kept.append({"itemid": item_id, "shopid": shop_id, "product_name": name, "price": int(price),
                     "commission_rate": rate, "sales": sales,
                     "product_link": url or f"https://shopee.vn/product/{shop_id}/{item_id}",
                     "image_link": (pick(row, COLS["image"]) or "").strip()})

    # sắp theo "tiền tiềm năng": price * rate% * sold (chỉ để dễ soi)
    kept.sort(key=lambda r: -(r["price"] * r["commission_rate"] / 100 * max(r["sales"], 1)))

    result = {
        "ok": bool(kept), "encoding": enc, "delimiter": delim, "header_row": h_i, "columns_detected": detected,
        "rows_total": len(reader_rows), "rows_kept": len(kept), "dropped": dropped,
        "top5": [{"name": r["product_name"][:60], "price": r["price"], "rate": r["commission_rate"],
                  "sold": r["sales"], "est_vnd_per_sale": round(r["price"] * r["commission_rate"] / 100)}
                 for r in kept[:5]],
        "output": str(out_path) if out_path else None,
    }
    if not kept:
        result["error"] = "không giữ được dòng nào — kiểm tra lại tên cột trong file feed"
        return result
    if not dry_run:
        out = Path(out_path or "feed.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=OUT_COLS)
            w.writeheader()
            w.writerows(kept)
        result["output"] = str(out)
    return result
