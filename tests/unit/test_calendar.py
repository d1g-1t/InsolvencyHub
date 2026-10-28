from datetime import date, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from insolvency_hub.domain.calendar import (
    is_verified_year,
    is_working_day,
    next_working_day,
    non_working_days,
    previous_working_day,
)

days = st.dates(min_value=date(2025, 1, 1), max_value=date(2028, 12, 31))


def weekday_holidays(year: int) -> list[date]:
    return sorted(d for d in non_working_days(year) if d.weekday() < 5)


def test_2026_matches_official_calendar() -> None:
    assert weekday_holidays(2026) == [
        date(2026, 1, 1),
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 2, 23),
        date(2026, 3, 9),
        date(2026, 5, 1),
        date(2026, 5, 11),
        date(2026, 6, 12),
        date(2026, 11, 4),
        date(2026, 12, 31),
    ]
    assert len(non_working_days(2026)) == 365 - 247


def test_2027_matches_official_calendar() -> None:
    assert weekday_holidays(2027) == [
        date(2027, 1, 1),
        date(2027, 1, 4),
        date(2027, 1, 5),
        date(2027, 1, 6),
        date(2027, 1, 7),
        date(2027, 1, 8),
        date(2027, 2, 22),
        date(2027, 2, 23),
        date(2027, 3, 8),
        date(2027, 5, 3),
        date(2027, 5, 10),
        date(2027, 6, 14),
        date(2027, 11, 4),
        date(2027, 11, 5),
        date(2027, 12, 31),
    ]
    assert len(non_working_days(2027)) == 365 - 247


def test_verified_years() -> None:
    assert is_verified_year(2026)
    assert is_verified_year(2027)
    assert not is_verified_year(2028)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 3, 7), date(2026, 3, 10)),
        (date(2026, 12, 30), date(2026, 12, 30)),
        (date(2026, 12, 31), date(2027, 1, 11)),
    ],
)
def test_next_working_day(day: date, expected: date) -> None:
    assert next_working_day(day) == expected


def test_previous_working_day() -> None:
    assert previous_working_day(date(2027, 1, 10)) == date(2026, 12, 30)


@given(days)
def test_next_and_previous_working_day_properties(day: date) -> None:
    following = next_working_day(day)
    preceding = previous_working_day(day)
    assert is_working_day(following)
    assert is_working_day(preceding)
    assert preceding <= day <= following
    assert all(not is_working_day(day + timedelta(days=i)) for i in range((following - day).days))
