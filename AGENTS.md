# AGENTS.md — luật chung cho Claude Code, Codex, Antigravity

Dự án: web hoàn tiền Shopee (60% hoa hồng cho user) + Tool API cho Muse AI. Tài liệu gốc: `docs/` (đọc `00`, `07`, `12` trước). Tiếng Việt cho tài liệu; tên biến/bảng/API tiếng Anh. `CLAUDE.md` chỉ trỏ về file này.

## Cấu trúc (sau refactor, xem `docs/refactor/04-ket-qua.md`)
- `backend/` — MỘT codebase Python, nhiều entrypoint. `app/main_api.py` (FastAPI). Chưa có `main_worker.py` (T-021).
  - `app/core/` dùng chung, **không nghiệp vụ**: `config`, `logging`, `errors`, `db`, `money`, `subid`, `cache`.
  - `app/modules/<ten>/` mỗi chức năng một thư mục: `api.py · service.py · repository.py · schemas.py · errors.py`. Hiện có `links`, `products`, `ai_posts`, `agent_auth`, `reports`; mẫu ở `_template/`.
  - `app/integrations/shopee/` **nơi duy nhất gọi Shopee** (`client.py`, `fake.py` cho `MOCK=1`, `browser.py`, `fixtures/`).
  - `app/legacy_api.py` — `/api/search`, `/api/link` cũ, lớp tương thích sắp bỏ.
  - `migrations/` Alembic (có `downgrade`), `scripts/` CLI, `tools/` schema tool AI, `tests/{unit,integration,contract,e2e}`.
- `infra/docker-compose.yml` (db, migrate, seed), `docs/` (`adr/`, `runbooks/`, `refactor/`), `backlog/` (`issues.csv`, `tasks/<id>.md`).
- Sẽ thêm: `frontend/`, `edge/go-worker/` (`/go/{code}` trên Cloudflare Worker), `app/jobs`.

## Bảng "muốn sửa X thì vào đâu"
| Việc | Chỗ |
|---|---|
| Sinh link affiliate | `modules/links/affiliate_link.py` — **không đổi hành vi** (golden test) |
| `sub_id` | `core/subid.py` |
| Tiền / ×1e5 | `core/money.py` |
| Tìm sản phẩm | `modules/products/` |
| Gọi Shopee | `integrations/shopee/client.py` |
| Tool API Muse AI | `modules/agent_auth/`, `modules/ai_posts/` |
| Biến môi trường | `core/config.py` + `.env.example` |
| Thêm chức năng | `docs/refactor/how-to-add-feature.md` |
| Debug | `docs/refactor/how-to-debug.md`, `docs/runbooks/` |

## Lệnh (phải xanh trước khi báo xong)
```
make venv                 # một lần
make test                 # toàn bộ pytest (MOCK=1); integration tự skip nếu không có Postgres
make lint                 # ruff
make db-up && make test-db   # Postgres dev + schema/migration up-down-up + Tool API (cần Docker)
make cov                  # coverage backend/app
```

## Luật phụ thuộc (CI ép: `backend/tests/contract/test_architecture.py`)
1. `api → service → repository`, không đi ngược. Module A chỉ gọi `service` công khai của B, không import `repository` của B.
2. `core/` không import `modules/` hay `integrations/`.
3. **Chỉ `integrations/shopee` gọi Shopee** (không `requests/httpx/playwright` hay host shopee ở nơi khác). **Chỉ `modules/wallet` ghi `wallets`/`wallet_entries`.**
4. **`os.environ` chỉ ở `core/config.py`.** Biến mới: thêm vào `Settings` và `.env.example`.

## Quy ước sub_id v1 (`docs/07-du-lieu.md`)
`utm_content = s1-s2-s3-s4-s5`, mỗi slot `[0-9a-z]`, **không có `-` trong slot**. s1 = `1`+loại (`u`,`l`,`p`,`x`); s2 = user_id/post_id; s3 = click_id/link_id/mã page; s4 = chữ ký HMAC 3 ký tự; s5 rỗng. Luôn dùng `app.core.subid`, không tự ghép chuỗi. Không đưa dữ liệu cá nhân (kể cả keyword) vào sub_id.

## Quy tắc tiền
Tiền là số nguyên (VND hoặc micro ×1e5), **không float**. Làm tròn xuống phần của user. Sổ cái chỉ thêm. Ví không bao giờ âm. Chỉ chuyển pending→available khi sync healthy.

## Quy tắc an toàn (bắt buộc)
- Không gọi live tới Shopee/Facebook nếu PO chưa cho phép; mặc định `MOCK=1`, dữ liệu trong `samples/`, fixtures hoặc test.
- Không đọc, in, commit `.env`, cookie, token. Không log cookie/mật khẩu/số tài khoản (logging tự che, nhưng đừng dựa vào đó).
- Không viết bot tự đăng nhập Shopee, không giải captcha, không tạo click/đơn giả.
- Migration luôn có `downgrade`; đổi DB phải qua `make test-db` (up → down → up).

## Quy tắc làm việc
- Mỗi task một nhánh `task/<id>`; hai agent không sửa cùng một file cùng lúc. PR nhỏ, theo `.github/pull_request_template.md`.
- Refactor **không đổi hành vi**: có test khóa trước, commit `refactor(<module>): ...`; sửa lỗi ở commit `fix(...)` riêng.
- **Phân việc:** Claude giữ kiến trúc, ERD, `sub_id`, ví/tiền, bảo mật, migration. Codex/Antigravity làm CRUD, UI, test, script.
- **Mỗi task Codex chỉ đụng MỘT module** (copy từ `_template/`). **Không sửa `core/`, `modules/wallet`, `core/subid.py`, `migrations/` khi chưa được giao rõ.** Cần đổi chúng thì dừng và báo.
- **Báo cáo trung thực về test:** báo cáo phải liệt kê test nào bị skip và lý do. Không viết "test pass" khi test DB bị skip (sandbox của Codex không có Postgres nên test tích hợp luôn skip).
- **Trước khi trình PO duyệt** (người review, không phải Codex): chạy lại toàn bộ test với Postgres thật **hai lần liên tiếp**, kiểm tra DB không còn dòng rác sau test, và chạy test đột biến (cố ý phá logic chính, test phải đỏ). Test chỉ "xanh" mà không bắt được đột biến thì chưa đủ.
