"""Biến động tiền do RÚT TIỀN. Chạy trong transaction của caller (module payout) để yêu cầu rút và bút toán ví cùng commit/rollback.
Chỉ module `wallet` ghi sổ cái (test_architecture): payout phải đi qua đây.

Mọi hàm đổi tiền là `@audited`: bắt buộc `audit=AuditContext` (không có mặc định) và tự ghi audit_logs trong cùng transaction.
Bút toán có khóa idempotent theo yêu cầu rút (`hold:w<id>`...): gọi lại không đổi số dư lần hai.
"""
from __future__ import annotations

from sqlalchemy import Connection

from app.modules.audit import service as audit_service
from app.modules.audit.service import AuditContext, audited
from app.modules.wallet import ledger, repository
from app.modules.wallet.errors import InsufficientFunds


class WalletMoney:
    # Hàm chỉ-đọc/khóa (không đổi tiền): được miễn @audited. Test contract đối chiếu danh sách này.
    READ_ONLY = frozenset({"lock"})

    @staticmethod
    def lock(conn: Connection, user_id: int) -> dict:
        """Khóa dòng ví tới hết transaction và trả số dư hiện tại. Gọi ĐẦU TIÊN để mọi thao tác của user được xếp hàng."""
        repository.ensure_wallet(conn, user_id)
        return dict(repository.lock_wallet(conn, user_id))

    @staticmethod
    def _audit(conn: Connection, audit: AuditContext, action: str, user_id: int, withdrawal_id: int, amount: int) -> None:
        audit_service.record(conn, audit.settings, audit.actor, action, target_type="withdrawal", target_id=withdrawal_id,
                             detail={"user_id": user_id, "amount_vnd": amount}, ip=audit.ip)

    @staticmethod
    @audited
    def hold(conn: Connection, user_id: int, withdrawal_id: int, amount: int, *, audit: AuditContext) -> bool:
        """rút được -> đang khóa. Không đủ số dư rút được thì InsufficientFunds (không bao giờ âm)."""
        w = WalletMoney.lock(conn, user_id)
        if w["available_vnd"] < amount:
            raise InsufficientFunds("Số dư rút được không đủ")
        fresh = ledger.post(conn, user_id, "hold", "held", amount, f"hold:w{withdrawal_id}", withdrawal_id=withdrawal_id, locked=True)
        if fresh:
            WalletMoney._audit(conn, audit, "wallet.hold", user_id, withdrawal_id, amount)
        return fresh

    @staticmethod
    @audited
    def refund_hold(conn: Connection, user_id: int, withdrawal_id: int, amount: int, *, audit: AuditContext) -> bool:
        """Từ chối/lỗi chi trả: đang khóa -> rút được, bằng bút toán mới (không sửa bút toán cũ)."""
        w = WalletMoney.lock(conn, user_id)
        if w["held_vnd"] < amount:
            raise InsufficientFunds("Số dư đang khóa không khớp yêu cầu rút")
        fresh = ledger.post(conn, user_id, "refund_hold", "available", amount, f"refund_hold:w{withdrawal_id}",
                            withdrawal_id=withdrawal_id, locked=True)
        if fresh:
            WalletMoney._audit(conn, audit, "wallet.refund_hold", user_id, withdrawal_id, amount)
        return fresh

    @staticmethod
    @audited
    def confirm_payout(conn: Connection, user_id: int, withdrawal_id: int, amount: int, *, audit: AuditContext) -> bool:
        """Đã chuyển tiền: đang khóa -> đã chi trả."""
        w = WalletMoney.lock(conn, user_id)
        if w["held_vnd"] < amount:
            raise InsufficientFunds("Số dư đang khóa không khớp yêu cầu rút")
        fresh = ledger.post(conn, user_id, "payout", "paid_out", amount, f"payout:w{withdrawal_id}",
                            withdrawal_id=withdrawal_id, locked=True)
        if fresh:
            WalletMoney._audit(conn, audit, "wallet.payout", user_id, withdrawal_id, amount)
        return fresh
