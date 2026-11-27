from app.core.errors import AppError


class InvalidAudit(AppError):
    status = 500
    code = "invalid_audit"
