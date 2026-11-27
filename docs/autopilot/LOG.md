# LOG

- Bước 0: gộp 7 nhánh vào autopilot/main. 594 passed ×2, vitest 189 passed (0 skip), tsc/build/lint sạch, DB sạch. Xung đột duy nhất: `backend/tests/unit/test_core_config.py` (giữ cả hai khối test).
- T-018 (task/T-018): SUBID_SECRET_PREVIOUS. 600 passed ×2, lint sạch, DB sạch. Đột biến 6/6 bị bắt. ponytail-review: không có lỗi cần sửa.
- audit-login (task/audit-login): auth.login vào audit_logs. 601 passed ×2, lint sạch, DB sạch. Đột biến 2/2 bị bắt. Review: thay đổi nhỏ trong auth.api, không có phát hiện.
- T-044 (task/T-044): gán tay đơn mồ côi (admin+TOTP). 608 passed ×2, lint sạch, DB sạch. Đột biến 8/9 bị bắt; O9 (bỏ kiểm tra kết quả UPDATE) tương đương vì còn khóa dòng (hai lớp phòng thủ). Quyết định staff→admin: xem DECISIONS.
- T-063 (task/T-063): cookie Shopee mã hóa trong DB (admin+TOTP, không đọc lại), trạng thái cho worker, worker dùng cookie DB. 616 passed ×2, lint sạch, DB sạch. Đột biến 10/10 bị bắt (1 ca sống sót đã thêm test). security-review: không có phát hiện ≥8; 2 ghi chú thấp.
- T-023 (task/T-023): cảnh báo Telegram cookie chết (ngay khi bị chặn, nhắc 6h, báo hồi phục) + notifier trong integrations/telegram. 624 passed ×2, lint sạch, DB sạch. Đột biến 8/8 bị bắt (N6 sau khi thêm test). Chưa gửi Telegram thật.
- Housekeeping (5 task): worktree đã gộp được gỡ (nhánh giữ nguyên). make test ≈ 31s/624 test.
- T-060 (task/T-060): backup_db.py (pg_dump→AES-GCM theo khối, xoay vòng, verify, restore) + runbook. 638 passed ×2, lint sạch, DB sạch. Đột biến 10: 8 bị bắt, 2 tương đương (rotate keep=0, nhánh dữ liệu thừa không tới được → đã xóa); đã thêm test cho tự kiểm + header-only; tìm ra và sửa lỗi để lại tệp hỏng. Thử đầu-cuối thật trên DB dev: backup→verify→restore, số dòng và phiên bản 0008 khớp. Cron/khóa: PO.
