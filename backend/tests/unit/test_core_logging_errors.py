import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import logging as clog
from app.core.errors import AppError, Conflict, register_error_handlers


def _emit(msg, **extra):
    rec = logging.LogRecord("t", logging.INFO, "f", 1, msg, (), None)
    rec.__dict__.update(extra)
    return json.loads(clog.JsonFormatter().format(rec))


def test_json_log_has_request_id():
    clog.set_request_id("rid123")
    assert _emit("hello")["request_id"] == "rid123"


def test_redacts_sensitive_fields_and_text():
    out = _emit("calling with cookie=abc123; token: xyz", headers={"Authorization": "Bearer s", "ok": "v"},
                account_no="9704")
    assert "abc123" not in out["msg"] and "xyz" not in out["msg"]
    assert out["headers"] == {"Authorization": "***", "ok": "v"} and out["account_no"] == "***"


def test_redact_nested():
    assert clog.redact({"a": [{"password": "p"}]}) == {"a": [{"password": "***"}]}


def test_error_format_and_validation():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom():
        raise Conflict("trùng post_key")

    @app.get("/n")
    def n(x: int):
        return x

    @app.get("/custom")
    def custom():
        raise AppError("x", code="my_code", status=418)

    c = TestClient(app)
    clog.set_request_id("r1")
    r = c.get("/boom")
    assert r.status_code == 409 and r.json() == {"error": {"code": "conflict", "message": "trùng post_key",
                                                           "request_id": "r1"}}
    r = c.get("/n", params={"x": "abc"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert c.get("/custom").status_code == 418
