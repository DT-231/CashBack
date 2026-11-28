# Báo cáo autopilot (cập nhật 2026-11-28)

Nhánh tích hợp: **`autopilot/main`** (đã push; `main` KHÔNG bị sửa). Số liệu cuối: `make test` **735 passed** (chạy 2 lần liên tiếp, 0 skip, DB sạch sau test), vitest **323 passed** (0 skip), `ruff`, `tsc`, `next build` sạch.

## Đã làm (mỗi mục: nhánh, đã qua thử đột biến; chi tiết số liệu trong `LOG.md`)
- Gộp 7 nhánh chờ duyệt: T-019 (TOTP admin), prep/T-041 + T-041a/b (rút tiền: backend, BFF, UI người dùng và admin), startup-db-guard, chore/codex-forbidden-paths, docs/launch-gates-table.
- **Bảo mật/tiền:** T-018 (`SUBID_SECRET_PREVIOUS`), T-044 (gán đơn mồ côi, admin+TOTP), T-063 (cookie Shopee mã hóa, không đọc lại được), T-023 (cảnh báo Telegram), T-053 (cờ gian lận, chỉ cờ), T-052 (đối soát + kiểm toàn vẹn sổ cái), `auth.login` vào audit, hardening (public `/health` tối giản, header web).
- **Vận hành:** T-060 (sao lưu mã hóa + khôi phục, đã thử đầu-cuối trên DB dev), T-065 (che log mở rộng + `/admin/health`), runbook (máy nhà tắt, đối soát lệch, sao lưu, email, gian lận, TOTP, DB role).
- **Tài khoản:** T-011 (xác minh email, quên/đặt lại mật khẩu; Mailer SMTP).
- **Admin:** T-043 backend (tổng quan, người dùng + khóa/mở, đơn) và UI (T-043a, T-043b, T-066: đơn mồ côi, cookie Shopee, health, đối soát); UI khôi phục tài khoản (T-066).
- **Admin (cờ gian lận):** UI `/admin/fraud-flags` (task/fraud-ui; đột biến 13: 10 bắt, 1 sống sót đã thêm test, 3 tương đương).
- **Muse AI:** T-051 (`/agent/insights` + schema tool).
- Codex: T-043a, T-043b, T-066 (UI), mỗi cái 1 đến 2 vòng phản hồi; tôi sửa trực tiếp các test còn thiếu sau vòng cuối.

## Quyết định tự đưa ra — PO nên xem lại TRƯỚC khi merge (`DECISIONS.md`)
1. **T-044 và T-043: staff không xem/gán/khóa**, chỉ admin (+TOTP) (backlog cũ ghi staff+). Đảo ngược: đổi dependency `require_admin`.
2. T-018: tối đa 3 khóa cũ; mỗi khóa tăng xác suất khớp nhầm chữ ký 3 ký tự ~1/46656 (còn kiểm tra sở hữu).
3. CSP chưa có `script-src` (cần nonce, không thử được trên trình duyệt thật ở đây).
4. Tài khoản đầu tiên cũng phải chờ 48 giờ (quyết định từ trước, không đổi).

## Việc của PO (`PO-INBOX.md`, 12 mục; quan trọng nhất)
Dữ liệu Shopee thật (ngày trả hoa hồng → `hold_days`; đơn mua thử; HAR có đủ trạng thái), domain riêng, xác nhận với Shopee về cashback, trang điều khoản (luật sư), `cashback_app`, sao lưu `BANK_ENC_KEY` và `BACKUP_ENC_KEY`, cron sao lưu, SMTP/Telegram nếu muốn, quyết định gỡ `legacy_api`. **Gỡ `.claude/settings.json` khỏi `autopilot/main` trước khi merge** (mục 9).

## Việc bị park / chưa làm
Không có việc bị kẹt (`PARKED.md` trống). Chưa làm có chủ ý: import CSV báo cáo thủ công T-024 (cần mẫu CSV thật của Shopee), VietQR (cần bảng mã BIN), giao diện chọn kênh (cần PO quyết thiết kế), `script-src` CSP, luật gian lận theo UA/thiết bị (chưa có dữ liệu), gỡ `legacy_api`.
`WITHDRAWALS_ENABLED` vẫn 0 ở mọi nơi; không có gọi live nào tới Shopee/Facebook/Cloudflare/Neon; không có secret trong repo.

## Cách xem và merge
```bash
git diff main...autopilot/main --stat
git log --oneline main..autopilot/main | head -80
git rm --cached .claude/settings.json && git commit -m "chore: untrack local plugin config"   # trên autopilot/main, trước khi merge
git checkout main && git merge --no-ff autopilot/main      # bạn tự duyệt và merge
```
Sau merge: `cd backend && DATABASE_URL=... ../.venv/bin/python -m alembic upgrade head` (migration 0004 đến 0010 đều có `downgrade`).
