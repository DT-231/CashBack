# Runbook: đối soát lệch

Có hai loại "lệch", xử lý khác nhau. Công cụ: `GET /api/v1/admin/ledger-integrity` và `GET /api/v1/admin/reconciliation?month=YYYY-MM` (admin + TOTP).

## A. Số dư ví lệch sổ cái (`ledger-integrity` có `mismatches > 0`): SỰ CỐ NGHIÊM TRỌNG
`wallets` phải bằng tổng suy ra từ `wallet_entries` (sổ cái chỉ thêm). Lệch nghĩa là có thứ đã ghi số dư mà không qua `ledger.post` (sửa tay trong DB, lỗi nghiêm trọng của mã, hoặc khôi phục DB sai).
1. **Dừng rút tiền ngay:** đặt `WITHDRAWALS_ENABLED=0` và khởi động lại API (chặn yêu cầu mới); không `approve`/`mark-paid` yêu cầu nào đang mở cho tới khi xong.
2. Lấy danh sách: `samples[]` cho `user_id`, giá trị đã lưu và suy ra của chờ/rút được/đang khóa.
3. Tìm nguyên nhân: `audit_logs` quanh thời điểm (`SELECT * FROM audit_logs ORDER BY id DESC LIMIT 100`), lịch sử `wallet_entries` của user (`ORDER BY id`), thay đổi DB gần đây (khôi phục từ `backup.md`? `psql` thủ công?). **Sổ cái là nguồn sự thật:** số dư suy ra từ sổ cái đúng hơn cột `wallets`.
4. Sửa: đưa cột `wallets` về đúng số suy ra, trong một transaction bằng role chủ bảng, kèm ghi chú vào sổ vận hành (không có API làm việc này vì cố ý). Chạy lại `ledger-integrity` phải 0.
5. Nếu sổ cái cũng sai (hiếm): KHÔNG sửa/xóa bút toán; thêm bút toán đảo (`adjust`/`reverse`) có `idem_key` rõ ràng và ghi nguyên nhân.

## B. Hoa hồng không khớp với số Shopee trả thật
`reconciliation` chỉ so dữ liệu trong hệ thống (đơn Shopee đã đồng bộ ↔ bút toán ví). Khi Shopee trả hoa hồng một kỳ (PO nhập số thật):
1. Lấy `completed.shopee_commission_vnd` của các tháng thuộc kỳ trả, so với số tiền Shopee chuyển thực. Chênh lệch nhỏ do làm tròn: `shopee_commission_vnd` cộng micro rồi quy đổi xuống nên ≤ vài đồng/tháng.
2. Chênh lớn: (a) đơn `COMPLETED` trong hệ thống nhưng Shopee chưa tính (đang trong thời gian chờ của Shopee, đối chiếu `hold_days`); (b) đơn bị Shopee điều chỉnh/hủy sau khi ta ghi `COMPLETED` (đối chiếu `status_conflicts` ở `order-sync.md`); (c) phần "đơn mồ côi" (không thuộc ai): nằm trong `platform_margin_vnd` nhưng không có người chịu chia; (d) lệch múi giờ ranh giới tháng (đối soát dùng UTC, nửa mở).
3. **Đừng chuyển tiền cho user chỉ dựa vào số ước tính**: nếu Shopee trả thiếu, kiểm tra các đơn nghi ngờ trước khi `release`, tăng `hold_days` (cấu hình `platform_settings`, có hiệu lực từ lúc đổi, không hồi tố).
4. Khoản lỗ admin (`admin_loss_vnd`, bút toán `adjust`): user đã rút trước khi đơn bị thu hồi. Theo dõi tổng theo tháng; tăng `hold_days` nếu tăng đều.
5. Ghi lại kết quả đối chiếu từng kỳ (tháng, số hệ thống, số Shopee, chênh, nguyên nhân) vào sổ vận hành.
