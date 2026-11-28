import smtplib

from app.core.config import Settings
from app.integrations.mail import NullMailer, SmtpMailer, build_mailer


def test_build_mailer_needs_host_and_sender_and_never_in_mock():
    base = dict(smtp_host="smtp.example.test", smtp_from="no-reply@example.test", mock=False)
    assert isinstance(build_mailer(Settings(**base)), SmtpMailer)
    assert isinstance(build_mailer(Settings(**{**base, "mock": True})), NullMailer)
    assert isinstance(build_mailer(Settings(**{**base, "smtp_host": ""})), NullMailer)
    assert isinstance(build_mailer(Settings(**{**base, "smtp_from": " "})), NullMailer)
    assert NullMailer().send("a@b", "s", "b") is False


def test_smtp_uses_starttls_before_login_and_sends(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, u, p):
            calls.append(("login", u))

        def send_message(self, msg):
            calls.append(("send", msg["To"], msg["Subject"], msg.get_content()))
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    assert SmtpMailer("h", 587, "u", "p", "from@x.test").send("to@x.test", "Chủ đề", "Nội dung") is True
    assert [c[0] for c in calls] == ["connect", "starttls", "login", "send"]               # mã hóa kênh TRƯỚC khi gửi mật khẩu
    assert calls[3][1:3] == ("to@x.test", "Chủ đề")


def test_smtp_failure_returns_false_and_logs_no_content(monkeypatch, caplog):
    import logging

    def boom(*a, **k):
        raise smtplib.SMTPException("x token=SECRETTOKEN to=victim@example.test")
    monkeypatch.setattr(smtplib, "SMTP", boom)
    with caplog.at_level(logging.DEBUG):
        assert SmtpMailer("h", 587, "u", "p", "f@x.test").send("victim@example.test", "s", "link?token=SECRETTOKEN") is False
    dump = "\n".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "SECRETTOKEN" not in dump and "victim@example.test" not in dump
