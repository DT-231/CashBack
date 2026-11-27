from app.core.errors import AppError


class LedgerError(AppError):
    status, code = 500, "ledger_error"


class InsufficientFunds(AppError):
    status, code = 409, "insufficient_funds"
