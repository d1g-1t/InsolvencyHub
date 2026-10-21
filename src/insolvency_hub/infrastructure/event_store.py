import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from insolvency_hub.core.clock import now
from insolvency_hub.domain.case import Event, EventType
from insolvency_hub.domain.errors import VersionConflict
from insolvency_hub.infrastructure.models import OutboxMessage, StoredEvent


class EventStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, aggregate_id: str) -> list[Event]:
        rows = await self._session.scalars(
            select(StoredEvent).where(StoredEvent.aggregate_id == aggregate_id).order_by(StoredEvent.version)
        )
        return [Event(EventType(row.event_type), row.data) for row in rows]

    async def current_version(self, aggregate_id: str) -> int:
        value = await self._session.scalar(
            select(func.max(StoredEvent.version)).where(StoredEvent.aggregate_id == aggregate_id)
        )
        return value or 0

    async def append(
        self, aggregate_id: str, organization_id: str, expected_version: int, events: list[Event], actor_id: str
    ) -> list[StoredEvent]:
        actual = await self.current_version(aggregate_id)
        if actual != expected_version:
            raise VersionConflict(expected_version, actual)
        occurred = now()
        stored: list[StoredEvent] = []
        for offset, event in enumerate(events, start=1):
            event_id = str(uuid.uuid4())
            version = expected_version + offset
            row = StoredEvent(
                event_id=event_id,
                aggregate_id=aggregate_id,
                organization_id=organization_id,
                version=version,
                event_type=event.type.value,
                data=event.data,
                actor_id=actor_id,
                occurred_at=occurred,
            )
            self._session.add(row)
            self._session.add(
                OutboxMessage(
                    event_id=event_id,
                    aggregate_id=aggregate_id,
                    organization_id=organization_id,
                    event_type=event.type.value,
                    version=version,
                    payload={"data": event.data, "actor_id": actor_id, "occurred_at": occurred.isoformat()},
                )
            )
            stored.append(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise VersionConflict(expected_version, expected_version + 1) from exc
        return stored

    async def history(self, aggregate_id: str) -> list[StoredEvent]:
        rows = await self._session.scalars(
            select(StoredEvent).where(StoredEvent.aggregate_id == aggregate_id).order_by(StoredEvent.version)
        )
        return list(rows)

    async def aggregate_ids(self) -> list[str]:
        rows = await self._session.scalars(select(StoredEvent.aggregate_id).distinct())
        return list(rows)
