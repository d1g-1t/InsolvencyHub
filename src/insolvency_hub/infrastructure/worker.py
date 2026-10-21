import asyncio
from collections.abc import Awaitable, Callable

from celery import Celery
from celery.schedules import crontab
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from insolvency_hub.application.cases import rebuild_projections
from insolvency_hub.application.outbox import relay_outbox
from insolvency_hub.application.reminders import scan_deadlines
from insolvency_hub.core.clock import today
from insolvency_hub.core.config import get_settings
from insolvency_hub.infrastructure.db import make_engine, make_session_factory
from insolvency_hub.infrastructure.publisher import RedisStreamPublisher

settings = get_settings()

celery_app = Celery("insolvency_hub", broker=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="Europe/Moscow",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "relay-outbox": {"task": "insolvency_hub.relay_outbox", "schedule": 10.0},
        "scan-deadlines": {"task": "insolvency_hub.scan_deadlines", "schedule": crontab(hour=7, minute=0)},
    },
)


async def _with_resources[T](
    work: Callable[[async_sessionmaker[AsyncSession], RedisStreamPublisher], Awaitable[T]],
) -> T:
    engine = make_engine(null_pool=True)
    client = Redis.from_url(settings.redis_url)
    try:
        return await work(make_session_factory(engine), RedisStreamPublisher(client))
    finally:
        await client.aclose()
        await engine.dispose()


@celery_app.task(name="insolvency_hub.relay_outbox")
def relay_outbox_task() -> int:
    return asyncio.run(
        _with_resources(
            lambda sessions, publisher: relay_outbox(sessions, publisher, settings.events_stream, settings.outbox_batch)
        )
    )


@celery_app.task(name="insolvency_hub.scan_deadlines")
def scan_deadlines_task() -> int:
    return asyncio.run(
        _with_resources(
            lambda sessions, publisher: scan_deadlines(
                sessions, publisher, settings.reminders_stream, today(), settings.reminder_horizon_days
            )
        )
    )


async def _rebuild(sessions: async_sessionmaker[AsyncSession], _: RedisStreamPublisher) -> int:
    async with sessions() as session:
        return await rebuild_projections(session)


@celery_app.task(name="insolvency_hub.rebuild_projections")
def rebuild_projections_task() -> int:
    return asyncio.run(_with_resources(_rebuild))
