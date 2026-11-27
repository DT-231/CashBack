class ShopeeError(RuntimeError):
    """Mọi lỗi từ phía Shopee/mạng; message đã đủ để hiển thị cho người vận hành (không chứa cookie)."""


class ShopeeConfigError(ShopeeError):
    """Thiếu cookie/cấu hình để gọi."""


class ShopeeBlockedError(ShopeeError):
    """401/403/429: cookie hết hạn hoặc IP bị chặn."""
