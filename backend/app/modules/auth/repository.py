"""SQL của auth. Nhận Connection đang trong transaction; không commit."""
from __future__ import annotations

from sqlalchemy import Connection, text


def email_exists(conn: Connection, email: str) -> bool:
    return conn.execute(text("SELECT 1 FROM users WHERE email = :e"), {"e": email}).first() is not None


def find_by_email(conn: Connection, email: str):
    return conn.execute(text("SELECT id, email, password_hash, role, status FROM users WHERE email = :e"),
                        {"e": email}).mappings().first()


def find_by_id(conn: Connection, user_id: int):
    return conn.execute(text("SELECT id, email, role, status FROM users WHERE id = :i"),
                        {"i": user_id}).mappings().first()


def create_user(conn: Connection, email: str, password_hash: str, status: str) -> int:
    # Không tạo ví ở đây: chỉ module `wallet` được ghi bảng ví (test_architecture). Ví tạo lười khi cần.
    return conn.execute(text("INSERT INTO users(email, password_hash, status) VALUES (:e, :p, :s) RETURNING id"),
                        {"e": email, "p": password_hash, "s": status}).scalar_one()


def save_refresh(conn: Connection, user_id: int, token_hash: str, ttl_days: int) -> None:
    conn.execute(text("INSERT INTO refresh_tokens(user_id, token_hash, expires_at) "
                      "VALUES (:u, :h, now() + make_interval(days => :d))"),
                 {"u": user_id, "h": token_hash, "d": ttl_days})


def consume_refresh(conn: Connection, token_hash: str) -> int | None:
    """Thu hồi và trả user_id nếu token còn hạn và chưa dùng. Một câu lệnh nên hai request song song không cùng thắng."""
    return conn.execute(text("UPDATE refresh_tokens SET revoked_at = now() "
                             "WHERE token_hash = :h AND revoked_at IS NULL AND expires_at > now() RETURNING user_id"),
                        {"h": token_hash}).scalar()


def owner_of_revoked(conn: Connection, token_hash: str) -> int | None:
    """User sở hữu token đã bị thu hồi (dấu hiệu token bị dùng lại/đánh cắp)."""
    return conn.execute(text("SELECT user_id FROM refresh_tokens WHERE token_hash = :h AND revoked_at IS NOT NULL"),
                        {"h": token_hash}).scalar()


def revoke_all(conn: Connection, user_id: int) -> None:
    conn.execute(text("UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = :u AND revoked_at IS NULL"),
                 {"u": user_id})
