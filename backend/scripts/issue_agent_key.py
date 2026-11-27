#!/usr/bin/env python3
"""Cấp API key cho Muse AI (Tool API). Key gốc chỉ in ra MỘT lần; DB chỉ lưu hash SHA-256.

    DATABASE_URL=... python3 backend/scripts/issue_agent_key.py muse-fanpage-1
Thu hồi: UPDATE agent_keys SET revoked_at = now() WHERE name = '...'
"""
import _bootstrap  # noqa: F401
import sys

from app.core.config import load_settings
from app.core.db import make_engine
from app.modules.agent_auth.service import AgentAuth


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print(__doc__)
        return 2
    s = load_settings()
    key = AgentAuth(s, make_engine(s)).issue(sys.argv[1].strip())
    print("Lưu key này ngay, sẽ không hiện lại:\n" + key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
