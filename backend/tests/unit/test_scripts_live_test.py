"""Công cụ cho runbook live-attribution-test: redact_har.py và decode_subid.py."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.core import subid

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HAR = {"log": {"entries": [{
    "request": {"url": "https://affiliate.shopee.vn/api/v3/report/list?purchase_time_s=1&csrf_token=SECRETQ&SPC_EC=abc",
                "headers": [{"name": "Cookie", "value": "SPC_ST=SECRETC"}, {"name": "X-CSRFToken", "value": "SECRETX"},
                            {"name": "Accept", "value": "json"}, {"name": "x-csrf-token", "value": "SECRETY"}],
                "cookies": [{"name": "SPC_ST", "value": "SECRETC"}],
                "queryString": [{"name": "csrf_token", "value": "SECRETQ"}, {"name": "purchase_time_s", "value": "1"}],
                "postData": {"text": '{"password": "SECRETP", "x": 1}'}},
    "response": {"headers": [{"name": "Set-Cookie", "value": "SPC_ST=SECRETS"}],
                 "cookies": [{"name": "a", "value": "SECRETS"}],
                 "content": {"text": '{"data":{"list":[{"utm_content":"1l-1-1-abc-","order_status":"X"}]},"token":"SECRETT"}'}}}]}}


def test_redact_har_removes_every_secret_but_keeps_order_data():
    out = json.dumps(_load("redact_har").redact(json.loads(json.dumps(HAR))))
    for secret in ("SECRETC", "SECRETX", "SECRETQ", "SECRETY", "SECRETS", "SECRETP", "SECRETT"):
        assert secret not in out, secret
    assert "1l-1-1-abc-" in out and "purchase_time_s=1" in out and "order_status" in out


def test_decode_subid_script_roundtrip(tmp_path, monkeypatch):
    secret = "s" * 20
    code = subid.encode("l", 7, 9, secret)
    env = {"SUBID_SECRET": secret, "PATH": "/usr/bin:/bin", "MOCK": "1"}
    r = subprocess.run([sys.executable, str(SCRIPTS / "decode_subid.py"), code], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0 and "owner(user/post id)=7" in r.stdout and "ref(link/click id)=9" in r.stdout
    assert secret not in r.stdout + r.stderr
    bad = subprocess.run([sys.executable, str(SCRIPTS / "decode_subid.py"), "1l-7-9-zzz-"], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert bad.returncode == 1 and "status=invalid" in bad.stdout
