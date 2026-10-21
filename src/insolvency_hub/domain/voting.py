from dataclasses import dataclass, field
from decimal import Decimal

from insolvency_hub.domain.claims import COMPETITIVE_KINDS
from insolvency_hub.domain.enums import ClaimStatus, CreditorKind, DebtorKind, Phase, Question, Queue, Vote
from insolvency_hub.domain.money import ZERO

TOTAL_MAJORITY_QUESTIONS = frozenset(
    {
        Question.CREDITORS_COMMITTEE,
        Question.COMMITTEE_TERMINATION,
        Question.FINANCIAL_RECOVERY,
        Question.REPAYMENT_SCHEDULE,
        Question.EXTERNAL_MANAGEMENT,
        Question.EXTERNAL_MANAGEMENT_PLAN,
        Question.BANKRUPTCY_PETITION,
        Question.MANAGER_SELECTION,
        Question.MANAGER_REMOVAL,
        Question.ADDITIONAL_AGENDA,
        Question.SETTLEMENT,
    }
)

SECURED_ALWAYS = frozenset({Question.MANAGER_SELECTION, Question.MANAGER_REMOVAL})
SECURED_IN_BANKRUPTCY_PROCEEDINGS = SECURED_ALWAYS | {Question.TRANSITION_TO_EXTERNAL_MANAGEMENT}


@dataclass(frozen=True, slots=True)
class VotingClaim:
    claim_id: str
    creditor_id: str
    creditor_kind: CreditorKind
    queue: Queue
    status: ClaimStatus
    base: Decimal
    secured: bool
    timely_for_first_meeting: bool


@dataclass(frozen=True, slots=True)
class VotingContext:
    debtor: DebtorKind
    phase: Phase
    first_meeting: bool = False
    collateral_sale_refused: bool = False


def secured_may_vote(context: VotingContext, question: Question) -> bool:
    if context.debtor is DebtorKind.CITIZEN or context.phase is Phase.OBSERVATION:
        return True
    if question in SECURED_ALWAYS:
        return True
    if context.phase in (Phase.FINANCIAL_RECOVERY, Phase.EXTERNAL_MANAGEMENT):
        return context.collateral_sale_refused
    if context.phase is Phase.BANKRUPTCY_PROCEEDINGS:
        return question in SECURED_IN_BANKRUPTCY_PROCEEDINGS
    return False


def voting_weights(
    claims: list[VotingClaim], context: VotingContext, question: Question = Question.ORDINARY
) -> dict[str, Decimal]:
    weights: dict[str, Decimal] = {}
    secured_allowed = secured_may_vote(context, question)
    for claim in claims:
        if claim.status is not ClaimStatus.INCLUDED or claim.queue is not Queue.THIRD:
            continue
        if claim.creditor_kind not in COMPETITIVE_KINDS or claim.base <= 0:
            continue
        if context.first_meeting and not claim.timely_for_first_meeting:
            continue
        if claim.secured and not secured_allowed:
            continue
        weights[claim.creditor_id] = weights.get(claim.creditor_id, ZERO) + claim.base
    return weights


def voting_basis(context: VotingContext, question: Question) -> tuple[str, ...]:
    basis: list[str] = ["127-FZ:12.1", "127-FZ:12.3", "127-FZ:2"]
    if context.first_meeting:
        basis.append("127-FZ:72.2")
    basis.append("127-FZ:213.10.4" if context.debtor is DebtorKind.CITIZEN else "127-FZ:12.1.secured")
    basis.append("127-FZ:15.2" if question in TOTAL_MAJORITY_QUESTIONS else "127-FZ:15.1")
    return tuple(basis)


@dataclass(frozen=True, slots=True)
class Quorum:
    total_votes: Decimal
    present_votes: Decimal
    threshold_percent: int
    reached: bool
    basis: tuple[str, ...] = ("127-FZ:12.4",)


def quorum(weights: dict[str, Decimal], present: set[str], repeated: bool, properly_notified: bool) -> Quorum:
    total = sum(weights.values(), ZERO)
    present_votes = sum((w for c, w in weights.items() if c in present), ZERO)
    if repeated and properly_notified:
        return Quorum(total, present_votes, 30, total > 0 and present_votes * 10 > total * 3)
    return Quorum(total, present_votes, 50, total > 0 and present_votes * 2 > total)


@dataclass(frozen=True, slots=True)
class ItemResult:
    item_id: str
    question: Question
    rule: str
    base_votes: Decimal
    votes_for: Decimal
    votes_against: Decimal
    votes_abstain: Decimal
    adopted: bool
    basis: tuple[str, ...] = field(default=())


def tally(
    item_id: str,
    question: Question,
    weights: dict[str, Decimal],
    present: set[str],
    ballots: dict[str, Vote],
    context: VotingContext,
) -> ItemResult:
    present_weights = {c: w for c, w in weights.items() if c in present}
    counted = {c: v for c, v in ballots.items() if c in present_weights}
    by_vote = {vote: sum((present_weights[c] for c, v in counted.items() if v is vote), ZERO) for vote in Vote}
    if question in TOTAL_MAJORITY_QUESTIONS:
        rule, base = "majority_of_total", sum(weights.values(), ZERO)
    else:
        rule, base = "majority_of_present", sum(present_weights.values(), ZERO)
    adopted = base > 0 and by_vote[Vote.FOR] * 2 > base
    return ItemResult(
        item_id,
        question,
        rule,
        base,
        by_vote[Vote.FOR],
        by_vote[Vote.AGAINST],
        by_vote[Vote.ABSTAIN],
        adopted,
        voting_basis(context, question),
    )
