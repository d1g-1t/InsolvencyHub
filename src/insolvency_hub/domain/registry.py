from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from insolvency_hub.domain.case import Claim, InsolvencyCase
from insolvency_hub.domain.distribution import RegistryDebt
from insolvency_hub.domain.enums import ClaimStatus, Queue
from insolvency_hub.domain.money import ZERO

QUEUE_BASIS = {
    Queue.FIRST: ("127-FZ:134.4",),
    Queue.SECOND: ("127-FZ:134.4",),
    Queue.THIRD: ("127-FZ:134.4", "127-FZ:137.3"),
    Queue.AFTER_THIRD: ("127-FZ:134.4", "127-FZ:142.4"),
}


@dataclass
class QueueSection:
    queue: Queue
    claims: list[Claim] = field(default_factory=list)
    base: Decimal = ZERO
    sanctions: Decimal = ZERO
    secured: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.base + self.sanctions


@dataclass
class RegistrySnapshot:
    as_of: date
    sections: list[QueueSection]
    pending: list[Claim]

    @property
    def total(self) -> Decimal:
        return sum((s.total for s in self.sections), ZERO)


def registry_snapshot(case: InsolvencyCase, as_of: date) -> RegistrySnapshot:
    sections = {queue: QueueSection(queue) for queue in Queue}
    for claim in case.claims.values():
        if not claim.in_registry_on(as_of):
            continue
        section = sections[claim.queue]
        outstanding = claim.outstanding
        section.claims.append(claim)
        section.base += outstanding.base
        section.sanctions += outstanding.sanctions
        if claim.secured:
            section.secured += outstanding.total
    pending = sorted(
        (c for c in case.claims.values() if c.status is ClaimStatus.FILED and c.filed_on <= as_of),
        key=lambda c: (c.filed_on, c.claim_id),
    )
    for section in sections.values():
        section.claims.sort(key=lambda c: (c.ruling_date or c.filed_on, c.claim_id))
    return RegistrySnapshot(as_of, list(sections.values()), pending)


def registry_debts(case: InsolvencyCase, as_of: date) -> list[RegistryDebt]:
    debts: list[RegistryDebt] = []
    for claim in case.claims.values():
        if claim.secured:
            continue
        if claim.in_registry_on(as_of):
            outstanding = claim.outstanding
            debts.append(RegistryDebt(claim.claim_id, claim.queue, outstanding.base, outstanding.sanctions))
        elif claim.status is ClaimStatus.FILED and claim.filed_on <= as_of:
            debts.append(RegistryDebt(claim.claim_id, claim.queue, claim.filed.base, claim.filed.sanctions, True))
    return sorted(debts, key=lambda d: d.claim_id)
