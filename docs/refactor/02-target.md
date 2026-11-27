# 02 — Cấu trúc đích và kế hoạch di chuyển (Giai đoạn 2)

Dựa trên `01-audit.md`. Quyết định đã chốt với PO (2026-11-27):

| Mã | Quyết định |
|---|---|
| D1 | Refactor chỉ **dọn service cũ vào cấu trúc mới**. Module mới (`auth`, `wallet`, `payouts`…) làm theo `backlog/`, dùng `_template/` |
| D2 | Lỗi #1–#4 trong audit sửa ở commit `fix(...)` **riêng**, sau khi có test tái hiện; không gộp với `refactor(...)` |
| D3 | **Dùng Postgres ngay.** SQLite (`store.py`) bị thay, không chạy song song |

## 1. Hệ quả của D3 (đã đối chiếu `docs/06`, `docs/08`)

- Lược đồ mới đã có đủ chỗ cho luồng cũ mà **không cần `users`/`auth` trước**: luồng AI (`/api/search`, `/api/link`) chính là `agent` → bảng `posts` + `agent_keys` (`post_key`, `sub_id`, `page_code`). `links`/`clicks` (cần `user_id`) chỉ dành cho luồng thành viên.
- `docs/08` đã định nghĩa đường chuyển: `/api/search → /agent/search`, `/api/link → /agent/links` (idempotent theo `post_key`, **không ghi đè đích**), `/api/stats`, `/api/revenue` bỏ (thay bằng `/agent/insights`, `/admin/overview`), `/go/<sub_id> → /go/{code}`. Kế hoạch dưới đây bám đúng bảng đó. Nó cũng **sửa tận gốc lỗi #1** (ghi đè sub_id) và #4 (sub_id từ keyword).
- **Mất dữ liệu cũ:** `data/links.db` (click log SQLite) không có chỗ tương ứng, vì link AI mới trả `direct_url` không qua `/go`. Mặc định: **không migrate**, giữ file làm bản lưu. Cần PO xác nhận (câu hỏi Q1).
- Nhắc lại ràng buộc `docs/06`: `/go/{code}` chạy trên **Cloudflare Worker** (không phải Python), ghi click qua Neon HTTP. Nên `modules/clicks` trong backend chỉ giữ phần **dữ liệu/đọc/báo cáo click**; Worker là thư mục riêng `edge/go-worker/` (Q2).

## 2. Cây thư mục đích

Giữ đúng tinh thần khung của PO: 1 backend Python dùng chung cho API và worker, 1 frontend. **Điều chỉnh có lý do:**

| Khung PO | Điều chỉnh | Lý do |
|---|---|---|
| `ai-agent/` | **Bỏ.** Thay bằng `backend/app/modules/ai_posts` + `backend/tools/` (schema tool) | `docs/06` §2: Muse AI là agent ngoài, gọi Tool API của ta; repo không chứa vòng lặp agent |
| `backend/app/core/subid.py`, `money.py` | Chuyển từ `packages/core/cashback_core/` vào đây | Không có consumer nào của `packages/core`, nên không cần package riêng; một nơi duy nhất |
| `apps/api/migrations` | Chuyển thành `backend/migrations` | Một codebase Python |
| `frontend/` | **Chưa tạo** trong refactor này | Chưa có code web (T-033); tạo thư mục rỗng là làm đẹp cho có. Quy ước frontend vẫn ghi ở §7 |
| `main_worker.py`, `jobs/` | **Chưa tạo**, chỉ chừa chỗ trong tài liệu | Chưa có job nào; sẽ thêm cùng T-021 |
| `modules/{users,payouts,orders,wallet,admin,fraud,auth}` | Chỉ tạo khi làm task tương ứng, copy từ `_template/` | D1 |
| `edge/go-worker/` | **Thêm** | `/go` chạy trên Cloudflare Worker |
| `packages/shared-types/` | Thêm khi có frontend/mobile, sinh từ OpenAPI | Chưa có consumer |

Cây sau khi hoàn tất refactor (phần **đậm** là có trong phạm vi refactor; còn lại để trống/đến sau):

```
.
├── README.md  AGENTS.md  CLAUDE.md  Makefile  .env.example  .gitignore
├── .github/{workflows/ci.yml, pull_request_template.md}
├── backend/
│   ├── pyproject.toml                    # ruff, mypy, pytest, coverage
│   ├── app/
│   │   ├── main_api.py                   # FastAPI: gắn router + middleware
│   │   ├── core/   config.py logging.py errors.py db.py money.py subid.py   (security.py: đến T-010)
│   │   ├── modules/
│   │   │   ├── _template/
│   │   │   ├── links/        affiliate_link.py (từ affiliate.py), service, schemas
│   │   │   ├── products/     search qua interface: feed | api | browser (từ *_search.py)
│   │   │   ├── ai_posts/     /agent/links, post_key idempotent, sub_id v1
│   │   │   ├── clicks/       đọc/báo cáo click (ghi click do edge/go-worker)
│   │   │   └── agent_auth/   API key cho Tool API (S1/S2 trong 00-hien-trang)
│   │   └── integrations/shopee/  client.py, fake.py (MOCK), fixtures/
│   ├── migrations/            # 0001 (chuyển nguyên) + 0002 index, có downgrade
│   ├── scripts/               # verify_link.py, feed_import.py, login_save_state.py, seed.py
│   ├── tools/                 # openai_tools.json, gemini_tools.json
│   └── tests/{unit,integration,contract,e2e}
├── edge/go-worker/            # Cloudflare Worker (T-015), ngoài phạm vi refactor
├── infra/docker-compose.yml   # db, migrate, seed, backend-api
├── docs/ {00-13, adr/, runbooks/, refactor/}
└── backlog/
```

## 3. Luật phụ thuộc và cách ép

1. `api → service → repository`; module khác chỉ gọi `service` công khai (không import `repository` của module khác).
2. `core/` không import `modules/` hoặc `integrations/`.
3. **Chỉ `integrations/shopee` gọi Shopee**; **chỉ module `wallet` ghi `wallets`/`wallet_entries`.**

Ép bằng test, không bằng thỏa thuận: `tests/contract/test_architecture.py` quét AST/grep và **fail** khi
- file ngoài `integrations/shopee/` import `requests`/`httpx`/`playwright` hoặc chứa host `shopee.vn`;
- file ngoài `modules/wallet/` chứa SQL ghi `wallets` hoặc `wallet_entries`;
- `api.py` import `repository`; module A import `repository` của module B;
- `os.environ`/`os.getenv` xuất hiện ngoài `core/config.py`.

Ở DB: `wallet_entries` đã chặn UPDATE/DELETE bằng trigger. Khi có module `wallet`, thêm migration thu quyền ghi `wallets` khỏi role của app khác (làm trong task ví, không thuộc refactor).

## 4. Phần dùng chung (`core/`)

- `config.py`: một lớp `Settings` (pydantic-settings) đọc env **một lần**, có kiểu, thiếu biến bắt buộc thì lỗi rõ khi khởi động. Thay 47 dòng `os.environ`. Không đọc env lúc import.
- `logging.py`: log JSON, `request_id`/`job_id` gắn bằng contextvar, bộ lọc che `cookie`, `token`, `authorization`, số tài khoản. Log timing cho đường chính.
- `errors.py`: `{"error":{"code","message","request_id"}}` đúng `docs/08`.
- `money.py`: kiểu tiền là `int`; hằng `MICRO = 100_000`; `micro_to_vnd` (làm tròn xuống), `vnd_to_micro`; **không float**. Giá/hoa hồng từ feed dùng `Decimal` rồi ra int.
- `subid.py`: chuyển nguyên bản v1 (đã có 10 test).
- `db.py`: engine/session/transaction; repository nhận session, service không biết SQL.

## 5. Mục tiêu theo nhu cầu

| Nhu cầu | Giải pháp |
|---|---|
| Fix bug/debug | `make dev`, `make test`, `make logs`; `scripts/repro_*.py` chạy bằng fixture; `docs/refactor/how-to-debug.md` ("lỗi X → xem file Y") |
| Review | PR nhỏ (một module), `pull_request_template.md` với checklist: tiền/ví, bảo mật, migration (có downgrade), test |
| Thêm chức năng | `modules/_template/` + `docs/refactor/how-to-add-feature.md` |
| Hiệu năng | Upsert hàng loạt thay vì từng commit (#23); index mới (#24, #28); cache TTL cho tìm kiếm/dashboard Shopee (#25); retry không `sleep` trong luồng request (#26); timing log; job sync theo lô, idempotent (khi có) |

## 6. Kế hoạch di chuyển (thấp → cao rủi ro)

Mỗi bước: 1 commit (hoặc ít), test xanh trước và sau. "Revert" = `git revert` commit đó. Bước đổi DB có migration hai chiều.

| # | Việc | File | Test bảo vệ | Revert |
|---|---|---|---|---|
| 0 | Commit `01-audit`, `02-target`; tạo nhánh `refactor/restructure` | docs | — | xóa nhánh |
| 1 | **Công cụ:** `backend/pyproject.toml`, venv, ruff, pytest, coverage, `Makefile` (`test`, `lint`, `fmt`). Chưa di chuyển code | mới | 3 bộ test hiện có chạy được qua `make test` | xóa file mới |
| 2 | **Characterization tests** cho service cũ (chạy trên code cũ): chuyển `test_offline.py` sang pytest dùng thư mục tạm (hết ghi đè `samples/`, hết cổng cố định); thêm test cho `revenue` (fixture JSON), `feed_search`, `feed_import`, `store.stats`, `shopee_search._normalize`; **test đánh dấu `xfail(strict)` tái hiện #1–#4** | `backend/tests/` | chính chúng; xfail đảm bảo lỗi vẫn như cũ | xóa test |
| 3 | `core/config` + `core/errors` + `core/logging`; chưa nối vào code cũ | `core/` | unit test cấu hình, che dữ liệu nhạy cảm | xóa file |
| 4 | `core/subid` (chuyển từ `packages/core`) + `core/money`; `modules/links/affiliate_link.py` (chuyển từ `affiliate.py`, **giữ nguyên `make_link`**); code cũ import từ chỗ mới | `affiliate.py`, `packages/core` | `test_make_link_regression` + 10 test subid, đưa vào `tests/contract/` | `git revert` |
| 5 | `integrations/shopee`: gom `shopee_search`, `revenue`, `browser_search`, `verify_link`, `login_save_state` sau một `ShopeeClient` + `FakeShopeeClient` (MOCK) + fixtures; thống nhất UA/proxy/cookie (`SHOPEE_COOKIE`, bỏ `AFF_COOKIE`) | các file Shopee | fixture test (không live); `test_architecture` bật rule "chỉ Shopee client" | revert |
| 6 | `modules/products`: `feed_search`, `feed_import` (dùng chung parser số, hết import private), engine `feed/api/browser` sau 1 interface, `do_search` rời `server.py` | `feed_*`, `server.py:52-75` | test feed + `test_offline` | revert |
| 7 | **DB:** `backend/migrations` (chuyển 0001), migration `0002` thêm index (`clicks(sub_id)`, `shopee_orders(click_id,post_id,status)`, `wallet_entries(order_id,withdrawal_id)`, `clicks(created_at)`) có `downgrade`; `core/db`; Postgres trong CI | `apps/api/*`, `infra/` | `test_schema` (chạy được bằng `make test-db`) + test up/down/up của migration | `alembic downgrade -1` |
| 8 | **Chuyển API sang FastAPI + Postgres.** `main_api.py`, `modules/ai_posts` + `agent_auth`; giữ `/api/search`, `/api/link` làm **alias mỏng** để Muse AI không vỡ; `/api/stats`, `/api/revenue` bỏ theo `docs/08`. Thay `store.py` bằng repository Postgres | `server.py`, `store.py` | contract test: shape JSON và `aff_link` **giống hệt** bản cũ (golden file chụp ở bước 2) | giữ `server.py` đến bước 10, revert commit chuyển route |
| 9 | **Sửa lỗi** (`fix:` riêng): #2 validate tham số → 422; #1 `post_key` idempotent, không ghi đè; #3 bắt buộc API key khi không bind localhost; #4 `sub_id` từ codec v1; #5 bỏ salt mặc định. Bỏ `xfail` ở các test tương ứng | `modules/ai_posts`, `agent_auth` | các test `xfail` chuyển thành pass | revert từng fix |
| 10 | Xóa code chết: 10 file gốc, `store.py`, `packages/core`. Chỉ xóa khi `test_architecture` + contract xanh và `grep` không còn import | gốc | toàn bộ suite | `git revert` |
| 11 | `README.md` ("muốn sửa X thì vào đâu"), `AGENTS.md`/`CLAUDE.md`, `ci.yml`, `pull_request_template.md`, `how-to-add-feature.md`, `how-to-debug.md`, ADR (`0001-fastapi`, `0002-postgres-only`, `0003-one-backend`, `0004-shopee-client-duy-nhat`), `_template/` | docs, `.github/` | CI xanh | revert |

Thứ tự này khác gợi ý của PO ở một điểm: **test (bước 2) đi trước mọi di chuyển**, `integrations/shopee` đi trước `links`/`products`, và `wallet`/`orders`/`payouts` không nằm trong danh sách vì chưa có code.

Điều kiện dừng: sau bước 2, 5, 8, 11 tôi báo tiến độ ngắn (mỗi 3–4 bước theo luật của PO). Bước 8 là bước rủi ro nhất vì đổi framework HTTP và DB cùng lúc; `docs/06` đã chốt FastAPI nên không coi là đổi công nghệ mới, nhưng nó cần golden test thật chặt.

## 7. Chuẩn bị cho mobile (không tốn công thêm bây giờ)

- API thuần, tiền tố `/api/v1`, OpenAPI do FastAPI sinh; ghi lại ở ADR.
- Auth access + refresh token (`docs/08` đang ghi cookie HttpOnly cho web; sẽ cập nhật khi làm T-010). Tool API đã dùng Bearer key.
- Không để nghiệp vụ trong Next.js; `frontend/features/*` + `lib/api-client.ts` là chỗ duy nhất gọi backend; `packages/shared-types` sinh từ OpenAPI khi có frontend.

## 8. Câu hỏi còn mở (không chặn bước 0–7)

- **Q1.** Click log trong `data/links.db` có cần giữ không? Mặc định: không migrate, giữ file làm bản lưu.
- **Q2.** `/go` chạy Worker đúng như `docs/06` (backend không phục vụ `/go`), hay giai đoạn đầu để FastAPI phục vụ tạm qua Tunnel? Ảnh hưởng bước 8 và có/không `modules/clicks`.
- **Q3.** Muse AI hiện đang gọi `/api/search` và `/api/link` ở đâu và có sửa được client không? Nếu không, alias ở bước 8 phải giữ lâu hơn.
