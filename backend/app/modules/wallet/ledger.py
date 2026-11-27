"""Sổ cái ví: nơi DUY NHẤT đổi số dư. Chỉ thêm bút toán; số dư luôn suy ra được từ bút toán.

Ý nghĩa (kind, state) -> (Δpending, Δavailable, Δheld) cho mỗi 1 đồng:
  accrual     pending    (+1, 0, 0)    đơn mới: phần của user vào "chờ xác nhận"
  release     available  (-1,+1, 0)    hết hạn trả hàng: sang "rút được"
  cancel      cancelled  (-1, 0, 0)    đơn hủy khi còn "chờ": bỏ khoản chờ (cũng dùng để điều chỉnh giảm khi hoa hồng đổi)
  reverse     reversed   ( 0,-1, 0)    đơn bị trả sau khi đã "rút được" nhưng chưa rút: thu hồi
  hold        held       ( 0,-1,+1)    khóa tiền khi user yêu cầu rút
  payout      paid_out   ( 0, 0,-1)    đã chuyển tiền
  refund_hold available  ( 0,+1,-1)    từ chối/lỗi chi trả: trả tiền lại "rút được"
  adjust      reversed   ( 0, 0, 0)    GHI NHẬN khoản lỗ của admin (user đã rút trước khi đơn bị trả): không đổi số dư ai
Số dư KHÔNG BAO GIỜ âm (CHECK ở DB). Thu hồi quá số đang có thì phần thiếu ghi bằng `adjust`, không trừ âm ví.
"""
from __future__ import annotations

from sqlalchemy import Connection

from app.modules.wallet import repository
from app.modules.wallet.errors import LedgerError

DELTAS: dict[tuple[str, str], tuple[int, int, int]] = {
    ("accrual", "pending"): (1, 0, 0),
    ("release", "available"): (-1, 1, 0),
    ("cancel", "cancelled"): (-1, 0, 0),
    ("reverse", "reversed"): (0, -1, 0),
    ("hold", "held"): (0, -1, 1),
    ("payout", "paid_out"): (0, 0, -1),
    ("refund_hold", "available"): (0, 1, -1),
    ("adjust", "reversed"): (0, 0, 0),
}


def post(conn: Connection, user_id: int, kind: str, state: str, amount: int, idem_key: str, *,
         order_id: int | None = None, withdrawal_id: int | None = None, share_bp: int | None = None,
         locked: bool = False) -> bool:
    """Ghi một bút toán và cập nhật số dư trong CÙNG transaction của caller. True nếu ghi mới, False nếu `idem_key`
    đã có (không đổi gì). Khóa dòng ví nên các bút toán của một user được xếp hàng. `locked=True`: caller đã gọi
    `repository.ensure_wallet` + `lock_wallet` trong transaction này (bỏ qua hai truy vấn thừa)."""
    delta = DELTAS.get((kind, state))
    if delta is None:
        raise LedgerError(f"cặp (kind, state) không hợp lệ: ({kind}, {state})")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise LedgerError("amount phải là số nguyên dương")
    if not locked:
        repository.ensure_wallet(conn, user_id)
        repository.lock_wallet(conn, user_id)
    if repository.insert_entry(conn, user_id, kind, state, amount, idem_key, order_id, withdrawal_id, share_bp) is None:
        return False
    dp, da, dh = delta
    repository.apply_delta(conn, user_id, dp * amount, da * amount, dh * amount)
    return True
