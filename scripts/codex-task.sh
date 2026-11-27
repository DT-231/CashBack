#!/usr/bin/env bash
# Giao 1 task cho Codex chạy trong git worktree riêng, không đụng vào thư mục Claude đang làm.
#
#   scripts/codex-task.sh <task-id> [base-branch]
#   ví dụ: scripts/codex-task.sh T012          # tách từ main
#          scripts/codex-task.sh T012 develop  # tách từ develop
#
# Kết quả:
#   branch      task/<id>
#   worktree    ../wt-<id>
#   báo cáo     .codex-runs/<id>.md   (tin nhắn cuối của Codex)
#   log đầy đủ  .codex-runs/<id>.log
#   chọn model: CODEX_MODEL=<tên> CODEX_EFFORT=low|medium|high scripts/codex-task.sh <id>
set -euo pipefail

ID="${1:?Cách dùng: scripts/codex-task.sh <task-id> [base-branch]}"
BASE="${2:-main}"
ROOT="$(git rev-parse --show-toplevel)"
TASK="${TASK_FILE:-$ROOT/backlog/tasks/$ID.md}"
BR="task/$ID"
WT="$(cd "$ROOT/.." && pwd)/wt-$ID"
RUNS="$ROOT/.codex-runs"

command -v codex >/dev/null || { echo "Chưa cài Codex CLI (npm i -g @openai/codex)" >&2; exit 1; }
[[ -f "$TASK" ]] || { echo "Không thấy file task: $TASK" >&2; exit 1; }
mkdir -p "$RUNS"

# 1) Tạo worktree + branch riêng cho task (chạy lại thì dùng lại worktree cũ)
if [[ ! -d "$WT" ]]; then
  if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BR"; then
    git -C "$ROOT" worktree add "$WT" "$BR"
  else
    git -C "$ROOT" worktree add -b "$BR" "$WT" "$BASE"
  fi
fi

# 2) Prompt cho Codex = luật chung + nội dung task
PROMPT="$(cat <<EOF
Bạn là Developer trong team. Tech Lead (Claude Code) giao cho bạn đúng 1 task bên dưới.

Luật:
- Đọc AGENTS.md ở thư mục gốc trước và làm theo.
- Chỉ sửa các file/thư mục nằm trong phạm vi task. Cần sửa ngoài phạm vi thì DỪNG và ghi lý do vào báo cáo.
- Không đọc, không in, không sửa .env, cookie, token. Không gọi live Shopee/Facebook (dùng MOCK=1, fixture).
- Không git commit, không push. Script sẽ tự commit sau khi bạn xong.
- Chạy lệnh test ghi trong task và sửa đến khi pass.

Khi xong, câu trả lời cuối cùng của bạn PHẢI theo đúng mẫu:
## Kết quả: DONE | BLOCKED
## File đã đổi
- ...
## Test
- lệnh đã chạy + kết quả (số passed/failed thật)
## Test bị bỏ qua (skip) và lý do
- liệt kê từng test/file bị skip và vì sao (ví dụ: không có Postgres trong sandbox). Không có thì ghi "không có". KHÔNG được viết "test pass" khi test DB bị skip
## Điểm chưa chắc / cần Tech Lead xem
- ...

--- TASK $ID ---
$(cat "$TASK")
EOF
)"

# 3) Chạy Codex không tương tác, cho phép ghi trong worktree
echo "▶ Codex đang làm $ID trong $WT ..."
set +e
( cd "$WT" && codex exec ${CODEX_MODEL:+-m "$CODEX_MODEL"} ${CODEX_EFFORT:+-c "model_reasoning_effort=\"$CODEX_EFFORT\""} --sandbox workspace-write -o "$RUNS/$ID.md" "$PROMPT" ) </dev/null >"$RUNS/$ID.log" 2>&1
CODE=$?
set -e

# 4) Tự commit thay đổi lên branch task (để Claude review bằng git diff)
if [[ -n "$(git -C "$WT" status --porcelain)" ]]; then
  git -C "$WT" add -A
  git -C "$WT" commit -q -m "task($ID): Codex implementation" -m "Báo cáo: .codex-runs/$ID.md"
  echo "✔ Đã commit lên $BR"
else
  echo "• Codex không thay đổi file nào"
fi

echo "■ Xong $ID (exit $CODE)"
echo "  báo cáo : $RUNS/$ID.md"
echo "  log     : $RUNS/$ID.log"
echo "  review  : git diff $BASE...$BR"
exit "$CODE"
