"""Tìm sản phẩm trong FILE FEED (CSV/JSON) tải từ dashboard affiliate — nguồn ổn định nhất:
không bị chặn, có sẵn %hoa hồng, chạy 0 đồng.
"""
from __future__ import annotations

import csv
import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.core.money import parse_vn_number

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


def strip_accents(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


def tokens(s) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", strip_accents(s)) if len(t) > 1]


def norm_key(s) -> str:
    """'ID Sản phẩm' -> 'idsanpham': khớp tên cột bất kể hoa/thường, dấu, khoảng trắng."""
    return re.sub(r"[^a-z0-9]+", "", strip_accents(s))


def pick(row: dict, keys: list[str]):
    cols = {norm_key(k): v for k, v in row.items() if k}
    for k in keys:
        v = cols.get(norm_key(k))
        if v is not None and str(v).strip() != "":
            return v
    for ck, v in cols.items():   # tên cột lệch nhẹ ("Commission Rate (%)" vs "commission_rate")
        if not ck or not str(v).strip():
            continue
        for k in keys:
            nk = norm_key(k)
            if len(nk) >= 4 and difflib.SequenceMatcher(None, ck, nk).ratio() >= 0.88:
                return v
    return None


@dataclass(frozen=True)
class FeedRow:
    item_id: int | None
    shop_id: int | None
    name: str
    price: int
    comm_rate: float
    sold: int
    image: str
    feed_url: str
    name_norm: str            # tính sẵn một lần khi nạp, không tính lại mỗi lần search
    name_tokens: frozenset


def to_record(row: dict) -> FeedRow | None:
    item_id = pick(row, COLS["item_id"])
    shop_id = pick(row, COLS["shop_id"])
    name = pick(row, COLS["name"])
    if not name:
        return None
    url = pick(row, COLS["url"]) or ""
    if not (item_id and shop_id) and url:
        m = re.search(r"-i\.(\d+)\.(\d+)", url) or re.search(r"/product/(\d+)/(\d+)", url)
        if m:
            shop_id, item_id = m.group(1), m.group(2)
    # Heuristic cũ giữ nguyên (audit #8): rate < 1 coi là phân số. 0,5% thật sẽ thành 50%.
    rate = parse_vn_number(pick(row, COLS["comm_rate"]))
    if rate < 1:
        rate *= 100
    name = str(name).strip()
    return FeedRow(
        item_id=int(parse_vn_number(item_id)) if item_id else None,
        shop_id=int(parse_vn_number(shop_id)) if shop_id else None,
        name=name, price=int(parse_vn_number(pick(row, COLS["price"]))),
        comm_rate=float(round(rate, 2)), sold=int(parse_vn_number(pick(row, COLS["sales"]))),
        image=pick(row, COLS["image"]) or "", feed_url=url,
        name_norm=strip_accents(name), name_tokens=frozenset(tokens(name)),
    )


def read_rows(path: Path) -> list[FeedRow]:
    if path.suffix.lower() in (".json", ".jsonl"):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("items") or raw.get("data") or []
        return [r for r in (to_record(x) for x in raw) if r]
    head = path.read_text(encoding="utf-8-sig", errors="ignore")[:4096].splitlines()[:1]
    delim = max([",", ";", "\t", "|"], key=lambda d: head[0].count(d)) or "," if head else ","
    with open(path, newline="", encoding="utf-8-sig", errors="ignore") as f:
        return [r for r in (to_record(x) for x in csv.DictReader(f, delimiter=delim)) if r]


class FeedStore:
    """Nạp feed và nhớ theo (đường dẫn, mtime)."""

    def __init__(self):
        self._key = None
        self._rows: list[FeedRow] = []

    def load(self, path: str) -> list[FeedRow]:
        p = Path(path)
        if not p.exists():
            return []
        key = (str(p), p.stat().st_mtime)
        if self._key != key:
            self._rows, self._key = read_rows(p), key
        return self._rows


def search_feed(store: FeedStore, path: str, keyword: str, limit: int = 10) -> dict:
    path = (path or "").strip()
    if not path:
        return {"ok": False, "items": [], "error": "chưa đặt FEED_FILE trong .env", "source": "feed"}
    rows = store.load(path)
    if not rows:
        return {"ok": False, "items": [], "error": f"feed rỗng hoặc không đọc được: {path}", "source": "feed"}

    kw_tokens = set(tokens(keyword))
    kw_norm = strip_accents(keyword)
    scored = []
    for r in rows:
        if kw_norm and kw_norm in r.name_norm:
            score = 1.0
        else:
            overlap = len(kw_tokens & r.name_tokens) / max(1, len(kw_tokens))
            ratio = difflib.SequenceMatcher(None, kw_norm, r.name_norm).ratio()
            score = 0.7 * overlap + 0.3 * ratio
        if score >= 0.3:
            scored.append((score, r))

    scored.sort(key=lambda x: (-x[0], -x[1].sold))
    items = [{"item_id": r.item_id, "shop_id": r.shop_id, "name": r.name, "price": r.price, "sold": r.sold,
              "comm_rate": r.comm_rate, "image": r.image, "match_score": round(score, 3)}
             for score, r in scored[: max(1, min(int(limit), 60))]]
    return {"ok": bool(items), "items": items,
            "error": None if items else "feed không có sản phẩm nào khớp tên", "source": "feed"}
