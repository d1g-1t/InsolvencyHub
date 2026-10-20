from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from insolvency_hub.domain.enums import DebtorKind, NoticeMethod
from insolvency_hub.domain.terms import Term, Unit, term_after, term_before


def notice_term(method: NoticeMethod, meeting_on: date, debtor: DebtorKind) -> Term:
    if debtor is DebtorKind.CITIZEN:
        title = {
            NoticeMethod.EFRSB: "включение уведомления в ЕФРСБ не позднее",
            NoticeMethod.POST: "направление уведомления заказным письмом не позднее",
            NoticeMethod.OTHER: "направление дополнительного уведомления не позднее",
        }[method]
        return term_before(f"notice_{method.value}", title, meeting_on, 14, Unit.CALENDAR_DAYS, ("127-FZ:213.8.5",))
    match method:
        case NoticeMethod.POST:
            return term_before(
                "notice_post",
                "направление уведомления по почте не позднее",
                meeting_on,
                14,
                Unit.CALENDAR_DAYS,
                ("127-FZ:13.1",),
            )
        case NoticeMethod.OTHER:
            return term_before(
                "notice_other",
                "направление уведомления иным способом не позднее",
                meeting_on,
                5,
                Unit.WORKING_DAYS,
                ("127-FZ:13.1",),
            )
        case NoticeMethod.EFRSB:
            return term_before(
                "notice_efrsb",
                "включение сообщения в ЕФРСБ не позднее",
                meeting_on,
                14,
                Unit.CALENDAR_DAYS,
                ("127-FZ:13.4",),
            )


def properly_notified(notices: list[tuple[NoticeMethod, bool]]) -> bool:
    if not notices or not all(timely for _, timely in notices):
        return False
    methods = {method for method, _ in notices}
    return NoticeMethod.EFRSB in methods and bool(methods - {NoticeMethod.EFRSB})


def notice_is_timely(method: NoticeMethod, sent_on: date, meeting_on: date, debtor: DebtorKind) -> bool:
    return sent_on <= notice_term(method, meeting_on, debtor).due


def after_meeting_terms(held_on: date) -> list[Term]:
    return [
        term_after(
            "protocol_to_court",
            "направление протокола собрания в арбитражный суд",
            held_on,
            5,
            Unit.CALENDAR_DAYS,
            ("127-FZ:12.7", "GK:193"),
        ),
        term_after(
            "efrsb_meeting_results",
            "включение сведений о решениях собрания в ЕФРСБ",
            held_on,
            5,
            Unit.WORKING_DAYS,
            ("127-FZ:12.7",),
        ),
        term_after(
            "challenge_decision",
            "заявление о недействительности решения собрания",
            held_on,
            20,
            Unit.CALENDAR_DAYS,
            ("127-FZ:15.4", "GK:193"),
        ),
    ]


@dataclass(frozen=True, slots=True)
class RequisitionAssessment:
    valid: bool
    share_percent: Decimal
    creditors_count: int
    total_creditors: int
    hold_by: Term | None
    basis: tuple[str, ...] = ("127-FZ:14.1", "127-FZ:14.3")


def assess_requisition(
    requesting: set[str], registry_amounts: dict[str, Decimal], received_on: date, by_committee: bool = False
) -> RequisitionAssessment:
    total = sum(registry_amounts.values(), Decimal("0"))
    requested = sum((amount for c, amount in registry_amounts.items() if c in requesting), Decimal("0"))
    count = len(requesting & registry_amounts.keys())
    share = (requested * 100 / total).quantize(Decimal("0.01")) if total else Decimal("0.00")
    valid = (
        by_committee
        or (total > 0 and requested * 10 >= total)
        or (len(registry_amounts) > 0 and count * 3 >= len(registry_amounts))
    )
    hold_by = (
        term_after(
            "requisition_meeting",
            "проведение собрания по требованию кредиторов",
            received_on,
            21,
            Unit.CALENDAR_DAYS,
            ("127-FZ:14.3", "GK:193"),
        )
        if valid
        else None
    )
    return RequisitionAssessment(valid, share, count, len(registry_amounts), hold_by)
