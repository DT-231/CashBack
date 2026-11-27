# 03 — Tiến độ refactor

Nhánh: `refactor/restructure`. Mỗi dòng = một bước trong `02-target.md` §6.

| Bước | Commit | Test thêm | Ghi chú |
|---|---|---|---|
| 0 | `c92d150` | — | Audit + kế hoạch. Quyết định D1–D3 đã chốt (Postgres ngay) |
| 1 | `7a6eda5`, `3c8f1db` | — | `backend/pyproject.toml`, `Makefile`, venv `.venv/` (gitignored). Lint tách commit riêng: xóa 3 import thừa, không đổi hành vi |

## Baseline bổ sung (đo ở bước 1, thay cho các ô "chưa đo" trong 01-audit)

| Chỉ số | Giá trị |
|---|---|
| `make test-db` (Postgres) | 5 test, pass, 0,21 s |
| Tổng test | **34 pass** (16 + 3 + 10 + 5) |
| Coverage service cũ + codec | **41 %** (976 dòng). `revenue` 18 %, `feed_import` 0 %, `browser_search` 11 %, `shopee_search` 25 %, `verify_link` 0 %, `server` 71 %, `subid` 100 % |
| Lint (`ruff` E9,F) | 3 lỗi → 0 |

Chạy: `make venv`, `make test`, `make test-db`, `make lint`, `make cov`.
