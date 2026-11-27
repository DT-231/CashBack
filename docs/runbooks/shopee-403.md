# Runbook — Shopee trả 403/429 khi tìm sản phẩm

1. `GET /api/v1/agent/search?...` trả `tried: ["...api:HTTP 403..."]` → engine `api` bị chặn.
2. Dùng feed: tải Product Feed từ dashboard → `python3 backend/scripts/feed_import.py <file> -o feed.csv` → `FEED_FILE=feed.csv`. `SEARCH_ENGINE=auto` tự ưu tiên feed.
3. Hoặc cookie **shopee.vn** mới vào `SHOPEE_WEB_COOKIE` (KHÔNG phải `SHOPEE_COOKIE` của affiliate.shopee.vn; dùng nhầm thì luôn 403) / `SHOPEE_PROXY`. Thiếu `SHOPEE_WEB_COOKIE` thì engine `api` báo lỗi ngay, không retry; 403 cũng không retry.
4. Engine `browser` (Playwright) là phương án cuối: `backend/scripts/login_save_state.py` rồi `PW_STATE=state.json`.
Kết quả lỗi **không** được cache (chỉ cache thành công, TTL `SHOPEE_CACHE_TTL`).
