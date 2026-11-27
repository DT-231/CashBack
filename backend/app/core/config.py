"""Cấu hình: đọc biến môi trường MỘT lần, có kiểu. Đây là nơi DUY NHẤT được đọc env.

Dùng: `settings = load_settings()` ở entrypoint rồi truyền xuống (hoặc `app.state.settings`).
Không đọc env lúc import. Biến thật thắng file `.env` (giống hành vi cũ của server.py).
"""
from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class ConfigError(RuntimeError):
    """Thiếu hoặc sai cấu hình; thông báo nói rõ biến nào."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    # --- chế độ ---
    mock: bool = False                      # MOCK=1: không gọi Shopee thật
    log_level: str = "INFO"

    # --- affiliate / link ---
    shopee_aff_id: str = ""
    aff_campaign: str = "-"
    link_template: str = ""
    sub_id_pad: bool = True
    subid_secret: SecretStr = SecretStr("")  # >= 16 byte, ký sub_id v1

    # --- Shopee (chỉ integrations/shopee được dùng) ---
    shopee_cookie: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("SHOPEE_COOKIE", "AFF_COOKIE"))
    shopee_af_ac_enc_dat: SecretStr = SecretStr("")
    shopee_proxy: str = ""
    shopee_ua: str = ""
    shopee_search_url: str = "https://shopee.vn/api/v4/search/search_items"
    shopee_cache_ttl: int = 300             # giây; 0 = tắt cache search/dashboard
    pw_state: str = ""
    headless: bool = True

    # --- tìm sản phẩm ---
    search_engine: str = "auto"             # auto | feed | api | browser
    feed_file: str = ""

    # --- server ---
    host: str = "127.0.0.1"
    port: int = 8080
    public_base: str = ""
    agent_api_key: SecretStr = SecretStr("")  # khóa khởi tạo cho Tool API; thêm khóa khác qua bảng agent_keys

    # --- DB ---
    database_url: str = ""

    @property
    def aff_id(self) -> str:
        return self.shopee_aff_id.strip()

    @property
    def is_loopback(self) -> bool:
        return self.host in LOOPBACK

    @property
    def auth_required(self) -> bool:
        """Tool API bắt buộc có khóa khi đã đặt AGENT_API_KEY hoặc khi lắng nghe ngoài localhost."""
        return bool(self.agent_api_key.get_secret_value()) or not self.is_loopback

    def require(self, *names: str) -> None:
        missing = []
        for n in names:
            v = getattr(self, n)
            v = v.get_secret_value() if isinstance(v, SecretStr) else v
            if not str(v).strip():
                missing.append(n.upper())
        if missing:
            raise ConfigError("Thiếu biến môi trường: " + ", ".join(missing))

    def validate_for_serving(self) -> None:
        if not self.is_loopback and not self.agent_api_key.get_secret_value():
            raise ConfigError(
                f"HOST={self.host} lắng nghe ngoài localhost nhưng chưa đặt AGENT_API_KEY; "
                "đặt khóa hoặc dùng HOST=127.0.0.1")


def load_settings(env_file: Path | str | None = REPO_ROOT / ".env", **overrides) -> Settings:
    """Đọc env (và .env nếu có). Test truyền env_file=None + overrides để cô lập."""
    f = Path(env_file) if env_file else None
    return Settings(_env_file=f if f and f.exists() else None, **overrides)
