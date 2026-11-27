"""Máy trạng thái đơn. Shopee là nguồn sự thật, nhưng dữ liệu lạ/thiếu KHÔNG được làm lùi trạng thái đã biết:
một lần sync mà trường trạng thái bị đổi tên hay có giá trị mới sẽ map về PENDING, và nếu cho ghi đè thì đơn
COMPLETED bị hạ về PENDING (rồi ví tính nhầm hoàn/thu hồi tiền).

  PENDING   -> bất kỳ trạng thái nào
  COMPLETED -> RETURNED (trả hàng) hoặc CANCELLED (Shopee thu hồi sau khi hoàn tất); mọi thứ khác (kể cả PENDING do
               dữ liệu lạ) bị bỏ qua. CANCELLED/RETURNED chỉ do giá trị NHẬN DIỆN ĐƯỢC rõ ràng mới có: trạng thái lạ luôn
               map về PENDING nên không bao giờ làm một đơn bị coi là hủy. Hướng này bảo vệ nền tảng: không tiếp tục trả tiền
               cho khoản Shopee đã thu hồi.
  CANCELLED, RETURNED: cuối, không đổi nữa
"""
from __future__ import annotations


def next_status(current: str, incoming: str) -> tuple[str, bool]:
    """(trạng thái sẽ lưu, có chấp nhận `incoming` không). `incoming == current` luôn hợp lệ."""
    if incoming == current:
        return current, True
    if current == "PENDING":
        return incoming, True
    if current == "COMPLETED" and incoming in ("RETURNED", "CANCELLED"):
        return incoming, True
    return current, False
