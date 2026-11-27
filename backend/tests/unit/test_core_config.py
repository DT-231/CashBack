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


def test_trust_proxy_headers_refused_when_not_loopback():
    with pytest.raises(ConfigError, match="TRUST_PROXY_HEADERS"):
        Settings(host="0.0.0.0", trust_proxy_headers=True, agent_api_key="k" * 20,
                 ip_salt="i" * 20).validate_for_serving()
    Settings(host="127.0.0.1", trust_proxy_headers=True).validate_for_serving()
    Settings(host="0.0.0.0", trust_proxy_headers=False, agent_api_key="k" * 20,
             ip_salt="i" * 20).validate_for_serving()


def test_bff_secret_status_and_warnings():
    assert Settings().visitor_ip_status == "direct" and Settings().startup_warnings() == []
    assert Settings(bff_enabled=True).visitor_ip_status == "missing_secret"
    assert Settings(bff_enabled=True, bff_shared_secret="short").visitor_ip_status == "short_secret"
    assert Settings(bff_enabled=True, bff_shared_secret="x" * 16).visitor_ip_status == "ok"
    assert Settings(bff_enabled=True, bff_shared_secret="x" * 16).startup_warnings() == []
    for kw in ({}, {"bff_shared_secret": "short"}):
        w = Settings(bff_enabled=True, **kw).startup_warnings()
        assert len(w) == 1 and "chung một bộ đếm" in w[0]
        assert "short" not in w[0].replace("quá ngắn", "")     # không in giá trị secret


def test_bff_warning_is_logged_at_startup(monkeypatch, caplog):
    import logging
    from app import main_api
    called = {}
    monkeypatch.setattr(main_api, "load_settings", lambda: Settings(bff_enabled=True))
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: called.setdefault("ran", True))
    with caplog.at_level(logging.WARNING):
        main_api.main()
    assert called.get("ran") and any("BFF_SHARED_SECRET" in r.getMessage() for r in caplog.records)


def test_withdrawals_cannot_be_enabled_without_mandatory_admin_totp():
    import base64
    import os
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    with pytest.raises(ConfigError, match="ADMIN_MFA_REQUIRED"):
        Settings(withdrawals_enabled=True, bank_enc_key=key, admin_mfa_required=False).validate_for_serving()
    Settings(withdrawals_enabled=True, bank_enc_key=key).validate_for_serving()
    Settings(withdrawals_enabled=False, admin_mfa_required=False).validate_for_serving()      # tắt cờ chỉ được khi chưa rút tiền
    assert Settings().admin_mfa_required is True                                           # mặc định BẬT
def test_main_refuses_to_start_when_withdrawals_enabled_and_db_user_is_privileged(monkeypatch):
    from app import main_api
    from app.core import db as dbmod
    started = {}
    import base64
    import os
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setattr(main_api, "load_settings", lambda: Settings(withdrawals_enabled=True, bank_enc_key=key, database_url="postgresql://x"))
    monkeypatch.setattr(dbmod, "make_engine", lambda s: type("E", (), {"dispose": lambda self: None})())
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: started.setdefault("ran", True))

    def refuse(engine):
        raise ConfigError("user DB là superuser")
    monkeypatch.setattr(dbmod, "assert_least_privilege", refuse)
    with pytest.raises(ConfigError, match="superuser"):
        main_api.main()
    assert "ran" not in started                                        # không khởi động server


def test_main_skips_the_db_privilege_check_when_withdrawals_disabled(monkeypatch):
    from app import main_api
    from app.core import db as dbmod
    called = []
    monkeypatch.setattr(main_api, "load_settings", lambda: Settings())
    monkeypatch.setattr(dbmod, "assert_least_privilege", lambda e: called.append(1))
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)
    main_api.main()
    assert called == []
