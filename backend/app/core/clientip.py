"""IP người dùng thật, và băm IP có khóa. Nơi DUY NHẤT quyết định có tin header của proxy hay không.

Chỉ tin `CF-Connecting-IP` khi `TRUST_PROXY_HEADERS=1` (origin chỉ truy cập được qua Cloudflare/Tunnel); nếu origin
mở trực tiếp ra Internet thì header này giả mạo được. Header sai định dạng bị bỏ qua và rơi về IP của kết nối.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress

from fastapi import Request

from app.core.config import Settings


def client_ip(request: Request, trust_proxy_headers: bool) -> str | None:
    """IP đã chuẩn hóa (IPv6 viết gọn) hoặc None nếu không xác định được."""
    if trust_proxy_headers:
        try:
            return str(ipaddress.ip_address((request.headers.get("cf-connecting-ip") or "").strip()))
        except ValueError:
            pass
    return request.client.host if request.client else None


def keyed_hash(settings: Settings, value: str | None) -> str | None:
    """HMAC-SHA256(IP_SALT, value), 16 ký tự hex đầu. Không có IP_SALT hoặc value rỗng thì None (không lưu gì)."""
    key = settings.ip_salt.get_secret_value()
    if not key or not value:
        return None
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]


def limiter_key(settings: Settings, value: str | None) -> str:
    """Khóa không chứa IP/email thô cho bộ giới hạn tốc độ. Có IP_SALT thì HMAC; không có thì SHA-256 không khóa
    (chấp nhận được vì dòng `rate_limits` chỉ sống bằng độ dài cửa sổ). Luôn trả chuỗi, kể cả khi không biết IP."""
    return keyed_hash(settings, value) or "u" + hashlib.sha256((value or "unknown").encode()).hexdigest()[:15]
