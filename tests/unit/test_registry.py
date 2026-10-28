from datetime import date
from decimal import Decimal

from insolvency_hub.domain.case import make_amounts
from insolvency_hub.domain.enums import CreditorKind, Queue
from insolvency_hub.domain.registry import registry_debts, registry_snapshot
from tests.factories import with_registry

D = Decimal


def test_snapshot_groups_by_queue() -> None:
    case = with_registry()
    case.file_claim("pending", "c-x", "Х", CreditorKind.COMPETITIVE, make_amounts(D(70)), date(2026, 4, 2), "осн")
    snapshot = registry_snapshot(case, date(2026, 6, 1))
    sections = {s.queue: s for s in snapshot.sections}
    assert sections[Queue.SECOND].total == D(40)
    assert sections[Queue.THIRD].base == D(1000)
    assert sections[Queue.THIRD].sanctions == D(50)
    assert sections[Queue.THIRD].secured == D(600)
    assert snapshot.total == D(1090)
    assert [c.claim_id for c in snapshot.pending] == ["pending"]
    assert registry_snapshot(case, date(2026, 5, 11)).total == D(0)


def test_registry_debts_exclude_secured_and_mark_pending() -> None:
    case = with_registry()
    case.file_claim("pending", "c-x", "Х", CreditorKind.COMPETITIVE, make_amounts(D(70)), date(2026, 4, 2), "осн")
    debts = {d.claim_id: d for d in registry_debts(case, date(2026, 6, 1))}
    assert "bank" not in debts
    assert debts["pending"].disputed
    assert debts["supplier"].sanctions == D(50)
    assert not debts["worker"].disputed
