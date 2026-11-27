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
