from app.modules.wallet.ledger import DELTAS


def test_every_kind_has_exactly_one_state_and_balanced_money_flow():
    kinds = [k for k, _ in DELTAS]
    assert len(kinds) == len(set(kinds)) == 8
    # tiền chỉ đi theo đường: pending -> available -> held -> trả ra; mỗi bút toán không tạo tiền từ không khí
    assert DELTAS[("release", "available")] == (-1, 1, 0)
    assert DELTAS[("hold", "held")] == (0, -1, 1) and DELTAS[("refund_hold", "available")] == (0, 1, -1)
    for pair in (("accrual", "pending"), ("cancel", "cancelled"), ("reverse", "reversed"), ("payout", "paid_out")):
        assert sum(DELTAS[pair]) != 0                      # chỉ vào/ra hệ thống ở 4 loại này
    for pair in (("release", "available"), ("hold", "held"), ("refund_hold", "available"), ("adjust", "reversed")):
        assert sum(DELTAS[pair]) == 0                      # còn lại chỉ chuyển giữa các ngăn
