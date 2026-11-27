"""Nghiệp vụ đăng ký, đăng nhập, làm mới phiên. KHÔNG biết HTTP, KHÔNG có SQL."""
from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from app.core import security
from app.core.config import Settings
from app.modules.auth import repository
from app.modules.auth.errors import (AccountLocked, EmailTaken, EmailUnverified, InvalidCredentials,
                                     InvalidRefresh)
from app.modules.auth.schemas import TokenOut, UserOut

REUSE_GRACE_SECONDS = 10   # hai request refresh cùng token trong khoảng này không bị coi là trộm


class AuthService:
    def __init__(self, settings: Settings, engine: Engine):
        self.s, self.engine = settings, engine

    def issue(self, conn, user_id: int, role: str, mfa_at=None) -> TokenOut:
        """Cặp token mới. `mfa_at` (datetime) ghi cả vào refresh token để giữ trạng thái đã xác minh hai lớp khi làm mới."""
        raw, hashed = security.new_refresh_token()
        repository.save_refresh(conn, user_id, hashed, self.s.refresh_ttl_days, mfa_at)
        return TokenOut(access_token=security.make_access_token(self.s, user_id, role, int(mfa_at.timestamp()) if mfa_at else None),
                        refresh_token=raw, expires_in=self.s.access_ttl_min * 60)

    _issue = issue

    def register(self, email: str, password: str) -> UserOut:
        status = "unverified" if self.s.require_email_verify else "active"
        pw_hash = security.hash_password(password)
        try:
            with self.engine.begin() as conn:
                uid = repository.create_user(conn, email, pw_hash, status)
        except IntegrityError:     # email trùng (UNIQUE) kể cả khi hai request đăng ký cùng lúc
            raise EmailTaken("Email đã được đăng ký") from None
        return UserOut(id=uid, email=email, role="member", status=status)

    def login(self, email: str, password: str) -> TokenOut:
        with self.engine.begin() as conn:
            u = repository.find_by_email(conn, email)
            if not security.verify_password(password, u["password_hash"] if u else None):
                raise InvalidCredentials("Email hoặc mật khẩu không đúng")
            if u["status"] == "locked":
                raise AccountLocked("Tài khoản đã bị khóa")
            if u["status"] != "active":
                raise EmailUnverified("Vui lòng xác minh email trước khi đăng nhập")
            repository.prune(conn, u["id"])
            return self._issue(conn, u["id"], u["role"])

    def refresh(self, raw_token: str) -> TokenOut:
        token_hash = security.hash_refresh_token(raw_token)
        reused_by = None
        with self.engine.begin() as conn:
            row = repository.consume_refresh(conn, token_hash)
            if row is not None:
                uid, mfa_at = row
                u = repository.find_by_id(conn, uid)
                if u and u["status"] == "active":
                    return self._issue(conn, uid, u["role"], mfa_at)
            else:
                reused_by = repository.owner_of_rotated(conn, token_hash, REUSE_GRACE_SECONDS)
                if reused_by is not None:       # token đã dùng mà vẫn bị đem ra dùng lại: thu hồi mọi phiên
                    repository.revoke_all(conn, reused_by)
        raise InvalidRefresh("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại")

    def logout_all(self, user_id: int) -> None:
        with self.engine.begin() as conn:
            repository.delete_all(conn, user_id)

    def user_from_token(self, token: str | None) -> UserOut | None:
        claims = security.decode_access_token(self.s, token) if token else None
        if not claims:
            return None
        with self.engine.connect() as conn:
            u = repository.find_by_id(conn, int(claims["sub"]))
        return UserOut(**u) if u and u["status"] == "active" else None
