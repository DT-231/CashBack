"""Tìm sản phẩm bằng BROWSER THẬT (Playwright) — dùng khi API nội bộ bị 403.

Không cần cookie kỹ thuật, nhưng:
  pip install playwright && playwright install chromium
Chậm hơn API (~4-8s/lần), tốn RAM. Chỉ bật khi cần.
Nếu Shopee bắt đăng nhập: chạy login_save_state.py một lần, rồi đặt PW_STATE=state.json
"""
import os
import re
from urllib.parse import quote

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def search(keyword, limit=10):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "items": [], "source": "browser",
                "error": "chưa cài playwright: pip install playwright && playwright install chromium"}

    state = os.environ.get("PW_STATE", "").strip()
    limit = max(1, min(int(limit), 40))
    items, err = [], None
    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=os.environ.get("HEADLESS", "1") == "1",
                                        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(
                locale="vi-VN", user_agent=UA,
                viewport={"width": 1366, "height": 900},
                storage_state=state if state and os.path.exists(state) else None,
            )
            page = ctx.new_page()
            page.goto(f"https://shopee.vn/search?keyword={quote(keyword)}", timeout=60000,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(4500)
            for _ in range(3):
                page.mouse.wheel(0, 1600)
                page.wait_for_timeout(1200)

            raw = page.eval_on_selector_all(
                "a[href*='-i.']",
                """els => els.map(e => ({href: e.href, text: (e.innerText||'').trim()}))""",
            )
            seen = set()
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
                items.append({
                    "item_id": item_id, "shop_id": shop_id,
                    "name": text.split("\n")[0][:160] or f"item {item_id}",
                    "price": int(price_m.group(1).replace(".", "")) if price_m else 0,
                    "sold": 0, "rating": 0, "image": "",
                })
                if len(items) >= limit:
                    break
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    finally:
        try:
            if browser:
                browser.close()
        except Exception:  # noqa: BLE001
            pass

    return {"ok": bool(items), "items": items, "source": "browser",
            "error": err or (None if items else "không thấy sản phẩm (bị captcha/login?)")}
