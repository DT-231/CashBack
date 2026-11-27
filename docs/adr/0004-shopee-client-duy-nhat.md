# ADR 0004 — Chỉ `integrations/shopee` được gọi Shopee; chỉ `wallet` đổi số dư

- **Trạng thái:** chấp nhận; ép bằng `backend/tests/contract/test_architecture.py`.
- **Bối cảnh:** trước đây 5 nơi gọi Shopee với 3 User-Agent và 2 tên biến cookie; endpoint nội bộ của Shopee dễ đổi.
- **Quyết định:** `ShopeeClient` (và `FakeShopeeClient` cho `MOCK=1`) là điểm duy nhất; nghiệp vụ nhận dữ liệu qua nó. `os.environ` chỉ đọc ở `core/config.py`. Chỉ `modules/wallet` ghi `wallets`/`wallet_entries`.
- **Hệ quả:** vi phạm làm CI đỏ. Khi Shopee đổi API chỉ sửa một file.
