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


class MfaRequired(AppError):
    status, code = 403, "mfa_required"


class MfaInvalid(AppError):
    status, code = 401, "mfa_invalid"


class MfaState(AppError):
    status, code = 409, "mfa_state"
