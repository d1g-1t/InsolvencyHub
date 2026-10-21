import calendar as std_calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from insolvency_hub.domain.calendar import is_verified_year, is_working_day, next_working_day


class Unit(StrEnum):
    CALENDAR_DAYS = "calendar_days"
    WORKING_DAYS = "working_days"
    MONTHS = "months"


class Direction(StrEnum):
    AFTER = "after"
    BEFORE = "before"


@dataclass(frozen=True, slots=True)
class Term:
    code: str
    title: str
    start: date
    due: date
    nominal_due: date
    unit: Unit
    amount: int
    direction: Direction
    basis: tuple[str, ...]
    calendar_verified: bool

    @property
    def shifted(self) -> bool:
        return self.due != self.nominal_due

    def status(self, today: date) -> str:
        if self.direction is Direction.BEFORE:
            return "open" if today <= self.due else "passed"
        return "open" if today <= self.due else "expired"


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    last_day = std_calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day))


def add_working_days(start: date, amount: int) -> date:
    current = start
    remaining = amount
    while remaining > 0:
        current += timedelta(days=1)
        if is_working_day(current):
            remaining -= 1
    return current


def subtract_working_days(end: date, amount: int) -> date:
    current = end
    remaining = amount
    while remaining > 0:
        current -= timedelta(days=1)
        if is_working_day(current):
            remaining -= 1
    return current


def term_after(code: str, title: str, start: date, amount: int, unit: Unit, basis: tuple[str, ...]) -> Term:
    match unit:
        case Unit.CALENDAR_DAYS:
            nominal = start + timedelta(days=amount)
        case Unit.MONTHS:
            nominal = add_months(start, amount)
        case Unit.WORKING_DAYS:
            nominal = add_working_days(start, amount)
    due = next_working_day(nominal)
    verified = is_verified_year(start.year) and is_verified_year(due.year)
    return Term(code, title, start, due, nominal, unit, amount, Direction.AFTER, basis, verified)


def term_before(code: str, title: str, event: date, amount: int, unit: Unit, basis: tuple[str, ...]) -> Term:
    match unit:
        case Unit.CALENDAR_DAYS:
            due = event - timedelta(days=amount)
        case Unit.MONTHS:
            due = add_months(event, -amount)
        case Unit.WORKING_DAYS:
            due = subtract_working_days(event, amount)
    verified = is_verified_year(event.year) and is_verified_year(due.year)
    return Term(code, title, event, due, due, unit, amount, Direction.BEFORE, basis, verified)
