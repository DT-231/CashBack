"""Chạy thật các script CLI trong tiến trình con với MOCK=1 (không gọi mạng, không dùng .env thật)."""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
FEED = Path(__file__).resolve().parents[3] / "samples" / "sample_feed.csv"


def run(script, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("SHOPEE_COOKIE", "AFF_COOKIE", "DATABASE_URL")}
    env.update(MOCK="1", SHOPEE_AFF_ID="17399999999")
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], env=env, capture_output=True, text=True,
                          timeout=60)


def test_revenue_report_json_and_human():
    r = run("revenue_report.py", "--json", "--days", "7")
    assert r.returncode == 0, r.stderr
    j = json.loads(r.stdout)
    assert j["totals"]["commission_micro"] == 403_750_000 and j["by_sub"][0]["sub_id"] == "fb01-1"
    h = run("revenue_report.py")
    assert h.returncode == 0 and "Hoa hồng: 4.038đ" in h.stdout and "fb01-1" in h.stdout


def test_verify_link_under_mock():
    r = run("verify_link.py", "--sub", "t1")
    assert r.returncode == 1 and "LINK   : https://shopee.vn/universal-link/product/" in r.stdout
    # fake trả tracked=True nhưng utm_source/utm_content rỗng -> báo "CHƯA ỔN", không bao giờ gọi mạng
    assert "CHƯA ỔN" in r.stdout


def test_feed_import_dry_run():
    r = run("feed_import.py", str(FEED), "--dry-run", "--json")
    assert r.returncode == 0, r.stderr
    j = json.loads(r.stdout)
    assert j["rows_kept"] == 3 and j["delimiter"] == ","


def test_example_agent_prints_usage_without_args():
    r = run("example_agent.py")
    assert r.returncode == 0 and "AGENT_API_KEY" in r.stdout


def test_issue_agent_key_prints_usage_without_name():
    r = run("issue_agent_key.py")
    assert r.returncode == 2 and "muse-fanpage-1" in r.stdout
