# STATE (đọc file này để tiếp tục)

Nhánh tích hợp: `autopilot/main` (từ `main` `ab014f0`). KHÔNG sửa `main`.
Lệnh kiểm chuẩn: `bash /tmp/gate.sh fe` (migrate dev DB, `make test` ×2, lint, vitest, tsc, build, đếm rác DB). Nếu /tmp bị xóa: xem mục "Kiểm" trong LOG.

## Đã gộp vào autopilot/main
T-019 (TOTP), prep/T-041 (backend+BFF), T-041a, T-041b (squash), startup-db-guard, chore/codex-forbidden-paths, docs/launch-gates-table.

## Đang làm
(xem LOG.md dòng cuối)

## Tiếp theo (ưu tiên)
1. T-018 SUBID_SECRET nhiều khóa
2. Ghi `auth.login` vào audit_logs
3. main_worker/app/jobs, legacy_api, rà soát bảo mật, runbook thiếu, độ phủ test

## Nhánh chờ
Không.

## Tiếp tục
`Đọc docs/autopilot/STATE.md và tiếp tục autopilot.`
