# LOG

- Bước 0: gộp 7 nhánh vào autopilot/main. 594 passed ×2, vitest 189 passed (0 skip), tsc/build/lint sạch, DB sạch. Xung đột duy nhất: `backend/tests/unit/test_core_config.py` (giữ cả hai khối test).
- T-018 (task/T-018): SUBID_SECRET_PREVIOUS. 600 passed ×2, lint sạch, DB sạch. Đột biến 6/6 bị bắt. ponytail-review: không có lỗi cần sửa.
- audit-login (task/audit-login): auth.login vào audit_logs. 601 passed ×2, lint sạch, DB sạch. Đột biến 2/2 bị bắt. Review: thay đổi nhỏ trong auth.api, không có phát hiện.
- T-044 (task/T-044): gán tay đơn mồ côi (admin+TOTP). 608 passed ×2, lint sạch, DB sạch. Đột biến 8/9 bị bắt; O9 (bỏ kiểm tra kết quả UPDATE) tương đương vì còn khóa dòng (hai lớp phòng thủ). Quyết định staff→admin: xem DECISIONS.
- T-063 (task/T-063): cookie Shopee mã hóa trong DB (admin+TOTP, không đọc lại), trạng thái cho worker, worker dùng cookie DB. 616 passed ×2, lint sạch, DB sạch. Đột biến 10/10 bị bắt (1 ca sống sót đã thêm test). security-review: không có phát hiện ≥8; 2 ghi chú thấp.
