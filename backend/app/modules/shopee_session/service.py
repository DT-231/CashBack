"""Cookie phiên Shopee Affiliate do admin dán (T-063). Mã hóa AES-GCM at-rest; KHÔNG có đường nào đọc lại cookie qua HTTP.

- `set_cookie` (admin, @audited): lưu bản mã; trạng thái về 'unknown' để lần sync kế tiếp xác nhận.
- `status` (đọc): chỉ trạng thái, không chứa cookie.
- `load_cookie` (nội bộ, cho worker): giải mã để dựng client; không có endpoint, không ghi log.
- `record_result` (worker): cập nhật healthy/degraded/expired/blocked và đếm lỗi (nền cho cảnh báo T-023).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Engine, text

from app.core.config import Settings
from app.core.crypto import CryptoError, ShopeeCookieCipher
from app.core.errors import AppError, Forbidden
from app.modules.audit import service as audit_service
from app.modules.audit.service import AuditContext, audited

MAX_COOKIE_BYTES = 8192
ROW_ID = 1


class InvalidCookie(AppError):
    status, code = 422, "invalid_cookie"


def clean_cookie(raw: str) -> str:
    """Chấp nhận dán nguyên dòng `Cookie: a=b; c=d` hoặc nhiều dòng (giống integrations/shopee/client._clean_cookie)."""
    s = (raw or "").strip()
    if s.lower().startswith("cookie:"):
        s = s[7:]
    return "; ".join(p.strip() for p in s.replace("\r", "\n").split("\n") if p.strip()).strip(" ;")


class ShopeeSessionService:
    READ_ONLY = frozenset({"status", "load_cookie", "record_result", "cipher"})

    def __init__(self, settings: Settings, engine: Engine, clock=lambda: datetime.now(UTC)):
        self.s, self.engine, self.clock = settings, engine, clock

    def cipher(self) -> ShopeeCookieCipher:
        return ShopeeCookieCipher(self.s)          # ConfigError (503) nếu thiếu/yếu BANK_ENC_KEY

    @audited
    def set_cookie(self, cookie: str, *, audit: AuditContext) -> None:
        if audit.actor.role != "admin":
            raise Forbidden("Chỉ admin được đổi cookie Shopee")
        value = clean_cookie(cookie)
        if "=" not in value or len(value.encode()) > MAX_COOKIE_BYTES:
            raise InvalidCookie("Cookie không hợp lệ (dạng a=b; c=d, tối đa 8KB)")
        key_id, token = self.cipher().encrypt(value, ROW_ID)
        with self.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO shopee_sessions(id, cookie_enc, key_id, status, failure_count, updated_by, updated_at) "
                "VALUES (:i, :c, :k, 'unknown', 0, :u, now()) ON CONFLICT (id) DO UPDATE SET cookie_enc = :c, key_id = :k, "
                "status = 'unknown', failure_count = 0, updated_by = :u, updated_at = now()"),
                {"i": ROW_ID, "c": token, "k": key_id, "u": audit.actor.id})
            audit_service.record(conn, audit.settings, audit.actor, "shopee_session.set", target_type="shopee_session",
                                 target_id=ROW_ID, detail={"bytes": len(value.encode())}, ip=audit.ip)

    def status(self) -> dict:
        with self.engine.connect() as conn:
            r = conn.execute(text("SELECT cookie_enc IS NOT NULL AS has_cookie, status, last_ok_at, failure_count, updated_at "
                                  "FROM shopee_sessions WHERE id = :i"), {"i": ROW_ID}).mappings().first()
        return dict(r) if r else {"has_cookie": False, "status": "unknown", "last_ok_at": None, "failure_count": 0, "updated_at": None}

    def load_cookie(self) -> str | None:
        with self.engine.connect() as conn:
            r = conn.execute(text("SELECT cookie_enc, key_id FROM shopee_sessions WHERE id = :i"), {"i": ROW_ID}).first()
        if not r or not r[0]:
            return None
        try:
            return self.cipher().decrypt(r[1], r[0], ROW_ID)
        except CryptoError:
            return None                             # khóa đã đổi: coi như chưa có cookie (worker báo thiếu cookie), không lộ chi tiết

    def record_result(self, result: str, blocked: bool = False, notifier=None) -> None:
        """result: ok | partial | failed (kết quả OrderSync). Chỉ cập nhật khi đã có cookie trong DB.
        Cảnh báo (T-023): bị chặn (403/hết hạn) báo ngay; lỗi thường báo sau ALERT_AFTER_FAILURES lần liên tiếp; còn lỗi thì nhắc lại
        sau ALERT_REPEAT_HOURS; hồi phục thì báo một lần. Tin nhắn không chứa cookie."""
        message = None
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT status, failure_count, last_alert_at FROM shopee_sessions WHERE id = :i "
                                    "AND cookie_enc IS NOT NULL FOR UPDATE"), {"i": ROW_ID}).mappings().first()
            if row is None:
                return
            now = self.clock()
            if result == "ok":
                conn.execute(text("UPDATE shopee_sessions SET status = 'healthy', last_ok_at = :n, failure_count = 0, last_alert_at = NULL "
                                  "WHERE id = :i"), {"n": now, "i": ROW_ID})
                if row["last_alert_at"] is not None:
                    message = "Cookie Shopee đã hoạt động trở lại (đồng bộ đơn thành công)."
            else:
                status = "degraded" if result == "partial" else ("blocked" if blocked else "degraded")
                failures = row["failure_count"] + (0 if result == "partial" else 1)
                due = row["last_alert_at"] is None or (now - row["last_alert_at"]).total_seconds() >= self.s.alert_repeat_hours * 3600
                should = result != "partial" and (blocked or failures >= self.s.alert_after_failures) and due
                if should:
                    message = ("Cookie Shopee bị chặn/hết hạn (HTTP 401/403/429 hoặc IP bị chặn): sync đơn dừng, ví KHÔNG chuyển tiền pending→rút được. "
                               "Dán cookie mới: PUT /api/v1/admin/shopee-session." if blocked else
                               f"Đồng bộ đơn Shopee lỗi {failures} lần liên tiếp. Xem log worker; ví không chuyển tiền cho tới khi sync lại ok.")
                conn.execute(text("UPDATE shopee_sessions SET status = :s, failure_count = :f, last_alert_at = CASE WHEN :a THEN :n ELSE last_alert_at END "
                                  "WHERE id = :i"), {"s": status, "f": failures, "a": should, "n": now, "i": ROW_ID})
        if message and notifier is not None:
            notifier.send(message)                         # ngoài transaction; lỗi gửi đã được notifier nuốt
