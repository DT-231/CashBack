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
# Đường dẫn CẤM: không bao giờ tự commit. `.env.example` là ngoại lệ hợp lệ (không chứa giá trị thật).
forbidden_paths() {
  local f base
  while IFS= read -r f; do
    base="${f##*/}"
    if { [[ "$base" == .env* && "$base" != ".env.example" ]]; } \
       || [[ "$base" =~ \.har($|\.) ]] \
       || [[ "/$f/" == */node_modules/* ]] \
       || [[ "$base" == *.key || "$base" == *.pem ]] \
       || [[ "$(printf '%s' "$f" | tr '[:upper:]' '[:lower:]')" == *secret* ]] \
       || [[ "/$f" == */raw/* || "/$f" == */live-test-data/* ]]; then
      printf '%s\n' "$f"
    fi
  done
}

if [[ -n "$(git -C "$WT" status --porcelain)" ]]; then
  git -C "$WT" add -A
  BAD="$(git -C "$WT" diff --cached --name-only | forbidden_paths)"
  if [[ -n "$BAD" ]]; then
    git -C "$WT" reset -q          # bỏ staging, KHÔNG commit; file vẫn còn trong worktree để xem
    echo "✖ DỪNG: Codex tạo/sửa đường dẫn bị cấm, không commit gì:" >&2
    while IFS= read -r bad_path; do echo "    $bad_path" >&2; done <<< "$BAD"
    echo "  (cấm: .env*, *.har*, node_modules, *.key, *.pem, *secret*, raw/, live-test-data/; xem $WT)" >&2
    exit 3
  fi
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
