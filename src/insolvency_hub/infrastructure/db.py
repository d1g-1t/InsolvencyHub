from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from insolvency_hub.core.config import get_settings


def make_engine(url: str | None = None, *, null_pool: bool = False) -> AsyncEngine:
    target = url or get_settings().database_url
    if null_pool:
        return create_async_engine(target, poolclass=NullPool)
    return create_async_engine(target, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
