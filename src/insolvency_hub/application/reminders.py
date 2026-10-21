import json
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from insolvency_hub.domain.case import InsolvencyCase
from insolvency_hub.domain.deadlines import case_terms
from insolvency_hub.domain.enums import TERMINAL_PHASES
from insolvency_hub.domain.terms import Term
from insolvency_hub.infrastructure.event_store import EventStore
from insolvency_hub.infrastructure.models import CaseView
from insolvency_hub.infrastructure.publisher import RedisStreamPublisher


def due_soon(terms: list[Term], today: date, horizon_days: int) -> list[Term]:
    limit = today + timedelta(days=horizon_days)
    return [t for t in terms if today <= t.due <= limit]


async def scan_deadlines(
    sessions: async_sessionmaker[AsyncSession],
    publisher: RedisStreamPublisher,
    stream: str,
    today: date,
    horizon_days: int,
) -> int:
    sent = 0
    terminal = [p.value for p in TERMINAL_PHASES]
    async with sessions() as session:
        views = list(await session.scalars(select(CaseView).where(CaseView.phase.not_in(terminal))))
        store = EventStore(session)
        for view in views:
            case = InsolvencyCase.rehydrate(view.case_id, await store.load(view.case_id))
            for term in due_soon(case_terms(case), today, horizon_days):
                key = f"insolvency_hub:reminder:{view.case_id}:{term.code}:{term.due.isoformat()}"
                if not await publisher.remember_once(key, ttl_seconds=60 * 60 * 24 * 60):
                    continue
                await publisher.publish(
                    stream,
                    {
                        "case_id": view.case_id,
                        "organization_id": view.organization_id,
                        "case_number": view.case_number,
                        "code": term.code,
                        "title": term.title,
                        "due": term.due.isoformat(),
                        "basis": json.dumps(list(term.basis)),
                    },
                )
                sent += 1
    return sent
