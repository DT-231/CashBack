import pytest

from app.core.config import ConfigError, Settings, load_settings


@pytest.fixture(autouse=True)
def blank_env(monkeypatch):
    """conftest đặt MOCK=1 và SHOPEE_AFF_ID; ở đây cần môi trường trống để thấy giá trị mặc định."""
    for k in ("MOCK", "SHOPEE_AFF_ID", "PORT", "SUB_ID_PAD", "AFF_COOKIE", "SHOPEE_COOKIE"):
        monkeypatch.delenv(k, raising=False)


def test_defaults_are_safe():
    s = Settings()
    assert s.mock is False and s.is_loopback and not s.auth_required
    assert s.aff_campaign == "-" and s.sub_id_pad is True and s.search_engine == "auto"


def test_env_parsing(monkeypatch):
    monkeypatch.setenv("MOCK", "1")
    monkeypatch.setenv("SUB_ID_PAD", "0")
    monkeypatch.setenv("PORT", "9000")
    s = Settings()
    assert s.mock is True and s.sub_id_pad is False and s.port == 9000


def test_legacy_cookie_alias(monkeypatch):
    monkeypatch.setenv("AFF_COOKIE", "a=1")
    assert Settings().shopee_cookie.get_secret_value() == "a=1"
    monkeypatch.setenv("SHOPEE_COOKIE", "b=2")
    assert Settings().shopee_cookie.get_secret_value() == "b=2"


def test_secrets_are_masked_in_repr():
    s = Settings(shopee_cookie="super-secret-cookie", agent_api_key="k" * 20)
    assert "super-secret-cookie" not in repr(s) and "kkkkk" not in repr(s)


def test_env_file_is_lower_priority_than_real_env(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('SHOPEE_AFF_ID="111"\nPORT=1234\n')
    monkeypatch.setenv("PORT", "5555")
    s = load_settings(f)
    assert s.shopee_aff_id == "111" and s.port == 5555


def test_load_settings_without_file(tmp_path):
    assert load_settings(tmp_path / "missing.env").shopee_aff_id == ""
    assert load_settings(None).mock is False


def test_require_reports_missing_names():
    with pytest.raises(ConfigError, match="SHOPEE_AFF_ID.*SHOPEE_COOKIE"):
        Settings().require("shopee_aff_id", "shopee_cookie")
    Settings(shopee_aff_id="1").require("shopee_aff_id")


def test_serving_outside_localhost_requires_ip_salt():
    with pytest.raises(ConfigError, match="IP_SALT"):
        Settings(host="0.0.0.0", agent_api_key="k" * 20).validate_for_serving()
    Settings(agent_api_key="k" * 20).validate_for_serving()   # localhost: không bắt buộc


def test_serving_outside_localhost_requires_key():
    with pytest.raises(ConfigError, match="AGENT_API_KEY"):
        Settings(host="0.0.0.0").validate_for_serving()
    Settings(host="0.0.0.0", agent_api_key="k" * 20, ip_salt="i" * 20).validate_for_serving()
    assert Settings(host="0.0.0.0").auth_required and Settings(agent_api_key="x").auth_required
