from datetime import date, timedelta
from functools import cache

NATIONAL_HOLIDAYS = (
    (1, 1),
    (1, 2),
    (1, 3),
    (1, 4),
    (1, 5),
    (1, 6),
    (1, 7),
    (1, 8),
    (2, 23),
    (3, 8),
    (5, 1),
    (5, 9),
    (6, 12),
    (11, 4),
)
NO_WEEKEND_SHIFT = frozenset((1, day) for day in range(1, 9))

GOVERNMENT_TRANSFERS: dict[int, tuple[tuple[date, date], ...]] = {
    2026: (
        (date(2026, 1, 3), date(2026, 1, 9)),
        (date(2026, 1, 4), date(2026, 12, 31)),
    ),
    2027: (
        (date(2027, 1, 2), date(2027, 11, 5)),
        (date(2027, 1, 3), date(2027, 12, 31)),
        (date(2027, 2, 20), date(2027, 2, 22)),
    ),
}

TRANSFER_ACTS = {
    2026: "Постановление Правительства РФ от 24.09.2025 № 1466",
    2027: "Постановление Правительства РФ от 17.09.2026 № 1187",
}


def is_verified_year(year: int) -> bool:
    return year in GOVERNMENT_TRANSFERS


@cache
def non_working_days(year: int) -> frozenset[date]:
    days: set[date] = set()
    current = date(year, 1, 1)
    while current.year == year:
        if current.weekday() >= 5:
            days.add(current)
        current += timedelta(days=1)
    holidays = {date(year, month, day) for month, day in NATIONAL_HOLIDAYS}
    days |= holidays
    for holiday in sorted(holidays):
        if (holiday.month, holiday.day) in NO_WEEKEND_SHIFT or holiday.weekday() < 5:
            continue
        candidate = holiday + timedelta(days=1)
        while candidate in days:
            candidate += timedelta(days=1)
        if candidate.year == year:
            days.add(candidate)
    for source, target in GOVERNMENT_TRANSFERS.get(year, ()):
        if source not in holidays:
            days.discard(source)
        days.add(target)
    return frozenset(days)


def is_working_day(day: date) -> bool:
    return day not in non_working_days(day.year)


def next_working_day(day: date) -> date:
    while not is_working_day(day):
        day += timedelta(days=1)
    return day


def previous_working_day(day: date) -> date:
    while not is_working_day(day):
        day -= timedelta(days=1)
    return day
