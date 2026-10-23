import csv
import io
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Response, status

from insolvency_hub.api.deps import Reader, Session, Version, Writer
from insolvency_hub.api.mappers import amounts_out, claim_out
from insolvency_hub.api.routers.common import execute, load
from insolvency_hub.api.routers.reference import collateral_out
from insolvency_hub.api.schemas import (
    AmountsIn,
    ClaimCreate,
    CollateralIn,
    DistributionIn,
    ExclusionIn,
    ObjectionIn,
    PaymentIn,
    RulingIn,
)
from insolvency_hub.core.clock import today
from insolvency_hub.domain.case import InsolvencyCase, make_amounts
from insolvency_hub.domain.claims import Amounts
from insolvency_hub.domain.distribution import CurrentPayment, distribute_collateral, distribute_estate
from insolvency_hub.domain.enums import ClaimStatus
from insolvency_hub.domain.errors import NotFound, ValidationFailed
from insolvency_hub.domain.registry import QUEUE_BASIS, registry_debts, registry_snapshot

router = APIRouter(prefix="/api/v1/cases/{case_id}", tags=["claims"])
exports = APIRouter(prefix="/api/v1/exports", tags=["claims"])


def _amounts(body: AmountsIn) -> Amounts:
    return make_amounts(body.principal, body.interest, body.sanctions)


def _claim(case: InsolvencyCase, claim_id: str) -> dict[str, Any]:
    claim = case.claims.get(claim_id)
    if claim is None:
        raise NotFound(f"требование {claim_id} не найдено")
    return claim_out(claim)


@router.post("/claims", status_code=status.HTTP_201_CREATED)
async def file_claim(
    case_id: str, body: ClaimCreate, session: Session, principal: Writer, version: Version, response: Response
) -> dict[str, Any]:
    claim_id = body.claim_id or str(uuid.uuid4())
    amounts = _amounts(body.amounts)
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.file_claim(
            claim_id,
            body.creditor_id,
            body.creditor_name,
            body.creditor_kind,
            amounts,
            body.filed_on,
            body.grounds,
            body.secured,
            body.credit_agreement,
            body.after_third_basis,
            body.term_restored,
        ),
    )
    response.headers["Location"] = f"/api/v1/cases/{case_id}/claims/{claim_id}"
    return _claim(case, claim_id)


@router.get("/claims")
async def list_claims(
    case_id: str, session: Session, principal: Reader, response: Response, status: ClaimStatus | None = None
) -> list[dict[str, Any]]:
    case = await load(session, case_id, principal, response)
    claims = sorted(case.claims.values(), key=lambda c: (c.filed_on, c.claim_id))
    return [claim_out(c) for c in claims if status is None or c.status is status]


@router.get("/claims/{claim_id}")
async def get_claim(
    case_id: str, claim_id: str, session: Session, principal: Reader, response: Response
) -> dict[str, Any]:
    return _claim(await load(session, case_id, principal, response), claim_id)


@router.post("/claims/{claim_id}/objections")
async def object_to_claim(
    case_id: str,
    claim_id: str,
    body: ObjectionIn,
    session: Session,
    principal: Writer,
    version: Version,
    response: Response,
) -> dict[str, Any]:
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.object_to_claim(claim_id, body.objector, body.reason, body.filed_on),
    )
    return _claim(case, claim_id)


@router.post("/claims/{claim_id}/ruling")
async def rule_on_claim(
    case_id: str,
    claim_id: str,
    body: RulingIn,
    session: Session,
    principal: Writer,
    version: Version,
    response: Response,
) -> dict[str, Any]:
    amounts = _amounts(body.amounts) if body.amounts else None
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.rule_on_claim(
            claim_id,
            body.included,
            body.ruling_date,
            amounts,
            body.queue,
            body.reason,
        ),
    )
    return _claim(case, claim_id)


@router.post("/claims/{claim_id}/exclusion")
async def exclude_claim(
    case_id: str,
    claim_id: str,
    body: ExclusionIn,
    session: Session,
    principal: Writer,
    version: Version,
    response: Response,
) -> dict[str, Any]:
    case = await execute(
        session,
        case_id,
        principal,
        version,
        response,
        lambda c: c.exclude_claim(claim_id, body.ruling_date, body.reason),
    )
    return _claim(case, claim_id)


@router.post("/claims/{claim_id}/payments")
async def record_payment(
    case_id: str,
    claim_id: str,
    body: PaymentIn,
    session: Session,
    principal: Writer,
    version: Version,
    response: Response,
) -> dict[str, Any]:
    amounts = _amounts(body.amounts)
    case = await execute(
        session, case_id, principal, version, response, lambda c: c.record_payment(claim_id, amounts, body.paid_on)
    )
    return _claim(case, claim_id)


@router.get("/registry")
async def registry(
    case_id: str, session: Session, principal: Reader, response: Response, as_of: date | None = None
) -> dict[str, Any]:
    case = await load(session, case_id, principal, response)
    snapshot = registry_snapshot(case, as_of or today())
    return {
        "case_id": case.case_id,
        "case_number": case.case_number,
        "as_of": snapshot.as_of,
        "total": str(snapshot.total),
        "queues": [
            {
                "queue": s.queue.value,
                "base": str(s.base),
                "sanctions": str(s.sanctions),
                "secured": str(s.secured),
                "total": str(s.total),
                "basis": list(QUEUE_BASIS[s.queue]),
                "claims": [
                    {
                        "claim_id": c.claim_id,
                        "creditor_id": c.creditor_id,
                        "creditor_name": c.creditor_name,
                        "creditor_kind": c.creditor_kind.value,
                        "secured": c.secured,
                        "ruling_date": c.ruling_date,
                        "outstanding": amounts_out(c.outstanding),
                    }
                    for c in s.claims
                ],
            }
            for s in snapshot.sections
        ],
        "pending": [
            {
                "claim_id": c.claim_id,
                "creditor_name": c.creditor_name,
                "filed_on": c.filed_on,
                "review_not_before": c.review_not_before,
                "filed": amounts_out(c.filed),
            }
            for c in snapshot.pending
        ],
    }


def _csv(case: InsolvencyCase, as_of: date) -> Response:
    snapshot = registry_snapshot(case, as_of)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "queue",
            "claim_id",
            "creditor_name",
            "creditor_kind",
            "secured",
            "ruling_date",
            "principal",
            "interest",
            "sanctions",
            "total",
        ]
    )
    for section in snapshot.sections:
        for c in section.claims:
            o = c.outstanding
            writer.writerow(
                [
                    section.queue.value,
                    c.claim_id,
                    c.creditor_name,
                    c.creditor_kind.value,
                    "yes" if c.secured else "no",
                    c.ruling_date.isoformat() if c.ruling_date else "",
                    o.principal,
                    o.interest,
                    o.sanctions,
                    o.total,
                ]
            )
    name = f"registry-{case.case_id}-{as_of.isoformat()}.csv"
    return Response(
        content=("\ufeff" + buffer.getvalue()).encode(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "ETag": f'"{case.version}"'},
    )


@router.get("/registry.csv")
async def registry_csv(
    case_id: str, session: Session, principal: Reader, response: Response, as_of: date | None = None
) -> Response:
    return _csv(await load(session, case_id, principal, response), as_of or today())


@exports.get("/registry/{case_id}")
async def export_registry(
    case_id: str, session: Session, principal: Reader, response: Response, as_of: date | None = None
) -> Response:
    return _csv(await load(session, case_id, principal, response), as_of or today())


@router.post("/distribution")
async def simulate_distribution(
    case_id: str,
    body: DistributionIn,
    session: Session,
    principal: Reader,
    response: Response,
    as_of: date | None = None,
) -> dict[str, Any]:
    case = await load(session, case_id, principal, response)
    current = [CurrentPayment(p.payment_id, p.order, p.amount, p.due_date) for p in body.current_payments]
    result = distribute_estate(body.available, current, registry_debts(case, as_of or today()))
    return {
        "available": str(result.available),
        "paid": str(result.paid),
        "reserved": str(result.reserved),
        "remainder": str(result.remainder),
        "tiers": [
            {
                "tier": t.tier,
                "demand": str(t.demand),
                "allocated": str(t.allocated),
                "fully_covered": t.fully_covered,
                "basis": list(t.basis),
            }
            for t in result.tiers
        ],
        "allocations": [
            {
                "item_id": a.item_id,
                "tier": a.tier,
                "demand": str(a.demand),
                "amount": str(a.amount),
                "reserved": a.reserved,
            }
            for a in result.allocations
        ],
    }


@router.post("/collateral")
async def simulate_collateral(
    case_id: str, body: CollateralIn, session: Session, principal: Reader, response: Response
) -> dict[str, Any]:
    case = await load(session, case_id, principal, response)
    debt, credit_agreement = body.secured_debt, body.credit_agreement
    if body.claim_id is not None:
        claim = case.claims.get(body.claim_id)
        if claim is None:
            raise NotFound(f"требование {body.claim_id} не найдено")
        if not claim.secured or claim.status is not ClaimStatus.INCLUDED:
            raise ValidationFailed("требование не является включенным залоговым", basis="127-FZ:138.1")
        debt, credit_agreement = claim.outstanding.base, claim.credit_agreement
    if debt is None:
        raise ValidationFailed("укажите claim_id или secured_debt")
    result = distribute_collateral(
        body.proceeds, debt, credit_agreement, body.first_second_unpaid, body.expenses_unpaid
    )
    return collateral_out(result)
