"""Rút tiền: yêu cầu → duyệt → chi trả thủ công (chuyển khoản ngoài hệ thống, admin ghi mã giao dịch).

Quy tắc:
- Mọi hàm ĐỔI dữ liệu là `@audited` (bắt buộc `audit=AuditContext`, không mặc định) và ghi audit_logs trong CÙNG transaction.
- Khóa tiền (rút được -> đang khóa) cùng transaction với việc tạo yêu cầu, sau khi khóa dòng ví. Từ chối/lỗi hoàn lại bằng
  bút toán mới (`refund_hold`), không sửa bút toán cũ. Chi trả ghi `payout`. Đổi trạng thái có điều kiện (không đánh dấu hai lần).
- Duyệt/chi trả/xem số tài khoản: CHỈ admin (kiểm lại ở đây, không chỉ ở API). Staff không xem số tài khoản, không duyệt tiền.
- Số tài khoản mã hóa AES-GCM (core.crypto); chỉ giải mã ở `view_account`, mỗi lần ghi audit `payout.view_account` TRƯỚC khi trả.
- Số tài khoản không bao giờ vào log, audit, hay lỗi.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.crypto import BankCipher
from app.core.errors import Forbidden
from app.modules.audit import service as audit_service
from app.modules.audit.service import AuditContext, audited
from app.modules.payout import export, repository
from app.modules.payout.errors import (BankAccountCoolingDown, BelowMinimum, DuplicateProviderRef, IdempotencyConflict,
                                       InvalidBankAccount, InvalidTransition, OpenRequestExists, TooManyBankAccounts,
                                       WithdrawalNotFound, WithdrawalsDisabled)
from app.modules.payout.schemas import (AdminWithdrawalOut, BankAccountIn, BankAccountOut, PayoutAccountOut, WithdrawalOut, WithdrawalRules)
from app.modules.platform_settings.service import PlatformSettings
from app.modules.wallet.money import WalletMoney

MAX_ACCOUNTS = 5


class PayoutService:
    READ_ONLY = frozenset({"list_bank_accounts", "list_my_withdrawals", "admin_list", "rules", "cipher"})

    def __init__(self, settings: Settings, engine: Engine, platform: PlatformSettings | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.s, self.engine, self.clock = settings, engine, clock
        self.platform = platform or PlatformSettings(engine, clock)
        self._cipher: BankCipher | None = None

    # ---------- nội bộ ----------
    def _require_enabled(self) -> None:
        if not self.s.withdrawals_enabled:
            raise WithdrawalsDisabled("Tính năng rút tiền chưa được bật")

    def cipher(self) -> BankCipher:
        if self._cipher is None:
            self._cipher = BankCipher(self.s)         # ConfigError nếu thiếu/yếu khóa
        return self._cipher

    @staticmethod
    def _require_admin(audit: AuditContext) -> None:
        if audit.actor.role != "admin":
            raise Forbidden("Chỉ admin được thực hiện thao tác này")

    def _audit(self, conn, audit: AuditContext, action: str, wid: int, detail: dict | None = None) -> None:
        audit_service.record(conn, audit.settings, audit.actor, action, target_type="withdrawal", target_id=wid,
                             detail=detail, ip=audit.ip)

    # ---------- tài khoản ngân hàng ----------
    @audited
    def add_bank_account(self, user_id: int, body: BankAccountIn, *, audit: AuditContext) -> BankAccountOut:
        self._require_enabled()
        enc_key_id, enc = self.cipher().encrypt(body.account_no, user_id)
        usable_from = self.clock() + timedelta(hours=self.platform.get_int("bank_change_cooldown_hours"))
        with self.engine.begin() as conn:
            WalletMoney.lock(conn, user_id)                        # xếp hàng theo user: đếm số tài khoản không bị đua
            if repository.count_active_accounts(conn, user_id) >= MAX_ACCOUNTS:
                raise TooManyBankAccounts(f"Tối đa {MAX_ACCOUNTS} tài khoản ngân hàng")
            row = repository.insert_account(conn, user_id, body.bank_code, enc, enc_key_id, body.account_no[-4:],
                                            body.account_name, usable_from)
            audit_service.record(conn, audit.settings, audit.actor, "bank_account.add", target_type="bank_account",
                                 target_id=row["id"], detail={"bank_code": body.bank_code}, ip=audit.ip)
        return self._account_out(row)

    def _account_out(self, row) -> BankAccountOut:
        return BankAccountOut(**row, usable_now=row["usable_from"] <= self.clock())

    def list_bank_accounts(self, user_id: int) -> list[BankAccountOut]:
        with self.engine.connect() as conn:
            return [self._account_out(r) for r in repository.list_accounts(conn, user_id)]

    def rules(self) -> WithdrawalRules:
        return WithdrawalRules(withdrawals_enabled=self.s.withdrawals_enabled, min_withdraw_vnd=self.platform.get_int("min_withdraw_vnd"),
                               bank_change_cooldown_hours=self.platform.get_int("bank_change_cooldown_hours"), max_bank_accounts=MAX_ACCOUNTS)

    # ---------- yêu cầu rút ----------
    @audited
    def request_withdrawal(self, user_id: int, amount_vnd: int, bank_account_id: int, idem_key: str, *,
                           audit: AuditContext) -> WithdrawalOut:
        self._require_enabled()
        if isinstance(amount_vnd, bool) or not isinstance(amount_vnd, int) or amount_vnd <= 0:
            raise BelowMinimum("Số tiền phải là số nguyên dương")
        with self.engine.begin() as conn:
            WalletMoney.lock(conn, user_id)                        # khóa dòng ví TRƯỚC: bấm hai lần được xếp hàng, không đua
            prior = repository.get_by_idem(conn, user_id, idem_key)
            if prior is not None:                                  # bấm lại cùng Idempotency-Key: trả lại yêu cầu cũ
                if prior["amount_vnd"] != amount_vnd or prior["bank_account_id"] != bank_account_id:
                    raise IdempotencyConflict("Idempotency-Key này đã dùng cho yêu cầu khác")
                return WithdrawalOut(**prior)
            if repository.has_open(conn, user_id):
                raise OpenRequestExists("Bạn đang có một yêu cầu rút chưa xử lý xong")
            account = repository.get_account(conn, user_id, bank_account_id)
            if account is None:
                raise InvalidBankAccount("Tài khoản ngân hàng không hợp lệ")
            if account["usable_from"] > self.clock():
                raise BankAccountCoolingDown("Tài khoản mới chưa dùng được để rút; vui lòng chờ hết thời gian an toàn")
            minimum = self.platform.get_int("min_withdraw_vnd")
            if amount_vnd < minimum:
                raise BelowMinimum(f"Số tiền rút tối thiểu là {minimum} đồng")
            # (số dư rút được đủ hay không do WalletMoney.hold kiểm tra dưới khóa ví)
            wid = repository.insert_withdrawal(conn, user_id, amount_vnd, bank_account_id, idem_key)
            WalletMoney.hold(conn, user_id, wid, amount_vnd, audit=audit)
            self._audit(conn, audit, "withdrawal.request", wid, {"amount_vnd": amount_vnd, "bank_account_id": bank_account_id})
            out = repository.get_withdrawal(conn, wid)
        return WithdrawalOut(**out)

    def list_my_withdrawals(self, user_id: int, limit: int = 50, offset: int = 0) -> list[WithdrawalOut]:
        with self.engine.connect() as conn:
            return [WithdrawalOut(**r) for r in repository.list_for_user(conn, user_id, limit, offset)]

    # ---------- admin ----------
    def admin_list(self, status: str | None = None, limit: int = 50, offset: int = 0) -> list[AdminWithdrawalOut]:
        with self.engine.connect() as conn:
            return [self._admin_out(r) for r in repository.list_all(conn, status, limit, offset)]

    @staticmethod
    def _admin_out(row) -> AdminWithdrawalOut:
        return AdminWithdrawalOut(**row, transfer_note=export.transfer_note(row["id"]))

    def _transition_or_error(self, conn, wid: int, to: str, from_states: tuple[str, ...], **cols):
        row = repository.transition(conn, wid, to, from_states, **cols)
        if row is None:
            if repository.get_withdrawal(conn, wid) is None:
                raise WithdrawalNotFound("Không có yêu cầu rút này")
            raise InvalidTransition("Trạng thái yêu cầu rút không cho phép thao tác này")
        return row

    @audited
    def approve(self, wid: int, *, audit: AuditContext) -> AdminWithdrawalOut:
        self._require_enabled(); self._require_admin(audit)
        with self.engine.begin() as conn:
            self._transition_or_error(conn, wid, "approved", ("requested",), approved_by=audit.actor.id, approved_at=self.clock())
            self._audit(conn, audit, "withdrawal.approve", wid)
            return self._admin_out(repository.get_withdrawal(conn, wid))

    def _refund(self, wid: int, to: str, from_states: tuple[str, ...], action: str, reason: str, audit: AuditContext):
        self._require_enabled(); self._require_admin(audit)
        with self.engine.begin() as conn:
            row = self._transition_or_error(conn, wid, to, from_states, decided_reason=reason)
            WalletMoney.refund_hold(conn, row["user_id"], wid, row["amount_vnd"], audit=audit)   # bút toán mới, không sửa cũ
            self._audit(conn, audit, action, wid, {"reason": reason})
            return self._admin_out(repository.get_withdrawal(conn, wid))

    @audited
    def reject(self, wid: int, reason: str, *, audit: AuditContext) -> AdminWithdrawalOut:
        return self._refund(wid, "rejected", ("requested", "approved"), "withdrawal.reject", reason, audit)

    @audited
    def fail(self, wid: int, reason: str, *, audit: AuditContext) -> AdminWithdrawalOut:
        """Đã duyệt nhưng chuyển khoản thất bại: hoàn tiền lại cho user."""
        return self._refund(wid, "failed", ("approved",), "withdrawal.fail", reason, audit)

    @audited
    def mark_paid(self, wid: int, provider_ref: str, *, audit: AuditContext) -> AdminWithdrawalOut:
        self._require_enabled(); self._require_admin(audit)
        try:
            with self.engine.begin() as conn:
                row = self._transition_or_error(conn, wid, "paid", ("approved",), provider_ref=provider_ref,
                                                paid_by=audit.actor.id, paid_at=self.clock())
                WalletMoney.confirm_payout(conn, row["user_id"], wid, row["amount_vnd"], audit=audit)
                self._audit(conn, audit, "withdrawal.mark_paid", wid, {"provider_ref": provider_ref})
                return self._admin_out(repository.get_withdrawal(conn, wid))
        except IntegrityError as e:
            if "provider_ref" in str(e.orig):
                raise DuplicateProviderRef("Mã giao dịch này đã được dùng cho một yêu cầu khác") from None
            raise

    @audited
    def view_account(self, wid: int, *, audit: AuditContext) -> PayoutAccountOut:
        """Giải mã số tài khoản để admin chuyển khoản. Ghi audit `payout.view_account` TRONG cùng transaction, TRƯỚC khi giải mã."""
        self._require_enabled(); self._require_admin(audit)
        cipher = self.cipher()
        with self.engine.begin() as conn:
            w = repository.get_withdrawal(conn, wid)
            if w is None:
                raise WithdrawalNotFound("Không có yêu cầu rút này")
            if w["status"] != "approved":
                raise InvalidTransition("Chỉ xem được tài khoản của yêu cầu đã duyệt, chưa chi trả")
            self._audit(conn, audit, "payout.view_account", wid, {"bank_account_id": w["bank_account_id"]})
            acct = repository.account_cipher(conn, w["bank_account_id"])
            number = cipher.decrypt(acct["key_id"], acct["account_no_enc"], acct["user_id"])
            return PayoutAccountOut(withdrawal_id=wid, amount_vnd=w["amount_vnd"], bank_code=acct["bank_code"],
                                    account_no=number, account_name=acct["account_name"])

    EXPORT_MAX = 200

    @audited
    def export_csv(self, *, audit: AuditContext) -> tuple[str, int]:
        """CSV các yêu cầu đã duyệt (chờ chuyển khoản) để chuyển hàng loạt. Giải mã số tài khoản của TỪNG dòng: ghi audit
        `payout.view_account` cho mỗi yêu cầu và một dòng `payout.export`, tất cả cùng transaction và TRƯỚC khi trả dữ liệu.
        Ô CSV đã vô hiệu hóa công thức (export.csv_safe). Tối đa EXPORT_MAX dòng mỗi lần."""
        self._require_enabled(); self._require_admin(audit)
        cipher = self.cipher()
        with self.engine.begin() as conn:
            rows = repository.list_all(conn, "approved", self.EXPORT_MAX, 0)
            out = []
            for w in reversed(rows):                       # cũ trước
                self._audit(conn, audit, "payout.view_account", w["id"], {"bank_account_id": w["bank_account_id"], "via": "export"})
                acct = repository.account_cipher(conn, w["bank_account_id"])
                out.append({"id": w["id"], "amount_vnd": w["amount_vnd"], "bank_code": acct["bank_code"],
                            "account_no": cipher.decrypt(acct["key_id"], acct["account_no_enc"], acct["user_id"]),
                            "account_name": acct["account_name"]})
            audit_service.record(conn, audit.settings, audit.actor, "payout.export", target_type="withdrawal_export", target_id="approved",
                                 detail={"count": len(out)}, ip=audit.ip)
        return export.build_csv(out), len(out)
