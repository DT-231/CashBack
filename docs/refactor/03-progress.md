# 03 — Tiến độ refactor

Nhánh `refactor/restructure`. Mỗi dòng = một bước trong `02-target.md` §6. Test xanh trước và sau mỗi bước.

| Bước | Commit | Test thêm / bảo vệ | Ghi chú |
|---|---|---|---|
| 0 | `c92d150` | — | Audit + kế hoạch. Quyết định D1–D3 (Postgres ngay) |
| 1 | `7a6eda5` `3c8f1db` | — | `backend/pyproject.toml`, `Makefile`, `.venv/`; xóa 3 import thừa (commit riêng) |
| 2 | `eb284c3` | 73 test + golden `search_mock.json`/`link_tt09.json` + 4 xfail (#1–#4) | Port `test_offline.py`; đột biến `utm_medium` làm test fail. Coverage 41 → 71 % |
| 3 | `73fc61e` | config / errors / logging | `Settings` đọc env một lần; log JSON che dữ liệu nhạy cảm |
| 4 | `3619eee` | `test_make_link_golden`, `test_money`, `test_subid` | `subid` → `core/`; `make_link` thành hàm thuần (`LinkConfig`); golden không đổi |
| 5 | `0be98e9` | client/fake/cache/reports/`test_architecture` | Một `ShopeeClient` + `FakeShopeeClient`; tiền trong báo cáo là micro nguyên |
| 6 | `9416f3f` | products feed/service/feed_import | Điểm số tìm kiếm giữ nguyên; tên chuẩn hóa tính một lần khi nạp |
| 7 | `f59ed14` | `test_migrations` (up→down→up trên DB tạm) | Migration/seed/schema test vào `backend/`; `0002` thêm 9 index, có `downgrade` |
| 8 | `1132d89` | integration Tool API, `test_legacy_api` | FastAPI + Postgres; golden giữ nguyên trừ `click_url` (xem dưới) |
| 9 | `eb1a2e6` | `test_known_bugs` (xfail → pass) | Sửa #2 #3 #4 #18; #1 và #5 hết do thiết kế |
| 10 | `2d1a77e` | smoke CLI (MOCK=1) | Xóa 8 module gốc + test cũ; `tools/*.json` bỏ 2 tool đã hết endpoint |
| fix | `fa0d808` | hồi quy: khóa trong `agent_keys` + engine lười | Phát hiện khi tự rà soát; test tích hợp trước đó truyền engine nên không thấy |
| 11 | `9daf57a` | — | README, AGENTS, `.env.example`, CI, PR template, 4 ADR, 2 runbook, how-to, `_template/` |

## Thay đổi hành vi có chủ đích (khác "giữ nguyên")

Tất cả đã được PO duyệt ở Checkpoint 1–2 (D1–D3) hoặc theo `docs/08`:
- **Bỏ** `GET /go/<sub_id>`, `/api/stats`, `/api/revenue` và trường `click_url` của `POST /api/link` (SQLite bị bỏ; `/go` chuyển sang Cloudflare Worker; doanh thu qua `scripts/revenue_report.py`).
- `limit`/`item_id` không phải số: 500 (kết nối đứt) → **400**. Khi cấu hình `AGENT_API_KEY` hoặc `HOST` ngoài localhost: `/api/search`, `/api/link` đòi Bearer key. CORS mặc định tắt (trước đây `*`).
- `/api/search` không có `sub`: tiền tố `api-<i>` (trước đây 12 ký tự đầu của keyword).
- `/health`: `feed_file` (đường dẫn) → `feed_configured` (bool).
- `/api/revenue` (nay là script) trả tiền dạng micro nguyên (`*_micro`, `*_rate_bp`) thay vì float VND.
- Dưới `MOCK=1`: engine `browser` bị tắt, dashboard dùng dữ liệu mẫu (trước đây có thể gọi live).
- Thống nhất User-Agent Shopee (Chrome 157/macOS). **Chưa kiểm live**: search trước đây dùng Chrome 124/Windows.
- `affiliate.make_link` và golden link: **không đổi** (test khóa từ bước 2).
