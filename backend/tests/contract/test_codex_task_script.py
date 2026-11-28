"""scripts/codex-task.sh: dùng codex GIẢ (không gọi Codex thật). Đường dẫn cấm thì không commit; việc bình thường vẫn commit."""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "codex-task.sh"
FAKE = """#!/bin/bash
out=""; while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; -m|-c|--sandbox) shift 2;; exec) shift;; *) shift;; esac; done
for f in $FAKE_FILES; do mkdir -p "$(dirname "$f")"; echo "x" > "$f"; done
echo "## Kết quả: DONE" > "$out"
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def sandbox(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "backlog" / "tasks").mkdir(parents=True)
    (repo / "scripts" / "codex-task.sh").write_text(SCRIPT.read_text())
    (repo / "backlog" / "tasks" / "T-999.md").write_text("# task giả\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.test")
    git(repo, "config", "user.name", "t")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "codex").write_text(FAKE)
    (bindir / "codex").chmod(0o755)

    def run(files: list[str]):
        env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", FAKE_FILES=" ".join(files))
        r = subprocess.run(["bash", "scripts/codex-task.sh", "T-999", "main"], cwd=repo, env=env, capture_output=True, text=True)
        wt = tmp_path / "wt-T-999"
        return r, git(wt, "rev-parse", "HEAD"), git(wt, "rev-parse", "main"), wt
    return run


FORBIDDEN = [".env", ".env.local", "frontend/.env.production", "capture.har", "traffic.har.json", "frontend/node_modules",
             "frontend/node_modules/x/index.js", "k.key", "certs/server.pem", "my_secret.txt", "docs/MySecrets.md",
             "raw/report.json", "backend/raw/x.json", "live-test-data/orders.json"]


@pytest.mark.parametrize("path", FORBIDDEN)
def test_forbidden_path_blocks_the_commit_with_a_clear_error(sandbox, path):
    r, head, base, wt = sandbox(["src/ok.txt", path])
    assert r.returncode == 3, r.stdout + r.stderr
    assert head == base                                             # không commit gì (kể cả file hợp lệ đi kèm)
    assert path.split("/")[0] in r.stderr or path in r.stderr
    assert "DỪNG" in r.stderr and "Đã commit" not in r.stdout
    assert git(wt, "diff", "--cached", "--name-only") == ""        # đã bỏ staging
    assert (wt / "src" / "ok.txt").exists()                         # file vẫn còn trong worktree để xem


@pytest.mark.parametrize("path", [".env.example", "frontend/.env.example", "src/ok.txt", "docs/har-notes.md", "frontend/src/harness.ts",
                                  "frontend/src/app/raw-data.ts", "docs/runbooks/live-attribution-test.md"])
def test_normal_files_are_still_committed(sandbox, path):
    r, head, base, wt = sandbox([path])
    assert r.returncode == 0, r.stdout + r.stderr
    assert head != base and "Đã commit" in r.stdout
    assert path in git(wt, "show", "--name-only", "--format=", "HEAD").splitlines()


def test_no_change_means_no_commit(sandbox):
    r, head, base, _ = sandbox([])
    assert r.returncode == 0 and head == base and "không thay đổi" in r.stdout
