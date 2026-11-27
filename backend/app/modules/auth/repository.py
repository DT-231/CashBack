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


def save_refresh(conn: Connection, user_id: int, token_hash: str, ttl_days: int, mfa_at=None) -> None:
    conn.execute(text("INSERT INTO refresh_tokens(user_id, token_hash, expires_at, mfa_at) "
                      "VALUES (:u, :h, now() + make_interval(days => :d), :m)"),
                 {"u": user_id, "h": token_hash, "d": ttl_days, "m": mfa_at})


def consume_refresh(conn: Connection, token_hash: str):
    """Thu hồi và trả (user_id, mfa_at) nếu token còn hạn và chưa dùng; None nếu không. Một câu lệnh nên hai request song song
    không cùng thắng. `mfa_at` được GIỮ NGUYÊN qua các lần xoay vòng (không tự gia hạn: hết `mfa_max_age_hours` phải nhập lại mã)."""
    return conn.execute(text("UPDATE refresh_tokens SET revoked_at = now() "
                             "WHERE token_hash = :h AND revoked_at IS NULL AND expires_at > now() RETURNING user_id, mfa_at"),
                        {"h": token_hash}).first()


def owner_of_rotated(conn: Connection, token_hash: str, grace_seconds: int) -> int | None:
    """User sở hữu token đã bị xoay vòng QUÁ `grace_seconds` giây trước mà vẫn bị đem dùng lại (dấu hiệu bị đánh cắp).
    Trong khoảng ân hạn (hai tab refresh cùng lúc, retry mạng) thì coi là va chạm vô hại, không phải trộm."""
    return conn.execute(text("SELECT user_id FROM refresh_tokens WHERE token_hash = :h AND revoked_at IS NOT NULL "
                             "AND revoked_at < now() - make_interval(secs => :g)"),
                        {"h": token_hash, "g": grace_seconds}).scalar()


def delete_all(conn: Connection, user_id: int) -> None:
    """Đăng xuất: xóa hẳn (không để lại dấu vết 'đã thu hồi' khiến token cũ bị nhầm là bị trộm)."""
    conn.execute(text("DELETE FROM refresh_tokens WHERE user_id = :u"), {"u": user_id})


def prune(conn: Connection, user_id: int, older_than_days: int = 30) -> None:
    """Dọn token hết hạn hoặc đã thu hồi từ lâu của user (gọi khi đăng nhập, không cần job riêng)."""
    conn.execute(text("DELETE FROM refresh_tokens WHERE user_id = :u AND (expires_at < now() - make_interval(days => :d) "
                      "OR revoked_at < now() - make_interval(days => :d))"), {"u": user_id, "d": older_than_days})


def revoke_all(conn: Connection, user_id: int) -> None:
    conn.execute(text("UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = :u AND revoked_at IS NULL"),
                 {"u": user_id})


# ---------- TOTP (T-019) ----------
def get_mfa(conn: Connection, user_id: int):
    return conn.execute(text("SELECT user_id, secret_enc, key_id, enabled_at, last_step FROM user_mfa WHERE user_id = :u"),
                        {"u": user_id}).mappings().first()


def put_pending_mfa(conn: Connection, user_id: int, secret_enc: str, key_id: str) -> bool:
    """Tạo/thay bí mật CHƯA kích hoạt. False nếu đã kích hoạt (phải tắt bằng mã trước)."""
    return conn.execute(text(
        "INSERT INTO user_mfa(user_id, secret_enc, key_id) VALUES (:u, :s, :k) "
        "ON CONFLICT (user_id) DO UPDATE SET secret_enc = :s, key_id = :k, last_step = 0, created_at = now() "
        "WHERE user_mfa.enabled_at IS NULL RETURNING 1"), {"u": user_id, "s": secret_enc, "k": key_id}).first() is not None


def advance_step(conn: Connection, user_id: int, step: int, enabling: bool = False) -> bool:
    """Ghi bước TOTP đã dùng NGUYÊN TỬ: chỉ thành công nếu step > last_step (hai request song song cùng mã: chỉ một thắng)."""
    cond = "enabled_at IS NULL" if enabling else "enabled_at IS NOT NULL"
    extra = ", enabled_at = now()" if enabling else ""
    return conn.execute(text(f"UPDATE user_mfa SET last_step = :s{extra} WHERE user_id = :u AND last_step < :s AND {cond} RETURNING 1"),
                        {"u": user_id, "s": step}).first() is not None


def delete_mfa(conn: Connection, user_id: int) -> None:
    conn.execute(text("DELETE FROM mfa_recovery_codes WHERE user_id = :u"), {"u": user_id})
    conn.execute(text("DELETE FROM user_mfa WHERE user_id = :u"), {"u": user_id})


def replace_recovery_codes(conn: Connection, user_id: int, hashes: list[str]) -> None:
    conn.execute(text("DELETE FROM mfa_recovery_codes WHERE user_id = :u"), {"u": user_id})
    for h in hashes:
        conn.execute(text("INSERT INTO mfa_recovery_codes(user_id, code_hash) VALUES (:u, :h)"), {"u": user_id, "h": h})


def use_recovery_code(conn: Connection, user_id: int, code_hash: str) -> bool:
    """Dùng mã khôi phục MỘT lần (nguyên tử)."""
    return conn.execute(text("UPDATE mfa_recovery_codes SET used_at = now() WHERE user_id = :u AND code_hash = :h "
                             "AND used_at IS NULL RETURNING 1"), {"u": user_id, "h": code_hash}).first() is not None


def unused_recovery_count(conn: Connection, user_id: int) -> int:
    return conn.execute(text("SELECT count(*) FROM mfa_recovery_codes WHERE user_id = :u AND used_at IS NULL"), {"u": user_id}).scalar_one()
