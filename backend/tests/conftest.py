"""Fixture dùng chung. Mọi test chạy MOCK=1 và không bao giờ dùng cookie/proxy/khóa thật:
`clean_env` xóa các biến nhạy cảm khỏi môi trường; `make_settings` tạo Settings không đọc .env.
"""
import pytest

SENSITIVE = [
    "SHOPEE_COOKIE", "AFF_COOKIE", "SHOPEE_PROXY", "SHOPEE_AF_AC_ENC_DAT", "SHOPEE_UA", "FEED_FILE",
    "SEARCH_ENGINE", "LINK_TEMPLATE", "AFF_CAMPAIGN", "SUB_ID_PAD", "PW_STATE", "AGENT_API_KEY", "SUBID_SECRET",
    "HOST", "PORT", "CORS_ORIGINS", "DATABASE_URL", "JWT_SECRET", "ACCESS_TTL_MIN", "REFRESH_TTL_DAYS",
    "REQUIRE_EMAIL_VERIFY", "IP_SALT", "TRUST_PROXY_HEADERS", "SYNC_DAYS", "SYNC_MAX_AGE_HOURS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in SENSITIVE:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setenv("SHOPEE_AFF_ID", "17399999999")


@pytest.fixture
def make_settings():
    """Settings cô lập: không đọc .env, MOCK bật, khóa sub_id đủ dài."""
    def make(**kw):
        from app.core.config import Settings
        base = dict(mock=True, shopee_aff_id="17399999999", subid_secret="s" * 32)
        return Settings(_env_file=None, **{**base, **kw})
    return make


@pytest.fixture
def client(make_settings):
    """FastAPI TestClient cho app mới (không DB). 500 trả về như response thay vì ném lỗi."""
    from fastapi.testclient import TestClient
    from app.main_api import create_app
    return TestClient(create_app(make_settings()), raise_server_exceptions=False)


@pytest.fixture
def feed_file(tmp_path, monkeypatch):
    f = tmp_path / "feed.csv"
    f.write_text(
        "itemid,shopid,product_name,price,commission_rate,sales,product_link\n"
        "900001,7001,Nồi chiên không dầu 6L,690000,8,1200,https://shopee.vn/product/7001/900001\n"
        "900002,7002,Kệ chén inox 2 tầng,159000,6,5100,https://shopee.vn/product/7002/900002\n"
        "900003,7003,Chảo chống dính 28cm,259000,5,2300,https://shopee.vn/product/7003/900003\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FEED_FILE", str(f))
    return f
