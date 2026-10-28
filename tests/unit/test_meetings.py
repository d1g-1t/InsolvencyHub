from datetime import date
from decimal import Decimal

import pytest

from insolvency_hub.domain.enums import DebtorKind, NoticeMethod
from insolvency_hub.domain.meetings import (
    after_meeting_terms,
    assess_requisition,
    notice_is_timely,
    notice_term,
    properly_notified,
)

MEETING = date(2026, 6, 15)


@pytest.mark.parametrize(
    ("method", "debtor", "due", "basis"),
    [
        (NoticeMethod.POST, DebtorKind.LEGAL_ENTITY, date(2026, 6, 1), "127-FZ:13.1"),
        (NoticeMethod.OTHER, DebtorKind.LEGAL_ENTITY, date(2026, 6, 5), "127-FZ:13.1"),
        (NoticeMethod.EFRSB, DebtorKind.LEGAL_ENTITY, date(2026, 6, 1), "127-FZ:13.4"),
        (NoticeMethod.EFRSB, DebtorKind.CITIZEN, date(2026, 6, 1), "127-FZ:213.8.5"),
        (NoticeMethod.POST, DebtorKind.CITIZEN, date(2026, 6, 1), "127-FZ:213.8.5"),
        (NoticeMethod.OTHER, DebtorKind.CITIZEN, date(2026, 6, 1), "127-FZ:213.8.5"),
    ],
)
def test_notice_terms(method: NoticeMethod, debtor: DebtorKind, due: date, basis: str) -> None:
    term = notice_term(method, MEETING, debtor)
    assert term.due == due
    assert term.basis == (basis,)
    assert notice_is_timely(method, due, MEETING, debtor)
    assert not notice_is_timely(method, date.fromordinal(due.toordinal() + 1), MEETING, debtor)


def test_properly_notified_requires_efrsb_and_individual_notice() -> None:
    assert not properly_notified([])
    assert not properly_notified([(NoticeMethod.EFRSB, True)])
    assert not properly_notified([(NoticeMethod.POST, True)])
    assert not properly_notified([(NoticeMethod.EFRSB, True), (NoticeMethod.POST, False)])
    assert properly_notified([(NoticeMethod.EFRSB, True), (NoticeMethod.OTHER, True)])


def test_after_meeting_terms() -> None:
    terms = {t.code: t for t in after_meeting_terms(MEETING)}
    assert terms["protocol_to_court"].due == date(2026, 6, 22)
    assert terms["efrsb_meeting_results"].due == date(2026, 6, 22)
    assert terms["challenge_decision"].nominal_due == date(2026, 7, 5)
    assert terms["challenge_decision"].due == date(2026, 7, 6)


def test_requisition_by_tenth_of_registry() -> None:
    amounts = {"a": Decimal(900), "b": Decimal(60), "c": Decimal(30), "d": Decimal(5), "e": Decimal(5)}
    ok = assess_requisition({"a"}, amounts, date(2026, 6, 1))
    assert ok.valid
    assert ok.hold_by is not None
    assert ok.hold_by.due == date(2026, 6, 22)
    assert ok.share_percent == Decimal("90.00")
    assert ok.total_creditors == 5
    tenth = assess_requisition({"b", "c", "d", "e"}, amounts, date(2026, 6, 1))
    assert tenth.valid
    short = assess_requisition({"c"}, amounts, date(2026, 6, 1))
    assert not short.valid
    assert short.hold_by is None


def test_requisition_by_third_of_creditors_and_committee() -> None:
    amounts = {"a": Decimal(1000), "b": Decimal(1), "c": Decimal(1)}
    assert assess_requisition({"b"}, amounts, date(2026, 6, 1)).valid
    assert assess_requisition(set(), {}, date(2026, 6, 1), by_committee=True).valid
    assert not assess_requisition({"x"}, {}, date(2026, 6, 1)).valid
