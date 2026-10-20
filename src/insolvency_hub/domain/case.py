from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

from insolvency_hub.domain.claims import Amounts, assess_filing, assign_queue
from insolvency_hub.domain.enums import (
    TERMINAL_PHASES,
    AfterThirdBasis,
    ClaimStatus,
    CreditorKind,
    DebtorKind,
    MeetingStatus,
    NoticeMethod,
    Phase,
    PublicationKind,
    Question,
    Queue,
    Vote,
)
from insolvency_hub.domain.errors import NotFound, TransitionNotAllowed, ValidationFailed
from insolvency_hub.domain.identifiers import require_case_number, require_inn, require_ogrn
from insolvency_hub.domain.meetings import assess_requisition, notice_is_timely, properly_notified
from insolvency_hub.domain.money import ZERO, money
from insolvency_hub.domain.procedures import (
    CLAIM_PHASES,
    MEETING_PHASES,
    PUBLICATION_FOR_PHASE,
    find_transition,
    initial_phase,
)
from insolvency_hub.domain.voting import (
    ItemResult,
    Quorum,
    VotingClaim,
    VotingContext,
    quorum,
    tally,
    voting_weights,
)


class EventType(StrEnum):
    CASE_OPENED = "CaseOpened"
    PHASE_CHANGED = "PhaseChanged"
    PUBLICATION_RECORDED = "PublicationRecorded"
    MANAGER_APPROVED = "ManagerApproved"
    CLAIM_FILED = "ClaimFiled"
    CLAIM_OBJECTED = "ClaimObjected"
    CLAIM_RULED = "ClaimRuled"
    CLAIM_EXCLUDED = "ClaimExcluded"
    CLAIM_PAYMENT_RECORDED = "ClaimPaymentRecorded"
    MEETING_SCHEDULED = "MeetingScheduled"
    MEETING_NOTICE_RECORDED = "MeetingNoticeRecorded"
    MEETING_PARTICIPANT_REGISTERED = "MeetingParticipantRegistered"
    BALLOT_CAST = "BallotCast"
    MEETING_CONCLUDED = "MeetingConcluded"
    MEETING_CANCELLED = "MeetingCancelled"
    REQUISITION_RECEIVED = "RequisitionReceived"


@dataclass(frozen=True, slots=True)
class Event:
    type: EventType
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Debtor:
    kind: DebtorKind
    name: str
    inn: str
    ogrn: str | None


@dataclass
class Claim:
    claim_id: str
    creditor_id: str
    creditor_name: str
    creditor_kind: CreditorKind
    queue: Queue
    after_third_basis: AfterThirdBasis | None
    filed: Amounts
    secured: bool
    credit_agreement: bool
    grounds: str
    filed_on: date
    filed_in_phase: Phase
    timely: bool
    votes_at_first_meeting: bool
    review_deferred: bool
    review_not_before: date | None
    closing_date: date | None
    status: ClaimStatus = ClaimStatus.FILED
    included: Amounts | None = None
    paid: Amounts = field(default_factory=lambda: Amounts(ZERO))
    ruling_date: date | None = None
    excluded_on: date | None = None
    reason: str | None = None
    objections: list[dict[str, str]] = field(default_factory=list)

    @property
    def outstanding(self) -> Amounts:
        if self.included is None:
            return self.filed
        return self.included.minus(self.paid)

    def in_registry_on(self, day: date) -> bool:
        if self.ruling_date is None or self.ruling_date > day or self.included is None:
            return False
        if self.status is ClaimStatus.EXCLUDED:
            return self.excluded_on is not None and self.excluded_on > day
        return self.status in (ClaimStatus.INCLUDED, ClaimStatus.SATISFIED)


@dataclass
class AgendaItem:
    item_id: str
    question: Question
    title: str


@dataclass
class Meeting:
    meeting_id: str
    meeting_on: date
    phase: Phase
    agenda: list[AgendaItem]
    first: bool
    repeated_of: str | None
    collateral_sale_refused: bool
    status: MeetingStatus = MeetingStatus.SCHEDULED
    notices: list[dict[str, Any]] = field(default_factory=list)
    present: set[str] = field(default_factory=set)
    ballots: dict[str, dict[str, Vote]] = field(default_factory=dict)
    quorum: dict[str, Any] | None = None
    results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def properly_notified(self) -> bool:
        return properly_notified([(NoticeMethod(n["method"]), n["timely"]) for n in self.notices])


@dataclass
class Requisition:
    requisition_id: str
    creditor_ids: list[str]
    received_on: date
    by_committee: bool
    agenda: list[str]
    valid: bool
    share_percent: str
    hold_by: date | None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _amounts_dict(amounts: Amounts) -> dict[str, str]:
    return {"principal": str(amounts.principal), "interest": str(amounts.interest), "sanctions": str(amounts.sanctions)}


def _amounts(data: dict[str, str]) -> Amounts:
    return Amounts(Decimal(data["principal"]), Decimal(data["interest"]), Decimal(data["sanctions"]))


def make_amounts(principal: Decimal, interest: Decimal = ZERO, sanctions: Decimal = ZERO) -> Amounts:
    amounts = Amounts(money(principal), money(interest), money(sanctions))
    if amounts.total <= 0:
        raise ValidationFailed("размер требования должен быть больше нуля")
    return amounts


class InsolvencyCase:
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self.version = 0
        self.organization_id = ""
        self.case_number = ""
        self.court = ""
        self.debtor: Debtor | None = None
        self.petition_received_on: date | None = None
        self.phase = initial_phase()
        self.phase_since: date | None = None
        self.phase_history: list[dict[str, Any]] = []
        self.observation_hearing_on: date | None = None
        self.publications: dict[PublicationKind, date] = {}
        self.manager: dict[str, Any] | None = None
        self.claims: dict[str, Claim] = {}
        self.meetings: dict[str, Meeting] = {}
        self.requisitions: dict[str, Requisition] = {}
        self.pending: list[Event] = []

    @classmethod
    def rehydrate(cls, case_id: str, events: Iterable[Event]) -> InsolvencyCase:
        case = cls(case_id)
        for event in events:
            case._apply(event)
        return case

    @property
    def opened(self) -> bool:
        return self.debtor is not None

    @property
    def debtor_kind(self) -> DebtorKind:
        if self.debtor is None:
            raise NotFound("дело не открыто")
        return self.debtor.kind

    def _record(self, event_type: EventType, data: dict[str, Any]) -> None:
        event = Event(event_type, data)
        self._apply(event)
        self.pending.append(event)

    def _ensure_active(self) -> None:
        if not self.opened:
            raise NotFound("дело не открыто")
        if self.phase in TERMINAL_PHASES:
            raise TransitionNotAllowed(f"производство в состоянии {self.phase.value}, изменения невозможны")

    def open(
        self,
        organization_id: str,
        case_number: str,
        court: str,
        debtor: Debtor,
        petition_received_on: date,
    ) -> None:
        if self.opened:
            raise TransitionNotAllowed("дело уже открыто")
        require_case_number(case_number)
        if debtor.kind is DebtorKind.LEGAL_ENTITY:
            require_inn(debtor.inn, length=10)
            if debtor.ogrn is None:
                raise ValidationFailed("для юридического лица требуется ОГРН")
            require_ogrn(debtor.ogrn, length=13)
        else:
            require_inn(debtor.inn, length=12)
            if debtor.ogrn is not None:
                require_ogrn(debtor.ogrn, length=15)
        self._record(
            EventType.CASE_OPENED,
            {
                "organization_id": organization_id,
                "case_number": case_number,
                "court": court,
                "debtor": {"kind": debtor.kind.value, "name": debtor.name, "inn": debtor.inn, "ogrn": debtor.ogrn},
                "petition_received_on": petition_received_on.isoformat(),
            },
        )

    def change_phase(self, target: Phase, court_act_date: date, hearing_on: date | None = None) -> None:
        self._ensure_active()
        transition = find_transition(self.debtor_kind, self.phase, target)
        if transition is None:
            raise TransitionNotAllowed(
                f"переход {self.phase.value} → {target.value} не предусмотрен для должника {self.debtor_kind.value}",
                basis="127-FZ:27" if self.debtor_kind is DebtorKind.LEGAL_ENTITY else "127-FZ:213.2",
            )
        if self.phase_since and court_act_date < self.phase_since:
            raise ValidationFailed("дата судебного акта раньше начала текущей процедуры")
        if hearing_on is not None and hearing_on <= court_act_date:
            raise ValidationFailed("дата судебного заседания должна быть позже даты судебного акта")
        self._record(
            EventType.PHASE_CHANGED,
            {
                "from": self.phase.value,
                "to": target.value,
                "court_act_date": court_act_date.isoformat(),
                "hearing_on": _iso(hearing_on),
                "basis": transition.basis,
            },
        )

    def record_publication(self, kind: PublicationKind, published_on: date) -> None:
        self._ensure_active()
        expected = PUBLICATION_FOR_PHASE.get(self.phase)
        if expected is not kind:
            raise ValidationFailed(f"публикация {kind.value} не соответствует процедуре {self.phase.value}")
        if self.phase_since and published_on < self.phase_since:
            raise ValidationFailed("дата публикации раньше введения процедуры")
        if kind in self.publications:
            raise ValidationFailed("публикация о введении процедуры уже учтена")
        self._record(EventType.PUBLICATION_RECORDED, {"kind": kind.value, "published_on": published_on.isoformat()})

    def approve_manager(self, full_name: str, sro: str, approved_on: date) -> None:
        self._ensure_active()
        if self.phase is Phase.PETITION_ACCEPTED:
            raise TransitionNotAllowed("управляющий утверждается при введении процедуры")
        self._record(
            EventType.MANAGER_APPROVED,
            {
                "full_name": full_name,
                "sro": sro,
                "approved_on": approved_on.isoformat(),
                "phase": self.phase.value,
            },
        )

    def file_claim(
        self,
        claim_id: str,
        creditor_id: str,
        creditor_name: str,
        creditor_kind: CreditorKind,
        amounts: Amounts,
        filed_on: date,
        grounds: str,
        secured: bool = False,
        credit_agreement: bool = False,
        after_third: AfterThirdBasis | None = None,
        term_restored: bool = False,
    ) -> None:
        self._ensure_active()
        if self.phase not in CLAIM_PHASES:
            raise TransitionNotAllowed(f"в процедуре {self.phase.value} требования не предъявляются")
        if claim_id in self.claims:
            raise ValidationFailed("требование с таким идентификатором уже заявлено")
        if self.phase_since and filed_on < self.phase_since:
            raise ValidationFailed("дата предъявления раньше введения процедуры")
        if secured and creditor_kind not in (CreditorKind.COMPETITIVE, CreditorKind.AUTHORIZED_BODY):
            raise ValidationFailed("залоговым может быть только требование конкурсного кредитора")
        if credit_agreement and not secured:
            raise ValidationFailed("признак кредитного договора имеет значение только для залоговых требований")
        publication = PUBLICATION_FOR_PHASE[self.phase]
        assessment = assess_filing(
            self.debtor_kind, self.phase, creditor_kind, filed_on, self.publications.get(publication), term_restored
        )
        if assessment.after_registry and after_third is None:
            after_third = AfterThirdBasis.LATE_FILING
        queue = assign_queue(self.debtor_kind, creditor_kind, after_third)
        self._record(
            EventType.CLAIM_FILED,
            {
                "claim_id": claim_id,
                "creditor_id": creditor_id,
                "creditor_name": creditor_name,
                "creditor_kind": creditor_kind.value,
                "queue": queue.queue.value,
                "after_third_basis": queue.after_third_basis.value if queue.after_third_basis else None,
                "amounts": _amounts_dict(amounts),
                "secured": secured,
                "credit_agreement": credit_agreement,
                "grounds": grounds,
                "filed_on": filed_on.isoformat(),
                "phase": self.phase.value,
                "timely": assessment.timely,
                "votes_at_first_meeting": assessment.votes_at_first_meeting,
                "review_deferred": assessment.review_deferred,
                "review_not_before": _iso(assessment.review_term.due if assessment.review_term else None),
                "closing_date": _iso(assessment.closing_term.due if assessment.closing_term else None),
                "basis": [*assessment.basis, *queue.basis],
            },
        )

    def _claim(self, claim_id: str) -> Claim:
        claim = self.claims.get(claim_id)
        if claim is None:
            raise NotFound(f"требование {claim_id} не найдено")
        return claim

    def object_to_claim(self, claim_id: str, objector: str, reason: str, filed_on: date) -> None:
        self._ensure_active()
        claim = self._claim(claim_id)
        if claim.status is not ClaimStatus.FILED:
            raise TransitionNotAllowed("возражения заявляются до рассмотрения требования судом")
        if claim.review_not_before and filed_on > claim.review_not_before:
            raise ValidationFailed(
                "срок для возражений истек",
                basis="127-FZ:71.3"
                if claim.filed_in_phase in (Phase.OBSERVATION, Phase.RESTRUCTURING)
                else "127-FZ:100.3.1",
            )
        self._record(
            EventType.CLAIM_OBJECTED,
            {
                "claim_id": claim_id,
                "objector": objector,
                "reason": reason,
                "filed_on": filed_on.isoformat(),
            },
        )

    def rule_on_claim(
        self,
        claim_id: str,
        included: bool,
        ruling_date: date,
        amounts: Amounts | None = None,
        queue: Queue | None = None,
        reason: str | None = None,
    ) -> None:
        self._ensure_active()
        claim = self._claim(claim_id)
        if claim.status is not ClaimStatus.FILED:
            raise TransitionNotAllowed("требование уже рассмотрено")
        if ruling_date < claim.filed_on:
            raise ValidationFailed("дата определения раньше даты предъявления требования")
        if claim.review_deferred and self.phase in (Phase.OBSERVATION, Phase.RESTRUCTURING):
            raise TransitionNotAllowed(
                "требование, предъявленное с пропуском срока, рассматривается после введения следующей процедуры",
                basis="127-FZ:71.7",
            )
        if claim.review_not_before and ruling_date < claim.review_not_before:
            raise ValidationFailed(
                f"требование рассматривается не ранее {claim.review_not_before.isoformat()}",
                basis="127-FZ:71.2" if claim.filed_in_phase is Phase.OBSERVATION else "127-FZ:100.3",
            )
        final = amounts or claim.filed
        if included and not final.fits_into(claim.filed):
            raise ValidationFailed("включаемый размер не может превышать заявленный")
        if included and final.total <= 0:
            raise ValidationFailed("включаемый размер должен быть больше нуля")
        self._record(
            EventType.CLAIM_RULED,
            {
                "claim_id": claim_id,
                "included": included,
                "ruling_date": ruling_date.isoformat(),
                "amounts": _amounts_dict(final) if included else None,
                "queue": (queue or claim.queue).value,
                "reason": reason,
                "basis": ["127-FZ:16.6"],
            },
        )

    def exclude_claim(self, claim_id: str, ruling_date: date, reason: str) -> None:
        self._ensure_active()
        claim = self._claim(claim_id)
        if claim.status is not ClaimStatus.INCLUDED:
            raise TransitionNotAllowed("исключить можно только включенное требование")
        if claim.ruling_date and ruling_date < claim.ruling_date:
            raise ValidationFailed("дата исключения раньше даты включения")
        self._record(
            EventType.CLAIM_EXCLUDED,
            {
                "claim_id": claim_id,
                "ruling_date": ruling_date.isoformat(),
                "reason": reason,
                "basis": ["127-FZ:16.6"],
            },
        )

    def record_payment(self, claim_id: str, amounts: Amounts, paid_on: date) -> None:
        self._ensure_active()
        claim = self._claim(claim_id)
        if claim.status is not ClaimStatus.INCLUDED:
            raise TransitionNotAllowed("погашение отражается только по включенному требованию")
        if not amounts.fits_into(claim.outstanding):
            raise ValidationFailed("сумма погашения превышает непогашенный остаток")
        if claim.queue is Queue.THIRD and amounts.sanctions > 0 and claim.outstanding.base > amounts.base:
            raise ValidationFailed(
                "санкции третьей очереди погашаются после основного долга и процентов", basis="127-FZ:137.3"
            )
        self._record(
            EventType.CLAIM_PAYMENT_RECORDED,
            {
                "claim_id": claim_id,
                "amounts": _amounts_dict(amounts),
                "paid_on": paid_on.isoformat(),
            },
        )

    def schedule_meeting(
        self,
        meeting_id: str,
        meeting_on: date,
        agenda: list[AgendaItem],
        first: bool = False,
        repeated_of: str | None = None,
        collateral_sale_refused: bool = False,
    ) -> None:
        self._ensure_active()
        if self.phase not in MEETING_PHASES:
            raise TransitionNotAllowed(f"в процедуре {self.phase.value} собрание кредиторов не проводится")
        if meeting_id in self.meetings:
            raise ValidationFailed("собрание с таким идентификатором уже создано")
        if not agenda:
            raise ValidationFailed("повестка собрания не может быть пустой")
        if len({item.item_id for item in agenda}) != len(agenda):
            raise ValidationFailed("идентификаторы вопросов повестки должны быть уникальными")
        if first and self.phase not in (Phase.OBSERVATION, Phase.RESTRUCTURING):
            raise ValidationFailed("первое собрание проводится в наблюдении или реструктуризации долгов")
        if first and any(m.first and m.status is MeetingStatus.HELD for m in self.meetings.values()):
            raise ValidationFailed("первое собрание кредиторов уже проведено")
        if repeated_of is not None:
            previous = self.meetings.get(repeated_of)
            if previous is None or previous.status is not MeetingStatus.FAILED:
                raise ValidationFailed("повторное собрание назначается после несостоявшегося")
        self._record(
            EventType.MEETING_SCHEDULED,
            {
                "meeting_id": meeting_id,
                "meeting_on": meeting_on.isoformat(),
                "phase": self.phase.value,
                "agenda": [{"item_id": i.item_id, "question": i.question.value, "title": i.title} for i in agenda],
                "first": first,
                "repeated_of": repeated_of,
                "collateral_sale_refused": collateral_sale_refused,
            },
        )

    def _meeting(self, meeting_id: str, *, scheduled: bool = True) -> Meeting:
        meeting = self.meetings.get(meeting_id)
        if meeting is None:
            raise NotFound(f"собрание {meeting_id} не найдено")
        if scheduled and meeting.status is not MeetingStatus.SCHEDULED:
            raise TransitionNotAllowed(f"собрание в статусе {meeting.status.value}")
        return meeting

    def record_notice(self, meeting_id: str, method: NoticeMethod, sent_on: date, recipients: int) -> None:
        self._ensure_active()
        meeting = self._meeting(meeting_id)
        if recipients < 1:
            raise ValidationFailed("число адресатов должно быть положительным")
        timely = notice_is_timely(method, sent_on, meeting.meeting_on, self.debtor_kind)
        self._record(
            EventType.MEETING_NOTICE_RECORDED,
            {
                "meeting_id": meeting_id,
                "method": method.value,
                "sent_on": sent_on.isoformat(),
                "recipients": recipients,
                "timely": timely,
            },
        )

    def _voting_context(self, meeting: Meeting) -> VotingContext:
        return VotingContext(self.debtor_kind, meeting.phase, meeting.first, meeting.collateral_sale_refused)

    def voting_claims(self, on: date) -> list[VotingClaim]:
        return [
            VotingClaim(
                c.claim_id,
                c.creditor_id,
                c.creditor_kind,
                c.queue,
                ClaimStatus.INCLUDED,
                c.outstanding.base,
                c.secured,
                c.votes_at_first_meeting,
            )
            for c in self.claims.values()
            if c.in_registry_on(on)
        ]

    def meeting_weights(self, meeting: Meeting, question: Question = Question.ORDINARY) -> dict[str, Decimal]:
        return voting_weights(self.voting_claims(meeting.meeting_on), self._voting_context(meeting), question)

    def register_participant(self, meeting_id: str, creditor_id: str) -> None:
        self._ensure_active()
        meeting = self._meeting(meeting_id)
        if creditor_id in meeting.present:
            raise ValidationFailed("участник уже зарегистрирован")
        registry_creditors = {c.creditor_id for c in self.claims.values() if c.in_registry_on(meeting.meeting_on)}
        if creditor_id not in registry_creditors:
            raise ValidationFailed("кредитор не включен в реестр на дату собрания", basis="127-FZ:12.1")
        self._record(EventType.MEETING_PARTICIPANT_REGISTERED, {"meeting_id": meeting_id, "creditor_id": creditor_id})

    def cast_ballot(self, meeting_id: str, item_id: str, creditor_id: str, vote: Vote) -> None:
        self._ensure_active()
        meeting = self._meeting(meeting_id)
        item = next((i for i in meeting.agenda if i.item_id == item_id), None)
        if item is None:
            raise NotFound(f"вопрос {item_id} отсутствует в повестке")
        if creditor_id not in meeting.present:
            raise ValidationFailed("голосует только зарегистрированный участник собрания")
        if creditor_id in meeting.ballots.get(item_id, {}):
            raise ValidationFailed("бюллетень по этому вопросу уже учтен")
        if self.meeting_weights(meeting, item.question).get(creditor_id, ZERO) <= 0:
            raise ValidationFailed(
                "у кредитора нет права голоса по этому вопросу",
                basis="127-FZ:12.1.secured" if self.debtor_kind is DebtorKind.LEGAL_ENTITY else "127-FZ:12.1",
            )
        self._record(
            EventType.BALLOT_CAST,
            {
                "meeting_id": meeting_id,
                "item_id": item_id,
                "creditor_id": creditor_id,
                "vote": vote.value,
            },
        )

    def evaluate_meeting(self, meeting: Meeting) -> tuple[Quorum, list[ItemResult]]:
        context = self._voting_context(meeting)
        base_weights = self.meeting_weights(meeting)
        repeated = meeting.repeated_of is not None
        quorum_result = quorum(base_weights, meeting.present, repeated, meeting.properly_notified)
        results = (
            [
                tally(
                    item.item_id,
                    item.question,
                    self.meeting_weights(meeting, item.question),
                    meeting.present,
                    meeting.ballots.get(item.item_id, {}),
                    context,
                )
                for item in meeting.agenda
            ]
            if quorum_result.reached
            else []
        )
        return quorum_result, results

    def conclude_meeting(self, meeting_id: str) -> None:
        self._ensure_active()
        meeting = self._meeting(meeting_id)
        quorum_result, results = self.evaluate_meeting(meeting)
        self._record(
            EventType.MEETING_CONCLUDED,
            {
                "meeting_id": meeting_id,
                "status": (MeetingStatus.HELD if quorum_result.reached else MeetingStatus.FAILED).value,
                "quorum": {
                    "total_votes": str(quorum_result.total_votes),
                    "present_votes": str(quorum_result.present_votes),
                    "threshold_percent": quorum_result.threshold_percent,
                    "reached": quorum_result.reached,
                    "properly_notified": meeting.properly_notified,
                    "basis": list(quorum_result.basis),
                },
                "results": [
                    {
                        "item_id": r.item_id,
                        "question": r.question.value,
                        "rule": r.rule,
                        "base_votes": str(r.base_votes),
                        "votes_for": str(r.votes_for),
                        "votes_against": str(r.votes_against),
                        "votes_abstain": str(r.votes_abstain),
                        "adopted": r.adopted,
                        "basis": list(r.basis),
                    }
                    for r in results
                ],
            },
        )

    def cancel_meeting(self, meeting_id: str, reason: str) -> None:
        self._ensure_active()
        self._meeting(meeting_id)
        self._record(EventType.MEETING_CANCELLED, {"meeting_id": meeting_id, "reason": reason})

    def receive_requisition(
        self,
        requisition_id: str,
        creditor_ids: list[str],
        received_on: date,
        agenda: list[str],
        by_committee: bool = False,
    ) -> None:
        self._ensure_active()
        if self.phase not in MEETING_PHASES:
            raise TransitionNotAllowed(f"в процедуре {self.phase.value} собрание кредиторов не проводится")
        if requisition_id in self.requisitions:
            raise ValidationFailed("требование о созыве уже учтено")
        if not agenda:
            raise ValidationFailed(
                "в требовании о созыве должны быть сформулированы вопросы повестки", basis="127-FZ:14.1"
            )
        amounts: dict[str, Decimal] = {}
        for claim in self.claims.values():
            if claim.in_registry_on(received_on) and claim.creditor_kind in (
                CreditorKind.COMPETITIVE,
                CreditorKind.AUTHORIZED_BODY,
            ):
                amounts[claim.creditor_id] = amounts.get(claim.creditor_id, ZERO) + claim.outstanding.total
        assessment = assess_requisition(set(creditor_ids), amounts, received_on, by_committee)
        self._record(
            EventType.REQUISITION_RECEIVED,
            {
                "requisition_id": requisition_id,
                "creditor_ids": creditor_ids,
                "received_on": received_on.isoformat(),
                "by_committee": by_committee,
                "agenda": agenda,
                "valid": assessment.valid,
                "share_percent": str(assessment.share_percent),
                "hold_by": _iso(assessment.hold_by.due if assessment.hold_by else None),
            },
        )

    def _apply(self, event: Event) -> None:
        handler = getattr(self, f"_on_{event.type.value}")
        handler(event.data)
        self.version += 1

    def _on_CaseOpened(self, d: dict[str, Any]) -> None:
        self.organization_id = d["organization_id"]
        self.case_number = d["case_number"]
        self.court = d["court"]
        debtor = d["debtor"]
        self.debtor = Debtor(DebtorKind(debtor["kind"]), debtor["name"], debtor["inn"], debtor["ogrn"])
        self.petition_received_on = date.fromisoformat(d["petition_received_on"])
        self.phase_since = self.petition_received_on
        self.phase_history.append({"phase": self.phase.value, "since": d["petition_received_on"]})

    def _on_PhaseChanged(self, d: dict[str, Any]) -> None:
        self.phase = Phase(d["to"])
        self.phase_since = date.fromisoformat(d["court_act_date"])
        if self.phase is Phase.OBSERVATION:
            self.observation_hearing_on = _date(d.get("hearing_on"))
        self.phase_history.append({"phase": self.phase.value, "since": d["court_act_date"], "basis": d["basis"]})

    def _on_PublicationRecorded(self, d: dict[str, Any]) -> None:
        self.publications[PublicationKind(d["kind"])] = date.fromisoformat(d["published_on"])

    def _on_ManagerApproved(self, d: dict[str, Any]) -> None:
        self.manager = dict(d)

    def _on_ClaimFiled(self, d: dict[str, Any]) -> None:
        self.claims[d["claim_id"]] = Claim(
            claim_id=d["claim_id"],
            creditor_id=d["creditor_id"],
            creditor_name=d["creditor_name"],
            creditor_kind=CreditorKind(d["creditor_kind"]),
            queue=Queue(d["queue"]),
            after_third_basis=AfterThirdBasis(d["after_third_basis"]) if d["after_third_basis"] else None,
            filed=_amounts(d["amounts"]),
            secured=d["secured"],
            credit_agreement=d["credit_agreement"],
            grounds=d["grounds"],
            filed_on=date.fromisoformat(d["filed_on"]),
            filed_in_phase=Phase(d["phase"]),
            timely=d["timely"],
            votes_at_first_meeting=d["votes_at_first_meeting"],
            review_deferred=d["review_deferred"],
            review_not_before=_date(d["review_not_before"]),
            closing_date=_date(d["closing_date"]),
        )

    def _on_ClaimObjected(self, d: dict[str, Any]) -> None:
        self.claims[d["claim_id"]].objections.append(
            {"objector": d["objector"], "reason": d["reason"], "filed_on": d["filed_on"]}
        )

    def _on_ClaimRuled(self, d: dict[str, Any]) -> None:
        claim = self.claims[d["claim_id"]]
        claim.ruling_date = date.fromisoformat(d["ruling_date"])
        claim.queue = Queue(d["queue"])
        claim.reason = d["reason"]
        if d["included"]:
            claim.status = ClaimStatus.INCLUDED
            claim.included = _amounts(d["amounts"])
        else:
            claim.status = ClaimStatus.REJECTED

    def _on_ClaimExcluded(self, d: dict[str, Any]) -> None:
        claim = self.claims[d["claim_id"]]
        claim.status = ClaimStatus.EXCLUDED
        claim.excluded_on = date.fromisoformat(d["ruling_date"])
        claim.reason = d["reason"]

    def _on_ClaimPaymentRecorded(self, d: dict[str, Any]) -> None:
        claim = self.claims[d["claim_id"]]
        paid = _amounts(d["amounts"])
        claim.paid = Amounts(
            claim.paid.principal + paid.principal,
            claim.paid.interest + paid.interest,
            claim.paid.sanctions + paid.sanctions,
        )
        if claim.outstanding.total == 0:
            claim.status = ClaimStatus.SATISFIED

    def _on_MeetingScheduled(self, d: dict[str, Any]) -> None:
        self.meetings[d["meeting_id"]] = Meeting(
            meeting_id=d["meeting_id"],
            meeting_on=date.fromisoformat(d["meeting_on"]),
            phase=Phase(d["phase"]),
            agenda=[AgendaItem(i["item_id"], Question(i["question"]), i["title"]) for i in d["agenda"]],
            first=d["first"],
            repeated_of=d["repeated_of"],
            collateral_sale_refused=d["collateral_sale_refused"],
        )

    def _on_MeetingNoticeRecorded(self, d: dict[str, Any]) -> None:
        self.meetings[d["meeting_id"]].notices.append(
            {"method": d["method"], "sent_on": d["sent_on"], "recipients": d["recipients"], "timely": d["timely"]}
        )

    def _on_MeetingParticipantRegistered(self, d: dict[str, Any]) -> None:
        self.meetings[d["meeting_id"]].present.add(d["creditor_id"])

    def _on_BallotCast(self, d: dict[str, Any]) -> None:
        self.meetings[d["meeting_id"]].ballots.setdefault(d["item_id"], {})[d["creditor_id"]] = Vote(d["vote"])

    def _on_MeetingConcluded(self, d: dict[str, Any]) -> None:
        meeting = self.meetings[d["meeting_id"]]
        meeting.status = MeetingStatus(d["status"])
        meeting.quorum = d["quorum"]
        meeting.results = d["results"]

    def _on_MeetingCancelled(self, d: dict[str, Any]) -> None:
        self.meetings[d["meeting_id"]].status = MeetingStatus.CANCELLED

    def _on_RequisitionReceived(self, d: dict[str, Any]) -> None:
        self.requisitions[d["requisition_id"]] = Requisition(
            requisition_id=d["requisition_id"],
            creditor_ids=d["creditor_ids"],
            received_on=date.fromisoformat(d["received_on"]),
            by_committee=d["by_committee"],
            agenda=d["agenda"],
            valid=d["valid"],
            share_percent=d["share_percent"],
            hold_by=_date(d["hold_by"]),
        )
