"""Lỗi riêng của module. Kế thừa AppError để API tự trả đúng định dạng {error:{code,message,request_id}}."""
from app.core.errors import Conflict, NotFound


class ThingNotFound(NotFound):
    code = "thing_not_found"


class ThingExists(Conflict):
    code = "thing_exists"
