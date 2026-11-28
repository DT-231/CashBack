from app.core.errors import AppError


class OrderNotFound(AppError):
    status, code = 404, "order_not_found"


class NotAnOrphan(AppError):
    status, code = 409, "not_an_orphan"


class InvalidAssignee(AppError):
    status, code = 422, "invalid_assignee"
