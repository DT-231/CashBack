"""Định dạng lỗi chung của API v1: {"error": {"code", "message", "request_id"}}."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_request_id


class AppError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status:
            self.status = status


class NotFound(AppError):
    status, code = 404, "not_found"


class Conflict(AppError):
    status, code = 409, "conflict"


class Unauthorized(AppError):
    status, code = 401, "unauthorized"


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "request_id": get_request_id()}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, e: AppError):
        return JSONResponse(error_body(e.code, e.message), status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        first = e.errors()[0] if e.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        return JSONResponse(error_body("validation_error", f"{loc}: {first.get('msg', 'không hợp lệ')}"),
                            status_code=422)
