#!/usr/bin/env python3
"""Chạy MỘT LẦN trên máy bạn (cần màn hình): mở Shopee -> bạn đăng nhập tay -> lưu phiên vào state.json
để engine 'browser' dùng.

  pip install playwright && playwright install chromium
  python3 backend/scripts/login_save_state.py     # rồi thêm vào .env:  PW_STATE=state.json
"""
import _bootstrap  # noqa: F401
from app.core.config import load_settings

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit("Chưa cài: pip install playwright && playwright install chromium")

OUT = load_settings().pw_state or "state.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(locale="vi-VN")
    page = ctx.new_page()
    page.goto("https://shopee.vn", timeout=90000)
    input("Đăng nhập xong (thấy avatar góc phải) thì bấm Enter tại đây... ")
    ctx.storage_state(path=OUT)
    browser.close()

print(f"Đã lưu phiên vào {OUT}. Thêm vào .env: PW_STATE={OUT}")
