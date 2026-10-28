from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from insolvency_hub.domain.calendar import is_working_day
from insolvency_hub.domain.terms import (
    Direction,
    Unit,
    add_months,
    add_working_days,
    subtract_working_days,
    term_after,
    term_before,
)

days = st.dates(min_value=date(2025, 1, 1), max_value=date(2028, 6, 30))


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 1, 31), 1, date(2028, 2, 29)),
        (date(2026, 8, 31), 6, date(2027, 2, 28)),
        (date(2026, 3, 15), -3, date(2025, 12, 15)),
        (date(2026, 11, 30), 2, date(2027, 1, 30)),
    ],
)
def test_add_months_respects_month_end(start: date, months: int, expected: date) -> None:
    assert add_months(start, months) == expected


def test_term_after_shifts_to_next_working_day() -> None:
    term = term_after("t", "t", date(2026, 3, 7), 30, Unit.CALENDAR_DAYS, ("GK:193",))
    assert term.nominal_due == date(2026, 4, 6)
    assert term.due == date(2026, 4, 6)
    assert not term.shifted
    shifted = term_after("t", "t", date(2026, 6, 15), 5, Unit.CALENDAR_DAYS, ("GK:193",))
    assert shifted.nominal_due == date(2026, 6, 20)
    assert shifted.due == date(2026, 6, 22)
    assert shifted.shifted
    assert shifted.direction is Direction.AFTER
    assert shifted.calendar_verified


def test_term_after_new_year_holidays() -> None:
    term = term_after("t", "t", date(2026, 12, 1), 1, Unit.MONTHS, ())
    assert term.nominal_due == date(2027, 1, 1)
    assert term.due == date(2027, 1, 11)


def test_working_days_terms() -> None:
    assert add_working_days(date(2026, 6, 15), 5) == date(2026, 6, 22)
    assert subtract_working_days(date(2026, 6, 15), 5) == date(2026, 6, 5)
    term = term_after("t", "t", date(2026, 12, 29), 3, Unit.WORKING_DAYS, ())
    assert term.due == date(2027, 1, 12)


def test_term_before_is_not_shifted_and_reports_status() -> None:
    term = term_before("t", "t", date(2026, 6, 15), 14, Unit.CALENDAR_DAYS, ())
    assert term.due == date(2026, 6, 1)
    assert term.direction is Direction.BEFORE
    assert term.status(date(2026, 6, 1)) == "open"
    assert term.status(date(2026, 6, 2)) == "passed"
    after = term_after("t", "t", date(2026, 6, 1), 10, Unit.CALENDAR_DAYS, ())
    assert after.status(date(2026, 6, 11)) == "open"
    assert after.status(date(2026, 6, 12)) == "expired"
    months_before = term_before("t", "t", date(2026, 6, 15), 1, Unit.MONTHS, ())
    assert months_before.due == date(2026, 5, 15)
    working_before = term_before("t", "t", date(2026, 6, 15), 2, Unit.WORKING_DAYS, ())
    assert working_before.due == date(2026, 6, 10)


def test_unverified_calendar_is_flagged() -> None:
    assert not term_after("t", "t", date(2028, 3, 1), 5, Unit.CALENDAR_DAYS, ()).calendar_verified


@given(days, st.integers(min_value=0, max_value=60), st.sampled_from(list(Unit)))
def test_term_after_due_is_working_day_not_before_nominal(start: date, amount: int, unit: Unit) -> None:
    term = term_after("t", "t", start, amount, unit, ())
    assert is_working_day(term.due)
    assert term.due >= term.nominal_due >= start


@given(days, st.integers(min_value=0, max_value=40))
def test_working_days_round_trip(start: date, amount: int) -> None:
    end = add_working_days(start, amount)
    assert (
        sum(1 for i in range(1, (end - start).days + 1) if is_working_day(date.fromordinal(start.toordinal() + i)))
        == amount
    )
    if is_working_day(start):
        assert subtract_working_days(end, amount) == start


@given(days, st.integers(min_value=-36, max_value=36))
def test_add_months_never_overflows_month(start: date, months: int) -> None:
    result = add_months(start, months)
    assert (result.year * 12 + result.month) - (start.year * 12 + start.month) == months
    assert result.day <= start.day
