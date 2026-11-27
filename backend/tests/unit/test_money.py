from decimal import Decimal

import pytest

from app.core import money


def test_micro_conversions_floor_and_round():
    assert money.micro_to_vnd(403_750_000) == 4037          # 4.037,5đ -> 4.037 (xuống)
    assert money.micro_to_vnd_round(403_750_000) == 4038    # hiển thị: nửa lên
    assert money.vnd_to_micro(95_000) == 9_500_000_000


def test_share_floor_never_favours_user_on_remainder():
    assert money.share_floor(1001, 6000) == 600             # 600,6 -> 600
    assert money.share_floor(0, 6000) == 0
    assert money.share_floor(10_000, 10_000) == 10_000
    with pytest.raises(ValueError):
        money.share_floor(1, 10_001)
    with pytest.raises(ValueError):
        money.share_floor(-1, 100)


def test_format_vnd():
    assert money.format_vnd(1250000) == "1.250.000"


@pytest.mark.parametrize("raw,expected", [
    ("690.000", 690000), ("259,000", 259000), ("8%", 8), ("0,08", Decimal("0.08")),
    ("1.250.000", 1250000), ("1,250,000", 1250000), ("259,5", Decimal("259.5")),
    ("", 0), (None, 0), ("abc", 0), ("nan", 0), ("inf", 0),
])
def test_parse_vn_number(raw, expected):
    assert money.parse_vn_number(raw) == expected


def test_micro_share_floor_is_a_single_rounding():
    from app.core.money import micro_share_floor
    assert micro_share_floor(4_037_500_000, 6000) == 24_225           # 40.375đ x 60%
    assert micro_share_floor(403_750_000, 6000) == 2_422              # 4.037,5đ x 60% = 2.422,5 -> xuống
    assert micro_share_floor(99_999, 10_000) == 0 and micro_share_floor(0, 6000) == 0
    # Ca phân biệt MỘT lần làm tròn với hai lần: 1,9đ x 60% = 1,14đ -> 1đ (làm tròn hai lần sẽ ra 0đ và user thiệt)
    assert micro_share_floor(190_000, 6000) == 1 and micro_share_floor(199_999, 10_000) == 1
    assert (190_000 // 100_000) * 6000 // 10_000 == 0     # chứng minh ca này thật sự phân biệt được
    assert micro_share_floor(10**15, 10_000) == 10**10                # không tràn, không float
    import pytest
    for bad in ((-1, 6000), (1, -1), (1, 10_001)):
        with pytest.raises(ValueError):
            micro_share_floor(*bad)
