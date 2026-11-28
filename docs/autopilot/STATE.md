# STATE (đọc file này để tiếp tục)

Nhánh tích hợp: `autopilot/main` (từ `main` `ab014f0`). KHÔNG sửa `main`.
Lệnh kiểm chuẩn: `bash /tmp/gate.sh fe` (migrate dev DB, `make test` ×2, lint, vitest, tsc, build, đếm rác DB). Nếu /tmp bị xóa: xem mục "Kiểm" trong LOG.

## Đã gộp vào autopilot/main
T-018, audit-login, T-044, T-063, T-023, T-060, T-043 (backend + UI a/b), prep/T-043, T-065, T-011 (+T-066 UI), T-052, T-053, runbooks-ops, T-019 (TOTP), prep/T-041 (backend+BFF), T-041a, T-041b (squash), startup-db-guard, chore/codex-forbidden-paths, docs/launch-gates-table, fix/public-health-minimal (rà soát bảo mật toàn repo), T-051, rà soát hiệu năng, e2e-journey, task/fraud-ui (UI cờ gian lận).

## Đang làm
Không có task Codex đang chạy.

## Tiếp theo (ưu tiên)
Backlog tự làm được đã hết. Còn: giao diện chọn kênh (cần PO quyết thiết kế), gỡ `legacy_api.py` (PO-INBOX #12), CSP nonce (đề xuất). Việc của PO: xem `PO-INBOX.md`, `REPORT.md`.

## Nhánh chờ
Không.

## Tiếp tục
`Đọc docs/autopilot/STATE.md và tiếp tục autopilot.`
