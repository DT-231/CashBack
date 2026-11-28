"""Gửi email giao dịch (xác minh, đặt lại mật khẩu). Integration duy nhất ra SMTP. Không cấu hình SMTP (hoặc MOCK=1) thì KHÔNG gửi gì.
Nội dung email chứa token một lần: không bao giờ ghi nội dung/ người nhận vào log (chỉ ghi kết quả)."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

from app.core.config import Settings

log = logging.getLogger("app.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> bool: ...


class NullMailer:
    def send(self, to: str, subject: str, body: str) -> bool:
        return False


class SmtpMailer:
    def __init__(self, host: str, port: int, user: str, password: str, sender: str, sender_name: str = "CashBack", timeout: float = 15.0):
        self.host, self.port, self.user, self.password, self.sender, self.name, self.timeout = host, port, user, password, sender, sender_name, timeout

    def send(self, to: str, subject: str, body: str) -> bool:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = formataddr((self.name, self.sender)), to, subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
                s.starttls(context=ssl.create_default_context())          # luôn mã hóa kênh trước khi gửi mật khẩu SMTP
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(msg)
            return True
        except (smtplib.SMTPException, OSError) as e:
            log.warning("gửi email thất bại", extra={"error": type(e).__name__})
            return False


def build_mailer(s: Settings) -> Mailer:
    if s.mock or not s.smtp_host.strip() or not s.smtp_from.strip():
        return NullMailer()
    return SmtpMailer(s.smtp_host.strip(), s.smtp_port, s.smtp_user, s.smtp_password.get_secret_value(), s.smtp_from.strip())
