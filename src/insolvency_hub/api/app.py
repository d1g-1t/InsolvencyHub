from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from insolvency_hub import __version__
from insolvency_hub.api.errors import register_error_handlers
from insolvency_hub.api.routers import admin, auth, cases, claims, meetings, reference, system
from insolvency_hub.core.config import get_settings
from insolvency_hub.core.logging import configure_logging
from insolvency_hub.infrastructure.db import make_engine, make_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = make_engine()
    app.state.sessions = make_session_factory(engine)
    app.state.redis = Redis.from_url(settings.redis_url)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    configure_logging(get_settings().log_json)
    app = FastAPI(
        title="InsolvencyHub",
        version=__version__,
        summary="Учет дел о банкротстве по 127-ФЗ: процедуры, реестр требований, собрания кредиторов, сроки",
        lifespan=lifespan,
    )
    register_error_handlers(app)
    for module in (system, auth, reference, cases, claims, meetings, admin):
        app.include_router(module.router)
    app.include_router(claims.exports)
    return app
