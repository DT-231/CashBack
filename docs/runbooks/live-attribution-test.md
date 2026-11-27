# Runbook: mua thử một đơn thật để kiểm chứng click → đơn → sub_id

**Mục tiêu:** (1) xác nhận Shopee giữ nguyên `utm_content` có chữ ký từ link tới báo cáo; (2) lấy dữ liệu thật để chốt **tên trường và giá trị trạng thái đơn** (`docs/runbooks/order-sync.md`, mục "CHƯA XÁC NHẬN") và **`hold_days`** (độ trễ trả hoa hồng).

**Ai làm:** PO, bằng tay, trên máy và tài khoản của PO. Claude/Codex **không** gọi Shopee và không đăng nhập hộ. Tốn một khoản nhỏ (giá món rẻ nhất); đơn sẽ chỉ ra hoa hồng nếu món có hoa hồng và Shopee công nhận.

## 0. Chuẩn bị
- `.env` có `SHOPEE_AFF_ID` (id affiliate của PO) và `SUBID_SECRET` (>= 16 ký tự). Không commit `.env`.
- **Sao lưu `SUBID_SECRET` NGOÀI `.env`** (trình quản lý mật khẩu hoặc ghi chú mã hóa, không để trong repo, không dán vào chat). `core/subid` hiện chỉ biết **một** khóa: nếu bạn **đổi hoặc mất** nó, mọi `utm_content` đã phát hành sẽ báo `invalid` (chữ ký sai) và các đơn từ link đó **không còn quy được về user**, rơi hết vào hàng đơn mồ côi. Xoay khóa (T-018): đặt khóa mới vào `SUBID_SECRET` và chuyển khóa cũ sang `SUBID_SECRET_PREVIOUS` (tối đa 3 khóa cũ, cách nhau dấu phẩy). Link mới luôn ký bằng khóa mới; đơn từ link cũ vẫn quy được về user. Mỗi khóa cũ thêm làm tăng xác suất khớp nhầm chữ ký 3 ký tự thêm ~1/46656 (đã có kiểm tra sở hữu click/link ở bước khớp đơn): chỉ giữ khóa cũ khi còn đơn/link cũ cần quy, và đừng xoay thường xuyên. Mất khóa cũ thì đơn từ link đó thành mồ côi.
- `make db-up`, rồi chạy API: `cd backend && ../.venv/bin/python -m app.main_api` (tạo link **không gọi Shopee**, `MOCK=1` vẫn đúng).

## 1. Tạo link bằng API
```bash
B=http://127.0.0.1:8080/api/v1
curl -s -X POST $B/auth/register -H 'content-type: application/json' -d '{"email":"mua-thu@example.com","password":"<mat-khau-dai>"}'
TOKEN=$(curl -s -X POST $B/auth/login -H 'content-type: application/json' \
  -d '{"email":"mua-thu@example.com","password":"<mat-khau-dai>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -X POST $B/links -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"url":"https://shopee.vn/<ten-san-pham>-i.<shop_id>.<item_id>"}'
```
- Dùng **`direct_url`** trong kết quả (không cần Worker/Tunnel). Nó có dạng `…&utm_content=1l-<user>-<link>-<ký tự ký>-`. **Chép lại nguyên chuỗi `utm_content`.**
- Chọn món **rẻ nhất có hiện % hoa hồng** (xem trong trang tạo link của dashboard Affiliate); món không có hoa hồng thì không kiểm chứng được gì.
- Đừng dán link vào ứng dụng rút gọn hay công cụ khác: dùng đúng `direct_url`.

## 2. Mua hàng
- Mở `direct_url` trong trình duyệt **đã đăng nhập bằng tài khoản Shopee KHÁC** tài khoản affiliate (thường Shopee không tính hoa hồng cho đơn tự mua; nếu không chắc, hỏi lại quản lý tài khoản).
- Mở thẳng link (không qua tìm kiếm, không qua app khác), đặt hàng món đó, thanh toán. Ghi lại **mã đơn** và **giờ mua**.
- Chụp trang chi tiết đơn của người mua mỗi khi trạng thái đổi (đang xử lý → đã giao → hoàn thành), kèm ngày.

## 3. Sau 24–48 giờ: xem gì
Vào dashboard Affiliate → **Báo cáo chuyển đổi (Conversion Report)**, lọc ngày mua. Tìm đơn theo mã đơn hoặc giờ mua và ghi lại **nguyên văn**:
1. **`utm_content` / cột Sub_id** của đơn: có đúng chuỗi ở bước 1 không (cùng chữ ký, không bị cắt, đổi chữ hoa/thường hay thêm ký tự).
2. **Trạng thái đơn** (chữ hiển thị trong giao diện, và giá trị thô nếu xem được qua HAR, bước 5).
3. Giờ mua, giờ hoàn tất (nếu có), hoa hồng, hoa hồng thực nhận (`capped`) nếu có.
4. Cột sub_id có thể hiển thị khác tên (Sub_id1..5 hoặc gộp): ghi cách hiển thị.
Đơn chưa xuất hiện sau 48 giờ là dữ liệu hữu ích: ghi lại, đừng mua lại.

## 4. Giải mã bằng `core/subid`
```bash
python3 backend/scripts/decode_subid.py "<chuỗi utm_content lấy từ báo cáo>"
```
Kết quả mong đợi: `status=ok kind=user_link owner(user/post id)=<id user> ref(link/click id)=<id link>`. `status=invalid` nghĩa là chữ ký không khớp hoặc Shopee đã đổi chuỗi: so với chuỗi gốc từng ký tự và báo lại. Script đọc `SUBID_SECRET` từ môi trường/.env, không in nó ra.

## 5. Lấy HAR (để chốt tên trạng thái, tên trường thời gian)
Chrome → trang Conversion Report → F12 → Network → bật "Preserve log" → tải lại danh sách → chuột phải → "Save all as HAR with content". Làm vào ba thời điểm nếu được: lúc đơn đang chờ, lúc hoàn thành, và (nếu có sẵn một đơn khác) lúc hủy/trả hàng. Cần request `…/api/v3/report/list`.

## 6. Che cookie/token trước khi gửi
Dùng script (che header `Cookie`/`Set-Cookie`/`Authorization`/`X-CSRFToken`/`x-sap-*`/`af-ac-enc-*`, cookie, tham số có `token|csrf|sign|spc_|session|key`, và các trường JSON có tên chứa `token|csrf|password|cookie|session|secret`), giữ nguyên URL, tham số thời gian và phần dữ liệu đơn:
```bash
python3 backend/scripts/redact_har.py ~/Downloads/report.har /tmp/report.redacted.har
```
Sau đó **tự kiểm bằng mắt**: mở file đã che, tìm các chuỗi `cookie`, `token`, `csrf`, `SPC_`, và email/số điện thoại/địa chỉ của bạn (họ tên, địa chỉ giao hàng có thể nằm trong thân phản hồi của trang đơn của người mua, ta chỉ cần trang báo cáo affiliate). Nếu còn gì nhạy cảm, xóa tay. Không dán cookie hay HAR gốc vào chat. Nếu không chắc, chỉ dán **một đối tượng JSON của đúng đơn thử** từ trường `list` trong phản hồi `report/list`, đã bỏ các giá trị cá nhân.
Cookie dùng khi lấy HAR coi như đã lộ nếu lỡ gửi nhầm: đăng xuất tài khoản affiliate để vô hiệu cookie.

## 7. Báo lại gì (checklist)
- [ ] `utm_content` gốc (bước 1) và `utm_content` trong báo cáo: **giống nhau hay khác** (nếu khác: khác chỗ nào).
- [ ] Kết quả `decode_subid.py`.
- [ ] Trạng thái đơn ở từng thời điểm (chữ hiển thị + giá trị thô trong HAR), tên trường thời gian mua/hoàn tất.
- [ ] Ngày Shopee **chuyển hoa hồng** cho bạn (đơn này thuộc kỳ nào, ngày tiền về) để chốt `hold_days`.
- [ ] HAR đã che (hoặc JSON một đơn).

## Quyết định sau khi có dữ liệu
| Dữ liệu | Việc tiếp theo |
|---|---|
| `utm_content` giữ nguyên, giải mã `ok` | Đánh dấu đã đạt mục "đơn mua thử khớp sub_id" trong điều kiện mở đăng ký (`docs/12-backlog.md`) |
| `utm_content` bị đổi/cắt | Điều chỉnh codec `core/subid` (ngắn hơn/ký tự khác), chạy lại thử với link mới |
| Có tên trạng thái/trường thời gian thật | Sửa `STATUS_KEYS`/`TIME_KEYS`/`COMPLETED_AT_KEYS` ở `orders/normalize.py`, thêm fixture từ HAR đã che, thêm test |
| Biết ngày Shopee trả tiền | Đặt `hold_days` ≥ độ trễ từ lúc đơn `COMPLETED` đến lúc tiền về + biên an toàn (ADR/`wallet.md`) |
