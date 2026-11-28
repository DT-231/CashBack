"""CSV chuyển khoản: vô hiệu hóa công thức độc, nội dung chuyển khoản chứa mã yêu cầu."""
import csv
import io

import pytest

from app.modules.payout.export import BOM, HEADER, build_csv, csv_safe, transfer_note


@pytest.mark.parametrize("evil", ["=1+1", "+SUM(A1)", "-2+3", "@cmd", "\t=1", "\r=1", "\n=1", "=HYPERLINK(\"http://x\",\"y\")",
                                  "=cmd|' /C calc'!A0", "+1", "-1", "@A1"])
def test_dangerous_prefixes_are_neutralised(evil):
    out = csv_safe(evil)
    assert out == "'" + evil and out[0] == "'"


@pytest.mark.parametrize("ok", ["VCB", "NGUYEN VAN A", "123456789", "a=b", "x+y", "1-2", "CASHBACK W12", "", "Ñ"])
def test_normal_values_are_unchanged(ok):
    assert csv_safe(ok) == ok


def test_none_and_numbers():
    assert csv_safe(None) == "" and csv_safe(200000) == "200000" and csv_safe(0) == "0"
    assert csv_safe(-5) == "'-5"                                         # số âm không bao giờ hợp lệ ở đây: nếu xuất hiện thì bị vô hiệu hóa


def test_build_csv_neutralises_every_cell_and_keeps_the_transfer_note():
    rows = [{"id": 7, "amount_vnd": 200000, "bank_code": "=VCB", "account_no": "+0123456789", "account_name": "@A B"},
            {"id": 8, "amount_vnd": 150000, "bank_code": "ACB", "account_no": "987654321", "account_name": "NGUYEN VAN A"}]
    text = build_csv(rows)
    assert text.startswith(BOM)
    parsed = list(csv.reader(io.StringIO(text[len(BOM):])))
    assert tuple(parsed[0]) == HEADER
    assert parsed[1] == ["7", "200000", "'=VCB", "'+0123456789", "'@A B", "CASHBACK W7"]
    assert parsed[2] == ["8", "150000", "ACB", "987654321", "NGUYEN VAN A", "CASHBACK W8"]
    for line in parsed[1:]:
        assert not any(cell[:1] in ("=", "+", "-", "@", "\t", "\r", "\n") for cell in line)
    assert transfer_note(123) == "CASHBACK W123" and "W123" in parsed[0][0] + transfer_note(123)


def test_quotes_commas_and_newlines_inside_cells_stay_inside_one_cell():
    text = build_csv([{"id": 1, "amount_vnd": 1, "bank_code": "A", "account_no": "1", "account_name": 'X, "Y"\nZ'}])
    row = list(csv.reader(io.StringIO(text[len(BOM):])))[1]
    assert row[4] == 'X, "Y"\nZ' and len(row) == 6
