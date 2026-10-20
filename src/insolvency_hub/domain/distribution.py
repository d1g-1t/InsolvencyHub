from dataclasses import dataclass, field, replace
from datetime import date
from decimal import ROUND_DOWN, Decimal

from insolvency_hub.domain.enums import CurrentPaymentOrder, Queue
from insolvency_hub.domain.money import KOPECK, ZERO, money, pro_rata

CURRENT_ORDERS = tuple(CurrentPaymentOrder)


@dataclass(frozen=True, slots=True)
class CurrentPayment:
    payment_id: str
    order: CurrentPaymentOrder
    amount: Decimal
    due_date: date


@dataclass(frozen=True, slots=True)
class RegistryDebt:
    claim_id: str
    queue: Queue
    base: Decimal
    sanctions: Decimal
    disputed: bool = False


@dataclass(frozen=True, slots=True)
class Allocation:
    item_id: str
    tier: str
    demand: Decimal
    amount: Decimal
    reserved: bool


@dataclass(frozen=True, slots=True)
class TierSummary:
    tier: str
    demand: Decimal
    allocated: Decimal
    basis: tuple[str, ...]

    @property
    def fully_covered(self) -> bool:
        return self.allocated == self.demand


@dataclass
class EstateDistribution:
    available: Decimal
    allocations: list[Allocation] = field(default_factory=list)
    tiers: list[TierSummary] = field(default_factory=list)
    remainder: Decimal = ZERO

    @property
    def paid(self) -> Decimal:
        return sum((a.amount for a in self.allocations if not a.reserved), ZERO)

    @property
    def reserved(self) -> Decimal:
        return sum((a.amount for a in self.allocations if a.reserved), ZERO)


def distribute_estate(
    available: Decimal, current: list[CurrentPayment], registry: list[RegistryDebt]
) -> EstateDistribution:
    available = money(available)
    current = [replace(p, amount=money(p.amount)) for p in current]
    registry = [replace(d, base=money(d.base), sanctions=money(d.sanctions)) for d in registry]
    result = EstateDistribution(available=available)
    cash = available
    for order in CURRENT_ORDERS:
        items = sorted((p for p in current if p.order is order), key=lambda p: (p.due_date, p.payment_id))
        if not items:
            continue
        tier = f"current:{order.value}"
        basis: tuple[str, ...] = (
            ("127-FZ:134.1.1",) if order is CurrentPaymentOrder.PRIORITY_SAFETY else ("127-FZ:134.1", "127-FZ:134.2")
        )
        allocated = ZERO
        for payment in items:
            amount = min(cash, payment.amount)
            cash -= amount
            allocated += amount
            result.allocations.append(Allocation(payment.payment_id, tier, payment.amount, amount, False))
        result.tiers.append(TierSummary(tier, sum((p.amount for p in items), ZERO), allocated, basis))
    tiers: list[tuple[str, list[tuple[RegistryDebt, Decimal]], tuple[str, ...]]] = [
        (
            "registry:first",
            [(d, d.base + d.sanctions) for d in registry if d.queue is Queue.FIRST],
            ("127-FZ:134.4", "127-FZ:142.2", "127-FZ:142.3"),
        ),
        (
            "registry:second",
            [(d, d.base + d.sanctions) for d in registry if d.queue is Queue.SECOND],
            ("127-FZ:134.4", "127-FZ:142.2", "127-FZ:142.3"),
        ),
        ("registry:third", [(d, d.base) for d in registry if d.queue is Queue.THIRD], ("127-FZ:134.4", "127-FZ:142.3")),
        (
            "registry:third_sanctions",
            [(d, d.sanctions) for d in registry if d.queue is Queue.THIRD],
            ("127-FZ:137.3", "127-FZ:142.3"),
        ),
        (
            "registry:after_third",
            [(d, d.base + d.sanctions) for d in registry if d.queue is Queue.AFTER_THIRD],
            ("127-FZ:134.4", "127-FZ:134.2.1", "127-FZ:142.4"),
        ),
    ]
    for tier, debts, basis in tiers:
        demands = {debt.claim_id: amount for debt, amount in debts if amount > 0}
        if not demands:
            continue
        shares = pro_rata(cash, demands)
        disputed = {debt.claim_id for debt, _ in debts if debt.disputed}
        allocated = sum(shares.values(), ZERO)
        cash -= allocated
        for claim_id, amount in shares.items():
            result.allocations.append(Allocation(claim_id, tier, demands[claim_id], amount, claim_id in disputed))
        basis_full = (*basis, "127-FZ:142.6") if disputed else basis
        result.tiers.append(TierSummary(tier, sum(demands.values(), ZERO), allocated, basis_full))
    result.remainder = cash
    return result


@dataclass(frozen=True, slots=True)
class CollateralDistribution:
    proceeds: Decimal
    to_secured: Decimal
    to_first_second: Decimal
    to_expenses: Decimal
    secured_top_up: Decimal
    to_estate: Decimal
    secured_unpaid: Decimal
    secured_share: Decimal
    reserve_share: Decimal
    expenses_share: Decimal
    basis: tuple[str, ...]


def distribute_collateral(
    proceeds: Decimal,
    secured_debt: Decimal,
    credit_agreement: bool,
    first_second_unpaid: Decimal,
    expenses_unpaid: Decimal,
) -> CollateralDistribution:
    proceeds, secured_debt = money(proceeds), money(secured_debt)
    first_second_unpaid, expenses_unpaid = money(first_second_unpaid), money(expenses_unpaid)
    main_rate, reserve_rate = (
        (Decimal("0.80"), Decimal("0.15")) if credit_agreement else (Decimal("0.70"), Decimal("0.20"))
    )
    secured_share = (proceeds * main_rate).quantize(KOPECK, rounding=ROUND_DOWN)
    reserve_share = (proceeds * reserve_rate).quantize(KOPECK, rounding=ROUND_DOWN)
    expenses_share = proceeds - secured_share - reserve_share
    to_secured = min(secured_share, secured_debt)
    to_first_second = min(reserve_share, first_second_unpaid)
    top_up = min(reserve_share - to_first_second, secured_debt - to_secured)
    to_expenses = min(expenses_share, expenses_unpaid)
    to_estate = (
        (secured_share - to_secured) + (reserve_share - to_first_second - top_up) + (expenses_share - to_expenses)
    )
    basis = ("127-FZ:138.2", "127-FZ:138.2.1") if credit_agreement else ("127-FZ:138.1", "127-FZ:138.2.1")
    return CollateralDistribution(
        proceeds=proceeds,
        to_secured=to_secured,
        to_first_second=to_first_second,
        to_expenses=to_expenses,
        secured_top_up=top_up,
        to_estate=to_estate,
        secured_unpaid=secured_debt - to_secured - top_up,
        secured_share=secured_share,
        reserve_share=reserve_share,
        expenses_share=expenses_share,
        basis=basis,
    )
