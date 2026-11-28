"""Kết nối Postgres. Repository nhận `Connection` đang trong transaction; service quyết định ranh giới."""
from __future__ import annotations

from sqlalchemy import Engine, create_engine, text

from app.core.config import ConfigError, Settings


def make_engine(settings: Settings) -> Engine:
    if not settings.database_url:
        raise ConfigError("Thiếu biến môi trường: DATABASE_URL")
    return create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)


# Bảng bất biến mà ứng dụng không được phép là chủ sở hữu (chủ sở hữu tắt được trigger, TRUNCATE sau khi tắt trigger...)
IMMUTABLE_TABLES = ("audit_logs", "wallet_entries")


def assert_least_privilege(engine: Engine) -> None:
    """Từ chối chạy nếu user DB hiện tại là superuser, chủ sở hữu (hoặc thành viên kế thừa của chủ sở hữu) các bảng bất biến.
    Kiểm bằng truy vấn catalog (không đoán theo tên role). Dùng khi bật rút tiền: xem docs/runbooks/db-roles.md."""
    with engine.connect() as conn:
        me, is_super = conn.execute(text("SELECT current_user, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)")).one()
        owners = conn.execute(text(
            "SELECT tablename, tableowner, pg_has_role(current_user, tableowner, 'USAGE') AS can_act_as_owner "
            "FROM pg_tables WHERE schemaname = current_schema() AND tablename = ANY(:t)"), {"t": list(IMMUTABLE_TABLES)}).all()
    found = {r[0] for r in owners}
    problems = []
    if is_super:
        problems.append("là superuser")
    problems += [f"là (hoặc kế thừa quyền của) chủ sở hữu bảng {t}" for t, _, acts in owners if acts]
    missing = set(IMMUTABLE_TABLES) - found
    if missing:
        problems.append(f"không thấy bảng {sorted(missing)} (chưa migrate hoặc sai schema)")
    if problems:
        raise ConfigError(
            f"WITHDRAWALS_ENABLED=1 nhưng user DB '{me}' " + "; ".join(problems) + ". Chạy API bằng role riêng không sở hữu bảng "
            "(infra/db/app-role.sql, docs/runbooks/db-roles.md); migration chạy bằng role chủ sở hữu")
