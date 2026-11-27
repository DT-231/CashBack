#!/usr/bin/env python3
"""Đổi file Product Feed (CSV Shopee export) -> feed.csv chuẩn cho feed_search.py.

Vì sao cần: feed_search.py đọc được nhiều tên cột, nhưng feed Shopee export ra
thường lệch (dấu BOM, phân cách ';', giá '690.000', rate '8%', item_id chỉ nằm
trong link dạng -i.7001.900001). Script này chuẩn hoá hết về 1 format, bỏ dòng rác,
rồi in ra thống kê để bạn biết feed có dùng được không.

Dùng:
    python3 feed_import.py feed_goc.csv                 # -> feed.csv
    python3 feed_import.py feed_goc.csv -o data/feed.csv --min-rate 5 --min-sales 50
    python3 feed_import.py feed_goc.csv --dry-run       # chỉ xem, không ghi

Sau đó thêm vào .env:
    FEED_FILE=./feed.csv
"""
import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

import feed_search

OUT_COLS = ["itemid", "shopid", "product_name", "price", "commission_rate",
            "sales", "product_link", "image_link"]

# link dạng https://shopee.vn/ten-san-pham-i.7001.900001  hoặc /product/7001/900001
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


def sniff_delim(line):
    best, best_n = ",", -1
    for d in (",", ";", "\t", "|"):
        n = line.count(d)
        if n > best_n:
            best, best_n = d, n
    return best


def to_int(v, default=0):
    if v is None:
        return default
    s = str(v).strip()
    if not s:
        return default
    s = re.sub(r"[^\d\-]", "", s)
    try:
        return int(s)
    except ValueError:
        return default


def to_float(v, default=0.0):
    if v is None:
        return default
    s = str(v).strip().replace("%", "")
    if not s:
        return default
    # 1.250.000 (VN) / 1,250,000 (US) / 259,5 / 690.000
    s = s.replace("\u00a0", "").replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
        s = s.replace(",", "")
    elif s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return default


def ids_from_url(url):
    if not url:
        return None, None
    m = RE_I.search(url) or RE_PRODUCT.search(url)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))  # shop_id, item_id


def find_header(rows):
    """Feed Shopee có thể có vài dòng tiêu đề quảng cáo phía trên -> tìm dòng header thật."""
    best_i, best_score = 0, -1
    keys = {feed_search._norm_key(k) for v in feed_search.COLS.values() for k in v}
    for i, row in enumerate(rows[:15]):
        cells = [feed_search._norm_key(c) for c in row]
        score = sum(1 for c in cells if c in keys)
        if score > best_score:
            best_i, best_score = i, score
    return best_i


def convert(src, out_path=None, min_rate=0.0, min_sales=0, keep_zero_rate=True, dry_run=False):
    text, enc = sniff_text(src)
    first_line = text.split("\n", 1)[0]
    delim = sniff_delim(first_line)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return {"ok": False, "error": "file rỗng"}

    h_i = find_header(rows)
    header = [str(c or "").strip() for c in rows[h_i]]
    body = [r for r in rows[h_i + 1:] if any(str(c).strip() for c in r)]
    reader_rows = [dict(zip(header, r + [""] * (len(header) - len(r)))) for r in body]

    detected = {}
    for field, cands in feed_search.COLS.items():
        for c in header:
            if c and feed_search._pick({c: "x"}, cands) is not None:
                detected[field] = c
                break

    kept, dropped, seen = [], {}, set()
    for row in reader_rows:
        item_id = to_int(feed_search._pick(row, feed_search.COLS["item_id"]))
        shop_id = to_int(feed_search._pick(row, feed_search.COLS["shop_id"]))
        url = (feed_search._pick(row, feed_search.COLS["url"]) or "").strip()
        if (not item_id or not shop_id) and url:
            s, i = ids_from_url(url)
            shop_id = shop_id or (s or 0)
            item_id = item_id or (i or 0)
        name = (feed_search._pick(row, feed_search.COLS["name"]) or "").strip()

        if not item_id or not shop_id:
            dropped["thiếu item_id/shop_id"] = dropped.get("thiếu item_id/shop_id", 0) + 1
            continue
        if not name:
            dropped["thiếu tên sản phẩm"] = dropped.get("thiếu tên sản phẩm", 0) + 1
            continue
        key = (shop_id, item_id)
        if key in seen:
            dropped["trùng item"] = dropped.get("trùng item", 0) + 1
            continue
        seen.add(key)

        rate = to_float(feed_search._pick(row, feed_search.COLS["comm_rate"]))
        sales = to_int(feed_search._pick(row, feed_search.COLS["sales"]))
        price = to_float(feed_search._pick(row, feed_search.COLS["price"]))

        if min_rate and rate < min_rate:
            dropped["rate dưới ngưỡng"] = dropped.get("rate dưới ngưỡng", 0) + 1
            continue
        if min_sales and sales < min_sales:
            dropped["sales dưới ngưỡng"] = dropped.get("sales dưới ngưỡng", 0) + 1
            continue
        if not rate and not keep_zero_rate:
            dropped["rate = 0"] = dropped.get("rate = 0", 0) + 1
            continue

        kept.append({
            "itemid": item_id, "shopid": shop_id, "product_name": name,
            "price": int(price), "commission_rate": rate, "sales": sales,
            "product_link": url or f"https://shopee.vn/product/{shop_id}/{item_id}",
            "image_link": (feed_search._pick(row, feed_search.COLS["image"]) or "").strip(),
        })

    # sắp theo "tiền tiềm năng": price * rate% * sold (chỉ để dễ soi, feed_search tự xếp lại)
    kept.sort(key=lambda r: -(r["price"] * r["commission_rate"] / 100 * max(r["sales"], 1)))

    result = {
        "ok": bool(kept), "encoding": enc, "delimiter": delim,
        "header_row": h_i, "columns_detected": detected,
        "rows_total": len(reader_rows), "rows_kept": len(kept), "dropped": dropped,
        "top5": [{"name": r["product_name"][:60], "price": r["price"],
                  "rate": r["commission_rate"], "sold": r["sales"],
                  "est_vnd_per_sale": round(r["price"] * r["commission_rate"] / 100)}
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


def main():
    ap = argparse.ArgumentParser(description="Chuẩn hoá Product Feed Shopee -> feed.csv")
    ap.add_argument("src", help="file CSV feed tải từ dashboard affiliate")
    ap.add_argument("-o", "--out", default="feed.csv")
    ap.add_argument("--min-rate", type=float, default=0.0, help="bỏ sản phẩm có %% hoa hồng thấp hơn")
    ap.add_argument("--min-sales", type=int, default=0, help="bỏ sản phẩm bán ít hơn N")
    ap.add_argument("--drop-zero-rate", action="store_true", help="bỏ luôn sản phẩm rate = 0")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in thống kê, không ghi file")
    ap.add_argument("--json", action="store_true", help="in JSON cho máy đọc")
    a = ap.parse_args()

    if not Path(a.src).exists():
        print(f"không thấy file: {a.src}", file=sys.stderr)
        return 1
    res = convert(a.src, a.out, a.min_rate, a.min_sales,
                  keep_zero_rate=not a.drop_zero_rate, dry_run=a.dry_run)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1

    print(f"encoding={res.get('encoding')}  delimiter={res.get('delimiter')!r}  header_row={res.get('header_row')}")
    print(f"cột nhận ra: {res.get('columns_detected')}")
    print(f"dòng đọc: {res.get('rows_total')}  ->  giữ: {res.get('rows_kept')}  bỏ: {res.get('dropped')}")
    for r in res.get("top5", []):
        print(f"  {r['rate']:>5}%  {r['price']:>10,}đ  bán {r['sold']:>6}  ~{r['est_vnd_per_sale']:>7,}đ/đơn  {r['name']}")
    if res.get("ok"):
        print(f"xong -> {res.get('output') or '(dry-run)'}")
        if not a.dry_run:
            print(f"thêm vào .env:  FEED_FILE={res.get('output')}")
        return 0
    print(f"LỖI: {res.get('error')}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
