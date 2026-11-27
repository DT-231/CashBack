from datetime import datetime

from pydantic import BaseModel


class WalletOut(BaseModel):
    pending_vnd: int
    available_vnd: int
    held_vnd: int
    share_pct: float            # tỷ lệ hiện hành, chỉ để hiển thị; mỗi đơn dùng tỷ lệ tại lúc phát sinh


class EntryOut(BaseModel):
    id: int
    kind: str
    state: str
    amount_vnd: int
    order_id: int | None
    withdrawal_id: int | None
    created_at: datetime


class OrderOut(BaseModel):
    """Đơn của tôi. Mọi giá trị tiền và mốc thời gian do backend tính; UI chỉ hiển thị."""
    id: int
    order_ref: str                         # chỉ 4 ký tự cuối của mã đơn, không lộ mã đầy đủ
    status: str                            # PENDING | COMPLETED | CANCELLED | RETURNED
    product_name: str | None = None        # chưa có nguồn tên sản phẩm cho đơn: luôn null
    purchased_at: datetime | None
    refund_vnd: int                        # phần hoàn của user theo sổ cái: đang chờ, hoặc đã vào ví; 0 nếu đã hủy/thu hồi/chưa có
    refund_state: str                      # none | pending | available | cancelled | reversed
    expected_release_at: datetime | None   # chỉ khi đơn COMPLETED và tiền còn chờ: hoàn tất + số ngày giữ có hiệu lực lúc hoàn tất
