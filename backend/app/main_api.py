"""Entrypoint HTTP (FastAPI): chỉ gắn router + middleware. Chạy: `python -m app.main_api`."""
from __future__ import annotations

import logging
import threading
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from app import legacy_api
from app.core.config import ConfigError, Settings, load_settings
from app.core.db import make_engine
from app.core.errors import error_body, register_error_handlers
from app.core.logging import configure_logging, set_request_id
from app.integrations.shopee import build_client
from app.modules.ai_posts import api as ai_posts_api
from app.modules.auth import api as auth_api
from app.modules.clicks import api as clicks_api
from app.modules.links.affiliate_link import LinkInputError
from app.modules.links import api as links_api
from app.modules.products.service import ProductSearch

log = logging.getLogger("app.access")


def create_app(settings: Settings | None = None, shopee=None, engine: Engine | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Cashback API", version="0.1.0")
    app.state.settings = settings
    app.state.shopee = shopee or build_client(settings)
    app.state.search = ProductSearch(settings, app.state.shopee)
    app.state.engine = engine

    engine_lock = threading.Lock()

    def get_engine() -> Engine:
        with engine_lock:
            if app.state.engine is None:
                app.state.engine = make_engine(settings)   # lười: chỉ cần khi gọi endpoint dùng DB
            return app.state.engine
    app.state.get_engine = get_engine

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origins:   # mặc định KHÔNG bật CORS: Tool API là server-to-server
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "OPTIONS"],
                           allow_headers=["Content-Type", "Authorization"])

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        rid = set_request_id(request.headers.get("x-request-id"))
        t0 = time.perf_counter()
        try:
            resp = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"method": request.method, "path": request.url.path})
            resp = JSONResponse(error_body("internal_error", "lỗi không xác định"), status_code=500)
        resp.headers["x-request-id"] = rid
        log.info("request", extra={"method": request.method, "path": request.url.path, "status": resp.status_code,
                                   "ms": round((time.perf_counter() - t0) * 1000, 1)})
        return resp

    @app.exception_handler(LinkInputError)
    async def _link_input(_: Request, e: LinkInputError):
        return JSONResponse(error_body("invalid_input", str(e)), status_code=400)

    @app.exception_handler(ConfigError)
    async def _config(_: Request, e: ConfigError):
        return JSONResponse(error_body("not_configured", str(e)), status_code=503)

    register_error_handlers(app)
    app.include_router(legacy_api.router)
    app.include_router(ai_posts_api.router)
    app.include_router(links_api.router)
    app.include_router(clicks_api.router)
    app.include_router(auth_api.router)
    return app


def main() -> None:
    import uvicorn
    s = load_settings()
    s.validate_for_serving()
    uvicorn.run(create_app(s), host=s.host, port=s.port, log_config=None)


if __name__ == "__main__":
    main()
