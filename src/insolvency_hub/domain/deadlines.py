from dataclasses import replace
from datetime import date

from insolvency_hub.domain.calendar import is_verified_year
from insolvency_hub.domain.case import InsolvencyCase
from insolvency_hub.domain.enums import ClaimStatus, DebtorKind, MeetingStatus, NoticeMethod, Phase, PublicationKind
from insolvency_hub.domain.meetings import after_meeting_terms, notice_term
from insolvency_hub.domain.procedures import DURATIONS
from insolvency_hub.domain.terms import Direction, Term, Unit, term_after, term_before

REVIEW_BY_PHASE = {
    Phase.OBSERVATION: ("127-FZ:71.2", "127-FZ:71.3"),
    Phase.RESTRUCTURING: ("127-FZ:213.8.2", "127-FZ:71.2"),
}


def case_terms(case: InsolvencyCase) -> list[Term]:
    terms = [*_procedure_terms(case), *_claim_terms(case), *_meeting_terms(case)]
    return sorted(terms, key=lambda t: (t.due, t.code))


def _procedure_terms(case: InsolvencyCase) -> list[Term]:
    terms: list[Term] = []
    if case.petition_received_on and case.phase in (Phase.PETITION_ACCEPTED, Phase.OBSERVATION):
        terms.append(
            term_after(
                "case_consideration",
                "рассмотрение дела о банкротстве",
                case.petition_received_on,
                7,
                Unit.MONTHS,
                ("127-FZ:51", "APK:114.4"),
            )
        )
    if case.phase is Phase.OBSERVATION:
        published = case.publications.get(PublicationKind.OBSERVATION)
        if published:
            terms.append(
                term_after(
                    "claims_first_meeting",
                    "предъявление требований для участия в первом собрании",
                    published,
                    30,
                    Unit.CALENDAR_DAYS,
                    ("127-FZ:71.1", "GK:193"),
                )
            )
        first_held = any(m.first and m.status is MeetingStatus.HELD for m in case.meetings.values())
        if case.observation_hearing_on and not first_held:
            terms.append(
                term_before(
                    "first_meeting",
                    "проведение первого собрания кредиторов не позднее",
                    case.observation_hearing_on,
                    10,
                    Unit.CALENDAR_DAYS,
                    ("127-FZ:72.1",),
                )
            )
    if case.phase is Phase.RESTRUCTURING:
        published = case.publications.get(PublicationKind.RESTRUCTURING)
        if published:
            terms.append(
                term_after(
                    "claims_restructuring",
                    "предъявление требований к гражданину",
                    published,
                    2,
                    Unit.MONTHS,
                    ("127-FZ:213.8.2", "GK:192.3", "GK:193"),
                )
            )
    if case.phase in (Phase.BANKRUPTCY_PROCEEDINGS, Phase.PROPERTY_REALIZATION):
        published = case.publications.get(PublicationKind(case.phase.value))
        if published:
            basis = (
                ("127-FZ:142.1",)
                if case.phase is Phase.BANKRUPTCY_PROCEEDINGS
                else ("127-FZ:213.24.4", "127-FZ:213.1.1", "127-FZ:142.1")
            )
            terms.append(
                term_after(
                    "registry_closing",
                    "закрытие реестра требований",
                    published,
                    2,
                    Unit.MONTHS,
                    (*basis, "GK:192.3", "GK:193"),
                )
            )
    if case.phase is Phase.BANKRUPTCY_PROCEEDINGS and case.manager and case.manager["phase"] == case.phase.value:
        approved = date.fromisoformat(case.manager["approved_on"])
        terms.append(
            term_after(
                "bankruptcy_publication",
                "направление сведений о банкротстве для опубликования",
                approved,
                10,
                Unit.CALENDAR_DAYS,
                ("127-FZ:128.1", "GK:193"),
            )
        )
    duration = DURATIONS.get(case.phase)
    if duration and case.phase_since:
        terms.append(
            term_after(
                f"{case.phase.value}_ends",
                "окончание срока процедуры",
                case.phase_since,
                duration.amount,
                duration.unit,
                (duration.basis, "GK:192.3", "GK:193"),
            )
        )
    return terms


def _claim_terms(case: InsolvencyCase) -> list[Term]:
    terms: list[Term] = []
    for claim in case.claims.values():
        if claim.status is not ClaimStatus.FILED or claim.review_not_before is None:
            continue
        due = claim.review_not_before
        terms.append(
            Term(
                code=f"claim_review:{claim.claim_id}",
                title=f"рассмотрение требования ({claim.creditor_name}) не ранее; до этой даты - возражения",
                start=claim.filed_on,
                due=due,
                nominal_due=due,
                unit=Unit.CALENDAR_DAYS,
                amount=30,
                direction=Direction.AFTER,
                basis=REVIEW_BY_PHASE.get(claim.filed_in_phase, ("127-FZ:100.3", "127-FZ:100.3.1")),
                calendar_verified=is_verified_year(due.year),
            )
        )
    return terms


def _meeting_terms(case: InsolvencyCase) -> list[Term]:
    terms: list[Term] = []
    for meeting in case.meetings.values():
        if meeting.status is MeetingStatus.SCHEDULED:
            methods = (
                (NoticeMethod.EFRSB, NoticeMethod.POST)
                if case.debtor_kind is DebtorKind.CITIZEN
                else (NoticeMethod.EFRSB, NoticeMethod.POST, NoticeMethod.OTHER)
            )
            for method in methods:
                term = notice_term(method, meeting.meeting_on, case.debtor_kind)
                terms.append(replace(term, code=f"{term.code}:{meeting.meeting_id}"))
        if meeting.status in (MeetingStatus.HELD, MeetingStatus.FAILED):
            terms.extend(
                replace(t, code=f"{t.code}:{meeting.meeting_id}") for t in after_meeting_terms(meeting.meeting_on)
            )
    for requisition in case.requisitions.values():
        if requisition.valid:
            terms.append(
                term_after(
                    f"requisition_meeting:{requisition.requisition_id}",
                    "проведение собрания по требованию кредиторов",
                    requisition.received_on,
                    21,
                    Unit.CALENDAR_DAYS,
                    ("127-FZ:14.3", "GK:193"),
                )
            )
    return terms
