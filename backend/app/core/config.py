"""Cấu hình: đọc biến môi trường MỘT lần, có kiểu. Đây là nơi DUY NHẤT được đọc env.

Dùng: `settings = load_settings()` ở entrypoint rồi truyền xuống (hoặc `app.state.settings`).
Không đọc env lúc import. Biến thật thắng file `.env` (giống hành vi cũ của server.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

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
    # Khóa cũ (cách nhau dấu phẩy) để GIẢI MÃ link đã phát hành trước khi đổi khóa (T-018). Không bao giờ dùng để ký. Tối đa 3.
    subid_secret_previous: SecretStr = SecretStr("")

    # --- Shopee (chỉ integrations/shopee được dùng) ---
    shopee_cookie: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("SHOPEE_COOKIE", "AFF_COOKIE"))
    shopee_af_ac_enc_dat: SecretStr = SecretStr("")
    # Cookie của shopee.vn (KHÁC host với shopee_cookie của affiliate.shopee.vn): chỉ dùng cho search.
    shopee_web_cookie: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("SHOPEE_WEB_COOKIE"))
    shopee_web_enc_dat: SecretStr = SecretStr("")
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
    cors_origins: str = ""                 # danh sách origin, ngăn bằng dấu phẩy; rỗng = tắt CORS
    agent_api_key: SecretStr = SecretStr("")  # khóa khởi tạo cho Tool API; thêm khóa khác qua bảng agent_keys

    # --- đồng bộ đơn ---
    sync_max_age_hours: int = Field(default=24, ge=1, le=720)   # lần sync ok gần nhất cũ hơn mức này thì KHÔNG chuyển tiền
    sync_days: int = Field(default=60, ge=1, le=366)   # quét lại cửa sổ này để bắt đơn đổi trạng thái

    # --- click (/go/{code}) ---
    ip_salt: SecretStr = SecretStr("")       # khóa HMAC băm IP/User-Agent; rỗng = KHÔNG lưu ip_hash/ua_hash
    # Bí mật chung với BFF Next.js (T-017): BFF gửi X-Visitor-IP kèm X-BFF-Secret; backend chỉ tin header IP khi secret khớp.
    # Rỗng = không tin X-Visitor-IP. Khi đặt phải >= 16 ký tự. Chỉ phía server, đặt cùng giá trị cho BFF (BFF_SHARED_SECRET).
    bff_shared_secret: SecretStr = SecretStr("")
    # Khai báo "web đi qua BFF Next.js" (BFF_ENABLED=1). Bật mà thiếu/ngắn BFF_SHARED_SECRET thì mọi khách dùng CHUNG một bộ đếm
    # rate limit (127.0.0.1): cảnh báo lúc khởi động và hiện trong /health.
    bff_enabled: bool = False
    trust_proxy_headers: bool = False        # True khi đứng sau Cloudflare/Tunnel: lấy IP thật từ CF-Connecting-IP

    # --- rút tiền (module payout) ---
    withdrawals_enabled: bool = False        # tắt mặc định; bật thì BẮT BUỘC có BANK_ENC_KEY đủ mạnh (khởi động từ chối nếu không)
    bank_enc_key: SecretStr = SecretStr("")  # AES-256-GCM, base64 của 32 byte ngẫu nhiên; sao lưu NGOÀI .env
    bank_enc_key_id: str = "k1"              # phiên bản khóa, lưu kèm mỗi giá trị mã hóa
    bank_enc_old_keys: SecretStr = SecretStr("")   # "k0:<khóa>,..." khóa cũ chỉ để giải mã sau khi đổi khóa
    rl_withdraw_per_hour: int = Field(default=5, ge=1)      # yêu cầu rút theo user
    rl_bank_add_per_hour: int = Field(default=5, ge=1)      # thêm tài khoản ngân hàng theo user

    # --- phát hiện gian lận (T-053): chỉ tạo CỜ cho admin xem, không tự khóa/giữ tiền ---
    fraud_shared_ip_users: int = Field(default=3, ge=2)           # >= chừng này chủ link khác nhau có click từ cùng một ip_hash trong 7 ngày
    fraud_cancel_min_orders: int = Field(default=5, ge=1)         # chỉ xét user có ít nhất chừng này đơn trong 60 ngày
    fraud_cancel_rate_pct: int = Field(default=50, ge=1, le=100)  # hủy + trả hàng >= chừng này % số đơn
    fraud_burst_clicks_per_hour: int = Field(default=60, ge=2)    # >= chừng này click/giờ từ cùng ip_hash vào cùng một link
    fraud_dismiss_cooldown_days: int = Field(default=30, ge=0)    # cờ bị bỏ qua thì không tạo lại cùng (user, rule) trong chừng này ngày

    # --- email giao dịch (T-011): thiếu SMTP_HOST/SMTP_FROM = không gửi ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    web_origin: str = ""                       # https://<domain>: gốc của liên kết trong email (verify/reset). Rỗng = không gửi liên kết
    rl_forgot_per_hour: int = Field(default=5, ge=1)       # quên mật khẩu / gửi lại xác minh, theo IP; theo email = 3 lần/giờ

    # --- sao lưu (T-060, T-065): thư mục chứa tệp .dump.enc để /admin/health báo tuổi bản mới nhất; rỗng = chưa cấu hình ---
    backup_dir: str = ""
    backup_max_age_hours: int = Field(default=36, ge=1)

    # --- cảnh báo vận hành (T-023): rỗng = không gửi ---
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
    alert_repeat_hours: int = Field(default=6, ge=1, le=168)      # còn lỗi thì nhắc lại sau chừng này giờ
    alert_after_failures: int = Field(default=3, ge=1)            # lỗi thường (không phải bị chặn) báo sau chừng này lần liên tiếp

    # --- đăng nhập hai lớp cho admin (TOTP, T-019) ---
    admin_mfa_required: bool = True          # route admin yêu cầu admin đã bật TOTP và đã xác minh gần đây. Bật rút tiền mà tắt cờ này: từ chối khởi động
    mfa_max_age_hours: int = Field(default=12, ge=1, le=168)   # sau chừng này giờ kể từ lần nhập mã phải nhập lại
    mfa_issuer: str = "CashBack"
    rl_mfa_per_minute: int = Field(default=5, ge=1)            # thử mã theo user và theo IP

    # --- đăng nhập (module auth) ---
    jwt_secret: SecretStr = SecretStr("")    # >= 32 ký tự; rỗng thì endpoint auth trả 503
    access_ttl_min: int = 15
    refresh_ttl_days: int = 30
    require_email_verify: bool = False       # bật khi đã có gửi email (T-011)

    # --- giới hạn tốc độ ---
    rl_enabled: bool = True
    rl_register_per_hour: int = Field(default=5, ge=1)
    rl_login_per_minute: int = Field(default=10, ge=1)
    rl_login_per_email_15min: int = Field(default=10, ge=1)
    rl_refresh_per_minute: int = Field(default=30, ge=1)
    rl_go_per_minute: int = Field(default=120, ge=1)

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

    MAX_PREVIOUS_SUBID_KEYS: ClassVar[int] = 3

    def subid_keys(self) -> tuple[str, ...]:
        """(khóa hiện hành, *khóa cũ) để giải mã. Ném ConfigError nếu thiếu/ngắn/trùng/quá nhiều."""
        cur = self.subid_secret.get_secret_value()
        old = [x.strip() for x in self.subid_secret_previous.get_secret_value().split(",") if x.strip()]
        keys = (cur, *old)
        if any(len(k.encode()) < 16 for k in keys):
            raise ConfigError("SUBID_SECRET và SUBID_SECRET_PREVIOUS phải có ít nhất 16 byte mỗi khóa")
        if len(set(keys)) != len(keys):
            raise ConfigError("SUBID_SECRET_PREVIOUS không được trùng khóa hiện hành hay trùng nhau")
        if len(old) > self.MAX_PREVIOUS_SUBID_KEYS:
            raise ConfigError(f"Tối đa {self.MAX_PREVIOUS_SUBID_KEYS} khóa cũ (mỗi khóa thêm tăng xác suất khớp nhầm chữ ký 3 ký tự)")
        return keys

    def require(self, *names: str) -> None:
        missing = []
        for n in names:
            v = getattr(self, n)
            v = v.get_secret_value() if isinstance(v, SecretStr) else v
            if not str(v).strip():
                missing.append(n.upper())
        if missing:
            raise ConfigError("Thiếu biến môi trường: " + ", ".join(missing))

    @property
    def visitor_ip_status(self) -> str:
        """direct (không BFF) | ok | missing_secret | short_secret. Không bao giờ chứa giá trị secret."""
        if not self.bff_enabled:
            return "direct"
        n = len(self.bff_shared_secret.get_secret_value())
        return "missing_secret" if n == 0 else "short_secret" if n < 16 else "ok"

    def startup_warnings(self) -> list[str]:
        out = []
        st = self.visitor_ip_status
        if st in ("missing_secret", "short_secret"):
            out.append(
                f"BFF_ENABLED=1 nhưng BFF_SHARED_SECRET {'chưa đặt' if st == 'missing_secret' else 'quá ngắn (< 16 ký tự)'}: "
                "backend không tin X-Visitor-IP nên MỌI khách qua web dùng chung một bộ đếm rate limit "
                "(một khách đăng nhập sai nhiều lần sẽ chặn tất cả). Đặt cùng một BFF_SHARED_SECRET (>= 16 ký tự) cho backend và BFF")
        return out

    def validate_for_serving(self) -> None:
        if self.subid_secret_previous.get_secret_value().strip():
            self.subid_keys()
        if self.withdrawals_enabled and not self.admin_mfa_required:
            raise ConfigError("WITHDRAWALS_ENABLED=1 nhưng ADMIN_MFA_REQUIRED=0: không được bật rút tiền khi admin chưa bắt buộc TOTP")
        if self.withdrawals_enabled:
            from app.core.crypto import keyring   # chỉ khi bật rút tiền; ném ConfigError nếu khóa thiếu/yếu/sai định dạng
            keyring(self)
        secret = self.bff_shared_secret.get_secret_value()
        if secret and len(secret) < 16:
            raise ConfigError("BFF_SHARED_SECRET phải có ít nhất 16 ký tự (hoặc để trống để không tin X-Visitor-IP)")
        if self.trust_proxy_headers and not self.is_loopback:
            raise ConfigError(
                f"TRUST_PROXY_HEADERS=1 nhưng HOST={self.host} lắng nghe ngoài localhost: ai tới được cổng "
                "cũng giả được CF-Connecting-IP để né rate limit. Đặt HOST=127.0.0.1 (cloudflared/BFF chạy "
                "cùng máy) hoặc TRUST_PROXY_HEADERS=0")
        if not self.is_loopback and not self.agent_api_key.get_secret_value():
            raise ConfigError(
                f"HOST={self.host} lắng nghe ngoài localhost nhưng chưa đặt AGENT_API_KEY; "
                "đặt khóa hoặc dùng HOST=127.0.0.1")
        if not self.is_loopback and not self.ip_salt.get_secret_value():
            raise ConfigError(
                f"HOST={self.host} lắng nghe ngoài localhost nhưng chưa đặt IP_SALT: click sẽ không có "
                "ip_hash/ua_hash (dữ liệu chống gian lận không khôi phục được); đặt IP_SALT hoặc dùng HOST=127.0.0.1")


def load_settings(env_file: Path | str | None = REPO_ROOT / ".env", **overrides) -> Settings:
    """Đọc env (và .env nếu có). Test truyền env_file=None + overrides để cô lập."""
    f = Path(env_file) if env_file else None
    return Settings(_env_file=f if f and f.exists() else None, **overrides)
