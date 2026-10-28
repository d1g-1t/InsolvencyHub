from datetime import date
from typing import Any

from insolvency_hub.application.cases import CaseService
from insolvency_hub.core.security import Principal, Role
from tests.conftest import ORG_A
from tests.factories import LEGAL


async def test_worker_tasks_run_against_real_services(sessions: Any, redis_client: Any) -> None:
    from insolvency_hub.core.config import get_settings
    from insolvency_hub.infrastructure import worker

    principal = Principal("00000000-0000-4000-8000-0000000000aa", ORG_A, Role.MANAGER)
    async with sessions() as session:
        await CaseService(session).open_case(principal, "А00-3/2026", "суд", LEGAL, date(2026, 2, 2))
    assert worker.celery_app.conf.timezone == "Europe/Moscow"
    assert set(worker.celery_app.conf.beat_schedule) == {"relay-outbox", "scan-deadlines"}
    assert await worker._with_resources(worker._rebuild) == 1
    relayed = await worker._with_resources(lambda s, p: worker.relay_outbox(s, p, get_settings().events_stream, 10))
    assert relayed == 1
    assert await redis_client.xlen(get_settings().events_stream) == 1


def test_celery_task_bodies(migrated: str) -> None:
    import asyncio

    from redis import Redis
    from sqlalchemy import text

    from insolvency_hub.core.config import get_settings
    from insolvency_hub.infrastructure import worker
    from insolvency_hub.infrastructure.db import make_engine

    async def reset() -> None:
        engine = make_engine(migrated, null_pool=True)
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE outbox, events, case_view CASCADE"))
        await engine.dispose()

    asyncio.run(reset())
    Redis.from_url(get_settings().redis_url).flushdb()
    assert worker.relay_outbox_task.run() == 0
    assert worker.scan_deadlines_task.run() == 0
    assert worker.rebuild_projections_task.run() == 0
