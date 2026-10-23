import uuid
from typing import Any

from fastapi import APIRouter, Response, status

from insolvency_hub.api.deps import Reader, Requester, Session, Version, Writer
from insolvency_hub.api.mappers import meeting_out, term_out
from insolvency_hub.api.routers.common import execute, load
from insolvency_hub.api.schemas import (
    BallotIn,
    CancelIn,
    MeetingCreate,
    NoticeIn,
    ParticipantIn,
    RequisitionIn,
)
from insolvency_hub.core.clock import today
from insolvency_hub.domain.case import AgendaItem, InsolvencyCase
from insolvency_hub.domain.enums import NoticeMethod
from insolvency_hub.domain.errors import NotFound
from insolvency_hub.domain.meetings import after_meeting_terms, notice_term

router = APIRouter(prefix="/api/v1/cases/{case_id}", tags=["meetings"])


def _meeting(case: InsolvencyCase, meeting_id: str) -> dict[str, Any]:
    meeting = case.meetings.get(meeting_id)
    if meeting is None:
        raise NotFound(f"собрание {meeting_id} не найдено")
    return meeting_out(case, meeting)


@router.post("/meetings", status_code=status.HTTP_201_CREATED)
async def schedule_meeting(
    case_id: str, body: MeetingCreate, session: Session, principal: Writer, version: Version, response: Response
) -> dict[str, Any]:
    meeting_id = body.meeting_id or str(uuid.uuid4())
    agenda = [AgendaItem(i.item_id or str(uuid.uuid4()), i.question, i.title) for i in body.agenda]
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.schedule_meeting(
            meeting_id,
            body.meeting_on,
            agenda,
            body.first,
            body.repeated_of,
            body.collateral_sale_refused,
        ),
    )
    response.headers["Location"] = f"/api/v1/cases/{case_id}/meetings/{meeting_id}"
    return _meeting(case, meeting_id)


@router.get("/meetings")
async def list_meetings(case_id: str, session: Session, principal: Reader, response: Response) -> list[dict[str, Any]]:
    case = await load(session, case_id, principal, response)
    return [meeting_out(case, m) for m in sorted(case.meetings.values(), key=lambda m: (m.meeting_on, m.meeting_id))]


@router.get("/meetings/{meeting_id}")
async def get_meeting(
    case_id: str, meeting_id: str, session: Session, principal: Reader, response: Response
) -> dict[str, Any]:
    return _meeting(await load(session, case_id, principal, response), meeting_id)


@router.get("/meetings/{meeting_id}/terms")
async def meeting_terms(
    case_id: str, meeting_id: str, session: Session, principal: Reader, response: Response
) -> dict[str, Any]:
    case = await load(session, case_id, principal, response)
    meeting = case.meetings.get(meeting_id)
    if meeting is None:
        raise NotFound(f"собрание {meeting_id} не найдено")
    now = today()
    return {
        "notice": [term_out(notice_term(m, meeting.meeting_on, case.debtor_kind), now) for m in NoticeMethod],
        "after_meeting": [term_out(t, now) for t in after_meeting_terms(meeting.meeting_on)],
    }


@router.post("/meetings/{meeting_id}/notices")
async def record_notice(
    case_id: str,
    meeting_id: str,
    body: NoticeIn,
    session: Session,
    principal: Writer,
    version: Version,
    response: Response,
) -> dict[str, Any]:
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.record_notice(meeting_id, body.method, body.sent_on, body.recipients),
    )
    return _meeting(case, meeting_id)


@router.post("/meetings/{meeting_id}/participants")
async def register_participant(
    case_id: str,
    meeting_id: str,
    body: ParticipantIn,
    session: Session,
    principal: Writer,
    version: Version,
    response: Response,
) -> dict[str, Any]:
    case = await execute(
        session, case_id, principal, version, response, lambda c: c.register_participant(meeting_id, body.creditor_id)
    )
    return _meeting(case, meeting_id)


@router.post("/meetings/{meeting_id}/ballots")
async def cast_ballot(
    case_id: str,
    meeting_id: str,
    body: BallotIn,
    session: Session,
    principal: Writer,
    version: Version,
    response: Response,
) -> dict[str, Any]:
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.cast_ballot(meeting_id, body.item_id, body.creditor_id, body.vote),
    )
    return _meeting(case, meeting_id)


@router.post("/meetings/{meeting_id}/conclusion")
async def conclude_meeting(
    case_id: str, meeting_id: str, session: Session, principal: Writer, version: Version, response: Response
) -> dict[str, Any]:
    case = await execute(session, case_id, principal, version, response, lambda c: c.conclude_meeting(meeting_id))
    return _meeting(case, meeting_id)


@router.post("/meetings/{meeting_id}/cancellation")
async def cancel_meeting(
    case_id: str,
    meeting_id: str,
    body: CancelIn,
    session: Session,
    principal: Writer,
    version: Version,
    response: Response,
) -> dict[str, Any]:
    case = await execute(
        session, case_id, principal, version, response, lambda c: c.cancel_meeting(meeting_id, body.reason)
    )
    return _meeting(case, meeting_id)


def _requisition_out(case: InsolvencyCase, requisition_id: str) -> dict[str, Any]:
    r = case.requisitions[requisition_id]
    return {
        "requisition_id": r.requisition_id,
        "creditor_ids": r.creditor_ids,
        "received_on": r.received_on,
        "by_committee": r.by_committee,
        "agenda": r.agenda,
        "valid": r.valid,
        "share_percent": r.share_percent,
        "hold_by": r.hold_by,
        "basis": ["127-FZ:14.1", "127-FZ:14.3"],
    }


@router.post("/requisitions", status_code=status.HTTP_201_CREATED)
async def receive_requisition(
    case_id: str, body: RequisitionIn, session: Session, principal: Requester, version: Version, response: Response
) -> dict[str, Any]:
    requisition_id = body.requisition_id or str(uuid.uuid4())
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.receive_requisition(
            requisition_id,
            body.creditor_ids,
            body.received_on,
            body.agenda,
            body.by_committee,
        ),
    )
    return _requisition_out(case, requisition_id)


@router.get("/requisitions")
async def list_requisitions(
    case_id: str, session: Session, principal: Reader, response: Response
) -> list[dict[str, Any]]:
    case = await load(session, case_id, principal, response)
    return [_requisition_out(case, r) for r in sorted(case.requisitions)]
