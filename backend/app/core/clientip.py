"""IP người dùng thật, và băm IP có khóa. Nơi DUY NHẤT quyết định có tin header của proxy hay không.

Thứ tự tin cậy:
1. `X-Visitor-IP`, **chỉ khi** kèm `X-BFF-Secret` khớp `BFF_SHARED_SECRET` (so sánh hằng thời gian). Đây là đường của BFF Next.js:
   qua BFF backend chỉ thấy 127.0.0.1, nên BFF chuyển IP thật (từ CF-Connecting-IP) kèm bí mật chung (T-017). Secret sai/thiếu
   hoặc chưa cấu hình thì header này bị bỏ qua hoàn toàn (không bao giờ tin chỉ vì có mặt).
2. `CF-Connecting-IP` khi `TRUST_PROXY_HEADERS=1` (origin chỉ truy cập được qua Cloudflare/Tunnel); nếu origin mở trực tiếp ra
   Internet thì header này giả mạo được.
3. IP của kết nối. Header sai định dạng luôn bị bỏ qua và rơi xuống bước sau.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress

from fastapi import Request

from app.core.config import Settings


def _valid_ip(value: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return None


def _bff_authenticated(request: Request, bff_secret: str) -> bool:
    """Secret rỗng (chưa cấu hình) thì không bao giờ xác thực, kể cả khi header cũng rỗng."""
    if not bff_secret:
        return False
    given = (request.headers.get("x-bff-secret") or "").encode()
    return hmac.compare_digest(hashlib.sha256(given).digest(), hashlib.sha256(bff_secret.encode()).digest())


def client_ip(request: Request, trust_proxy_headers: bool, bff_secret: str = "") -> str | None:
    """IP đã chuẩn hóa (IPv6 viết gọn) hoặc None nếu không xác định được."""
    if _bff_authenticated(request, bff_secret):
        ip = _valid_ip(request.headers.get("x-visitor-ip"))
        if ip:
            return ip
    if trust_proxy_headers:
        try:
            return str(ipaddress.ip_address((request.headers.get("cf-connecting-ip") or "").strip()))
        except ValueError:
            pass
    return request.client.host if request.client else None


def request_ip(request: Request, settings: Settings) -> str | None:
    """Cách DUY NHẤT để module lấy IP khách: áp dụng cấu hình tin cậy của `settings`."""
    return client_ip(request, settings.trust_proxy_headers, settings.bff_shared_secret.get_secret_value())


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
