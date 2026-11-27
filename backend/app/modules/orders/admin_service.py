"""Gán tay đơn mồ côi cho user (T-044). CHỈ admin (kết quả là tiền cho user): kiểm lại ở đây, không chỉ ở API.

Đơn được gán thành đơn của user; lần chốt ví kế tiếp (wallet.settle) tự tạo bút toán. Sync không ghi đè việc gán tay
(`repository.update_order` không đụng user_id). Gán đúng MỘT lần (khóa dòng đơn, kiểm lại trạng thái mồ côi). Cấm admin tự gán
cho chính mình. Ghi audit `orders.assign_orphan` cùng transaction (lý do do admin nhập; số dài bị che trong detail)."""
from __future__ import annotations

from sqlalchemy import Engine

from app.core.config import Settings
from app.core.errors import Forbidden
from app.modules.audit import service as audit_service
from app.modules.audit.service import AuditContext, audited
from app.modules.auth.service import AuthService
from app.modules.orders import repository
from app.modules.orders.errors import InvalidAssignee, NotAnOrphan, OrderNotFound


class OrphanAdmin:
    READ_ONLY = frozenset({"list"})

    def __init__(self, settings: Settings, engine: Engine):
        self.s, self.engine = settings, engine

    def list(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self.engine.connect() as conn:
            return [dict(r) for r in repository.list_orphans(conn, limit, offset)]

    @audited
    def assign(self, order_id: int, user_id: int, reason: str, *, audit: AuditContext) -> None:
        if audit.actor.role != "admin":
            raise Forbidden("Chỉ admin được gán đơn mồ côi")
        if user_id == audit.actor.id:
            raise InvalidAssignee("Không được tự gán đơn cho chính mình")
        if AuthService(self.s, self.engine).find_user(user_id) is None:
            raise InvalidAssignee("User không tồn tại hoặc không hoạt động")
        with self.engine.begin() as conn:
            row = repository.lock_order(conn, order_id)
            if row is None:
                raise OrderNotFound("Không có đơn này")
            if row["user_id"] is not None or row["post_id"] is not None or not repository.has_open_orphan(conn, order_id):
                raise NotAnOrphan("Đơn này không còn là đơn mồ côi")
            if not repository.assign_orphan(conn, order_id, user_id, audit.actor.id):     # lớp thứ hai (ngoài khóa dòng): UPDATE có điều kiện
                raise NotAnOrphan("Đơn này không còn là đơn mồ côi")
            audit_service.record(conn, audit.settings, audit.actor, "orders.assign_orphan", target_type="order", target_id=order_id,
                                 detail={"user_id": user_id, "reason": reason}, ip=audit.ip)
