# STATE (đọc file này để tiếp tục)

Nhánh tích hợp: `autopilot/main` (từ `main` `ab014f0`). KHÔNG sửa `main`.
Lệnh kiểm chuẩn: `bash /tmp/gate.sh fe` (migrate dev DB, `make test` ×2, lint, vitest, tsc, build, đếm rác DB). Nếu /tmp bị xóa: xem mục "Kiểm" trong LOG.

## Đã gộp vào autopilot/main
T-018, audit-login, T-044, T-063, T-023, T-060, T-043 (backend), prep/T-043, T-019 (TOTP), prep/T-041 (backend+BFF), T-041a, T-041b (squash), startup-db-guard, chore/codex-forbidden-paths, docs/launch-gates-table.

## Đang làm
Codex T-043a (UI admin: tổng quan, người dùng, đơn) ở worktree `../wt-T-043a`, nhánh `task/T-043a` (log: /tmp/codex-T-043a.out; báo cáo `.codex-runs/T-043a.md`). Khi xong: kiểm (vitest, tsc, build, đột biến), tối đa 2 vòng phản hồi, squash vào autopilot/main. Sau đó viết `backlog/tasks/T-043b.md` (đơn mồ côi `/admin/orphans` + cookie Shopee `/admin/session`) và giao.

## Tiếp theo (ưu tiên)
1. (đã xong auth.login; login_failed cố ý không ghi: tránh phình bảng, rate limit đã có)
3. main_worker/app/jobs, legacy_api, rà soát bảo mật, runbook thiếu, độ phủ test

## Nhánh chờ
Không.

## Tiếp tục
`Đọc docs/autopilot/STATE.md và tiếp tục autopilot.`
