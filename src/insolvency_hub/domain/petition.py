from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from insolvency_hub.domain.enums import DebtorKind
from insolvency_hub.domain.money import money
from insolvency_hub.domain.terms import add_months

THRESHOLDS = {
    DebtorKind.LEGAL_ENTITY: Decimal("2000000.00"),
    DebtorKind.CITIZEN: Decimal("500000.00"),
}


@dataclass(frozen=True, slots=True)
class OverdueDebt:
    amount: Decimal
    due_date: date


@dataclass(frozen=True, slots=True)
class PetitionAssessment:
    admissible: bool
    qualifying_amount: Decimal
    threshold: Decimal
    reasons: list[str] = field(default_factory=list)
    basis: tuple[str, ...] = ()


def assess_petition(kind: DebtorKind, debts: list[OverdueDebt], filed_on: date) -> PetitionAssessment:
    threshold = THRESHOLDS[kind]
    qualifying = sum((money(d.amount) for d in debts if add_months(d.due_date, 3) <= filed_on), Decimal("0.00"))
    reasons: list[str] = []
    if qualifying < threshold:
        reasons.append(
            f"просроченные более трех месяцев требования составляют {qualifying} руб., "
            f"порог для заявления - {threshold} руб."
        )
    basis = ("127-FZ:33.2",) if kind is DebtorKind.LEGAL_ENTITY else ("127-FZ:33.2", "127-FZ:213.3.2")
    return PetitionAssessment(not reasons, qualifying, threshold, reasons, basis)
