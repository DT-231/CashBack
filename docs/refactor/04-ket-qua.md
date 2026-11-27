# 04 — Kết quả refactor

Nhánh `refactor/restructure`, 19 commit trên `main`. Baseline: `01-audit.md` §3 và `03-progress.md`.

## So sánh trước / sau

| Chỉ số | Trước (`4fb184e`) | Sau |
|---|---|---|
| Test (gồm DB, migration) | 34 | **166** |
| Thời gian chạy test | ~1,3 s (không gồm DB) | ~0,6 s không DB · ~3 s gồm Postgres + migration up/down |
| Coverage | 41 % (service cũ + codec) | **92 %** `backend/app` (1.122 dòng) |
| Lint (ruff E9,F) | 3 lỗi | 0 |
| Module Python ở thư mục gốc | 10 | 0 (mọi thứ trong `backend/`) |
| Nơi gọi Shopee | 5 (2 thư viện HTTP, 3 UA) | **1** (`integrations/shopee`) |
| Dòng đọc `os.environ` | 47 ở 11 file | **0** ngoài `core/config.py` |
| Hàm > 50 dòng (code ứng dụng) | 5 | 2 (`convert` 78, `build_summary` 58) |
| Nguồn lưu dữ liệu | SQLite + Postgres (lệch) | Postgres |
| Index DB (ngoài PK/UNIQUE) | 3 | 12 (+9, `0002`) |
| Luật kiến trúc | trong tài liệu | **ép bằng test** (`test_architecture.py`, 5 luật) |

Thời gian phản hồi `MOCK=1`, in-process, p50 (so cùng cách đo ở audit): `/health` 1,7 → **0,8 ms**, `/api/search?limit=5` 2,5 → **1,0 ms** (không còn ghi 5 dòng SQLite mỗi request), `POST /api/link` 1,0 → **0,8 ms**. Số mới đo trên uvicorn thật, số cũ trên `http.server`, nên chỉ so được về cỡ độ lớn. **Job sync và `/api/revenue` live chưa đo được** (cần cookie thật / chưa có worker).

## Lỗi trong audit

| # | Tình trạng |
|---|---|
| 1 link ghi đè | Hết do thiết kế: đường cũ không lưu gì; link AI idempotent theo `post_key`, trùng khác sản phẩm → 409 |
| 2 `limit=abc` đứt kết nối | Sửa → 400 |
| 3 không xác thực | Sửa: Bearer key bắt buộc khi cấu hình hoặc ngoài localhost; server từ chối khởi động nếu thiếu |
| 4 sub_id chứa keyword | Sửa; link AI mới dùng sub_id v1 có chữ ký |
| 5 `IP_SALT` yếu | Hết cùng `/go` |
| 6, 7, 9–11, 13–17 | Sửa bằng cấu trúc mới (`legacy_api` mỏng, một codec, một client, một config, fixture riêng, lỗi hẹp hơn, log có `request_id`) |
| 8 tiền float / heuristic | **Một phần**: quy đổi ×1e5 nằm một chỗ, báo cáo dùng micro nguyên; heuristic giá/hoa hồng giữ nguyên có test khóa (xem nợ) |
| 12 hai lược đồ | Sửa: Postgres duy nhất |
| 18 lộ `FEED_FILE` | Sửa |
| 19–22 test thiếu | Sửa trừ ví/đối soát/sync (chưa có code) |
| 23–28 hiệu năng | Sửa: không ghi từng item, index, cache TTL (chỉ lưu thành công), một cửa sổ thời gian/snapshot, không `sleep` trong luồng search dư |

Rà soát bằng `code-review` (medium) cho 10 điểm; 7 điểm đã sửa kèm test (`test_review_fixes.py`): feed hỏng/`.jsonl` làm 500, cache không giới hạn, `SUBID_SECRET` ngắn → 503, lỗi cũ còn sót khi retry thành công, DB sập lúc xác thực → 503 (+ khóa tạo engine), kiểu/dấu của `url`/`item_id`, `LINK_TEMPLATE` hỏng, `X-Request-ID` không kiểm. 3 điểm còn lại ghi vào nợ.

Đã thêm một lỗi tự phát hiện và sửa trong lúc rà soát: khóa trong `agent_keys` không bao giờ xác thực được vì engine tạo lười (`fa0d808`).

## Nợ kỹ thuật còn lại (đề xuất xử lý)

| Nợ | Đề xuất |
|---|---|
| **#8**: `price > 10_000_000 → ÷1e5` sai với giá thật ≥ 10 triệu; `comm_rate < 1` đọc 0,5% thành 50% (test `test_normalize_heuristic…`, `test_record_comm_rate_fraction…` đang khóa lỗi) | Lấy fixture HAR thật (T-007), đổi sang đọc đúng trường đơn vị, rồi đảo test |
| `convert` (feed_import) 78 dòng, `build_summary` 58 dòng | Tách khi có việc đụng tới |
| `legacy_api` (`/api/search`, `/api/link`) | Chuyển Muse AI sang `/api/v1/agent/*` rồi xóa file (Q3: cần biết client của Muse AI) |
| `/go/{code}` + `modules/clicks` | Làm T-015 (Cloudflare Worker). Click log SQLite cũ **không** migrate (Q1, mặc định) |
| Chưa có code ví, đơn, rút tiền, `auth`/`users`, sync-worker | Theo backlog, dùng `_template/` (`docs/refactor/how-to-add-feature.md`) |
| Luật "chỉ `wallet` đổi số dư" mới ép ở mức mã nguồn, DB chưa thu quyền ghi | Migration phân quyền khi làm T-030 |
| UA Shopee thống nhất chưa kiểm live; cache trong bộ nhớ một tiến trình | Kiểm khi PO cho phép gọi live; Redis chỉ khi có nhiều tiến trình |
| `integrations/shopee/browser.py` coverage 54 % (Playwright) | Chấp nhận; test bằng DOM mẫu nếu dùng nhiều |
| CI (`.github/workflows/ci.yml`) chưa chạy trên GitHub | Đẩy nhánh và xem lần chạy đầu |
| Refresh token / OpenAPI → `packages/shared-types` / `frontend/` | Khi làm T-010 và web (chuẩn bị mobile) |
| `parse_vn_number`: `0.080`/`8.500` (3 chữ số thập phân) bị đọc là số nghìn (80/8500); `feed_import --min-rate` so giá trị thô còn `feed.py` đổi rate < 1 thành %, hai nơi lệch đơn vị (hành vi cũ, rà soát code review) | Cần feed thật để chốt định dạng; sau đó thống nhất một hàm đọc rate |
| `reports`: `capped_commission` = 0 hợp lệ vẫn rơi về `gross_commission` (hành vi cũ) | Xác nhận ý nghĩa trường bằng HAR thật rồi đổi sang kiểm `is None` |
| `AgentAuth.issue` chưa có endpoint admin (có script `issue_agent_key.py`) | T-050 |
