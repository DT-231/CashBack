# STATUS — shopee-link-api

- Bản hiện tại: **v1.2** (2026-11-27)
- Mục tiêu: cho AI bên ngoài gọi HTTP để lấy link affiliate Shopee từ tên sản phẩm,
  và đọc được **tiền thật** Shopee ghi nhận về từng `sub_id`.

## Đã chốt trong v1.2 (2026-11-27 — từ HAR thật của user)

HAR `affiliate.shopee.vn` (41 request, 27/11) cho ra 3 endpoint report quan trọng nhất:

- `GET /api/v3/dashboard/detail?start_time=&end_time=` — click/đơn/hoa hồng theo ngày
- `GET /api/v1/click_report/list?click_time_s=...` — từng click + `sub_id`
- `GET /api/v3/report/list?purchase_time_s=...` — từng đơn, có tên shop, item, category,
  `platform_commission_rate`, `brand_commission_rate`, `utm_content`, tiền hoa hồng

**Header cần dùng:** `cookie` + `affiliate-program-type: 1`. Trang report **không** gửi
`x-sap-sec` mà vẫn `code:0` ⇒ mấy endpoint này không cần chữ ký, cookie là đủ.
(Trang dashboard/detail có `x-sap-sec` nhưng nghi không bắt buộc — chưa test live được.)

**Đơn vị tiền:** × 1e5 (micro-VND). Đã đối chiếu 1 đơn thật khớp 100%
(item_price 9.5e9 = 95.000đ, qty 2, rate 2,5% → commission 403.750.000 = 4.037,5đ).

**Số liệu mẫu:** đã xác nhận tracking nhận click và một đơn `COMPLETED` đối chiếu khớp công thức
(số liệu cá nhân đã được lược bỏ khỏi bản công khai).

⇒ Kết luận: **bước xác nhận "click > 0" đã xong**, và đã chứng minh được luôn
"1 sub_id = 1 bài" là thứ duy nhất cần để biết bài nào ra tiền.

## Đã chốt trong v1.1 (2026-11-26)

- Format link affiliate verify từ `batchCustomLink` (GraphQL) của dashboard:
  `https://shopee.vn/universal-link/product/{shop_id}/{item_id}?utm_source=an_{aff_id}&utm_medium=affiliates&utm_campaign={campaign}&utm_content={sub_id}`
- Affiliate id user: `17300000000` (điền sẵn trong `.env.example`).
- `utm_content` = 5 slot ngăn `-`. Test thật: 301 → giữ utm + Shopee tự thêm `uls_trackid`.
- `verify_link.py`, `test_offline.py` (16/16 pass).

## Thêm trong v1.2

- `revenue.py` — CLI + module: `summary(days)` trả tổng, `by_day`, `by_sub`, `top_items`.
  Có `--json` cho AI đọc. Không cần CSV, không cần API engine.
- `GET /api/revenue?days=7` trong `server.py` (502 + thông báo rõ nếu thiếu/hết cookie).
- `shopee_revenue` trong `tools/*_tools.json`.

## Đã test / chưa test

- ✅ Test offline: parse 3 response thật từ HAR, gộp theo sub_id, quy đổi tiền, in bảng — đúng.
- ✅ `server.py` boot, `/health` ok, `/api/revenue` trả lỗi rõ ràng khi chưa có cookie.
- ❌ **Chưa gọi live**: không có cookie của user và IP datacenter dễ 403. User cần tự chạy
  `python3 revenue.py` trên máy mình để xác nhận.

## v1.3 (2026-11-27) — thêm `feed_import.py`

- Đổi feed export thô (BOM / `;` / tiếng Việt / giá `690.000` / rate `8%` /
  item_id chỉ nằm trong link `-i.shop.item`) -> `feed.csv` chuẩn 8 cột.
- `feed_search.py`: khớp tên cột không phân biệt hoa-thường-dấu (`_norm_key`), tự nhận
  dấu phân cách CSV, đọc số kiểu VN lẫn US.
- Test: 16/16 test_offline.py pass; import thử file feed giả lập (header VN, BOM, `;`,
  dòng rác, dòng trùng, dòng thiếu id) -> giữ 3/6 dòng đúng, bỏ đúng lý do.
- **Chưa có feed THẬT**: user chưa gửi export. `samples/sample_feed.csv` là 3 dòng giả.

## Việc tiếp nếu user quay lại

1. User chạy `python3 revenue.py --days 30` → nếu 403 thì đặt `SHOPEE_PROXY`.
2. Ranker: dùng `top_items` (rate thật theo ngành) thay vì feed CSV. Feed CSV vẫn cần
   nếu muốn biết % hoa hồng của sản phẩm **chưa bán** — header feed user chưa gửi.
3. Engine `api` tìm sản phẩm vẫn cần cookie + IP nhà; feed vẫn là đường chính.
4. Link ngắn `s.shopee.vn`: chỉ dashboard tạo được (cần `x-sap-sec` sinh theo phiên) — bỏ.
