# CashBack — nền tảng hoàn tiền Shopee Affiliate

> Web hoàn tiền (cashback) cho người mua trên Shopee Việt Nam: dán link sản phẩm → nhận link affiliate → mua hàng → nhận lại một phần hoa hồng vào ví và rút về. Kèm một Tool API để một AI agent tự tìm sản phẩm và tạo link theo từng bài đăng fanpage, rồi học xem ngành nào ra tiền.

**Trạng thái:** đang phát triển (Sprint 0). Đã có backend FastAPI + Postgres (Tool API cho AI, tạo link, tìm sản phẩm, codec `sub_id` có chữ ký, báo cáo doanh thu) và bộ tài liệu thiết kế; web, ví và đồng bộ đơn đang được xây. Backend vừa được tái cấu trúc, xem [`docs/refactor/`](docs/refactor/04-ket-qua.md).

## Bài toán

Shopee Affiliate không có API chính thức hay webhook để biết đơn nào đến từ ai. Muốn hoàn tiền đúng người, hệ thống phải:

1. Gắn **danh tính nguồn** vào từng link ngay trong tham số `utm_content` (chỉ có 5 ô, cách nhau bằng `-`).
2. Đọc báo cáo của Shopee, **khớp ngược** từng đơn về đúng người dùng hoặc đúng bài đăng.
3. Quản lý tiền như một hệ thống tài chính thật: trạng thái chờ → rút được → đã hủy, không bao giờ âm, không bao giờ ghi trùng.

## Kiến trúc

```mermaid
flowchart LR
  U([Người dùng]) --> WEB[Web - Next.js]
  U -->|/go/code| GO[Redirect + ghi click]
  AI([AI agent fanpage]) -->|Tool API| API
  WEB --> API[Backend - FastAPI]
  GO --> DB[(Postgres)]
  API --> DB
  SYNC[Sync worker] --> DB
  SYNC -->|đọc báo cáo| SP[(Shopee Affiliate)]
  API -->|payout| PAY[(Chuyển khoản / cổng chi trả)]
```

- **Chi phí hạ tầng 0đ:** web và redirect trên edge miễn phí, Postgres free tier, riêng worker đồng bộ chạy ở máy cá nhân vì Shopee chặn IP datacenter.
- Thiết kế chịu lỗi: nếu phiên đăng nhập Shopee hết hạn, hệ thống **ngừng cộng tiền**, cảnh báo, và có đường nhập báo cáo thủ công thay thế.

## Điểm kỹ thuật đáng chú ý

| Chủ đề | Cách làm |
|---|---|
| **Truy vết đơn hàng** | Codec `sub_id` phiên bản hóa: `1u-<user>-<click>-<chữ ký>-`. Mỗi ô chỉ `[0-9a-z]`, ngắn (base36), không chứa dữ liệu cá nhân. Chữ ký HMAC chống giả mạo; đơn không khớp được đưa vào hàng "đơn mồ côi" |
| **Tiền** | Số nguyên (không float), làm tròn xuống, sổ cái chỉ thêm với khóa idempotent, ví có ràng buộc không âm ở tầng DB |
| **Đồng bộ** | Quét lại cửa sổ 60 ngày để bắt đơn đổi trạng thái; chạy bù khi bật lại; đánh dấu lần sync dở dang thay vì cắt dữ liệu im lặng |
| **Bảo mật** | Cookie Shopee mã hóa at-rest, rate limit, RBAC, audit log, validate host đầu vào chống SSRF/open redirect |
| **Chống gian lận** | Cờ theo IP/thiết bị băm, tỷ lệ hủy bất thường, thời gian giữ tiền trước khi cho rút |
| **AI agent** | API riêng có key: tìm sản phẩm theo % hoa hồng, tạo link theo bài, đọc thống kê theo ngành/giờ để agent tự điều chỉnh |

## Công nghệ

Python (FastAPI, SQLAlchemy/Alembic), PostgreSQL, Docker Compose, GitHub Actions. Kế hoạch: Next.js, Cloudflare (Pages/Workers/Tunnel); xem [`docs/`](docs/).

## Chạy trong 5 phút

```bash
make venv                                   # một lần: tạo .venv, cài backend
cp .env.example .env                        # rồi đặt SHOPEE_AFF_ID; để MOCK=1 khi phát triển
make test && make lint                      # test + lint (mặc định MOCK=1, không gọi Shopee)
make db-up && make test-db                  # Postgres dev (Docker) + test schema/migration/Tool API
cd backend && MOCK=1 ../.venv/bin/python -m app.main_api          # API tại http://127.0.0.1:8080
curl "http://127.0.0.1:8080/api/search?keyword=noi%20chien&limit=3&sub=fb01"
```

| Lệnh | Việc |
|---|---|
| `make test` / `make cov` | toàn bộ test / coverage `backend/app` |
| `make lint` | ruff |
| `make db-up` / `make test-db` | Postgres + migrate + seed / test cần DB (tự skip nếu không có DB) |

## Cấu trúc thư mục

```
backend/
  app/
    main_api.py            # entrypoint FastAPI: chỉ gắn router + middleware
    legacy_api.py          # /api/search, /api/link cũ (lớp tương thích, sắp bỏ)
    core/                  # dùng chung, KHÔNG nghiệp vụ: config, logging, errors, db, money, subid, cache
    modules/               # mỗi thư mục = 1 chức năng: links, products, ai_posts, agent_auth, reports (+ _template)
    integrations/shopee/   # NƠI DUY NHẤT gọi Shopee (client, fake cho MOCK=1, browser, fixtures)
  migrations/              # Alembic, mỗi migration có downgrade
  scripts/                 # revenue_report, verify_link, feed_import, login_save_state, seed, example_agent
  tools/                   # schema tool cho AI (OpenAI/Gemini)
  tests/                   # unit, integration (Postgres), contract (golden + kiến trúc), e2e (CLI)
infra/                     # docker-compose (db, migrate, seed)
docs/                      # thiết kế (00–13), adr/, runbooks/, refactor/
backlog/                   # issues.csv, tasks/<id>.md
```

## Muốn sửa X thì vào đâu

| Muốn sửa | Vào |
|---|---|
| Cách sinh link affiliate (utm, template) | `backend/app/modules/links/affiliate_link.py` (khóa bởi golden test, **không đổi hành vi**) |
| Quy ước `sub_id` | `backend/app/core/subid.py` (cần được giao rõ) |
| Quy đổi tiền, làm tròn | `backend/app/core/money.py` |
| Nguồn tìm sản phẩm (feed/api/browser) | `backend/app/modules/products/` |
| Gọi Shopee, cookie, proxy, cache | `backend/app/integrations/shopee/client.py` |
| Tool API cho Muse AI (key, link theo bài) | `backend/app/modules/{agent_auth,ai_posts}/` |
| Báo cáo doanh thu | `backend/app/modules/reports/` + `backend/scripts/revenue_report.py` |
| Biến môi trường mới | `backend/app/core/config.py` **và** `.env.example` |
| Bảng/index mới | `backend/migrations/versions/` (có `downgrade`) |
| Thêm chức năng | [`docs/refactor/how-to-add-feature.md`](docs/refactor/how-to-add-feature.md) |
| Debug | [`docs/refactor/how-to-debug.md`](docs/refactor/how-to-debug.md), [`docs/runbooks/`](docs/runbooks/) |

Luật phụ thuộc (CI ép bằng `tests/contract/test_architecture.py`): `api → service → repository`; chỉ `integrations/shopee` gọi Shopee; chỉ `modules/wallet` ghi ví; `os.environ` chỉ ở `core/config.py`.

## Tài liệu thiết kế

| | |
|---|---|
| [Tổng quan](docs/01-tong-quan.md) · [Tác nhân](docs/02-tac-nhan.md) · [Chức năng](docs/03-chuc-nang.md) | Phạm vi và người dùng |
| [Luồng nghiệp vụ](docs/04-luong-nghiep-vu.md) · [Trạng thái](docs/05-trang-thai.md) | Sequence và state diagram |
| [Kiến trúc](docs/06-kien-truc.md) · [Dữ liệu và sub_id](docs/07-du-lieu.md) · [API](docs/08-api.md) | Thiết kế kỹ thuật |
| [Phi chức năng](docs/09-phi-chuc-nang.md) · [Rủi ro](docs/10-rui-ro.md) | Bảo mật, chịu lỗi, rủi ro |
| [Quy trình Scrum](docs/11-scrum.md) · [Backlog](docs/12-backlog.md) · [Kế hoạch sprint](docs/13-ke-hoach-sprint.md) | Cách làm việc |

## Cách làm việc

Dự án do một người thực hiện, có sự hỗ trợ của các công cụ AI (Claude Code, Codex, Antigravity) theo quy trình Scrum: backlog có acceptance criteria dạng Given/When/Then, mỗi task một nhánh, luật chung ở [`AGENTS.md`](AGENTS.md).

## Lưu ý

Dự án học tập và portfolio. Không chứa khóa, cookie hay dữ liệu người dùng thật. Mô hình hoàn tiền phụ thuộc điều khoản của Shopee Affiliate; chỉ vận hành thật khi đã được chấp thuận.
