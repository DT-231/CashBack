"""NƠI DUY NHẤT gọi Shopee (search nội bộ + dashboard affiliate). Nghiệp vụ không gọi thẳng ra ngoài.

- `search(...)`: endpoint nội bộ của Shopee web, KHÔNG phải API công khai, có thể đổi bất kỳ lúc nào.
- `dashboard_snapshot(days)`: số liệu thật từ affiliate.shopee.vn (cần cookie). 3 endpoint lấy từ HAR thật:
    GET /api/v3/dashboard/detail?start_time=&end_time=
    GET /api/v1/click_report/list?click_time_s=&click_time_e=&page_num=&page_size=
    GET /api/v3/report/list?purchase_time_s=&purchase_time_e=&page_num=&page_size=&version=1
- Tiền Shopee trả là số nguyên ×1e5 (micro-VND). Client trả nguyên giá trị, không quy đổi.

MOCK=1 dùng FakeShopeeClient (fake.py) với fixture ẩn danh, không đụng mạng.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from app.core.cache import TTLCache
from app.core.config import Settings
from app.core.money import micro_to_vnd_round
from app.integrations.shopee.errors import ShopeeBlockedError, ShopeeConfigError, ShopeeError

AFFILIATE_BASE = "https://affiliate.shopee.vn"
PAGE_SIZE = 100
VN_TZ = timezone(timedelta(hours=7))
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36")


@dataclass
class DashboardSnapshot:
    window: tuple[int, int]            # epoch giây [đầu, cuối]
    daily: dict = field(default_factory=dict)
    clicks: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)


def window(days: int, now: datetime | None = None) -> tuple[int, int]:
    """[đầu ngày (days-1) ngày trước .. hết hôm nay] theo giờ VN, ra epoch giây."""
    now = now or datetime.now(VN_TZ)
    start = (now - timedelta(days=max(days, 1) - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return int(start.timestamp()), int(end.timestamp())


class ShopeeClient:
    def __init__(self, settings: Settings, sleep=time.sleep):
        self.s = settings
        self._sleep = sleep
        self._cache = TTLCache(settings.shopee_cache_ttl)
        self._local = threading.local()   # mỗi luồng giữ session riêng (requests.Session không an toàn đa luồng)

    # ---------- chung ----------
    def _cookie(self) -> str:
        return self.s.shopee_cookie.get_secret_value().strip()

    def _session(self, headers: dict, kind: str = "search") -> requests.Session:
        """Session dùng lại theo (luồng, kind) để giữ Set-Cookie và kết nối TLS.

        Tách riêng search (shopee.vn), dash (affiliate.shopee.vn) và check (link người dùng) để header
        Cookie/Referer của host này không dính sang host kia.
        """
        sess = getattr(self._local, kind, None)
        if sess is None:
            sess = requests.Session()
            proxy = self.s.shopee_proxy.strip()
            if proxy:
                sess.proxies = {"http": proxy, "https": proxy}
            setattr(self._local, kind, sess)
        sess.headers.update(headers)   # chỉ cập nhật, không reset
        return sess

    @property
    def _ua(self) -> str:
        return self.s.shopee_ua or DEFAULT_UA

    # ---------- search ----------
    def search(self, keyword: str, limit: int = 10, sort: str = "relevancy") -> dict:
        """Trả {"ok", "items", "error", "source"}. Không ném lỗi mạng; gói vào `error`."""
        limit = max(1, min(int(limit), 60))
        key = ("search", keyword, limit, sort)
        return self._cache.get_or_set(key, lambda: self._search_live(keyword, limit, sort),
                                      cacheable=lambda r: bool(r.get("ok")))

    def _search_headers(self, keyword: str) -> dict:
        h = {
            "User-Agent": self._ua, "Accept": "application/json",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            "Referer": "https://shopee.vn/search?keyword=" + requests.utils.quote(keyword),
            "X-Requested-With": "XMLHttpRequest", "X-API-SOURCE": "pc", "X-Shopee-Language": "vi",
        }
        # Cookie của shopee.vn. TUYỆT ĐỐI không fallback sang cookie affiliate (khác host -> luôn 403)
        c = self.s.shopee_web_cookie.get_secret_value().strip()
        if c:
            h["Cookie"] = c
        enc = (self.s.shopee_web_enc_dat.get_secret_value().strip()
               or self.s.shopee_af_ac_enc_dat.get_secret_value().strip())
        if enc:   # header chống bot, đổi theo phiên
            h["af-ac-enc-dat"] = enc
        return h

    @staticmethod
    def _normalize_item(basic: dict) -> dict:
        price_raw = basic.get("price_min") or basic.get("price") or 0
        # Shopee trả giá ×1e5; heuristic cũ giữ nguyên (xem audit #8, sẽ xử lý riêng).
        price = micro_to_vnd_round(price_raw) if price_raw > 10_000_000 else int(round(price_raw))
        rating = (basic.get("item_rating") or {}).get("rating_star") or 0
        img = basic.get("image") or ""
        return {
            "item_id": basic.get("itemid"), "shop_id": basic.get("shopid"), "name": basic.get("name"),
            "price": price, "sold": basic.get("sold") or 0, "rating": round(float(rating), 2),
            "image": "https://down-vn.img.susercontent.com/file/" + img if img else "",
        }

    def _search_live(self, keyword: str, limit: int, sort: str) -> dict:
        if not self.s.shopee_web_cookie.get_secret_value().strip():
            # Không bắn 3 request để nhận 403 chung chung: báo thẳng để ProductSearch rơi sang engine kế
            return {"ok": False, "items": [], "source": "shopee",
                    "error": "Thiếu SHOPEE_WEB_COOKIE (cookie của shopee.vn, không phải affiliate.shopee.vn)"}
        params = {"by": "sales" if sort == "sales" else "relevancy", "keyword": keyword, "limit": limit,
                  "newest": 0, "order": "desc", "page_type": "search", "scenario": "PAGE_GLOBAL_SEARCH",
                  "version": 2, "item_card": 2}
        last_err = None
        for attempt in range(3):
            try:
                r = self._session(self._search_headers(keyword), "search").get(self.s.shopee_search_url, params=params,
                                                                     timeout=20)
                if r.status_code in (403, 429):
                    last_err = f"HTTP {r.status_code} (cookie/IP bị chặn — cần cookie mới hoặc proxy)"
                    self._sleep(2 + attempt * 2)
                    continue
                data = r.json()
                block = data.get("error") or data.get("error_msg")
                if block not in (None, 0, ""):
                    last_err = f"Shopee trả lỗi: {block}"
                    self._sleep(1.5)
                    continue
                items = []
                for entry in (data.get("data") or {}).get("items") or []:
                    basic = entry.get("item_basic") or entry
                    if basic.get("itemid"):
                        items.append(self._normalize_item(basic))
                if not items:
                    last_err = "Không parse được item nào (Shopee đổi schema hoặc trả trang login)"
                return {"ok": bool(items), "items": items, "error": None if items else last_err, "source": "shopee"}
            except (requests.RequestException, ValueError, AttributeError) as e:
                last_err = f"{type(e).__name__}: {e}"
                self._sleep(1.5 + attempt + random.random())
        return {"ok": False, "items": [], "error": last_err, "source": "shopee"}

    # ---------- dashboard affiliate ----------
    def _get(self, path: str, params: dict) -> dict:
        """GET json; phân biệt cookie hết hạn / bị chặn IP / lỗi thật. Thông báo lỗi không chứa cookie."""
        if not self._cookie():
            raise ShopeeConfigError(
                "Thiếu SHOPEE_COOKIE trong .env.\n"
                "Lấy: Chrome -> login affiliate.shopee.vn -> F12 -> Network -> F5 ->\n"
                "      bấm 1 request bất kỳ -> Request Headers -> copy nguyên dòng Cookie: ...\n"
                "Chỉ dán vào .env trên máy bạn. Cookie sống 7-15 ngày.")
        sess = self._session({
            "accept": "application/json, text/plain, */*", "accept-language": "vi-VN,vi;q=0.9,en;q=0.8",
            "affiliate-program-type": "1", "referer": f"{AFFILIATE_BASE}/dashboard",
            "user-agent": self._ua, "cookie": self._cookie()}, "dash")
        for attempt in (1, 2):
            try:
                r = sess.get(f"{AFFILIATE_BASE}{path}", params=params, timeout=25)
            except requests.RequestException as e:
                if attempt == 2:
                    raise ShopeeError(f"Không gọi được dashboard: {type(e).__name__}") from e
                self._sleep(2)
                continue
            if r.status_code in (401, 403):
                raise ShopeeBlockedError(
                    f"HTTP {r.status_code} — cookie hết hạn hoặc IP bị chặn.\n"
                    "  • Lấy lại SHOPEE_COOKIE (F12 -> Network -> Request Headers -> Cookie)\n"
                    "  • Nếu vẫn 403: đặt SHOPEE_PROXY = proxy IP nhà (datacenter IP hay bị chặn)")
            if r.status_code >= 400:
                raise ShopeeError(f"HTTP {r.status_code}: {r.text[:200]}")
            try:
                j = r.json()
            except ValueError as e:
                raise ShopeeError(f"Dashboard trả HTML thay vì JSON (bị chặn?): {r.text[:160]}") from e
            if j.get("code") not in (0, None):
                raise ShopeeError(f"API code={j.get('code')} msg={j.get('msg')}")
            return j
        raise ShopeeError("unreachable")

    def _paged(self, path: str, params: dict, max_pages: int = 40) -> list[dict]:
        out: list[dict] = []
        page = 1
        while page <= max_pages:
            data = self._get(path, dict(params, page_num=page, page_size=PAGE_SIZE)).get("data") or {}
            rows = data.get("list") or []
            out.extend(rows)
            if not rows:
                break
            total = data.get("total_count")
            # Chỉ tin total_count khi có (response thiếu trường này không được coi là "đã đủ")
            if isinstance(total, int) and total > 0 and len(out) >= total:
                break
            if len(rows) < PAGE_SIZE:      # trang cuối
                break
            page += 1
        return out

    def dashboard_snapshot(self, days: int = 7) -> DashboardSnapshot:
        """Một cửa sổ thời gian duy nhất cho cả 3 nguồn (tránh lệch mốc qua nửa đêm); có cache TTL."""
        return self._cache.get_or_set(("dash", days), lambda: self._snapshot_live(days))

    def _snapshot_live(self, days: int) -> DashboardSnapshot:
        s, e = window(days)
        daily = self._get("/api/v3/dashboard/detail", {"start_time": s, "end_time": e}).get("data") or {}
        clicks = self._paged("/api/v1/click_report/list", {"click_time_s": s, "click_time_e": e})
        orders = self._paged("/api/v3/report/list", {"purchase_time_s": s, "purchase_time_e": e, "version": 1})
        return DashboardSnapshot((s, e), daily, clicks, orders)

    # ---------- kiểm tra link ----------
    def check_link(self, link: str, timeout: int = 20) -> dict:
        """Đi tối đa 3 hop (không tự theo redirect) qua proxy cấu hình; dừng khi thấy `uls_trackid`.

        Link rút gọn (shope.ee) không có trackid ở hop đầu nên phải đi tiếp.
        `status`/`redirect` là của hop ĐẦU (giữ hành vi cũ); `final_*` là của hop cuối.
        """
        from urllib.parse import parse_qs, urljoin, urlparse
        sess = self._session({"User-Agent": self._ua, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
                              "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}, "check")
        url, hops = link, []
        first_status = first_location = final_status = None
        target, tracked = link, False
        for _ in range(3):
            hops.append(url)
            try:
                r = sess.get(url, allow_redirects=False, timeout=timeout)
            except requests.RequestException as e:
                raise ShopeeError(f"Không gọi được Shopee: {type(e).__name__}") from e
            location = r.headers.get("Location")
            if first_status is None:
                first_status, first_location = r.status_code, location
            final_status = r.status_code
            target = urljoin(url, location) if location else url
            tracked = bool(parse_qs(urlparse(target).query).get("uls_trackid"))
            if tracked or not location or not (300 <= r.status_code < 400):
                break
            url = target
        q = parse_qs(urlparse(target).query)
        return {"status": first_status, "redirect": first_location, "tracked": tracked,
                "utm_source": (q.get("utm_source") or [None])[0], "utm_medium": (q.get("utm_medium") or [None])[0],
                "utm_content": (q.get("utm_content") or [None])[0], "final_host": urlparse(target).netloc,
                "hops": hops, "final_url": target, "final_status": final_status}
