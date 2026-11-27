"""Tìm sản phẩm bằng BROWSER THẬT (Playwright) — dùng khi API nội bộ bị 403. Chậm (~4-8s), tốn RAM.

Cài: pip install playwright && playwright install chromium.
Shopee bắt đăng nhập: chạy scripts/login_save_state.py một lần rồi đặt PW_STATE=state.json.
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import quote

from app.core.config import Settings

log = logging.getLogger(__name__)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def parse_links(raw: list[dict], limit: int) -> list[dict]:
    """Rút item từ danh sách {href, text} của trang tìm kiếm."""
    items, seen = [], set()
    for r in raw:
        m = re.search(r"-i\.(\d+)\.(\d+)", r["href"])
        if not m:
            continue
        shop_id, item_id = int(m.group(1)), int(m.group(2))
        if item_id in seen:
            continue
        seen.add(item_id)
        text = re.sub(r"\s+", " ", r["text"] or "").strip()
        price_m = re.search(r"₫\s?([\d.]+)", text)
        items.append({"item_id": item_id, "shop_id": shop_id,
                      "name": text.split("\n")[0][:160] or f"item {item_id}",
                      "price": int(price_m.group(1).replace(".", "")) if price_m else 0,
                      "sold": 0, "rating": 0, "image": ""})
        if len(items) >= limit:
            break
    return items


def search(settings: Settings, keyword: str, limit: int = 10) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "items": [], "source": "browser",
                "error": "chưa cài playwright: pip install playwright && playwright install chromium"}

    state = settings.pw_state.strip()
    limit = max(1, min(int(limit), 40))
    items, err = [], None
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.headless,
                                        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(locale="vi-VN", user_agent=UA, viewport={"width": 1366, "height": 900},
                                      storage_state=state if state and os.path.exists(state) else None)
            page = ctx.new_page()
            page.goto(f"https://shopee.vn/search?keyword={quote(keyword)}", timeout=60000,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(4500)
            for _ in range(3):
                page.mouse.wheel(0, 1600)
                page.wait_for_timeout(1200)
            raw = page.eval_on_selector_all(
                "a[href*='-i.']", "els => els.map(e => ({href: e.href, text: (e.innerText||'').trim()}))")
            items = parse_links(raw, limit)
    except Exception as e:  # noqa: BLE001 - Playwright ném nhiều loại lỗi; biến thành thông báo cho người vận hành
        log.warning("browser search failed", extra={"error": f"{type(e).__name__}: {e}"})
        err = f"{type(e).__name__}: {e}"
    finally:
        if browser:
            try:
                browser.close()
            except Exception:  # noqa: BLE001
                log.debug("browser.close failed", exc_info=True)
    return {"ok": bool(items), "items": items, "source": "browser",
            "error": err or (None if items else "không thấy sản phẩm (bị captcha/login?)")}
