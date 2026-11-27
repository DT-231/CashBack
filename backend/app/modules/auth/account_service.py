"""Xác minh email, quên và đặt lại mật khẩu (T-011). KHÔNG biết HTTP.

- Token: 32 byte ngẫu nhiên (urlsafe), chỉ lưu SHA-256; dùng MỘT lần (cập nhật nguyên tử); mỗi (user, mục đích) một token còn hiệu lực.
  Hạn: xác minh 24 giờ, đặt lại mật khẩu 1 giờ.
- Không lộ email nào tồn tại: các hàm `request_*` luôn trả kết quả giống nhau; việc gửi thư chạy SAU khi đã trả lời (BackgroundTasks ở API)
  nên độ trễ SMTP không làm lộ.
- Đặt lại mật khẩu: đổi mật khẩu, xóa MỌI refresh token (đăng xuất mọi thiết bị), vô hiệu token còn lại; email đã chứng minh quyền sở hữu nên
  user `unverified` thành `active`. Tài khoản `locked` KHÔNG được mở bởi đặt lại mật khẩu.
"""
from __future__ import annotations

from sqlalchemy import Engine

from app.core import security
from app.core.config import Settings
from app.core.errors import AppError
from app.modules.audit import service as audit_service
from app.modules.audit.service import Actor
from app.modules.auth import repository

VERIFY_MINUTES = 24 * 60
RESET_MINUTES = 60


class InvalidToken(AppError):
    status, code = 400, "invalid_token"


class AccountService:
    def __init__(self, settings: Settings, engine: Engine):
        self.s, self.engine = settings, engine

    # ----- phát token (trả (email, token) để API gửi thư SAU khi trả lời; None nếu không có gì để gửi) -----
    def _issue(self, conn, user, purpose: str, minutes: int):
        raw, hashed = security.new_refresh_token()          # cùng sinh 32 byte urlsafe + SHA-256
        repository.new_email_token(conn, user["id"], purpose, hashed, minutes)
        return user["email"], raw

    def request_verification(self, email: str):
        with self.engine.begin() as conn:
            u = repository.find_by_email_any(conn, email)
            return self._issue(conn, u, "verify", VERIFY_MINUTES) if u and u["status"] == "unverified" else None

    def request_reset(self, email: str):
        with self.engine.begin() as conn:
            u = repository.find_by_email_any(conn, email)
            return self._issue(conn, u, "reset", RESET_MINUTES) if u and u["status"] != "locked" else None

    def issue_verification_for(self, user_id: int, email: str):
        with self.engine.begin() as conn:
            return self._issue(conn, {"id": user_id, "email": email}, "verify", VERIFY_MINUTES)

    # ----- dùng token -----
    def verify_email(self, raw_token: str) -> None:
        with self.engine.begin() as conn:
            uid = repository.consume_email_token(conn, security.hash_refresh_token(raw_token), "verify")
            if uid is None:
                raise InvalidToken("Liên kết không hợp lệ, đã dùng hoặc đã hết hạn")
            repository.activate_if_unverified(conn, uid)
            audit_service.record(conn, self.s, Actor(uid, "user"), "auth.email_verified", target_type="user", target_id=uid)

    def reset_password(self, raw_token: str, new_password: str, ip: str | None = None) -> None:
        pw_hash = security.hash_password(new_password)                # băm trước (tốn thời gian như nhau dù token đúng hay sai)
        with self.engine.begin() as conn:
            uid = repository.consume_email_token(conn, security.hash_refresh_token(raw_token), "reset")
            if uid is None:
                raise InvalidToken("Liên kết không hợp lệ, đã dùng hoặc đã hết hạn")
            repository.set_password(conn, uid, pw_hash)
            repository.delete_all(conn, uid)                          # đăng xuất mọi thiết bị
            repository.invalidate_email_tokens(conn, uid, "reset")
            repository.activate_if_unverified(conn, uid)
            audit_service.record(conn, self.s, Actor(uid, "user"), "auth.password_reset", target_type="user", target_id=uid, ip=ip)
