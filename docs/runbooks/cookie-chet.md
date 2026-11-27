# Runbook — Cookie Shopee hết hạn / chết

Có 2 cookie khác host: `SHOPEE_COOKIE` (affiliate.shopee.vn, dashboard/báo cáo — runbook này) và `SHOPEE_WEB_COOKIE` (shopee.vn, search — xem `shopee-403.md`).

**Dấu hiệu:** `scripts/revenue_report.py` báo `HTTP 401/403 — cookie hết hạn`; sync dừng (về sau: cảnh báo Telegram).
1. Chrome → đăng nhập `affiliate.shopee.vn` → F12 → Network → F5 → bấm 1 request → Request Headers → copy dòng `Cookie`.
2. Dán vào `SHOPEE_COOKIE` trong `.env` **trên máy chạy sync** (không gửi qua chat, không commit).
3. Chạy `python3 backend/scripts/revenue_report.py --days 1`; có số liệu là xong.
4. Vẫn 403: IP bị chặn → đặt `SHOPEE_PROXY` bằng proxy IP nhà.
**Trong lúc chờ:** không chuyển tiền pending→available (quy tắc tiền); dùng import CSV báo cáo thủ công (T-024).
