from datetime import date
from decimal import Decimal

from insolvency_hub.domain.enums import DebtorKind
from insolvency_hub.domain.petition import OverdueDebt, assess_petition


def test_legal_entity_threshold_counts_only_three_months_overdue() -> None:
    debts = [OverdueDebt(Decimal("1500000"), date(2026, 1, 10)), OverdueDebt(Decimal("700000"), date(2026, 3, 1))]
    early = assess_petition(DebtorKind.LEGAL_ENTITY, debts, date(2026, 5, 31))
    assert not early.admissible
    assert early.qualifying_amount == Decimal("1500000.00")
    assert early.reasons
    later = assess_petition(DebtorKind.LEGAL_ENTITY, debts, date(2026, 6, 1))
    assert later.admissible
    assert later.qualifying_amount == Decimal("2200000.00")
    assert later.basis == ("127-FZ:33.2",)


def test_citizen_threshold() -> None:
    result = assess_petition(DebtorKind.CITIZEN, [OverdueDebt(Decimal("500000"), date(2026, 1, 1))], date(2026, 4, 1))
    assert result.admissible
    assert result.threshold == Decimal("500000.00")
    assert "127-FZ:213.3.2" in result.basis
    below = assess_petition(DebtorKind.CITIZEN, [OverdueDebt(Decimal("499999.99"), date(2026, 1, 1))], date(2026, 4, 1))
    assert not below.admissible
