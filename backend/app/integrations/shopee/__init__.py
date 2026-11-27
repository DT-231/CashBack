from app.core.config import Settings
from app.integrations.shopee.client import ShopeeClient
from app.integrations.shopee.fake import FakeShopeeClient


def build_client(settings: Settings):
    """MOCK=1 -> client giả (không bao giờ gọi mạng)."""
    return FakeShopeeClient() if settings.mock else ShopeeClient(settings)
