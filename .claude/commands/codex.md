---
description: Giao 1 hoặc nhiều task cho Codex chạy song song (vd /codex T012 T013)
argument-hint: <task-id> [task-id ...]
---

Giao các task sau cho Codex: $ARGUMENTS

Với MỖI task ID:
1. Chạy subagent `codex-worker` với task đó **ở chế độ chạy nền**, để các task chạy song song và tôi (Tech Lead) tiếp tục làm việc khác.
2. Không chờ. Báo ngay cho tôi danh sách task đã giao, rồi quay lại việc đang làm.

Khi từng subagent trả kết quả:
- **ĐẠT**: review `git diff main...task/<id>` theo checklist trong AGENTS.md. Nếu ổn thì đề xuất lệnh merge cho tôi duyệt, không tự merge.
- **CẦN TECH LEAD XEM / BLOCKED**: tóm tắt vấn đề và đề xuất hướng xử lý.
