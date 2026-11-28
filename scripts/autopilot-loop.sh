#!/usr/bin/env bash
# Chạy autopilot lặp lại: mỗi vòng là một phiên Claude Code MỚI (claude -p), đọc luật + trạng thái rồi làm tiếp.
# Lý do: một lần dán prompt chỉ chạy đến khi Claude tự kết thúc lượt (viết tóm tắt rồi dừng). Vòng lặp này nối tiếp.
#
#   caffeinate -dimsu bash scripts/autopilot-loop.sh        # macOS: giữ máy không ngủ
#   Dừng:  touch docs/autopilot/STOP   (hoặc Ctrl+C)
#   Cờ quyền: CLAUDE_FLAGS="..." bash scripts/autopilot-loop.sh   (cùng chế độ quyền bạn đang dùng; xem `claude --help`)
#   Log mỗi vòng: .autopilot-runs/<thời gian>.log  (đã thêm vào .gitignore)
set -u
cd "$(git rev-parse --show-toplevel)"

STOP=docs/autopilot/STOP
RULES=docs/autopilot/RULES.md
STATE=docs/autopilot/STATE.md
RUNS=.autopilot-runs
FLAGS="${CLAUDE_FLAGS:-}"
PAUSE_LIMIT="${PAUSE_ON_LIMIT:-1800}"   # giây nghỉ khi lỗi liên tiếp (thường là hết hạn mức)

command -v claude >/dev/null || { echo "Chưa cài Claude Code CLI" >&2; exit 1; }
[[ -f "$RULES" ]] || { echo "Thiếu $RULES: chép PROMPT_autopilot.md vào đó và commit trước khi chạy" >&2; exit 1; }
BR="$(git branch --show-current)"
if [[ "$BR" == "main" || "$BR" == "master" ]]; then
  echo "Đang ở nhánh $BR. Autopilot không được chạy trên nhánh này. Chạy: git switch autopilot/main" >&2; exit 1
fi
mkdir -p "$RUNS"
grep -qxF "$RUNS/" .gitignore 2>/dev/null || echo "$RUNS/" >> .gitignore

PROMPT="Đọc docs/autopilot/RULES.md (luật bắt buộc, không được sửa) và docs/autopilot/STATE.md (nếu có), rồi tiếp tục autopilot theo đúng luật. Làm liên tục nhiều task. Khi đã xong khoảng 5 task hoặc context sắp đầy: cập nhật STATE.md, LOG.md, REPORT.md rồi kết thúc phiên (vòng sau sẽ tự nối tiếp). Không hỏi lại."

fails=0; n=0
while [[ ! -f "$STOP" ]]; do
  n=$((n + 1)); ts=$(date +%Y%m%d-%H%M%S)
  echo "▶ vòng $n ($ts)"
  # shellcheck disable=SC2086
  claude -p "$PROMPT" $FLAGS >"$RUNS/$ts-v$n.log" 2>&1
  rc=$?
  if [[ $rc -ne 0 ]]; then
    fails=$((fails + 1))
    echo "  lỗi rc=$rc ($fails lần liên tiếp), xem $RUNS/$ts.log"
    if [[ $fails -ge 3 ]]; then
      echo "  3 lỗi liên tiếp (có thể hết hạn mức): nghỉ ${PAUSE_LIMIT}s rồi thử lại"
      sleep "$PAUSE_LIMIT"; fails=0
    else
      sleep 60
    fi
  else
    fails=0; sleep 5
  fi
done
echo "■ thấy $STOP, dừng sau $n vòng."
