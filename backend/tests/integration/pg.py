"""Kết nối Postgres cho integration test. DB dev: `make db-up` (docker compose, cổng 5433)."""
import os

from sqlalchemy import create_engine, text

DB_URL = os.environ.get("DATABASE_URL") or "postgresql+psycopg://cashback:cashback_dev@127.0.0.1:5433/cashback"


def pg_available() -> bool:
    try:
        with create_engine(DB_URL, connect_args={"connect_timeout": 2}).connect() as c:
            c.execute(text("SELECT 1 FROM users LIMIT 1"))   # đã migrate chưa
        return True
    except Exception:  # noqa: BLE001 - mọi lỗi kết nối/thiếu bảng đều nghĩa là "bỏ qua"
        return False
