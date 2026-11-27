"""Luật phụ thuộc, ép bằng test (docs/refactor/02-target.md §3). Test fail = vi phạm kiến trúc."""
import ast
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
FILES = [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]
HTTP_LIBS = {"requests", "httpx", "urllib3", "playwright", "aiohttp"}


def rel(p: Path) -> str:
    return p.relative_to(APP).as_posix()


def imports(p: Path):
    for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            yield from (a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            yield n.module


def test_only_shopee_integration_uses_http_libs_or_shopee_hosts():
    bad = []
    for p in FILES:
        if rel(p).startswith("integrations/") or rel(p) == "core/config.py":   # config chỉ chứa URL mặc định
            continue
        if any(i.split(".")[0] in HTTP_LIBS for i in imports(p)) or re.search(r"https?://[\w.-]*shopee\.vn/api",
                                                                              p.read_text(encoding="utf-8")):
            bad.append(rel(p))
    assert not bad, f"chỉ integrations/ được gọi ra ngoài: {bad}"


def test_env_is_read_only_in_config():
    bad = [rel(p) for p in FILES if rel(p) != "core/config.py"
           and re.search(r"os\.(environ|getenv)", p.read_text(encoding="utf-8"))]
    assert not bad, f"chỉ core/config.py được đọc env: {bad}"


def test_core_does_not_import_modules_or_integrations():
    bad = [rel(p) for p in FILES if rel(p).startswith("core/")
           and any(i.startswith(("app.modules", "app.integrations")) for i in imports(p))]
    assert not bad, bad


def test_only_audit_module_writes_audit_logs():
    pat = re.compile(r"(?is)(insert\s+into|update|delete\s+from)\s+audit_logs\b")
    bad = [rel(p) for p in FILES if not rel(p).startswith("modules/audit/") and pat.search(p.read_text(encoding="utf-8"))]
    assert not bad, f"chỉ modules/audit được ghi audit_logs: {bad}"


def test_only_wallet_module_writes_wallet_tables():
    pat = re.compile(r"(?is)(insert\s+into|update|delete\s+from)\s+(wallets|wallet_entries)\b")
    bad = [rel(p) for p in FILES if not rel(p).startswith("modules/wallet/")
           and pat.search(p.read_text(encoding="utf-8"))]
    assert not bad, f"chỉ modules/wallet được ghi ví: {bad}"


def test_layering_api_service_repository():
    bad = []
    for p in FILES:
        parts = rel(p).split("/")
        if len(parts) != 3 or parts[0] != "modules":
            continue
        mod, name = parts[1], parts[2]
        for i in imports(p):
            m = re.match(r"app\.modules\.(\w+)\.(\w+)", i)
            if not m:
                continue
            other_mod, other_file = m.groups()
            if name == "api.py" and other_file == "repository":
                bad.append(f"{rel(p)} api -> repository ({i})")
            if name == "repository.py" and other_file in ("service", "api"):
                bad.append(f"{rel(p)} repository đi ngược lên ({i})")
            if other_mod != mod and other_file == "repository":
                bad.append(f"{rel(p)} import repository của module khác ({i})")
    assert not bad, bad
