from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from insolvency_hub.domain.distribution import (
    CurrentPayment,
    EstateDistribution,
    RegistryDebt,
    TierSummary,
    distribute_collateral,
    distribute_estate,
)
from insolvency_hub.domain.enums import CurrentPaymentOrder, Queue
from insolvency_hub.domain.money import ZERO

D = Decimal
money_st = st.integers(min_value=0, max_value=10**10).map(lambda v: D(v) / 100)


def tier(result: EstateDistribution, name: str) -> TierSummary:
    return next(t for t in result.tiers if t.tier == name)


def test_current_payments_go_first_by_order_and_date() -> None:
    current = [
        CurrentPayment("utilities", CurrentPaymentOrder.FOURTH, D(50), date(2026, 1, 1)),
        CurrentPayment("fee-late", CurrentPaymentOrder.FIRST, D(30), date(2026, 3, 1)),
        CurrentPayment("fee-early", CurrentPaymentOrder.FIRST, D(30), date(2026, 2, 1)),
    ]
    registry = [RegistryDebt("c1", Queue.THIRD, D(100), ZERO)]
    result = distribute_estate(D(70), current, registry)
    paid = {a.item_id: a.amount for a in result.allocations}
    assert paid == {"fee-early": D(30), "fee-late": D(30), "utilities": D(10), "c1": ZERO}
    assert result.remainder == ZERO


def test_registry_queues_and_sanctions_after_base() -> None:
    registry = [
        RegistryDebt("injury", Queue.FIRST, D(10), ZERO),
        RegistryDebt("wages", Queue.SECOND, D(20), ZERO),
        RegistryDebt("bank", Queue.THIRD, D(100), D(40)),
        RegistryDebt("supplier", Queue.THIRD, D(100), D(10)),
        RegistryDebt("late", Queue.AFTER_THIRD, D(50), ZERO),
    ]
    result = distribute_estate(D(255), [], registry)
    assert tier(result, "registry:first").fully_covered
    assert tier(result, "registry:second").fully_covered
    assert tier(result, "registry:third").allocated == D(200)
    assert tier(result, "registry:third_sanctions").allocated == D(25)
    assert {a.item_id: a.amount for a in result.allocations if a.tier == "registry:third_sanctions"} == {
        "bank": D(20),
        "supplier": D(5),
    }
    assert tier(result, "registry:after_third").allocated == ZERO
    assert result.paid == D(255)


def test_surplus_reaches_after_third_and_remainder() -> None:
    result = distribute_estate(D(1000), [], [RegistryDebt("late", Queue.AFTER_THIRD, D(50), D(5))])
    assert tier(result, "registry:after_third").allocated == D(55)
    assert result.remainder == D(945)


def test_disputed_claims_are_reserved() -> None:
    registry = [RegistryDebt("ok", Queue.THIRD, D(100), ZERO), RegistryDebt("pending", Queue.THIRD, D(100), ZERO, True)]
    result = distribute_estate(D(100), [], registry)
    assert result.paid == D(50)
    assert result.reserved == D(50)
    assert "127-FZ:142.6" in tier(result, "registry:third").basis


def test_safety_current_payments_have_priority_basis() -> None:
    current = [CurrentPayment("safety", CurrentPaymentOrder.PRIORITY_SAFETY, D(5), date(2026, 1, 1))]
    result = distribute_estate(D(5), current, [])
    assert tier(result, "current:priority_safety").basis == ("127-FZ:134.1.1",)


debts_st = st.lists(
    st.builds(RegistryDebt, st.uuids().map(str), st.sampled_from(list(Queue)), money_st, money_st, st.booleans()),
    max_size=15,
    unique_by=lambda d: d.claim_id,
)
current_st = st.lists(
    st.builds(
        CurrentPayment,
        st.uuids().map(str),
        st.sampled_from(list(CurrentPaymentOrder)),
        money_st,
        st.dates(min_value=date(2025, 1, 1), max_value=date(2027, 1, 1)),
    ),
    max_size=8,
    unique_by=lambda p: p.payment_id,
)


@given(money_st, current_st, debts_st)
def test_estate_conservation_and_priority(
    available: Decimal, current: list[CurrentPayment], registry: list[RegistryDebt]
) -> None:
    result = distribute_estate(available, current, registry)
    allocated = sum((a.amount for a in result.allocations), ZERO)
    assert allocated + result.remainder == available
    assert result.paid + result.reserved == allocated
    assert result.remainder >= ZERO
    for allocation in result.allocations:
        assert ZERO <= allocation.amount <= allocation.demand
    seen_short = False
    for summary in result.tiers:
        if seen_short:
            assert summary.allocated == ZERO
        if summary.allocated < summary.demand:
            seen_short = True
    if result.remainder > 0:
        assert all(t.fully_covered for t in result.tiers)


def test_collateral_ordinary_pledge() -> None:
    result = distribute_collateral(D(1000), D(500), False, D(100), D(30))
    assert (result.secured_share, result.reserve_share, result.expenses_share) == (D(700), D(200), D(100))
    assert result.to_secured == D(500)
    assert result.to_first_second == D(100)
    assert result.secured_top_up == ZERO
    assert result.to_expenses == D(30)
    assert result.to_estate == D(200 + 100 + 70)
    assert result.secured_unpaid == ZERO
    assert result.basis[0] == "127-FZ:138.1"


def test_collateral_credit_agreement_and_top_up() -> None:
    result = distribute_collateral(D(1000), D(900), True, D(50), ZERO)
    assert (result.secured_share, result.reserve_share) == (D(800), D(150))
    assert result.to_first_second == D(50)
    assert result.secured_top_up == D(100)
    assert result.secured_unpaid == ZERO
    assert result.to_estate == D(50)
    assert result.basis[0] == "127-FZ:138.2"


@given(money_st, money_st, st.booleans(), money_st, money_st)
def test_collateral_conservation(
    proceeds: Decimal, debt: Decimal, credit: bool, first_second: Decimal, expenses: Decimal
) -> None:
    r = distribute_collateral(proceeds, debt, credit, first_second, expenses)
    assert r.secured_share + r.reserve_share + r.expenses_share == r.proceeds
    assert r.to_secured + r.to_first_second + r.secured_top_up + r.to_expenses + r.to_estate == r.proceeds
    assert r.to_secured + r.secured_top_up + r.secured_unpaid == debt
    assert min(r.to_secured, r.to_first_second, r.secured_top_up, r.to_expenses, r.to_estate, r.secured_unpaid) >= 0
    assert r.to_secured <= r.secured_share
