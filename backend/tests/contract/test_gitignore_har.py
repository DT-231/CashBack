"""HAR và báo cáo thô chứa cookie/token/dữ liệu cá nhân: không bao giờ được vào git (xem runbook live-attribution-test)."""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("path", [
    "report.har", "samples/affiliate.shopee.vn.har", "downloads/x.redacted.har", "x.har.json",
    "har/a.json", "hars/a.json", "raw/a.json", "raw-reports/orders.json", "live-test-data/report.json",
    ".env", "image.png",
])
def test_sensitive_paths_are_gitignored(path):
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
    assert r.returncode == 0, f"{path} chưa được .gitignore chặn"


def test_committed_fixtures_are_not_ignored():
    for ok in ["backend/app/integrations/shopee/fixtures/x.json", "samples/sample_feed.csv", ".env.example"]:
        assert subprocess.run(["git", "check-ignore", "-q", ok], cwd=ROOT).returncode == 1, ok
