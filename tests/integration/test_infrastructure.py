import asyncio
import json
from datetime import date
from typing import Any

import pytest
from sqlalchemy import func, select, text

from insolvency_hub.application.cases import CaseService, rebuild_projections
from insolvency_hub.application.outbox import relay_outbox
from insolvency_hub.application.reminders import scan_deadlines
from insolvency_hub.core.security import Principal, Role
from insolvency_hub.domain.case import Event, EventType
from insolvency_hub.domain.enums import Phase, PublicationKind
from insolvency_hub.domain.errors import VersionConflict
from insolvency_hub.infrastructure.event_store import EventStore
from insolvency_hub.infrastructure.models import CaseView, OutboxMessage
from insolvency_hub.infrastructure.publisher import RedisStreamPublisher
from tests.conftest import ORG_A
from tests.factories import LEGAL

STREAM = "test:events"
PRINCIPAL = Principal("00000000-0000-4000-8000-0000000000aa", ORG_A, Role.MANAGER)


async def open_case(sessions: Any) -> str:
    async with sessions() as session:
        case = await CaseService(session).open_case(PRINCIPAL, "А00-9/2026", "суд", LEGAL, date(2026, 2, 2))
        await CaseService(session).execute(
            case.case_id,
            PRINCIPAL,
            1,
            lambda c: (
                c.change_phase(Phase.OBSERVATION, date(2026, 3, 2), hearing_on=date(2026, 9, 1)),
                c.record_publication(PublicationKind.OBSERVATION, date(2026, 3, 7)),
            ),
        )
        return case.case_id


class FailingPublisher:
    def __init__(self, fail_after: int) -> None:
        self.calls = 0
        self.fail_after = fail_after

    async def publish(self, stream: str, fields: dict[str, str]) -> str:
        self.calls += 1
        if self.calls > self.fail_after:
            raise ConnectionError("redis unavailable")
        return f"{self.calls}-0"


async def test_outbox_relay_publishes_once_in_order(sessions: Any, redis_client: Any) -> None:
    case_id = await open_case(sessions)
    publisher = RedisStreamPublisher(redis_client)
    assert await relay_outbox(sessions, publisher, STREAM, 100) == 3
    assert await relay_outbox(sessions, publisher, STREAM, 100) == 0
    entries = await redis_client.xrange(STREAM)
    assert [e[1][b"event_type"].decode() for e in entries] == ["CaseOpened", "PhaseChanged", "PublicationRecorded"]
    first = entries[0][1]
    assert first[b"aggregate_id"].decode() == case_id
    assert first[b"version"] == b"1"
    assert json.loads(first[b"payload"])["data"]["case_number"] == "А00-9/2026"


async def test_outbox_failure_keeps_messages_pending(sessions: Any) -> None:
    await open_case(sessions)
    assert await relay_outbox(sessions, FailingPublisher(1), STREAM, 100) == 1
    async with sessions() as session:
        pending = list(await session.scalars(select(OutboxMessage).where(OutboxMessage.published_at.is_(None))))
    assert len(pending) == 2
    assert pending[0].attempts == 1
    assert pending[0].last_error == "redis unavailable"
    assert pending[1].attempts == 0


async def test_concurrent_relays_do_not_duplicate(sessions: Any, redis_client: Any) -> None:
    for _ in range(4):
        await open_case(sessions)
    publisher = RedisStreamPublisher(redis_client)
    counts = await asyncio.gather(*(relay_outbox(sessions, publisher, STREAM, 3) for _ in range(6)))
    while await relay_outbox(sessions, publisher, STREAM, 3):
        pass
    entries = await redis_client.xrange(STREAM)
    ids = [e[1][b"event_id"] for e in entries]
    assert len(ids) == len(set(ids)) == 12
    assert sum(counts) <= 12


async def test_skip_locked_leaves_locked_rows_to_others(sessions: Any, redis_client: Any) -> None:
    await open_case(sessions)
    async with sessions() as holder:
        locked = list(
            await holder.scalars(
                select(OutboxMessage).order_by(OutboxMessage.id).limit(1).with_for_update(skip_locked=True)
            )
        )
        assert len(locked) == 1
        published = await relay_outbox(sessions, RedisStreamPublisher(redis_client), STREAM, 100)
        assert published == 2
        await holder.rollback()
    assert await relay_outbox(sessions, RedisStreamPublisher(redis_client), STREAM, 100) == 1


async def test_concurrent_append_raises_version_conflict(sessions: Any) -> None:
    case_id = await open_case(sessions)
    event = Event(
        EventType.MANAGER_APPROVED, {"full_name": "А", "sro": "С", "approved_on": "2026-03-02", "phase": "observation"}
    )
    async with sessions() as first, sessions() as second:
        await EventStore(first).append(case_id, ORG_A, 3, [event], PRINCIPAL.user_id)
        competing = asyncio.create_task(EventStore(second).append(case_id, ORG_A, 3, [event], PRINCIPAL.user_id))
        await asyncio.sleep(0.2)
        await first.commit()
        with pytest.raises(VersionConflict):
            await competing
    async with sessions() as session:
        with pytest.raises(VersionConflict):
            await EventStore(session).append(case_id, ORG_A, 3, [event], PRINCIPAL.user_id)


async def test_service_rejects_stale_version(sessions: Any) -> None:
    case_id = await open_case(sessions)
    async with sessions() as session:
        with pytest.raises(VersionConflict):
            await CaseService(session).execute(
                case_id, PRINCIPAL, 1, lambda c: c.approve_manager("А", "С", date(2026, 3, 2))
            )


async def test_rebuild_restores_projections(sessions: Any) -> None:
    case_id = await open_case(sessions)
    async with sessions() as session:
        await session.execute(text("TRUNCATE case_view CASCADE"))
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(CaseView)) == 0
        assert await rebuild_projections(session) == 1
        view = await session.get(CaseView, case_id)
    assert view is not None
    assert view.phase == "observation"
    assert view.version == 3


async def test_deadline_reminders_are_deduplicated(sessions: Any, redis_client: Any) -> None:
    case_id = await open_case(sessions)
    publisher = RedisStreamPublisher(redis_client)
    sent = await scan_deadlines(sessions, publisher, "test:reminders", date(2026, 4, 2), 5)
    assert sent == 1
    assert await scan_deadlines(sessions, publisher, "test:reminders", date(2026, 4, 3), 5) == 0
    entries = await redis_client.xrange("test:reminders")
    fields = entries[0][1]
    assert fields[b"case_id"].decode() == case_id
    assert fields[b"code"] == b"claims_first_meeting"
    assert fields[b"due"] == b"2026-04-06"
    assert json.loads(fields[b"basis"]) == ["127-FZ:71.1", "GK:193"]
