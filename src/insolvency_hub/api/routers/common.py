from collections.abc import Callable

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from insolvency_hub.application.cases import CaseService
from insolvency_hub.core.security import Principal
from insolvency_hub.domain.case import InsolvencyCase


def etag(response: Response, case: InsolvencyCase) -> None:
    response.headers["ETag"] = f'"{case.version}"'


async def load(session: AsyncSession, case_id: str, principal: Principal, response: Response) -> InsolvencyCase:
    case = await CaseService(session).load(case_id, principal)
    etag(response, case)
    return case


async def execute(
    session: AsyncSession,
    case_id: str,
    principal: Principal,
    version: int | None,
    response: Response,
    action: Callable[[InsolvencyCase], None],
) -> InsolvencyCase:
    case = await CaseService(session).execute(case_id, principal, version, action)
    etag(response, case)
    return case
