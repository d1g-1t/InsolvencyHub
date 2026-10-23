from datetime import date
from decimal import Decimal
from typing import Any

from insolvency_hub.api.schemas import TermOut
from insolvency_hub.domain.case import Claim, InsolvencyCase, Meeting
from insolvency_hub.domain.claims import Amounts
from insolvency_hub.domain.errors import NotFound
from insolvency_hub.domain.procedures import allowed_targets
from insolvency_hub.domain.terms import Term


def amounts_out(amounts: Amounts | None) -> dict[str, str] | None:
    if amounts is None:
        return None
    return {
        "principal": str(amounts.principal),
        "interest": str(amounts.interest),
        "sanctions": str(amounts.sanctions),
        "total": str(amounts.total),
    }


def term_out(term: Term, today: date) -> TermOut:
    return TermOut(
        code=term.code,
        title=term.title,
        start=term.start,
        due=term.due,
        nominal_due=term.nominal_due,
        shifted=term.shifted,
        unit=term.unit,
        amount=term.amount,
        direction=term.direction,
        status=term.status(today),
        calendar_verified=term.calendar_verified,
        basis=list(term.basis),
    )


def case_out(case: InsolvencyCase) -> dict[str, Any]:
    if case.debtor is None:
        raise NotFound(f"дело {case.case_id} не найдено")
    return {
        "case_id": case.case_id,
        "version": case.version,
        "case_number": case.case_number,
        "court": case.court,
        "debtor": {
            "kind": case.debtor.kind.value,
            "name": case.debtor.name,
            "inn": case.debtor.inn,
            "ogrn": case.debtor.ogrn,
        },
        "petition_received_on": case.petition_received_on,
        "phase": case.phase.value,
        "phase_since": case.phase_since,
        "phase_history": case.phase_history,
        "allowed_transitions": [p.value for p in allowed_targets(case.debtor.kind, case.phase)],
        "publications": {k.value: v.isoformat() for k, v in case.publications.items()},
        "manager": case.manager,
        "observation_hearing_on": case.observation_hearing_on,
        "claims_count": len(case.claims),
        "meetings_count": len(case.meetings),
    }


def claim_out(claim: Claim) -> dict[str, Any]:
    return {
        "claim_id": claim.claim_id,
        "creditor_id": claim.creditor_id,
        "creditor_name": claim.creditor_name,
        "creditor_kind": claim.creditor_kind.value,
        "queue": claim.queue.value,
        "after_third_basis": claim.after_third_basis.value if claim.after_third_basis else None,
        "status": claim.status.value,
        "filed": amounts_out(claim.filed),
        "included": amounts_out(claim.included),
        "paid": amounts_out(claim.paid),
        "outstanding": amounts_out(claim.outstanding),
        "secured": claim.secured,
        "credit_agreement": claim.credit_agreement,
        "grounds": claim.grounds,
        "filed_on": claim.filed_on,
        "filed_in_phase": claim.filed_in_phase.value,
        "timely": claim.timely,
        "votes_at_first_meeting": claim.votes_at_first_meeting,
        "review_deferred": claim.review_deferred,
        "review_not_before": claim.review_not_before,
        "closing_date": claim.closing_date,
        "ruling_date": claim.ruling_date,
        "excluded_on": claim.excluded_on,
        "reason": claim.reason,
        "objections": claim.objections,
    }


def _percent(part: Decimal, total: Decimal) -> str:
    return str((part * 100 / total).quantize(Decimal("0.01"))) if total else "0.00"


def meeting_out(case: InsolvencyCase, meeting: Meeting) -> dict[str, Any]:
    weights = case.meeting_weights(meeting)
    total = sum(weights.values(), Decimal("0"))
    return {
        "meeting_id": meeting.meeting_id,
        "meeting_on": meeting.meeting_on,
        "phase": meeting.phase.value,
        "status": meeting.status.value,
        "first": meeting.first,
        "repeated_of": meeting.repeated_of,
        "collateral_sale_refused": meeting.collateral_sale_refused,
        "agenda": [{"item_id": i.item_id, "question": i.question.value, "title": i.title} for i in meeting.agenda],
        "notices": meeting.notices,
        "properly_notified": meeting.properly_notified,
        "present": sorted(meeting.present),
        "ballots": {item: {c: v.value for c, v in votes.items()} for item, votes in meeting.ballots.items()},
        "voters": [
            {"creditor_id": c, "votes": str(w), "share_percent": _percent(w, total)} for c, w in sorted(weights.items())
        ],
        "total_votes": str(total),
        "quorum": meeting.quorum,
        "results": meeting.results,
    }
