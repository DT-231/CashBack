# AGENTS.md — luật chung cho Claude Code, Codex, Antigravity

Dự án: web hoàn tiền Shopee (60% hoa hồng cho user) + Tool API cho Muse AI. Tài liệu gốc: `docs/` (đọc `00`, `07`, `12` trước). Tiếng Việt cho tài liệu; tên biến/bảng/API tiếng Anh.

## Cấu trúc hiện tại
- Thư mục gốc: service cũ `shopee-link-api` (Python, đã verify một phần). **Không đổi hành vi `affiliate.make_link`**.
- `packages/core/cashback_core/`: mã dùng chung (codec `sub_id` v1). Test: `PYTHONPATH=packages/core python3 -m unittest discover -s packages/core/tests`.
- `docs/`, `backlog/` (`issues.csv`, `tasks/<id>.md` khi giao Codex).
- `apps/api`: Alembic + schema Postgres (T-005). `infra/docker-compose.yml`: db, migrate, seed.
- Sẽ thêm: `apps/web`, `apps/api`, `services/{link-api,sync-worker}`, `infra/`.

## Lệnh test (phải pass trước khi báo xong)
```
make test                                     # pytest backend/tests + 2 bộ unittest cũ (cần `make venv` một lần)
python3 test_make_link_regression.py          # hồi quy make_link
PYTHONPATH=packages/core python3 -m unittest discover -s packages/core/tests
# schema DB: docker compose -f infra/docker-compose.yml up -d db migrate seed, rồi
cd apps/api && DATABASE_URL=postgresql+psycopg://cashback:cashback_dev@127.0.0.1:5433/cashback python -m unittest discover -s tests
```

## Quy ước sub_id v1 (`docs/07-du-lieu.md`)
`utm_content = s1-s2-s3-s4-s5`, mỗi slot `[0-9a-z]`, **không có `-` trong slot**. s1 = `1`+loại (`u`,`l`,`p`,`x`); s2 = user_id/post_id; s3 = click_id/link_id/mã page; s4 = chữ ký HMAC 3 ký tự; s5 rỗng. Luôn dùng `cashback_core.subid`, không tự ghép chuỗi. Không đưa dữ liệu cá nhân vào sub_id.

## Quy tắc tiền
Tiền là số nguyên (VND hoặc micro ×1e5), **không float**. Làm tròn xuống phần của user. Sổ cái chỉ thêm. Ví không bao giờ âm. Chỉ chuyển pending→available khi sync healthy.

## Quy tắc an toàn (bắt buộc)
- Không gọi live tới Shopee/Facebook nếu PO chưa cho phép; mặc định `MOCK=1`, dữ liệu trong `samples/` hoặc test.
- Không đọc, in, commit `.env`, cookie, token. Không log cookie/mật khẩu/số tài khoản.
- Không viết bot tự đăng nhập Shopee, không giải captcha, không tạo click/đơn giả.
- Mỗi task một nhánh `task/<id>`; hai agent không sửa cùng một file cùng lúc.
- Phân việc: Claude giữ kiến trúc, ERD, sub_id, ví/tiền, bảo mật, migration; Codex/Antigravity làm CRUD, UI, test, script.
