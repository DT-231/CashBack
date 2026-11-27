from app.core.errors import AppError


class WithdrawalsDisabled(AppError):
    status, code = 503, "withdrawals_disabled"


class InvalidBankAccount(AppError):
    status, code = 422, "invalid_bank_account"


class BankAccountCoolingDown(AppError):
    status, code = 409, "bank_account_cooling_down"


class BelowMinimum(AppError):
    status, code = 422, "below_minimum"


class OpenRequestExists(AppError):
    status, code = 409, "withdrawal_open_exists"


class IdempotencyConflict(AppError):
    status, code = 409, "idempotency_conflict"


class InvalidTransition(AppError):
    status, code = 409, "invalid_transition"


class WithdrawalNotFound(AppError):
    status, code = 404, "withdrawal_not_found"


class DuplicateProviderRef(AppError):
    status, code = 409, "duplicate_provider_ref"


class TooManyBankAccounts(AppError):
    status, code = 409, "too_many_bank_accounts"
