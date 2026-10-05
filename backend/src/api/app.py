import time
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routers import (
    analysis,
    assets,
    engine,
    feed,
    health,
    insights,
    marketdata,
    portfolio,
    settings,
    sources,
)
from src.core.config import get_settings
from src.core.errors import DomainError
from src.core.logging import configure_logging

logger = structlog.get_logger()


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


def create_app() -> FastAPI:
    configure_logging()
    app_settings = get_settings()
    app = FastAPI(title="Opes API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(DomainError, domain_error_handler)

    @app.middleware("http")
    async def log_requests(request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        structlog.contextvars.bind_contextvars(
            request_id=str(uuid4()), path=request.url.path, method=request.method
        )
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
            logger.info(
                "request",
                status=response.status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            return response
        finally:
            structlog.contextvars.clear_contextvars()

    app.include_router(health.router)
    for router in (
        portfolio, feed, assets, insights, settings, marketdata, analysis, sources, engine
    ):
        app.include_router(router.router, prefix="/api/v1")
    return app
