# STATE (đọc file này để tiếp tục)

Nhánh tích hợp: `autopilot/main` (từ `main` `ab014f0`). KHÔNG sửa `main`.
Lệnh kiểm chuẩn: `bash /tmp/gate.sh fe` (migrate dev DB, `make test` ×2, lint, vitest, tsc, build, đếm rác DB). Nếu /tmp bị xóa: xem mục "Kiểm" trong LOG.

## Đã gộp vào autopilot/main
T-018, audit-login, T-044, T-063, T-023, T-060, T-043 (backend + UI a/b), prep/T-043, T-065, T-011 (+T-066 UI), T-052, T-053, runbooks-ops, T-019 (TOTP), prep/T-041 (backend+BFF), T-041a, T-041b (squash), startup-db-guard, chore/codex-forbidden-paths, docs/launch-gates-table.

## Đang làm
Không có task Codex đang chạy.

## Tiếp theo (ưu tiên)
1. `/security-review` toàn repo (đã làm riêng cho T-063; làm bản tổng) và sửa lỗi tìm thấy (mỗi lỗi một commit `fix(...)`)
2. T-050/T-051 Tool API Muse AI: rà soát đủ + test hợp đồng; hiệu năng (index DB, N+1)
3. UI còn thiếu: trang cờ gian lận admin (`/admin/fraud-flags`, cần thêm allowlist), giao diện chọn kênh. Việc của PO: xem `PO-INBOX.md`

## Nhánh chờ
Không.

## Tiếp tục
`Đọc docs/autopilot/STATE.md và tiếp tục autopilot.`
