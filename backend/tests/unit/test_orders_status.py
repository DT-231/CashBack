import pytest

from app.modules.orders.status import next_status

CASES = [
    ("PENDING", "COMPLETED", ("COMPLETED", True)), ("PENDING", "CANCELLED", ("CANCELLED", True)),
    ("PENDING", "RETURNED", ("RETURNED", True)), ("PENDING", "PENDING", ("PENDING", True)),
    ("COMPLETED", "COMPLETED", ("COMPLETED", True)), ("COMPLETED", "RETURNED", ("RETURNED", True)),
    ("COMPLETED", "PENDING", ("COMPLETED", False)),     # dữ liệu lạ/thiếu không được hạ đơn đã hoàn tất
    ("COMPLETED", "CANCELLED", ("COMPLETED", False)),
    ("CANCELLED", "COMPLETED", ("CANCELLED", False)), ("CANCELLED", "PENDING", ("CANCELLED", False)),
    ("CANCELLED", "CANCELLED", ("CANCELLED", True)),
    ("RETURNED", "COMPLETED", ("RETURNED", False)), ("RETURNED", "PENDING", ("RETURNED", False)),
    ("RETURNED", "RETURNED", ("RETURNED", True)),
]


@pytest.mark.parametrize("cur,inc,expected", CASES)
def test_transitions(cur, inc, expected):
    assert next_status(cur, inc) == expected
