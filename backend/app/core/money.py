"""Tiền: số nguyên. VND, hoặc micro-VND (= VND × 1e5, đơn vị Shopee trả về). KHÔNG float.

Quy đổi ×1e5 chỉ được viết ở file này.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

MICRO = 100_000
BP = 10_000   # 100% = 10.000 basis point


def micro_to_vnd(micro: int) -> int:
    """Làm tròn xuống (phần lẻ không bao giờ có lợi cho user)."""
    return int(micro) // MICRO


def micro_to_vnd_round(micro: int) -> int:
    """Làm tròn nửa lên; dùng để HIỂN THỊ giá sản phẩm, không dùng cho sổ cái."""
    return (int(micro) + MICRO // 2) // MICRO


def vnd_to_micro(vnd: int) -> int:
    return int(vnd) * MICRO


def share_floor(amount: int, share_bp: int) -> int:
    """Phần của user = amount × share_bp / 10.000, làm tròn xuống."""
    if amount < 0 or not 0 <= share_bp <= BP:
        raise ValueError("amount >= 0 và share_bp trong [0, 10000]")
    return amount * share_bp // BP


def micro_share_floor(micro: int, share_bp: int) -> int:
    """Phần của user (VND) từ hoa hồng micro-VND: MỘT lần làm tròn xuống (không làm tròn hai lần).
    40.375đ = 4.037.500.000 micro, 60% -> 24.225đ."""
    if micro < 0 or not 0 <= share_bp <= BP:
        raise ValueError("micro >= 0 và share_bp trong [0, 10000]")
    return micro * share_bp // (BP * MICRO)


def format_vnd(vnd: int) -> str:
    return f"{int(vnd):,}".replace(",", ".")


def parse_vn_number(v, default: Decimal = Decimal(0)) -> Decimal:
    """Đọc số kiểu VN lẫn US: '690.000' -> 690000, '259,000' -> 259000, '8%' -> 8, '0,08' -> 0.08."""
    s = str(v or "").replace("%", "").replace(" ", "").replace(" ", "").strip()
    if not s:
        return default
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
        s = s.replace(",", "")
    elif s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return default
    return d if d.is_finite() else default
