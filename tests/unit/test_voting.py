from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from insolvency_hub.domain.enums import ClaimStatus, CreditorKind, DebtorKind, Phase, Question, Queue, Vote
from insolvency_hub.domain.voting import (
    VotingClaim,
    VotingContext,
    quorum,
    secured_may_vote,
    tally,
    voting_basis,
    voting_weights,
)

D = Decimal
LE = DebtorKind.LEGAL_ENTITY


def claim(
    cid: str,
    base: int,
    *,
    secured: bool = False,
    kind: CreditorKind = CreditorKind.COMPETITIVE,
    queue: Queue = Queue.THIRD,
    timely: bool = True,
    status: ClaimStatus = ClaimStatus.INCLUDED,
) -> VotingClaim:
    return VotingClaim(cid, cid, kind, queue, status, D(base), secured, timely)


@pytest.mark.parametrize(
    ("debtor", "phase", "question", "refused", "allowed"),
    [
        (LE, Phase.OBSERVATION, Question.ORDINARY, False, True),
        (LE, Phase.EXTERNAL_MANAGEMENT, Question.ORDINARY, False, False),
        (LE, Phase.EXTERNAL_MANAGEMENT, Question.ORDINARY, True, True),
        (LE, Phase.FINANCIAL_RECOVERY, Question.MANAGER_SELECTION, False, True),
        (LE, Phase.BANKRUPTCY_PROCEEDINGS, Question.ORDINARY, False, False),
        (LE, Phase.BANKRUPTCY_PROCEEDINGS, Question.TRANSITION_TO_EXTERNAL_MANAGEMENT, False, True),
        (LE, Phase.BANKRUPTCY_PROCEEDINGS, Question.MANAGER_REMOVAL, False, True),
        (LE, Phase.SETTLEMENT, Question.ORDINARY, False, False),
        (DebtorKind.CITIZEN, Phase.PROPERTY_REALIZATION, Question.ORDINARY, False, True),
    ],
)
def test_secured_may_vote(debtor: DebtorKind, phase: Phase, question: Question, refused: bool, allowed: bool) -> None:
    assert secured_may_vote(VotingContext(debtor, phase, collateral_sale_refused=refused), question) is allowed


def test_weights_count_only_competitive_third_queue_base() -> None:
    claims = [
        claim("bank", 600, secured=True),
        claim("sup", 300),
        claim("sup", 50),
        claim("fns", 100, kind=CreditorKind.AUTHORIZED_BODY),
        claim("emp", 40, kind=CreditorKind.EMPLOYEE, queue=Queue.SECOND),
        claim("late", 70, queue=Queue.AFTER_THIRD),
        claim("filed", 90, status=ClaimStatus.FILED),
        claim("zero", 0),
        claim("untimely", 80, timely=False),
    ]
    weights = voting_weights(claims, VotingContext(LE, Phase.BANKRUPTCY_PROCEEDINGS))
    assert weights == {"sup": D(350), "fns": D(100), "untimely": D(80)}
    first = voting_weights(claims, VotingContext(LE, Phase.OBSERVATION, first_meeting=True))
    assert first == {"bank": D(600), "sup": D(350), "fns": D(100)}


def test_voting_basis() -> None:
    basis = voting_basis(
        VotingContext(DebtorKind.CITIZEN, Phase.RESTRUCTURING, first_meeting=True), Question.MANAGER_SELECTION
    )
    assert "127-FZ:72.2" in basis
    assert "127-FZ:213.10.4" in basis
    assert "127-FZ:15.2" in basis
    assert voting_basis(VotingContext(LE, Phase.OBSERVATION), Question.ORDINARY)[-1] == "127-FZ:15.1"


@pytest.mark.parametrize(
    ("present", "repeated", "notified", "reached", "threshold"),
    [
        ({"a"}, False, True, False, 50),
        ({"a", "b"}, False, True, True, 50),
        ({"c"}, True, True, True, 30),
        ({"c"}, True, False, False, 50),
        ({"d"}, True, True, False, 30),
    ],
)
def test_quorum(present: set[str], repeated: bool, notified: bool, reached: bool, threshold: int) -> None:
    result = quorum({"a": D(50), "b": D(1), "c": D(31), "d": D(18)}, present, repeated, notified)
    assert result.reached is reached
    assert result.threshold_percent == threshold


def test_quorum_empty_registry() -> None:
    assert not quorum({}, set(), False, True).reached


def test_tally_majority_of_present_vs_total() -> None:
    weights = {"a": D(40), "b": D(35), "c": D(25)}
    present = {"a", "b"}
    ballots = {"a": Vote.FOR, "b": Vote.AGAINST, "c": Vote.FOR}
    context = VotingContext(LE, Phase.OBSERVATION)
    ordinary = tally("i", Question.ORDINARY, weights, present, ballots, context)
    assert ordinary.rule == "majority_of_present"
    assert ordinary.base_votes == D(75)
    assert ordinary.votes_for == D(40)
    assert ordinary.adopted
    total = tally("i", Question.BANKRUPTCY_PETITION, weights, present, ballots, context)
    assert total.rule == "majority_of_total"
    assert total.base_votes == D(100)
    assert not total.adopted


def test_tally_tie_is_not_adopted() -> None:
    result = tally(
        "i",
        Question.ORDINARY,
        {"a": D(1), "b": D(1)},
        {"a", "b"},
        {"a": Vote.FOR, "b": Vote.ABSTAIN},
        VotingContext(LE, Phase.OBSERVATION),
    )
    assert not result.adopted
    assert result.votes_abstain == D(1)


weights_st = st.dictionaries(st.sampled_from("abcdefgh"), st.integers(1, 10**9).map(D), min_size=1)


@given(weights_st, st.data())
def test_quorum_threshold_property(weights: dict[str, Decimal], data: st.DataObject) -> None:
    present = data.draw(st.sets(st.sampled_from(sorted(weights))))
    repeated = data.draw(st.booleans())
    result = quorum(weights, present, repeated, True)
    share = sum(weights[c] for c in present) / sum(weights.values())
    limit = D("0.3") if repeated else D("0.5")
    assert result.reached is (share > limit)


@given(weights_st, st.data())
def test_tally_votes_bounded(weights: dict[str, Decimal], data: st.DataObject) -> None:
    present = data.draw(st.sets(st.sampled_from(sorted(weights))))
    ballots = {c: data.draw(st.sampled_from(list(Vote))) for c in present}
    question = data.draw(st.sampled_from(list(Question)))
    result = tally("i", question, weights, present, ballots, VotingContext(LE, Phase.OBSERVATION))
    assert result.votes_for + result.votes_against + result.votes_abstain <= result.base_votes
    assert result.adopted is (result.votes_for * 2 > result.base_votes > 0)
