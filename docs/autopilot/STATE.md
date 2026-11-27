# STATE (đọc file này để tiếp tục)

Nhánh tích hợp: `autopilot/main` (từ `main` `ab014f0`). KHÔNG sửa `main`.
Lệnh kiểm chuẩn: `bash /tmp/gate.sh fe` (migrate dev DB, `make test` ×2, lint, vitest, tsc, build, đếm rác DB). Nếu /tmp bị xóa: xem mục "Kiểm" trong LOG.

## Đã gộp vào autopilot/main
T-018, audit-login, T-044, T-063, T-023, T-060, T-043 (backend + UI a/b), prep/T-043, T-065, T-011, T-052, T-019 (TOTP), prep/T-041 (backend+BFF), T-041a, T-041b (squash), startup-db-guard, chore/codex-forbidden-paths, docs/launch-gates-table.

## Đang làm
Không có task Codex đang chạy.

## Tiếp theo (ưu tiên)
1. UI còn thiếu cho Codex: trang health + đối soát admin (`/admin/health`, `/admin/reconciliation`, `/admin/ledger-integrity`); trang member `/forgot-password`, `/reset-password`, `/verify-email` (cần thêm vào BFF allowlist: `auth/verify`, `auth/forgot`, `auth/reset`, `auth/verify/resend` là PUBLIC, đi qua `/bff/auth/*` không cần cookie)
2. T-053 phát hiện gian lận (cờ cùng ip_hash, tự mua, tỷ lệ hủy); rà soát `legacy_api.py`; runbook thiếu (Shopee 403, máy nhà tắt, đối soát lệch); độ phủ test (`make cov`); `/security-review` toàn repo; hiệu năng (index, N+1)

## Nhánh chờ
Không.

## Tiếp tục
`Đọc docs/autopilot/STATE.md và tiếp tục autopilot.`
