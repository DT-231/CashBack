# Lỗi X thì xem file nào

Chạy: `make venv` (một lần), `MOCK=1 python -m app.main_api` (trong `backend/`), `make test`, log JSON ra stderr (mỗi dòng có `request_id`; header `x-request-id` trả về cho client).

| Triệu chứng | Xem |
|---|---|
| Link affiliate sai (utm, sub_id) | `modules/links/affiliate_link.py`; khóa bởi `tests/contract/test_make_link_golden.py` + golden JSON |
| `sub_id` "chữ ký sai" / đơn thành mồ côi | `core/subid.py`, `SUBID_SECRET` (đổi khóa là mất khớp), `tests/unit/test_subid.py` |
| Tìm sản phẩm trống / sai nguồn | `modules/products/service.py` (nhật ký `tried` trong response), `feed.py`, runbook `shopee-403.md` |
| 403/429, cookie hết hạn | `integrations/shopee/client.py`, runbook `cookie-chet.md` |
| 401 từ Tool API | `modules/agent_auth/`; `AGENT_API_KEY` hoặc bảng `agent_keys`; `HOST` ngoài localhost bắt buộc có khóa |
| 503 `not_configured` | thiếu biến (message nêu rõ tên): `core/config.py`, `.env.example` |
| Số liệu doanh thu lệch | `modules/reports/service.py` (tiền micro-VND, ×1e5 chỉ ở `core/money.py`) |
| Migration lỗi | `backend/migrations/`, `make test-db` |
| Tái hiện lỗi bằng dữ liệu mẫu | `MOCK=1` + `FakeShopeeClient` (fixtures ở `integrations/shopee/fixtures/`); `python backend/scripts/revenue_report.py` |
| CI đỏ ở `test_architecture` | vi phạm luật phụ thuộc: gọi Shopee ngoài `integrations/`, đọc env ngoài `config.py`, api→repository, ghi ví ngoài `wallet` |
