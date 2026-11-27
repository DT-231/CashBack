# 03 — Tiến độ refactor

Nhánh: `refactor/restructure`. Mỗi dòng = một bước trong `02-target.md` §6.

| Bước | Commit | Test thêm | Ghi chú |
|---|---|---|---|
| 0 | `c92d150` | — | Audit + kế hoạch. Quyết định D1–D3 đã chốt (Postgres ngay) |
| 1 | `7a6eda5`, `3c8f1db` | — | `backend/pyproject.toml`, `Makefile`, venv `.venv/` (gitignored). Lint tách commit riêng: xóa 3 import thừa, không đổi hành vi |
| 2 | (commit bước 2) | 73 test pass + 4 xfail strict: contract HTTP (port từ `test_offline.py`, có golden `search_mock.json`, `link_tt09.json`), `store`, `shopee_search`, `feed_search`, `feed_import`, `revenue`, và `test_known_bugs.py` (#1–#4) | `test_offline.py` bị xóa vì đã port (hết ghi đè `samples/sample_feed.csv`, hết cổng cố định). Test chạy 0,4 s. Đã kiểm tra bằng đột biến: đổi `utm_medium` làm 2 test golden fail. Test ghi nhận cả hành vi sai hiện tại (#8 giá ≥ 10 triệu, `0,5%` → 50%, #15 JSON hỏng) để bước 9 biết chỗ cần đổi |

## Baseline bổ sung (đo ở bước 1, thay cho các ô "chưa đo" trong 01-audit)

| Chỉ số | Giá trị |
|---|---|
| `make test-db` (Postgres) | 5 test, pass, 0,21 s |
| Tổng test | **34 pass** (16 + 3 + 10 + 5) |
| Coverage service cũ + codec | **41 %** (976 dòng). `revenue` 18 %, `feed_import` 0 %, `browser_search` 11 %, `shopee_search` 25 %, `verify_link` 0 %, `server` 71 %, `subid` 100 % |
| Lint (`ruff` E9,F) | 3 lỗi → 0 |

Chạy: `make venv`, `make test`, `make test-db`, `make lint`, `make cov`.

## Sau bước 2

| Chỉ số | Trước | Sau |
|---|---|---|
| Test (pytest + unittest + DB) | 34 | **96 pass + 4 xfail** (73 + 4 pytest, 3 + 10 unittest, 5 DB, khi tính cả xfail) |
| Coverage | 41 % | **71 %** (`revenue` 18→75, `feed_import` 0→75, `feed_search` 82→98, `shopee_search` 25→89, `server` 71→82) |

Chưa phủ: `browser_search`, `verify_link`, `login_save_state`, `example_agent` (gọi live/Playwright hoặc CLI; sẽ phủ khi gom vào `integrations/shopee` ở bước 5).
