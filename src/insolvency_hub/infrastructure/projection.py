from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from insolvency_hub.core.clock import now
from insolvency_hub.domain.case import InsolvencyCase
from insolvency_hub.domain.enums import ClaimStatus
from insolvency_hub.infrastructure.models import CaseView, ClaimView, MeetingView


async def project_case(session: AsyncSession, case: InsolvencyCase) -> None:
    if case.debtor is None:
        return
    registry_total = sum(
        (c.outstanding.total for c in case.claims.values() if c.status is ClaimStatus.INCLUDED), Decimal("0")
    )
    values = {
        "case_id": case.case_id,
        "organization_id": case.organization_id,
        "case_number": case.case_number,
        "court": case.court,
        "debtor_kind": case.debtor.kind.value,
        "debtor_name": case.debtor.name,
        "debtor_inn": case.debtor.inn,
        "phase": case.phase.value,
        "phase_since": case.phase_since,
        "manager_name": case.manager["full_name"] if case.manager else None,
        "claims_count": len(case.claims),
        "registry_total": registry_total,
        "version": case.version,
        "updated_at": now(),
    }
    statement = insert(CaseView).values(**values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[CaseView.case_id], set_={k: statement.excluded[k] for k in values if k != "case_id"}
        )
    )
    await session.execute(delete(ClaimView).where(ClaimView.case_id == case.case_id))
    await session.execute(delete(MeetingView).where(MeetingView.case_id == case.case_id))
    for claim in case.claims.values():
        session.add(
            ClaimView(
                claim_id=claim.claim_id,
                case_id=case.case_id,
                organization_id=case.organization_id,
                creditor_id=claim.creditor_id,
                creditor_name=claim.creditor_name,
                creditor_kind=claim.creditor_kind.value,
                queue=claim.queue.value,
                after_third_basis=claim.after_third_basis.value if claim.after_third_basis else None,
                status=claim.status.value,
                secured=claim.secured,
                timely=claim.timely,
                filed_on=claim.filed_on,
                ruling_date=claim.ruling_date,
                review_not_before=claim.review_not_before,
                filed_principal=claim.filed.principal,
                filed_interest=claim.filed.interest,
                filed_sanctions=claim.filed.sanctions,
                included_principal=claim.included.principal if claim.included else None,
                included_interest=claim.included.interest if claim.included else None,
                included_sanctions=claim.included.sanctions if claim.included else None,
                paid_total=claim.paid.total,
            )
        )
    for meeting in case.meetings.values():
        session.add(
            MeetingView(
                meeting_id=meeting.meeting_id,
                case_id=case.case_id,
                organization_id=case.organization_id,
                meeting_on=meeting.meeting_on,
                status=meeting.status.value,
                first=meeting.first,
                agenda=[{"item_id": i.item_id, "question": i.question.value, "title": i.title} for i in meeting.agenda],
                quorum=meeting.quorum,
                results=meeting.results,
            )
        )
    await session.flush()
