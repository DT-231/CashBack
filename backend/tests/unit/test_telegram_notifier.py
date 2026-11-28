import logging

import requests

from app.core.config import Settings
from app.integrations.telegram import NullNotifier, TelegramNotifier, build_notifier


def test_build_notifier_is_null_unless_fully_configured_and_not_mock():
    assert isinstance(build_notifier(Settings(mock=False)), NullNotifier)
    assert isinstance(build_notifier(Settings(mock=False, telegram_bot_token="t" * 10)), NullNotifier)       # thiếu chat id
    assert isinstance(build_notifier(Settings(mock=True, telegram_bot_token="t" * 10, telegram_chat_id="1")), NullNotifier)   # MOCK: không bao giờ gửi
    assert isinstance(build_notifier(Settings(mock=False, telegram_bot_token="t" * 10, telegram_chat_id="1")), TelegramNotifier)
    assert NullNotifier().send("x") is False


def test_send_posts_json_with_timeout_and_truncates(monkeypatch):
    seen = {}
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: seen.update(url=url, json=json, timeout=timeout) or type("R", (), {"ok": True})())
    assert TelegramNotifier("TOKEN123", "42").send("a" * 5000) is True
    assert seen["url"].endswith("/botTOKEN123/sendMessage") and seen["json"]["chat_id"] == "42" and len(seen["json"]["text"]) == 3500 and seen["timeout"] > 0


def test_send_failure_is_swallowed_and_never_logs_the_token(monkeypatch, caplog):
    def boom(*a, **k):
        raise requests.ConnectionError("https://api.telegram.org/botSECRETTOKEN/sendMessage down")
    monkeypatch.setattr(requests, "post", boom)
    with caplog.at_level(logging.DEBUG):
        assert TelegramNotifier("SECRETTOKEN", "42").send("x") is False
    assert "SECRETTOKEN" not in "\n".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
