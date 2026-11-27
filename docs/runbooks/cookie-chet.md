# Runbook — Cookie Shopee hết hạn / chết

Có 2 cookie khác host: `SHOPEE_COOKIE` (affiliate.shopee.vn, dashboard/báo cáo — runbook này) và `SHOPEE_WEB_COOKIE` (shopee.vn, search — xem `shopee-403.md`).

**Dấu hiệu:** `scripts/revenue_report.py` báo `HTTP 401/403 — cookie hết hạn`; sync dừng (về sau: cảnh báo Telegram).
1. Chrome → đăng nhập `affiliate.shopee.vn` → F12 → Network → F5 → bấm 1 request → Request Headers → copy dòng `Cookie`.
2. Dán vào `SHOPEE_COOKIE` trong `.env` **trên máy chạy sync** (không gửi qua chat, không commit).
3. Chạy `python3 backend/scripts/revenue_report.py --days 1`; có số liệu là xong.
4. Vẫn 403: IP bị chặn → đặt `SHOPEE_PROXY` bằng proxy IP nhà.
**Cách khuyến nghị (T-063): lưu cookie mã hóa trong DB thay vì `.env`.** Admin (đã bật TOTP) gọi `PUT /api/v1/admin/shopee-session {"cookie": "<dòng Cookie>"}`: cookie được mã hóa AES-GCM bằng `BANK_ENC_KEY`, **không có đường nào đọc lại** qua API/log/audit (audit chỉ ghi số byte). Worker (`main_worker sync-once`, MOCK=0) dùng cookie trong DB thay cho `SHOPEE_COOKIE`. Xem trạng thái: `GET /api/v1/admin/shopee-session/status` → `healthy | degraded | blocked | unknown`, `failure_count`, `last_ok_at` (nền cho cảnh báo T-023). Đặt cookie mới thì trạng thái về `unknown` và đếm lỗi về 0. Mất `BANK_ENC_KEY` thì worker coi như chưa có cookie trong DB (rơi về `SHOPEE_COOKIE` nếu có): dán lại cookie.

**Trong lúc chờ:** không chuyển tiền pending→available (quy tắc tiền); dùng import CSV báo cáo thủ công (T-024).
