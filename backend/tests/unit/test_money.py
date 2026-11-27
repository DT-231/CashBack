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
