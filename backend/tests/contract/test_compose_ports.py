"""Mọi cổng publish trong docker-compose phải gắn vào 127.0.0.1 (T-017): chỉ cloudflared/BFF cùng máy mới tới được.
Cổng '5433:5432' (không ghi IP) nghĩa là 0.0.0.0, tức mở ra mạng LAN/Internet và cho phép giả header IP."""
import re
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[3] / "infra" / "docker-compose.yml"
LOOPBACK_PORT = re.compile(r'^127\.0\.0\.1:\d+:\d+(/(tcp|udp))?$')


def published_ports(text: str) -> list[str]:
    ports, in_ports, indent = [], False, 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        cur = len(line) - len(line.lstrip())
        if stripped == "ports:":
            in_ports, indent = True, cur
        elif in_ports and stripped.startswith("- ") and cur > indent:
            ports.append(stripped[2:].strip().strip('"').strip("'"))
        elif in_ports and cur <= indent:
            in_ports = False
    return ports


def test_every_published_port_is_bound_to_loopback():
    ports = published_ports(COMPOSE.read_text())
    assert ports, "không tìm thấy mục ports: (parser hỏng hoặc compose đổi cấu trúc)"
    bad = [p for p in ports if not LOOPBACK_PORT.match(p)]
    assert not bad, f"cổng không gắn 127.0.0.1: {bad}"


def test_checker_catches_exposed_ports():
    for exposed in ['"5433:5432"', '"0.0.0.0:8080:8080"', '"8080"', '"[::]:8080:8080"']:
        text = f"services:\n  api:\n    ports:\n      - {exposed}\n"
        assert [p for p in published_ports(text) if not LOOPBACK_PORT.match(p)], exposed
    ok = 'services:\n  api:\n    ports:\n      - "127.0.0.1:8080:8080"\n'
    assert all(LOOPBACK_PORT.match(p) for p in published_ports(ok))
