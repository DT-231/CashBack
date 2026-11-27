"""Gửi cảnh báo cho người vận hành (integration duy nhất ra Telegram). Mặc định KHÔNG gửi đi đâu (cần TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID).
Thông điệp không bao giờ chứa cookie/token: caller chỉ truyền chữ mô tả. Lỗi gửi chỉ ghi log, không làm hỏng việc đang chạy."""
from __future__ import annotations

import logging
from typing import Protocol

import requests

from app.core.config import Settings

log = logging.getLogger("app.notify")


class Notifier(Protocol):
    def send(self, text: str) -> bool: ...


class NullNotifier:
    def send(self, text: str) -> bool:
        return False


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timeout: float = 10.0):
        self._url, self._chat, self._timeout = f"https://api.telegram.org/bot{token}/sendMessage", chat_id, timeout

    def send(self, text: str) -> bool:
        try:
            r = requests.post(self._url, json={"chat_id": self._chat, "text": text[:3500]}, timeout=self._timeout)
            return r.ok
        except requests.RequestException as e:
            log.warning("gửi Telegram thất bại", extra={"error": type(e).__name__})      # không log URL (chứa token)
            return False


def build_notifier(s: Settings) -> Notifier:
    token, chat = s.telegram_bot_token.get_secret_value(), s.telegram_chat_id.strip()
    return TelegramNotifier(token, chat) if token and chat and not s.mock else NullNotifier()
