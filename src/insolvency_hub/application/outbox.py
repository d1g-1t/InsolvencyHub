import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from insolvency_hub.core.clock import now
from insolvency_hub.core.logging import get_logger
from insolvency_hub.infrastructure.models import OutboxMessage
from insolvency_hub.infrastructure.publisher import Publisher

log = get_logger(__name__)


async def relay_outbox(
    sessions: async_sessionmaker[AsyncSession], publisher: Publisher, stream: str, batch: int
) -> int:
    published = 0
    async with sessions() as session:
        rows = list(
            await session.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.published_at.is_(None))
                .order_by(OutboxMessage.id)
                .limit(batch)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.attempts += 1
            try:
                await publisher.publish(
                    stream,
                    {
                        "event_id": row.event_id,
                        "aggregate_id": row.aggregate_id,
                        "organization_id": row.organization_id,
                        "event_type": row.event_type,
                        "version": str(row.version),
                        "payload": json.dumps(row.payload, ensure_ascii=False),
                    },
                )
            except Exception as exc:
                row.last_error = str(exc)[:500]
                log.warning("outbox.publish_failed", event_id=row.event_id, error=row.last_error)
                break
            row.published_at = now()
            row.last_error = None
            published += 1
        await session.commit()
    return published
