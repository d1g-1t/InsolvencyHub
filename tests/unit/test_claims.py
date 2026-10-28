from datetime import date
from decimal import Decimal

import pytest

from insolvency_hub.domain.claims import Amounts, assess_filing, assign_queue
from insolvency_hub.domain.enums import AfterThirdBasis, CreditorKind, DebtorKind, Phase, Queue
from insolvency_hub.domain.errors import ValidationFailed

LE, CIT = DebtorKind.LEGAL_ENTITY, DebtorKind.CITIZEN


@pytest.mark.parametrize(
    ("debtor", "creditor", "queue"),
    [
        (LE, CreditorKind.INJURY, Queue.FIRST),
        (LE, CreditorKind.EMPLOYEE, Queue.SECOND),
        (LE, CreditorKind.AUTHOR, Queue.SECOND),
        (LE, CreditorKind.COMPETITIVE, Queue.THIRD),
        (LE, CreditorKind.AUTHORIZED_BODY, Queue.THIRD),
        (CIT, CreditorKind.ALIMONY, Queue.FIRST),
        (CIT, CreditorKind.INJURY, Queue.FIRST),
        (CIT, CreditorKind.EMPLOYEE, Queue.SECOND),
        (CIT, CreditorKind.AUTHOR, Queue.THIRD),
    ],
)
def test_assign_queue(debtor: DebtorKind, creditor: CreditorKind, queue: Queue) -> None:
    assert assign_queue(debtor, creditor).queue is queue


def test_alimony_only_for_citizen() -> None:
    with pytest.raises(ValidationFailed):
        assign_queue(LE, CreditorKind.ALIMONY)


@pytest.mark.parametrize(
    ("basis", "norm"),
    [
        (AfterThirdBasis.INVALIDATED_TRANSACTION, "127-FZ:134.4"),
        (AfterThirdBasis.EXCESS_SEVERANCE, "127-FZ:134.2.1"),
        (AfterThirdBasis.LATE_FILING, "127-FZ:142.4"),
    ],
)
def test_after_third(basis: AfterThirdBasis, norm: str) -> None:
    result = assign_queue(LE, CreditorKind.COMPETITIVE, basis)
    assert result.queue is Queue.AFTER_THIRD
    assert result.basis == (norm,)


def test_amounts_arithmetic() -> None:
    a = Amounts(Decimal(100), Decimal(10), Decimal(5))
    assert a.base == Decimal(110)
    assert a.total == Decimal(115)
    assert Amounts(Decimal(50), Decimal(10)).fits_into(a)
    assert not Amounts(Decimal(50), Decimal(11)).fits_into(a)
    assert a.minus(Amounts(Decimal(40), Decimal(10), Decimal(5))) == Amounts(Decimal(60), Decimal(0), Decimal(0))


def test_observation_timely_filing() -> None:
    result = assess_filing(LE, Phase.OBSERVATION, CreditorKind.COMPETITIVE, date(2026, 4, 6), date(2026, 3, 7))
    assert result.timely
    assert result.votes_at_first_meeting
    assert not result.review_deferred
    assert result.closing_term is not None
    assert result.closing_term.due == date(2026, 4, 6)
    assert result.review_term is not None
    assert result.review_term.due == date(2026, 5, 6)


def test_observation_late_filing_is_deferred() -> None:
    result = assess_filing(LE, Phase.OBSERVATION, CreditorKind.COMPETITIVE, date(2026, 4, 7), date(2026, 3, 7))
    assert not result.timely
    assert result.review_deferred
    assert not result.votes_at_first_meeting
    assert result.review_term is None
    assert "127-FZ:71.7" in result.basis


def test_observation_late_filing_with_restored_term() -> None:
    result = assess_filing(
        LE, Phase.OBSERVATION, CreditorKind.COMPETITIVE, date(2026, 4, 20), date(2026, 3, 7), term_restored=True
    )
    assert result.timely


def test_observation_before_publication() -> None:
    result = assess_filing(LE, Phase.OBSERVATION, CreditorKind.COMPETITIVE, date(2026, 3, 5), None)
    assert result.timely
    assert result.closing_term is None


@pytest.mark.parametrize("phase", [Phase.FINANCIAL_RECOVERY, Phase.EXTERNAL_MANAGEMENT])
def test_any_time_procedures(phase: Phase) -> None:
    result = assess_filing(LE, phase, CreditorKind.COMPETITIVE, date(2026, 7, 1), date(2026, 6, 1))
    assert result.timely
    assert result.review_term is not None
    assert result.review_term.due == date(2026, 7, 31)


def test_restructuring_two_months() -> None:
    timely = assess_filing(CIT, Phase.RESTRUCTURING, CreditorKind.COMPETITIVE, date(2026, 5, 5), date(2026, 3, 5))
    assert timely.timely
    assert timely.closing_term is not None
    assert timely.closing_term.due == date(2026, 5, 5)
    late = assess_filing(CIT, Phase.RESTRUCTURING, CreditorKind.COMPETITIVE, date(2026, 5, 6), date(2026, 3, 5))
    assert not late.timely
    assert late.review_deferred
    unpublished = assess_filing(CIT, Phase.RESTRUCTURING, CreditorKind.COMPETITIVE, date(2026, 5, 6), None)
    assert unpublished.timely


@pytest.mark.parametrize(("debtor", "phase"), [(LE, Phase.BANKRUPTCY_PROCEEDINGS), (CIT, Phase.PROPERTY_REALIZATION)])
def test_registry_closing(debtor: DebtorKind, phase: Phase) -> None:
    timely = assess_filing(debtor, phase, CreditorKind.COMPETITIVE, date(2026, 9, 7), date(2026, 7, 7))
    assert timely.timely
    assert not timely.after_registry
    late = assess_filing(debtor, phase, CreditorKind.COMPETITIVE, date(2026, 9, 8), date(2026, 7, 7))
    assert late.after_registry
    assert not late.timely
    assert "127-FZ:142.4" in late.basis
