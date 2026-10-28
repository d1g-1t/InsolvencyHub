from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from insolvency_hub.domain.errors import ValidationFailed
from insolvency_hub.domain.money import ZERO, money, pro_rata

cents = st.integers(min_value=0, max_value=10**12).map(lambda v: Decimal(v) / 100)


def test_money_rounds_half_up() -> None:
    assert money("1.005") == Decimal("1.01")
    assert money(3) == Decimal("3.00")


def test_money_rejects_negative() -> None:
    with pytest.raises(ValidationFailed):
        money("-0.01")


def test_pro_rata_pays_in_full_when_enough() -> None:
    assert pro_rata(Decimal(100), {"a": Decimal(30), "b": Decimal(20)}) == {"a": Decimal(30), "b": Decimal(20)}


def test_pro_rata_splits_proportionally_and_spreads_kopecks() -> None:
    shares = pro_rata(Decimal("100.00"), {"a": Decimal(100), "b": Decimal(100), "c": Decimal(100)})
    assert sum(shares.values()) == Decimal("100.00")
    assert sorted(shares.values()) == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert shares["a"] == Decimal("33.34")


def test_pro_rata_nothing_available() -> None:
    assert pro_rata(ZERO, {"a": Decimal(5)}) == {"a": ZERO}


@given(available=cents, demands=st.dictionaries(st.text(min_size=1, max_size=4), cents, min_size=1, max_size=12))
def test_pro_rata_invariants(available: Decimal, demands: dict[str, Decimal]) -> None:
    shares = pro_rata(available, demands)
    total = sum(demands.values(), ZERO)
    assert set(shares) == set(demands)
    assert sum(shares.values(), ZERO) == min(available, total)
    for key, share in shares.items():
        assert ZERO <= share <= demands[key]
        assert share == share.quantize(Decimal("0.01"))
    if total > available and total > 0:
        for key, share in shares.items():
            exact = demands[key] * available / total
            assert abs(share - exact) < Decimal("0.01")
