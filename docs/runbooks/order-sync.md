# Runbook: đồng bộ đơn Shopee → DB

Chạy một lần: `make db-up && make sync-once` (mặc định `MOCK=1`, dùng fixture, không gọi Shopee).
Mã: `backend/app/modules/orders/` (service, normalize, attribution, status), `backend/app/main_worker.py`.

## Hành vi đã được khóa bằng test
- Idempotent theo `order_sn`; nhiều dòng báo cáo cùng `order_sn` được **gộp** (cộng hoa hồng, nối mặt hàng).
- Hoa hồng đơn = tổng `item_commission`, bị giới hạn bởi `capped_commission` (chia theo tỷ lệ, làm tròn xuống). `capped_commission = 0` là 0 thật, **không** rơi về `gross_commission`.
- Trạng thái chỉ đi tiến (`status.py`): đơn `COMPLETED` không bao giờ bị hạ về `PENDING` vì dữ liệu lạ/thiếu, chỉ đi tiếp được sang `RETURNED` hoặc `CANCELLED` (Shopee thu hồi); `CANCELLED`/`RETURNED` là cuối. Thay đổi bị từ chối được ghi vào `status_conflicts` và log cảnh báo.
- `completed_at`: lấy từ Shopee nếu có, không thì thời điểm sync đầu tiên thấy `COMPLETED`; **giữ nguyên** kể cả khi sau đó bị trả hàng.
- Khớp `sub_id`: chữ ký đúng **và** click/link/bài thật sự thuộc đúng user; không khớp → `orphan_orders` (thuộc admin). Đơn mồ côi chưa ai nhận sẽ được khớp lại ở lần sync sau nếu dữ liệu về muộn. Staff gán tay thì sync không ghi đè.
- Một đơn hỏng chỉ làm hỏng chính nó (savepoint); lần sync thành `partial`. Chỉ một tiến trình sync tại một thời điểm (khóa advisory); chạy chồng thì `skipped`, không ghi `sync_runs`.
- `sync_runs.result`: `ok` | `partial` (chưa lấy đủ trang, hoặc có đơn lỗi) | `failed` (cookie chết/403/lỗi mạng). **Module `wallet` (T-031) chỉ được chuyển tiền khi lần sync gần nhất là `ok`.**

## CHƯA XÁC NHẬN — cần HAR thật có đơn đủ trạng thái (việc của PO, không gọi live)
`normalize.py` đang đọc kiểu dung thứ ở **một chỗ** (`STATUS_KEYS`, `TIME_KEYS`, `COMPLETED_AT_KEYS`):
1. Tên trường trạng thái đơn (đoán: `order_status`, `status`...) và các giá trị khi hủy/trả hàng (đang map `CANCELLED`/`CANCELED`/`RETURNED`/`REFUNDED`/`RETURN_REFUND`).
2. Tên trường thời gian mua và thời gian hoàn tất.
3. Hoa hồng mức dòng (`capped_commission`) với dòng có nhiều đơn: hiện chia theo tỷ lệ.
Đọc không ra trạng thái thì đơn là `PENDING` (không bao giờ được chuyển tiền) và `raw_status` giữ nguyên để nhìn thấy. Khi có HAR: sửa các hằng trên, thêm fixture ẩn danh, đảo test liên quan.

## Khi lỗi
| Triệu chứng | Làm gì |
|---|---|
| `result: failed`, `error` chứa 403/hết hạn | Cookie chết hoặc IP bị chặn: xem `docs/runbooks/` về cookie; không có tiền nào được chuyển cho đến khi sync `ok` |
| `result: partial` | Chưa lấy đủ (quá nhiều trang) hoặc có đơn lỗi (`errors > 0`, xem log `app.orders`); chạy lại, thu hẹp `--days` nếu cần |
| `result: skipped` | Đang có tiến trình sync khác; bình thường |
| `status_conflicts` khác rỗng | Shopee báo trạng thái "lùi" so với DB: kiểm tra có đổi tên trường/giá trị không (mục chưa xác nhận ở trên) |
