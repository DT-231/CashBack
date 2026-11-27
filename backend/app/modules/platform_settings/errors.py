from app.core.errors import AppError


class InvalidSetting(AppError):
    status, code = 422, "invalid_setting"
