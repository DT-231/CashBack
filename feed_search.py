"""Tìm sản phẩm trong FILE FEED có sẵn (CSV/JSON) — đường ổn định nhất.

Mày đã tải được Product Feed từ dashboard affiliate thì đây là nguồn tốt nhất:
không bị chặn, có sẵn %hoa hồng, chạy 0 đồng. AI chỉ cần đưa tên -> tool trả link.
"""
import csv
import difflib
import json
import os
import re
import unicodedata
from pathlib import Path

# tên cột có thể gặp ở các bản feed khác nhau
COLS = {
    "item_id": ["itemid", "item_id", "product_id", "id", "id_san_pham", "ma_san_pham", "ma_sp"],
    "shop_id": ["shopid", "shop_id", "shopid_", "seller_id", "id_shop", "ma_shop"],
    "name": ["product_name", "item_name", "name", "title", "ten_san_pham", "ten"],
    "price": ["price", "price_min", "sale_price", "gia", "gia_ban", "price_max"],
    "comm_rate": ["commission_rate", "commission", "comm_rate", "rate", "hoa_hong",
                  "ty_le_hoa_hong", "commission_percent"],
    "sales": ["sales", "sold", "item_sold", "sold_30d", "da_ban", "luot_ban"],
    "url": ["product_link", "product_url", "url", "link", "item_link", "link_san_pham"],
    "image": ["image_link", "image_url", "image", "img", "link_anh", "anh"],
}

_cache = {"path": None, "mtime": 0, "rows": []}


def _strip_accents(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


def _tokens(s):
    return [t for t in re.split(r"[^a-z0-9]+", _strip_accents(s)) if len(t) > 1]


def _norm_key(s):
    """'ID Sản phẩm' -> 'idsanpham' — để khớp tên cột bất kể hoa/thường, dấu, khoảng trắng."""
    return re.sub(r"[^a-z0-9]+", "", _strip_accents(s))


def _pick(row, keys):
    cols = {_norm_key(k): v for k, v in row.items() if k}
    for k in keys:
        v = cols.get(_norm_key(k))
        if v is not None and str(v).strip() != "":
            return v
    # tên cột lệch nhẹ ("Commission Rate (%)" vs "commission_rate")
    for ck, v in cols.items():
        if not ck or not str(v).strip():
            continue
        for k in keys:
            nk = _norm_key(k)
            if len(nk) >= 4 and difflib.SequenceMatcher(None, ck, nk).ratio() >= 0.88:
                return v
    return None


def _num(v, default=0):
    """Đọc số kiểu VN lẫn US: '690.000' -> 690000, '259,000' -> 259000, '8%' -> 8, '0,08' -> 0.08."""
    s = str(v or "").replace("%", "").replace("\u00a0", "").replace(" ", "").strip()
    if not s:
        return default
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
    except Exception:  # noqa: BLE001
        return default


def _record(row):
    item_id = _pick(row, COLS["item_id"])
    shop_id = _pick(row, COLS["shop_id"])
    name = _pick(row, COLS["name"])
    if not name:
        return None
    url = _pick(row, COLS["url"]) or ""
    if not (item_id and shop_id) and url:
        m = re.search(r"-i\.(\d+)\.(\d+)", url) or re.search(r"/product/(\d+)/(\d+)", url)
        if m:
            shop_id, item_id = m.group(1), m.group(2)
    return {
        "item_id": int(_num(item_id)) if item_id else None,
        "shop_id": int(_num(shop_id)) if shop_id else None,
        "name": str(name).strip(),
        "price": int(_num(_pick(row, COLS["price"]))),
        "comm_rate": round(_num(_pick(row, COLS["comm_rate"])) * (100 if _num(_pick(row, COLS["comm_rate"])) < 1 else 1), 2),
        "sold": int(_num(_pick(row, COLS["sales"]))),
        "image": (_pick(row, COLS["image"]) or ""),
        "feed_url": url,
    }


def _load(path):
    p = Path(path)
    if not p.exists():
        return []
    if _cache["path"] == str(p) and _cache["mtime"] == p.stat().st_mtime:
        return _cache["rows"]

    rows = []
    if p.suffix.lower() in (".json", ".jsonl"):
        raw = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("items") or raw.get("data") or []
        rows = [r for r in (_record(x) for x in raw) if r]
    else:
        # đọc được cả CSV utf-8 và utf-8-sig (Excel hay thêm BOM), và CSV ngăn ';' / tab
        head = p.read_text(encoding="utf-8-sig", errors="ignore")[:4096].splitlines()[:1]
        delim = ","
        if head:
            delim = max([",", ";", "\t", "|"], key=lambda d: head[0].count(d)) or ","
        with open(p, newline="", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f, delimiter=delim)
            rows = [r for r in (_record(x) for x in reader) if r]

    _cache.update(path=str(p), mtime=p.stat().st_mtime, rows=rows)
    return rows


def search(keyword, limit=10):
    path = os.environ.get("FEED_FILE", "").strip()
    if not path:
        return {"ok": False, "items": [], "error": "chưa đặt FEED_FILE trong .env", "source": "feed"}

    rows = _load(path)
    if not rows:
        return {"ok": False, "items": [], "error": f"feed rỗng hoặc không đọc được: {path}", "source": "feed"}

    kw_tokens = set(_tokens(keyword))
    kw_norm = _strip_accents(keyword)
    scored = []
    for r in rows:
        name_norm = _strip_accents(r["name"])
        if kw_norm and kw_norm in name_norm:
            score = 1.0
        else:
            overlap = len(kw_tokens & set(_tokens(r["name"]))) / max(1, len(kw_tokens))
            ratio = difflib.SequenceMatcher(None, kw_norm, name_norm).ratio()
            score = 0.7 * overlap + 0.3 * ratio
        if score >= 0.3:
            scored.append((score, r))

    scored.sort(key=lambda x: (-x[0], -x[1]["sold"]))
    items = []
    for score, r in scored[: max(1, min(int(limit), 60))]:
        items.append({
            "item_id": r["item_id"], "shop_id": r["shop_id"], "name": r["name"],
            "price": r["price"], "sold": r["sold"], "comm_rate": r["comm_rate"],
            "image": r["image"], "match_score": round(score, 3),
        })
    return {"ok": bool(items), "items": items,
            "error": None if items else "feed không có sản phẩm nào khớp tên", "source": "feed"}
