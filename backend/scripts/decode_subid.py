#!/usr/bin/env python3
"""Giải mã utm_content (sub_id v1) bằng SUBID_SECRET trong môi trường/.env. Không gọi mạng, không in secret.

    python3 backend/scripts/decode_subid.py 1l-1-1-abc-
"""
import _bootstrap  # noqa: F401  (phải import trước app.*)
import sys

from app.core.config import ConfigError, load_settings
from app.core.subid import SubIdError, decode


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Cách dùng: decode_subid.py <utm_content>", file=sys.stderr)
        return 2
    try:
        d = decode(argv[0], list(load_settings().subid_keys()))
    except (SubIdError, ConfigError) as e:  # thiếu hoặc quá ngắn: phải đúng giá trị đã dùng khi tạo link
        print(f"SUBID_SECRET không dùng được: {e}", file=sys.stderr)
        return 2
    print(f"status={d.status} kind={d.kind} owner(user/post id)={d.owner} ref(link/click id)={d.ref} reason={d.reason}")
    return 0 if d.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
