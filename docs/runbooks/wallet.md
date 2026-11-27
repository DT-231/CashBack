# Runbook: ví hoàn tiền

Chạy: `make run-once` (đồng bộ đơn rồi chốt ví) hoặc riêng `make sync-once` / `make settle-once`. Mã: `backend/app/modules/wallet/`.

## Mô hình
Số dư 3 ngăn (VND, số nguyên): **pending** (chờ xác nhận), **available** (rút được), **held** (đang khóa cho yêu cầu rút).
`wallet_entries` là sổ cái **chỉ thêm** (trigger DB chặn UPDATE/DELETE); số dư luôn bằng tổng các bút toán (test ép bất biến này). Chỉ `ledger.post` được đổi số dư; `idem_key` trùng thì không đổi gì.

| Bút toán | Ý nghĩa |
|---|---|
| `accrual` | Đơn mới: `floor(hoa hồng x tỷ lệ)` vào pending. Tỷ lệ (`share_bp`) được chốt trên bút toán, đổi cấu hình sau không ảnh hưởng đơn cũ |
| `release` | pending → available, khi đơn `COMPLETED` + `hold_days` (cấu hình có hiệu lực **lúc đơn hoàn tất**) **và** sync đơn gần nhất là `ok`, không cũ hơn `SYNC_MAX_AGE_HOURS` |
| `cancel` | Đơn hủy/trả khi còn pending, hoặc Shopee giảm hoa hồng khi còn pending |
| `reverse` | Đơn bị trả/hủy sau khi đã release: thu hồi phần còn `available` |
| `adjust` | **Lỗ của admin**: user đã rút trước khi đơn bị thu hồi; không đổi số dư ai, không bao giờ trừ âm ví |
| `hold` / `payout` / `refund_hold` | Luồng rút tiền (T-040) |

## Quy tắc an toàn
- Sync không khỏe (`partial`, `failed`, hoặc quá cũ) → **không release** (`release_blocked` > 0 trong kết quả). Accrual/cancel/reverse vẫn chạy vì không làm tăng số tiền rút được.
- Ví không bao giờ âm (CHECK ở DB). Chốt sổ chạy lại bao nhiêu lần cũng cho cùng kết quả (idempotent); đơn đã chốt bị bỏ qua mà không khóa ví.
- Đổi cấu hình (`user_share_bp`, `hold_days`, `min_withdraw_vnd`) chỉ nối thêm bản ghi có hiệu lực từ bây giờ; không sửa được quá khứ hay ghi đè một mốc.

## Khi có chuyện
| Triệu chứng | Làm gì |
|---|---|
| `release_blocked` > 0 | Kiểm tra `sync_runs` gần nhất (`docs/runbooks/order-sync.md`, `cookie-chet.md`); sau khi sync `ok` lại chạy `make settle-once` |
| `errors` > 0 | Xem log `app.wallet` (có `order_id`); giao dịch của đơn đó đã rollback hoàn toàn, chạy lại là tự lành |
| Có bút toán `adjust` | User đã rút trước khi Shopee thu hồi: ghi nhận vào đối soát (T-052). Cần quyết định có truy thu hay không, đó là quyết định của PO |
| Cần hủy một bút toán sai | **Không sửa/xóa.** Thêm bút toán đối ứng (kind phù hợp) kèm ghi chú trong PR/ticket |

## Chưa làm
Rút tiền (T-040/T-041), chuyển ngăn `available` → `held` nằm ở module `payouts`. Hiện `hold`/`payout`/`refund_hold` chỉ có ở sổ cái và test.
