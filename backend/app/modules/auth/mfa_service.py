"""Đăng nhập hai lớp TOTP cho admin (T-019). KHÔNG biết HTTP.

- Bí mật TOTP mã hóa AES-GCM (core.crypto.MfaCipher, key_id, AAD gắn user); không bao giờ vào log/audit/response sau lúc thiết lập.
- Mã chỉ dùng một lần (last_step cập nhật nguyên tử, chống phát lại kể cả hai request song song).
- Mã khôi phục: 8 mã ngẫu nhiên, hiện một lần, lưu HMAC, mỗi mã dùng một lần.
- Phiên đã xác minh = access token có `mfa_at` còn trong `mfa_max_age_hours`; `mfa_at` đi theo refresh token và KHÔNG tự gia hạn.
- Mọi thay đổi trạng thái là `@audited` và ghi audit_logs trong cùng transaction; thất bại ghi riêng (không lộ mã).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from sqlalchemy import Engine

from app.core import totp
from app.core.config import Settings
from app.core.crypto import CryptoError, MfaCipher
from app.modules.audit import service as audit_service
from app.modules.audit.service import AuditContext, audited
from app.modules.auth import repository
from app.modules.auth.errors import MfaInvalid, MfaRequired, MfaState
from app.modules.auth.schemas import MfaStatusOut, TokenOut, UserOut
from app.modules.auth.service import AuthService

RECOVERY_CODES = 8
_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"


def new_recovery_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


class MfaService:
    READ_ONLY = frozenset({"status", "require_fresh", "cipher"})

    def __init__(self, settings: Settings, engine: Engine, clock=lambda: datetime.now(UTC)):
        self.s, self.engine, self.clock = settings, engine, clock
        self._cipher: MfaCipher | None = None

    def cipher(self) -> MfaCipher:
        if self._cipher is None:
            self._cipher = MfaCipher(self.s)         # ConfigError (503) nếu thiếu/yếu BANK_ENC_KEY
        return self._cipher

    def _hash_recovery(self, code: str) -> str:
        norm = code.strip().lower().replace("-", "").replace(" ", "")
        key = (self.s.jwt_secret.get_secret_value() + "|mfa-recovery").encode()
        return hmac.new(key, norm.encode(), hashlib.sha256).hexdigest()

    def _secret_of(self, row) -> str:
        try:
            return self.cipher().decrypt(row["key_id"], row["secret_enc"], row["user_id"])
        except CryptoError:
            raise MfaState("Không giải mã được bí mật TOTP (khóa mã hóa đã đổi?)") from None

    def _fail(self, audit: AuditContext, action: str, kind: str) -> None:
        audit_service.record_best_effort(self.engine, audit.settings, audit.actor, action, target_type="user",
                                         target_id=audit.actor.id, detail={"kind": kind}, ip=audit.ip)

    # ---------- đọc ----------
    def status(self, user_id: int, claims: dict | None = None) -> MfaStatusOut:
        with self.engine.connect() as conn:
            row = repository.get_mfa(conn, user_id)
        enabled = bool(row and row["enabled_at"])
        return MfaStatusOut(enabled=enabled, pending=bool(row and not row["enabled_at"]),
                            verified=enabled and self._fresh(claims or {}))

    def _fresh(self, claims: dict) -> bool:
        at = claims.get("mfa_at")
        return isinstance(at, int) and 0 <= self.clock().timestamp() - at <= self.s.mfa_max_age_hours * 3600

    def require_fresh(self, user_id: int, claims: dict) -> None:
        """Dùng cho route admin: đã bật TOTP VÀ phiên này đã nhập mã gần đây. Kiểm DB mỗi lần (tắt TOTP có hiệu lực ngay)."""
        with self.engine.connect() as conn:
            row = repository.get_mfa(conn, user_id)
        if not (row and row["enabled_at"]):
            raise MfaRequired("Admin phải bật đăng nhập hai lớp (TOTP) trước khi dùng chức năng này")
        if not self._fresh(claims):
            raise MfaRequired("Cần nhập mã TOTP (đăng nhập hai lớp) cho phiên này")

    # ---------- thiết lập ----------
    @audited
    def setup(self, user: UserOut, *, audit: AuditContext) -> tuple[str, str]:
        secret = totp.generate_secret()
        key_id, enc = self.cipher().encrypt(secret, user.id)
        with self.engine.begin() as conn:
            if not repository.put_pending_mfa(conn, user.id, enc, key_id):
                raise MfaState("Đã bật TOTP; tắt bằng mã hiện tại trước khi thiết lập lại")
            audit_service.record(conn, audit.settings, audit.actor, "mfa.setup", target_type="user", target_id=user.id, ip=audit.ip)
        return secret, totp.provisioning_uri(secret, user.email, self.s.mfa_issuer)

    @audited
    def enable(self, user: UserOut, code: str, *, audit: AuditContext) -> list[str]:
        codes = [new_recovery_code() for _ in range(RECOVERY_CODES)]
        with self.engine.begin() as conn:
            row = repository.get_mfa(conn, user.id)
            if row is None or row["enabled_at"]:
                raise MfaState("Chưa thiết lập TOTP, hoặc đã bật rồi")
            step = totp.verify(self._secret_of(row), code, self.clock().timestamp(), row["last_step"])
            if step is None or not repository.advance_step(conn, user.id, step, enabling=True):
                ok = False
            else:
                ok = True
                repository.replace_recovery_codes(conn, user.id, [self._hash_recovery(c) for c in codes])
                audit_service.record(conn, audit.settings, audit.actor, "mfa.enable", target_type="user", target_id=user.id,
                                     detail={"recovery_codes": RECOVERY_CODES}, ip=audit.ip)
        if not ok:
            self._fail(audit, "mfa.enable_failed", "totp")
            raise MfaInvalid("Mã không đúng hoặc đã dùng")
        return codes

    # ---------- xác minh phiên ----------
    @audited
    def verify(self, user: UserOut, code: str | None, recovery_code: str | None, *, audit: AuditContext) -> TokenOut:
        now = self.clock()
        kind = "totp" if code is not None else "recovery"
        with self.engine.begin() as conn:
            row = repository.get_mfa(conn, user.id)
            if row is None or not row["enabled_at"]:
                raise MfaState("Chưa bật TOTP")
            if code is not None:
                step = totp.verify(self._secret_of(row), code, now.timestamp(), row["last_step"])
                ok = step is not None and repository.advance_step(conn, user.id, step)
            else:
                ok = repository.use_recovery_code(conn, user.id, self._hash_recovery(recovery_code))
            if ok:
                action = "mfa.verify" if kind == "totp" else "mfa.recovery_used"
                detail = None if kind == "totp" else {"remaining": repository.unused_recovery_count(conn, user.id)}
                audit_service.record(conn, audit.settings, audit.actor, action, target_type="user", target_id=user.id,
                                     detail=detail, ip=audit.ip)
                return AuthService(self.s, self.engine).issue(conn, user.id, user.role, now)
        self._fail(audit, "mfa.verify_failed", kind)
        raise MfaInvalid("Mã không đúng hoặc đã dùng")

    @audited
    def disable(self, user: UserOut, code: str, *, audit: AuditContext) -> None:
        with self.engine.begin() as conn:
            row = repository.get_mfa(conn, user.id)
            if row is None or not row["enabled_at"]:
                raise MfaState("TOTP chưa được bật")
            step = totp.verify(self._secret_of(row), code, self.clock().timestamp(), row["last_step"])
            ok = step is not None and repository.advance_step(conn, user.id, step)
            if ok:
                repository.delete_mfa(conn, user.id)
                audit_service.record(conn, audit.settings, audit.actor, "mfa.disable", target_type="user", target_id=user.id, ip=audit.ip)
                return
        self._fail(audit, "mfa.disable_failed", "totp")
        raise MfaInvalid("Mã không đúng hoặc đã dùng")
