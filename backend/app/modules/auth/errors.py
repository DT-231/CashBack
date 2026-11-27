from app.core.errors import AppError, Conflict, Unauthorized


class EmailTaken(Conflict):
    code = "email_taken"


class InvalidCredentials(Unauthorized):
    code = "invalid_credentials"


class InvalidRefresh(Unauthorized):
    code = "invalid_refresh"


class AccountLocked(AppError):
    status, code = 403, "account_locked"


class EmailUnverified(AppError):
    status, code = 403, "email_unverified"
