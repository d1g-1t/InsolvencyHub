import uuid
from collections.abc import Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from insolvency_hub.core.security import Principal
from insolvency_hub.domain.case import Debtor, InsolvencyCase
from insolvency_hub.domain.errors import NotFound, VersionConflict
from insolvency_hub.infrastructure.event_store import EventStore
from insolvency_hub.infrastructure.models import CaseView, StoredEvent
from insolvency_hub.infrastructure.projection import project_case


class CaseService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._store = EventStore(session)

    async def load(self, case_id: str, principal: Principal) -> InsolvencyCase:
        case = InsolvencyCase.rehydrate(case_id, await self._store.load(case_id))
        if not case.opened or case.organization_id != principal.organization_id:
            raise NotFound(f"дело {case_id} не найдено")
        return case

    async def open_case(
        self, principal: Principal, case_number: str, court: str, debtor: Debtor, petition_received_on: date
    ) -> InsolvencyCase:
        case = InsolvencyCase(str(uuid.uuid4()))
        case.open(principal.organization_id, case_number, court, debtor, petition_received_on)
        await self._commit(case, principal, 0)
        return case

    async def execute(
        self,
        case_id: str,
        principal: Principal,
        expected_version: int | None,
        action: Callable[[InsolvencyCase], None],
    ) -> InsolvencyCase:
        case = await self.load(case_id, principal)
        if expected_version is not None and expected_version != case.version:
            raise VersionConflict(expected_version, case.version)
        base_version = case.version
        action(case)
        await self._commit(case, principal, base_version)
        return case

    async def _commit(self, case: InsolvencyCase, principal: Principal, base_version: int) -> None:
        if case.pending:
            await self._store.append(case.case_id, case.organization_id, base_version, case.pending, principal.user_id)
            await project_case(self._session, case)
        case.pending = []
        await self._session.commit()

    async def history(self, case_id: str, principal: Principal) -> list[StoredEvent]:
        await self.load(case_id, principal)
        return await self._store.history(case_id)


class CaseQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_cases(self, principal: Principal, phase: str | None = None) -> list[CaseView]:
        query = select(CaseView).where(CaseView.organization_id == principal.organization_id)
        if phase:
            query = query.where(CaseView.phase == phase)
        return list(await self._session.scalars(query.order_by(CaseView.updated_at.desc())))


async def rebuild_projections(session: AsyncSession) -> int:
    store = EventStore(session)
    ids = await store.aggregate_ids()
    for aggregate_id in ids:
        case = InsolvencyCase.rehydrate(aggregate_id, await store.load(aggregate_id))
        await project_case(session, case)
    await session.commit()
    return len(ids)
