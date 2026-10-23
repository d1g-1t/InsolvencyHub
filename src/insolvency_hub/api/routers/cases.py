from typing import Any

from fastapi import APIRouter, Response, status

from insolvency_hub.api.deps import Reader, Session, Version, Writer
from insolvency_hub.api.mappers import case_out, term_out
from insolvency_hub.api.routers.common import etag, execute, load
from insolvency_hub.api.schemas import CaseCreate, ManagerIn, PublicationIn, TermOut, TransitionIn
from insolvency_hub.application.cases import CaseQueries, CaseService
from insolvency_hub.core.clock import today
from insolvency_hub.domain.case import Debtor
from insolvency_hub.domain.deadlines import case_terms
from insolvency_hub.domain.enums import Phase

router = APIRouter(prefix="/api/v1/cases", tags=["cases"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def open_case(body: CaseCreate, session: Session, principal: Writer, response: Response) -> dict[str, Any]:
    debtor = Debtor(body.debtor.kind, body.debtor.name, body.debtor.inn, body.debtor.ogrn)
    case = await CaseService(session).open_case(
        principal, body.case_number, body.court, debtor, body.petition_received_on
    )
    etag(response, case)
    response.headers["Location"] = f"/api/v1/cases/{case.case_id}"
    return case_out(case)


@router.get("")
async def list_cases(session: Session, principal: Reader, phase: Phase | None = None) -> list[dict[str, Any]]:
    views = await CaseQueries(session).list_cases(principal, phase.value if phase else None)
    return [
        {
            "case_id": v.case_id,
            "case_number": v.case_number,
            "court": v.court,
            "debtor_kind": v.debtor_kind,
            "debtor_name": v.debtor_name,
            "debtor_inn": v.debtor_inn,
            "phase": v.phase,
            "phase_since": v.phase_since,
            "manager_name": v.manager_name,
            "claims_count": v.claims_count,
            "registry_total": str(v.registry_total),
            "version": v.version,
        }
        for v in views
    ]


@router.get("/{case_id}")
async def get_case(case_id: str, session: Session, principal: Reader, response: Response) -> dict[str, Any]:
    return case_out(await load(session, case_id, principal, response))


@router.get("/{case_id}/events")
async def events(case_id: str, session: Session, principal: Reader) -> list[dict[str, Any]]:
    history = await CaseService(session).history(case_id, principal)
    return [
        {
            "version": e.version,
            "type": e.event_type,
            "data": e.data,
            "actor_id": e.actor_id,
            "occurred_at": e.occurred_at,
        }
        for e in history
    ]


@router.post("/{case_id}/transitions")
async def change_phase(
    case_id: str, body: TransitionIn, session: Session, principal: Writer, version: Version, response: Response
) -> dict[str, Any]:
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.change_phase(body.target, body.court_act_date, body.hearing_on),
    )
    return case_out(case)


@router.post("/{case_id}/publications")
async def record_publication(
    case_id: str, body: PublicationIn, session: Session, principal: Writer, version: Version, response: Response
) -> dict[str, Any]:
    case = await execute(
        session, case_id, principal, version, response, lambda c: c.record_publication(body.kind, body.published_on)
    )
    return case_out(case)


@router.post("/{case_id}/manager")
async def approve_manager(
    case_id: str, body: ManagerIn, session: Session, principal: Writer, version: Version, response: Response
) -> dict[str, Any]:
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.approve_manager(body.full_name, body.sro, body.approved_on),
    )
    return case_out(case)


@router.get("/{case_id}/deadlines")
async def deadlines(case_id: str, session: Session, principal: Reader, response: Response) -> list[TermOut]:
    case = await load(session, case_id, principal, response)
    now = today()
    return [term_out(t, now) for t in case_terms(case)]
