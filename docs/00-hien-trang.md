# 00 — Hiện trạng `shopee-link-api` (v1.2/1.3)

> Giai đoạn A: chỉ đọc và phân tích, chưa sửa code. Ngày: 2026-11-27.
> Kết quả `python3 test_offline.py`: **16/16 pass** (là baseline hồi quy cho `affiliate.make_link`).

## 1. Service đang làm được gì

| Khả năng | File | Trạng thái |
|---|---|---|
| Sinh link affiliate từ `shop_id`/`item_id` hoặc URL (nhiều dạng URL) | `affiliate.py` | Đã verify thật (301 + `uls_trackid`, có click thật) |
| Tìm sản phẩm: feed CSV → API nội bộ → Playwright | `feed_search.py`, `shopee_search.py`, `browser_search.py` | Feed ổn định; api/browser chưa chạy live |
| Chuẩn hóa feed export thô | `feed_import.py` | Test bằng feed giả, **chưa có feed thật** |
| Redirect `/go/<sub_id>` + ghi click | `server.py`, `store.py` | Test offline OK |
| Đọc click/đơn/hoa hồng thật từ dashboard Shopee bằng cookie | `revenue.py` | Parse HAR thật OK, **chưa gọi live** |
| Schema function-calling cho AI | `tools/*.json`, `example_agent.py` | Có |

## 2. Chưa làm được

- Không có user, ví, rút tiền, đăng nhập, phân quyền. Đây là service công cụ, chưa phải hệ thống cashback.
- Không có bảng đơn hàng: `revenue.py` chỉ tổng hợp trong bộ nhớ, **không lưu đơn**, nên không có vòng đời đơn (chờ → hoàn thành → hủy) và không cộng/trừ ví được.
- Không đồng bộ định kỳ, không chạy bù, không cảnh báo khi cookie chết.
- Không có module AI fanpage, không có Facebook Graph API, không có hàng chờ duyệt bài.
- Không phát hiện gian lận, không có hàng "đơn mồ côi".
- Chưa test live với Shopee (cookie, IP nhà).

## 3. Nợ kỹ thuật và lỗ hổng phát hiện khi đọc code

### 3.1 Kiến trúc
- `http.server` thuần: không auth, không middleware, không rate limit, không validate input (`int(q.get("limit"))` với giá trị rác → 500).
- SQLite một file, mở kết nối mỗi lần gọi. Ổn cho link-api đơn lẻ, **không hợp** làm DB trung tâm có ví tiền (cần transaction, ràng buộc, migration) → chuyển Postgres.
- `load_env()` tự viết, `.env` chứa cookie dạng plaintext.
- `store.py`/`server.py` gắn chặt với nhau, nhiều module đọc `os.environ` trực tiếp.

### 3.2 Bảo mật (cần xử lý trước khi đưa ra Internet / Cloudflare Tunnel)
| # | Vấn đề | Mức |
|---|---|---|
| S1 | `/api/revenue`, `/api/stats` **không auth** và `Access-Control-Allow-Origin: *`. Ai biết URL tunnel cũng đọc được doanh thu, sub_id, top sản phẩm. | Cao |
| S2 | `POST /api/link` và `/api/search` ghi `links` mà không auth. Kẻ lạ spam đầy DB. | Cao |
| S3 | `save_link` có `ON CONFLICT(sub_id) DO UPDATE SET target=…`: gọi lại với cùng `sub` thì **ghi đè đích redirect** của link đã phát. Ai gọi được `/api/link` có thể đổi đích `/go/<sub>` (open-redirect do lưu trữ). | Cao |
| S4 | `sub` do client tự đặt, không whitelist ký tự, không giới hạn độ dài; `sid` trong search lấy từ `keyword[:12]` (có thể chứa `-`, ký tự lạ). | Cao |
| S5 | Cookie Shopee trong `.env`; `/health` lộ `cookie_set`. Chưa có mã hóa, chưa có quy trình xoay. | Cao |
| S6 | `IP_SALT` mặc định `"zaka"`: hash IP dễ dò ngược (không gian IPv4 nhỏ). | Trung bình |
| S7 | Thông báo lỗi trả nguyên `str(e)` ra client. | Thấp |

### 3.3 Quy ước `sub_id` cũ (phải bỏ)
- "slot1 = bài/kênh, slot2 = số thứ tự sản phẩm", do client tự đặt, **không mã hóa nguồn, user, click, phiên bản**.
- `normalize_sub_id` đổi `_` và khoảng trắng thành `-`, trong khi `-` là dấu phân cách slot ⇒ `fb-01` bị hiểu thành 2 slot. Mơ hồ.
- `revenue.slot()` dùng `.strip("-")` rồi gộp: `fb01----` và `fb01` cùng khóa, nhưng `fb01-3` tách riêng; không tách được slot nên **không group theo "bài" được**.
- `sub_id` là khóa chính bảng `links` và cũng là đường dẫn `/go/<sub_id>`: một sub = một link = một đích. Không có khái niệm `click_id` riêng, nên không truy ngược "ai bấm" từ đơn hàng.
- Chưa có độ dài tối đa đã kiểm chứng. Cần test thực tế với Shopee (xem câu hỏi mở Q9).

### 3.4 Cookie và endpoint nội bộ (điểm yếu số 1)
- `revenue.py` phụ thuộc cookie phiên (sống ~7–15 ngày) và endpoint không công bố. Hết hạn/403/đổi format là dừng toàn bộ đối soát.
- Retry chỉ 2 lần, không có backoff, không phân loại "cookie chết" bằng mã lỗi có cấu trúc (chỉ chuỗi tiếng Việt), không health-check, không cảnh báo.
- `_paged` giới hạn 40 trang × 100 dòng, **cắt im lặng** nếu vượt (không báo thiếu dữ liệu). Với tiền thật, mất đơn không báo là không chấp nhận được.
- Cửa sổ thời gian theo `purchase_time` của đơn: đơn đổi trạng thái sau (hủy/hoàn thành) nằm ngoài cửa sổ sẽ không được cập nhật. Sync-worker phải quét lại cửa sổ dài (ví dụ 60 ngày) và so khác biệt.
- Tiền ×1e5: `vnd()` dùng `float`. **Ví phải dùng số nguyên** (lưu micro-VND hoặc đồng + phần dư), không dùng float.
- `capped_commission` rơi về `gross_commission` bằng `or`: nếu capped = 0 thật (đơn bị cap về 0) thì lại lấy gross ⇒ **tính dư hoa hồng**. Cần xử lý theo trạng thái đơn rõ ràng.
- Thiếu cột trạng thái đơn trong output (`COMPLETED`/`PENDING`/`CANCELLED`...): `summary` cộng gộp mọi đơn, kể cả đơn chưa chắc có hoa hồng.

### 3.5 Khác
- `test_offline.py` ghi đè `samples/sample_feed.csv` (side effect lên file mẫu), ghi `data/test.db`.
- `feed_search` cache theo mtime, không thread-safe rõ ràng.
- `example_agent.py`, `tools/*.json` hiện trỏ tới HTTP không auth.
- Không có lint, CI, type check, `.gitignore` (thư mục chưa phải git repo).
- Log click lưu `ip_hash` + UA + referer: nếu mở cho user ngoài thì thuộc dữ liệu cá nhân (xem `09-phi-chuc-nang.md`).

## 4. Giữ lại / viết lại

| Thành phần | Quyết định | Lý do |
|---|---|---|
| `affiliate.make_link` + `parse_product_url` | **Giữ nguyên hành vi** (có test hồi quy) | Đã verify với Shopee |
| `normalize_sub_id` | **Viết lại** theo quy ước mới (codec versioned, kiểm tra ký tự/độ dài) | Mơ hồ, không mang nguồn/user/click |
| `revenue.py` | **Giữ phần gọi và parse**, tách thành `ShopeeReportClient`; thêm lỗi có kiểu, phân trang không cắt im lặng, trả trạng thái đơn, số nguyên | Logic parse đã đối chiếu số thật |
| `server.py` | **Viết lại** (FastAPI, auth service-to-service, validate) | Không auth, không validate |
| `store.py` (SQLite) | **Thay bằng Postgres** ở backend chính; link-api chỉ giữ cache/redirect | Cần transaction cho ví |
| `feed_search.py`, `feed_import.py` | **Giữ**, đóng gói thành module của ai-agent | Đường tìm SP ổn định nhất |
| `shopee_search.py`, `browser_search.py` | **Giữ làm tùy chọn**, mặc định tắt | Dễ 403, không nên ở đường chính |
| `login_save_state.py` | **Bỏ khỏi luồng chính** | Gần với tự động đăng nhập, trái quy tắc an toàn mục 8 |
| `tools/*.json`, `example_agent.py` | Giữ làm tham chiếu, viết lại khi ai-agent có tool riêng | |
| `verify_link.py` | Giữ, dùng làm công cụ kiểm tra thủ công | Gọi Shopee live, chỉ chạy khi PO cho phép |

## 5. Câu hỏi mở

Xem phần tóm tắt Checkpoint 1 (gồm 8 câu của đề bài và các câu bổ sung từ phân tích này).
