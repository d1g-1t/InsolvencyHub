from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, status

from insolvency_hub.api.mappers import term_out
from insolvency_hub.api.schemas import CollateralIn, PetitionCheckIn, TermIn, TermOut
from insolvency_hub.core.clock import today
from insolvency_hub.domain.calendar import TRANSFER_ACTS, is_verified_year, non_working_days
from insolvency_hub.domain.distribution import distribute_collateral
from insolvency_hub.domain.enums import DebtorKind
from insolvency_hub.domain.legal import CHECKED_ON, NORMS
from insolvency_hub.domain.petition import OverdueDebt, assess_petition
from insolvency_hub.domain.procedures import DURATIONS, TRANSITIONS
from insolvency_hub.domain.terms import Direction, term_after, term_before

router = APIRouter(prefix="/api/v1/reference", tags=["reference"])


@router.get("/norms")
async def norms() -> dict[str, Any]:
    return {
        "checked_on": CHECKED_ON,
        "norms": [{"code": n.code, "act": n.act, "reference": n.reference, "quote": n.quote} for n in NORMS.values()],
    }


@router.get("/norms/{code}")
async def norm(code: str) -> dict[str, str]:
    item = NORMS.get(code)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "норма не найдена")
    return {
        "code": item.code,
        "act": item.act,
        "reference": item.reference,
        "quote": item.quote,
        "checked_on": CHECKED_ON,
    }


@router.get("/procedures/{debtor_kind}")
async def procedures(debtor_kind: DebtorKind) -> dict[str, Any]:
    return {
        "debtor_kind": debtor_kind.value,
        "transitions": [
            {"from": t.source.value, "to": t.target.value, "basis": t.basis} for t in TRANSITIONS[debtor_kind].values()
        ],
        "durations": {
            phase.value: {"amount": d.amount, "unit": d.unit.value, "extension": d.extension, "basis": d.basis}
            for phase, d in DURATIONS.items()
        },
    }


@router.get("/calendar/{year}")
async def calendar(year: int) -> dict[str, Any]:
    if not 2000 <= year <= 2100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "год вне допустимого диапазона")
    days = sorted(non_working_days(year))
    return {
        "year": year,
        "verified": is_verified_year(year),
        "transfer_act": TRANSFER_ACTS.get(year),
        "basis": ["TK:112", *(["PP:1466"] if year == 2026 else []), *(["PP:1187"] if year == 2027 else [])],
        "non_working_weekdays": [d.isoformat() for d in days if d.weekday() < 5],
        "working_weekends": [
            d.isoformat()
            for d in (
                date.fromordinal(o) for o in range(date(year, 1, 1).toordinal(), date(year, 12, 31).toordinal() + 1)
            )
            if d.weekday() >= 5 and d not in days
        ],
        "non_working_total": len(days),
    }


@router.post("/terms")
async def calculate_term(body: TermIn) -> TermOut:
    builder = term_after if body.direction is Direction.AFTER else term_before
    basis = ("GK:191", "GK:192.3", "GK:193") if body.direction is Direction.AFTER else ()
    term = builder("custom", "расчет срока", body.start, body.amount, body.unit, basis)
    return term_out(term, today())


@router.post("/petition-check")
async def petition_check(body: PetitionCheckIn) -> dict[str, Any]:
    result = assess_petition(body.debtor_kind, [OverdueDebt(d.amount, d.due_date) for d in body.debts], body.filed_on)
    return {
        "admissible": result.admissible,
        "qualifying_amount": str(result.qualifying_amount),
        "threshold": str(result.threshold),
        "reasons": result.reasons,
        "basis": list(result.basis),
    }


@router.post("/collateral")
async def collateral(body: CollateralIn) -> dict[str, Any]:
    if body.secured_debt is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "укажите secured_debt")
    result = distribute_collateral(
        body.proceeds, body.secured_debt, body.credit_agreement, body.first_second_unpaid, body.expenses_unpaid
    )
    return collateral_out(result)


def collateral_out(result: Any) -> dict[str, Any]:
    return {
        "proceeds": str(result.proceeds),
        "secured_share": str(result.secured_share),
        "reserve_share": str(result.reserve_share),
        "expenses_share": str(result.expenses_share),
        "to_secured": str(result.to_secured),
        "to_first_second": str(result.to_first_second),
        "to_expenses": str(result.to_expenses),
        "secured_top_up": str(result.secured_top_up),
        "to_estate": str(result.to_estate),
        "secured_unpaid_to_third_queue": str(result.secured_unpaid),
        "basis": list(result.basis),
    }
