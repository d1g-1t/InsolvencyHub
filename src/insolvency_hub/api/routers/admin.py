from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from insolvency_hub.api.deps import Admin, Session
from insolvency_hub.application.cases import rebuild_projections
from insolvency_hub.core.clock import now
from insolvency_hub.infrastructure.models import OutboxMessage

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/outbox")
async def outbox(session: Session, _: Admin) -> dict[str, Any]:
    pending = OutboxMessage.published_at.is_(None)
    count = await session.scalar(select(func.count()).select_from(OutboxMessage).where(pending)) or 0
    oldest = await session.scalar(select(func.min(OutboxMessage.created_at)).where(pending))
    failing = (
        await session.scalar(
            select(func.count()).select_from(OutboxMessage).where(pending, OutboxMessage.last_error.is_not(None))
        )
        or 0
    )
    return {
        "pending": count,
        "failing": failing,
        "lag_seconds": round((now() - oldest).total_seconds(), 1) if oldest else 0.0,
    }


@router.post("/projections/rebuild")
async def rebuild(session: Session, _: Admin) -> dict[str, int]:
    return {"cases": await rebuild_projections(session)}
