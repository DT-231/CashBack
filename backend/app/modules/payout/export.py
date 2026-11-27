"""Xuất CSV chuyển khoản cho admin. Chống công thức độc (CSV/formula injection): ô bắt đầu bằng = + - @ hoặc tab/CR/LF bị vô hiệu hóa
bằng dấu nháy đơn đứng trước, nên Excel/Sheets hiểu là chữ, không chạy công thức."""
from __future__ import annotations

import csv
import io

DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
BOM = "﻿"          # để Excel mở đúng UTF-8 (tên có dấu)
HEADER = ("request_id", "amount_vnd", "bank_code", "account_no", "account_name", "transfer_note")


def csv_safe(value) -> str:
    """Luôn trả chuỗi an toàn để ghi vào ô CSV."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(DANGEROUS_PREFIXES) else text


def transfer_note(withdrawal_id: int) -> str:
    """Nội dung chuyển khoản chứa mã yêu cầu để đối soát sao kê ngân hàng với `withdrawals.id`."""
    return f"CASHBACK W{withdrawal_id}"


def build_csv(rows: list[dict]) -> str:
    """rows: dict có id, amount_vnd, bank_code, account_no, account_name. Mọi ô đi qua csv_safe."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    w.writerow(HEADER)
    for r in rows:
        w.writerow([csv_safe(r["id"]), csv_safe(r["amount_vnd"]), csv_safe(r["bank_code"]), csv_safe(r["account_no"]),
                    csv_safe(r["account_name"]), csv_safe(transfer_note(r["id"]))])
    return BOM + buf.getvalue()
