"""audit_logs là bảng chỉ-thêm (trigger chặn DELETE), nên test không dọn từng dòng được. Sau cả phiên test, xóa mọi dòng audit
sinh ra TRONG phiên này (id > mốc lúc bắt đầu) để DB dev không còn rác. Trigger tắt/bật trong cùng một transaction."""
import pytest
from sqlalchemy import create_engine, text

from sqlalchemy.engine import make_url

from tests.integration.pg import DB_URL, pg_available

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


@pytest.fixture(scope="session", autouse=True)
def _cleanup_audit_rows_created_by_tests():
    if not pg_available():
        yield
        return
    if make_url(DB_URL).host not in LOOPBACK:      # dọn bằng cách tắt trigger: tuyệt đối không làm trên DB không phải máy này
        yield
        return
    eng = create_engine(DB_URL)
    with eng.connect() as c:
        start = c.execute(text("SELECT COALESCE(MAX(id), 0) FROM audit_logs")).scalar_one()
    yield
    with eng.begin() as c:
        c.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_no_change"))
        c.execute(text("DELETE FROM audit_logs WHERE id > :s"), {"s": start})
        c.execute(text("ALTER TABLE audit_logs ENABLE TRIGGER audit_logs_no_change"))
    eng.dispose()
