# LOG

- Bước 0: gộp 7 nhánh vào autopilot/main. 594 passed ×2, vitest 189 passed (0 skip), tsc/build/lint sạch, DB sạch. Xung đột duy nhất: `backend/tests/unit/test_core_config.py` (giữ cả hai khối test).
- T-018 (task/T-018): SUBID_SECRET_PREVIOUS. 600 passed ×2, lint sạch, DB sạch. Đột biến 6/6 bị bắt. ponytail-review: không có lỗi cần sửa.
- audit-login (task/audit-login): auth.login vào audit_logs. 601 passed ×2, lint sạch, DB sạch. Đột biến 2/2 bị bắt. Review: thay đổi nhỏ trong auth.api, không có phát hiện.
