from app.core.errors import AppError


class InvalidLink(AppError):
    """URL người dùng không phải link sản phẩm Shopee được hỗ trợ."""

    status, code = 400, "invalid_input"
