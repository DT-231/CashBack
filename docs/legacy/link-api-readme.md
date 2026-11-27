# Shopee Link API — cho AI của bạn tự lấy link sản phẩm

Microservice 1 file, 0 phụ thuộc nặng. AI của bạn chỉ cần gọi HTTP:

```
tên sản phẩm  ->  GET /api/search?keyword=...  ->  {tên, giá, link affiliate đã gắn sub_id}
```

Chạy local hay VPS đều được. Không cần API key của Shopee.

---

## 1. Cài + chạy (2 phút)

```bash
pip install -r requirements.txt
cp .env.example .env        # điền SHOPEE_AFF_ID
python3 server.py --port 8080
```

Mở `http://127.0.0.1:8080/api/search?keyword=noi%20chien&limit=5&sub=fb01` để xem kết quả.

Muốn test mà chưa có gì: đặt `MOCK=1` trong `.env` → trả 5 sản phẩm giả, kiểm tra luồng trước.

Chạy test toàn bộ endpoint (không cần mạng):

```bash
python3 test_offline.py
```

---

## 2. Ba endpoint

| Endpoint | Việc |
|---|---|
| `GET /api/search?keyword=&limit=&sort=&sub=&engine=` | tìm sản phẩm + trả luôn `aff_link` |
| `POST /api/link` `{"url": "..."}` hoặc `{"item_id","shop_id","sub"}` | link sản phẩm có sẵn → link affiliate |
| `GET /go/<sub_id>` | 302 sang link affiliate **và ghi click** |
| `GET /api/stats?days=7` | link `/go/` của mình được click bao nhiêu |
| `GET /api/revenue?days=7` | **số liệu thật Shopee ghi nhận**: click / đơn / hoa hồng / từng `sub_id` / top sản phẩm ra tiền |

`sort`: `relevancy` (đúng tên) | `sales` (bán chạy).
`sub`: mã bài đăng/kênh. **Mỗi bài phải 1 sub khác nhau** — đây là thứ duy nhất nối "bài đăng" với "tiền về" khi bạn không có postback.

---

## 3. Ba nguồn tìm sản phẩm (`engine`)

| engine | Cần gì | Độ ổn |
|---|---|---|
| `feed` | file CSV/JSON tải từ dashboard affiliate, đặt `FEED_FILE=./feed.csv` | ⭐ cao nhất — không bao giờ bị chặn, có sẵn %hoa hồng |
| `api` | `SHOPEE_COOKIE` (copy header Cookie từ DevTools) + IP nhà | trung bình, dễ 403 |
| `browser` | `pip install playwright && playwright install chromium` | chậm (4–8s/lần) nhưng vượt được chặn API |

`engine=auto` (mặc định): **feed → api → browser**, cái nào chạy được thì thôi.
Kết quả trả về có `engine` và `tried` để bạn biết nó đã đi đường nào.

> Vì sao feed là đường chính: API search nội bộ của Shopee chặn IP datacenter (403 ngay).
> Feed thì bạn tải 1 lần, tool tìm offline trong đó → nhanh, miễn nhiễm chặn.
> Nếu cần sản phẩm **mới nhất trong ngày** thì mới phải dùng `api`/`browser`.

### 3.1 Từ feed Shopee export → `feed.csv` (`feed_import.py`)

Feed tải từ dashboard thường lệch: có BOM, ngăn bằng `;`, giá `690.000`, rate `8%`,
`item_id` chỉ nằm trong link `-i.7001.900001`, header tiếng Việt, vài dòng rác phía trên.
`feed_import.py` chuẩn hoá hết về 1 format cố định:

```bash
python3 feed_import.py feed_goc.csv -o feed.csv            # đổi + ghi file
python3 feed_import.py feed_goc.csv --dry-run              # chỉ xem có nhận đúng cột không
python3 feed_import.py feed_goc.csv -o feed.csv --min-rate 5 --min-sales 100
```

Nó in ra: encoding / dấu phân cách / **cột nào nhận ra được** / bao nhiêu dòng giữ / bỏ vì lý do gì /
top 5 sản phẩm theo tiền hoa hồng 1 đơn. Nhận cả header tiếng Việt (`Tên sản phẩm`, `Giá`,
`Hoa hồng (%)`, `Đã bán`, `Link sản phẩm`) lẫn tiếng Anh (`product_name`, `price`, `commission_rate`).

Sau đó thêm vào `.env`: `FEED_FILE=./feed.csv`.

> ⚠️ `samples/sample_feed.csv` là **dữ liệu giả 3 dòng** (`item_id 900001...`) chỉ để test luồng.
> Đăng link từ file đó = link trỏ vào sản phẩm không tồn tại. Muốn tìm sản phẩm thật thì
> phải có feed export thật của tài khoản bạn, hoặc `SHOPEE_COOKIE` cho engine `api`.

---

## 4. Nối vào AI của bạn

Schema function-calling có sẵn:
- Gemini / Claude tools: `tools/gemini_tools.json`
- OpenAI tools: `tools/openai_tools.json`

Khai báo 3 hàm đó, rồi map mỗi hàm sang 1 request HTTP:

| hàm | gọi |
|---|---|
| `shopee_find_links` | `GET {BASE}/api/search?keyword={keyword}&limit={limit}&sub={sub}` |
| `shopee_link_from_url` | `POST {BASE}/api/link` `{"url":..., "sub":...}` |
| `shopee_click_stats` | `GET {BASE}/api/stats?days={days}` |
| `shopee_revenue` | `GET {BASE}/api/revenue?days={days}` |

Ví dụ vòng lặp đầy đủ: `example_agent.py`.

**Nếu AI của bạn chạy trên cloud (Gemini API, OpenAI API...)** thì nó không gọi được `127.0.0.1`.
Mở tunnel 1 lệnh, không cần VPS:

```bash
cloudflared tunnel --url http://localhost:8080
# -> https://abc-xyz.trycloudflare.com   (dùng URL này làm BASE)
```

Rồi đặt `PUBLIC_BASE=https://abc-xyz.trycloudflare.com` để response có thêm `click_url`.

---

## 5. Định dạng link affiliate — ĐÃ CHỐT (2026-11-26)

Lấy trực tiếp từ HAR của dashboard `affiliate.shopee.vn` (API `batchCustomLink`), đã test thật.

Dashboard trả link dài:

```
https://shopee.vn/universal-link/<slug>-i.<shop_id>.<item_id>
  ?utm_source=an_<affiliate_id>
  &utm_medium=affiliates
  &utm_campaign=-
  &utm_content=<sub_id1>-<sub_id2>-<sub_id3>-<sub_id4>-<sub_id5>
```

Bốn tham số quyết định, tên chính xác:

| Tham số | Ý nghĩa | Giá trị |
|---|---|---|
| `utm_source` | affiliate id, **phải có tiền tố `an_`** | `an_17300000000` |
| `utm_medium` | cố định | `affiliates` |
| `utm_campaign` | tên chiến dịch | `-` nếu để trống |
| `utm_content` | sub_id, 5 slot ngăn bằng `-` | `fb01----` |

Service sinh link KHÔNG cần slug, dùng path `/product/{shop_id}/{item_id}`:

```
https://shopee.vn/universal-link/product/1020310358/24088489429
  ?utm_source=an_17300000000&utm_medium=affiliates&utm_campaign=-&utm_content=fb01----
```

Test thật: URL trên trả `301` → `shopee.vn/product/...` với toàn bộ utm còn nguyên
**và Shopee tự thêm `uls_trackid=`** — đó là dấu hiệu link đã vào hệ thống tracking.

### Tự kiểm tra bất cứ lúc nào

```bash
SHOPEE_AFF_ID=17300000000 python3 verify_link.py --sub fb01
```

Nó in ra link, HTTP status, Location sau 301, và `tracked: True/False`.
Thiếu `uls_trackid` = Shopee không nhận link (vẫn mở được sản phẩm nhưng 0 hoa hồng).

### Về sub_id (quan trọng để đối soát)

`utm_content` được Shopee tách thành 5 cột `sub_id1..sub_id5` trong báo cáo.
Quy ước ở đây: **slot 1 = kênh/bài, slot 2 = số thứ tự sản phẩm**.

```
fb01        -> fb01----        (sub_id1 = fb01)
fb01-3      -> fb01-3---       (sub_id1 = fb01, sub_id2 = 3)
```

Muốn giữ sub_id nguyên văn: `SUB_ID_PAD=0` trong `.env`.

### Vì sao không dùng link ngắn `s.shopee.vn/...`

Link ngắn chỉ dashboard tạo được (nó gắn affiliate + sub_id ở phía server).
Tự gọi API tạo link ngắn cần `csrf-token` + `af-ac-enc-dat` + `x-sap-sec` (chữ ký sinh theo phiên,
vài phút là hết) — không đáng để phụ thuộc. Link dài ở trên tự sinh được, tracking y hệt,
lại đổi sub_id theo từng bài thoải mái.

### Bước cuối không được bỏ

Nhờ **1 người máy/IP khác** bấm link, mua món rẻ nhất (đừng tự mua bằng nick mình).
24–48h sau vào Báo cáo → Clicks phải > 0. Có click = chắc chắn đúng tham số.

---

## 6. Giới hạn phải biết

- `api` engine phụ thuộc cookie phiên — hết hạn là 403, phải lấy cookie mới. Đừng dựng hệ 24/7 chỉ trên nó.
- `browser` engine tốn RAM, Shopee có thể bắt captcha/login → chạy `login_save_state.py` 1 lần, đặt `PW_STATE=state.json`.
- `feed` engine chỉ biết sản phẩm **có trong file** — feed cũ thì không có hàng mới.
- `comm_rate` chỉ có khi dùng `feed`. Với `api`/`browser` phải tự map % theo category.
- `api` engine vẫn cần cookie cho phần **tìm sản phẩm**; riêng phần **đối soát doanh thu** thì cookie là đủ (mục 7).
- Số liệu dashboard cập nhật chậm: click thường trong ngày, đơn/hoa hồng có thể chậm 24–48h (đơn cần `COMPLETED`).

---

## 7. Đối soát doanh thu tự động — KHÔNG cần export CSV

Lấy từ HAR thật của dashboard (26–27/11/2026). Ba endpoint report **không cần `x-sap-sec`**
(chữ ký đó chỉ trang dashboard đính vào, trang report gọi trơn vẫn qua), nên **chỉ cần cookie**.

| Endpoint | Cho ra gì |
|---|---|
| `GET /api/v3/dashboard/detail?start_time=&end_time=` | theo ngày: `clicks`, `cv_by_order`, `order_amount`, `total_commission`, `total_income` |
| `GET /api/v1/click_report/list?click_time_s=&click_time_e=&page_num=&page_size=` | từng click + `sub_id` + nguồn (browser/app) |
| `GET /api/v3/report/list?purchase_time_s=&purchase_time_e=&page_num=&page_size=&version=1` | từng đơn: shop, item, category, `%` hoa hồng, `utm_content` (sub_id), tiền hoa hồng |

### Chạy

```bash
python3 revenue.py              # 7 ngày
python3 revenue.py --days 30
python3 revenue.py --days 30 --json   # cho AI đọc
```

In ra: tổng click/đơn/hoa hồng, bảng theo `sub_id` (click → đơn → CVR → tiền),
và top sản phẩm ra tiền kèm `shop_id.item_id` + `%` hoa hồng thật của từng ngành.

### Đơn vị tiền

Shopee trả số nguyên × 100.000 (micro-VND). `403750000` = **4.037,5 đ**.
Đã đối chiếu 1 đơn thật: `item_price` 9.500.000.000 → 95.000đ, qty 2, platform rate 2,5%
→ 161.500 × 2,5% = 4.037,5đ = `item_commission`. Khớp tuyệt đối.

### Vì sao cái này quan trọng hơn feed CSV

`report/list` trả về **`platform_commission_rate` và `brand_commission_rate` của từng item đã bán được**.
Nghĩa là bạn không cần đoán ngành nào ăn % cao — cứ đăng, có đơn, rồi đọc ngược lại:
ngành nào ra tiền thì dồn bài vào ngành đó. Đây là dữ liệu thật, không phải bảng tham khảo.
