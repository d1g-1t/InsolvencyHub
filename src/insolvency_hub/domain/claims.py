from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from insolvency_hub.domain.enums import AfterThirdBasis, CreditorKind, DebtorKind, Phase, Queue
from insolvency_hub.domain.errors import ValidationFailed
from insolvency_hub.domain.money import ZERO
from insolvency_hub.domain.terms import Term, Unit, term_after

COMPETITIVE_KINDS = frozenset({CreditorKind.COMPETITIVE, CreditorKind.AUTHORIZED_BODY})


@dataclass(frozen=True, slots=True)
class Amounts:
    principal: Decimal
    interest: Decimal = ZERO
    sanctions: Decimal = ZERO

    @property
    def base(self) -> Decimal:
        return self.principal + self.interest

    @property
    def total(self) -> Decimal:
        return self.principal + self.interest + self.sanctions

    def fits_into(self, other: Amounts) -> bool:
        return (
            self.principal <= other.principal and self.interest <= other.interest and self.sanctions <= other.sanctions
        )

    def minus(self, other: Amounts) -> Amounts:
        return Amounts(
            self.principal - other.principal,
            self.interest - other.interest,
            self.sanctions - other.sanctions,
        )


@dataclass(frozen=True, slots=True)
class QueueAssignment:
    queue: Queue
    after_third_basis: AfterThirdBasis | None
    basis: tuple[str, ...]


def assign_queue(
    debtor: DebtorKind, creditor: CreditorKind, after_third: AfterThirdBasis | None = None
) -> QueueAssignment:
    if after_third is AfterThirdBasis.INVALIDATED_TRANSACTION:
        return QueueAssignment(Queue.AFTER_THIRD, after_third, ("127-FZ:134.4",))
    if after_third is AfterThirdBasis.EXCESS_SEVERANCE:
        return QueueAssignment(Queue.AFTER_THIRD, after_third, ("127-FZ:134.2.1",))
    if after_third is AfterThirdBasis.LATE_FILING:
        return QueueAssignment(Queue.AFTER_THIRD, after_third, ("127-FZ:142.4",))
    citizen = debtor is DebtorKind.CITIZEN
    rules = ("127-FZ:213.27.3",) if citizen else ("127-FZ:134.4",)
    match creditor:
        case CreditorKind.INJURY:
            return QueueAssignment(Queue.FIRST, None, rules)
        case CreditorKind.ALIMONY:
            if not citizen:
                raise ValidationFailed(
                    "требования о взыскании алиментов возможны только в деле о банкротстве гражданина",
                    basis="127-FZ:213.27.3",
                )
            return QueueAssignment(Queue.FIRST, None, rules)
        case CreditorKind.EMPLOYEE:
            return QueueAssignment(Queue.SECOND, None, rules)
        case CreditorKind.AUTHOR:
            return QueueAssignment(Queue.THIRD if citizen else Queue.SECOND, None, rules)
        case _:
            return QueueAssignment(Queue.THIRD, None, rules)


@dataclass(frozen=True, slots=True)
class FilingAssessment:
    timely: bool
    closing_term: Term | None
    review_term: Term | None
    votes_at_first_meeting: bool
    review_deferred: bool
    after_registry: bool
    basis: tuple[str, ...]


def _review_after_filing(filed_on: date) -> Term:
    return term_after(
        "claim_review",
        "рассмотрение требования судом не ранее",
        filed_on,
        30,
        Unit.CALENDAR_DAYS,
        ("127-FZ:100.3", "127-FZ:100.3.1"),
    )


def assess_filing(
    debtor: DebtorKind,
    phase: Phase,
    creditor: CreditorKind,
    filed_on: date,
    published_on: date | None,
    term_restored: bool = False,
) -> FilingAssessment:
    if phase is Phase.OBSERVATION:
        if published_on is None:
            return FilingAssessment(True, None, None, True, False, False, ("127-FZ:71.1",))
        closing = term_after(
            "claims_first_meeting",
            "предъявление требований для участия в первом собрании",
            published_on,
            30,
            Unit.CALENDAR_DAYS,
            ("127-FZ:71.1", "GK:191", "GK:193"),
        )
        timely = filed_on <= closing.due or term_restored
        review = term_after(
            "claim_review",
            "рассмотрение требований судом не ранее",
            closing.due,
            30,
            Unit.CALENDAR_DAYS,
            ("127-FZ:71.2", "127-FZ:71.3"),
        )
        if timely:
            return FilingAssessment(True, closing, review, True, False, False, ("127-FZ:71.1", "127-FZ:71.2"))
        return FilingAssessment(False, closing, None, False, True, False, ("127-FZ:71.1", "127-FZ:71.7"))
    if phase in (Phase.FINANCIAL_RECOVERY, Phase.EXTERNAL_MANAGEMENT):
        return FilingAssessment(True, None, _review_after_filing(filed_on), True, False, False, ("127-FZ:100.1",))
    if phase is Phase.RESTRUCTURING:
        if published_on is None:
            return FilingAssessment(True, None, None, True, False, False, ("127-FZ:213.8.2",))
        closing = term_after(
            "claims_restructuring",
            "предъявление требований к гражданину",
            published_on,
            2,
            Unit.MONTHS,
            ("127-FZ:213.8.2", "GK:192.3", "GK:193"),
        )
        timely = filed_on <= closing.due or term_restored
        review = term_after(
            "claim_review",
            "рассмотрение требований судом не ранее",
            closing.due,
            30,
            Unit.CALENDAR_DAYS,
            ("127-FZ:213.8.2", "127-FZ:71.2"),
        )
        return FilingAssessment(
            timely, closing, review if timely else None, timely, not timely, False, ("127-FZ:213.8.2",)
        )
    if phase in (Phase.BANKRUPTCY_PROCEEDINGS, Phase.PROPERTY_REALIZATION):
        basis = (
            ("127-FZ:142.1",)
            if phase is Phase.BANKRUPTCY_PROCEEDINGS
            else ("127-FZ:213.24.4", "127-FZ:213.1.1", "127-FZ:142.1")
        )
        review = _review_after_filing(filed_on)
        if published_on is None:
            return FilingAssessment(True, None, review, True, False, False, basis)
        closing = term_after(
            "registry_closing",
            "закрытие реестра требований",
            published_on,
            2,
            Unit.MONTHS,
            (*basis, "GK:192.3", "GK:193"),
        )
        timely = filed_on <= closing.due or term_restored
        after_registry = not timely and creditor in COMPETITIVE_KINDS
        return FilingAssessment(
            timely,
            closing,
            review,
            timely,
            False,
            after_registry,
            (*basis, "127-FZ:142.4") if after_registry else basis,
        )
    raise ValidationFailed(f"в процедуре {phase.value} требования кредиторов не предъявляются")
