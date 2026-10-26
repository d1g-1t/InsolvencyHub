from datetime import date
from decimal import Decimal

from insolvency_hub.domain.case import AgendaItem, Debtor, InsolvencyCase, make_amounts
from insolvency_hub.domain.enums import CreditorKind, DebtorKind, NoticeMethod, Phase, PublicationKind, Question

ORG = "org-1"
LEGAL = Debtor(DebtorKind.LEGAL_ENTITY, "ООО «Тест»", "0000000018", "1000000000010")
CITIZEN = Debtor(DebtorKind.CITIZEN, "Тестов Тест Тестович", "000000000184", None)


def opened(debtor: Debtor = LEGAL, case_id: str = "case-1") -> InsolvencyCase:
    case = InsolvencyCase(case_id)
    case.open(ORG, "А00-1/2026", "Тестовый суд", debtor, date(2026, 2, 2))
    return case


def in_observation(published_on: date = date(2026, 3, 7)) -> InsolvencyCase:
    case = opened()
    case.change_phase(Phase.OBSERVATION, date(2026, 3, 2), hearing_on=date(2026, 9, 1))
    case.record_publication(PublicationKind.OBSERVATION, published_on)
    return case


def with_registry() -> InsolvencyCase:
    case = in_observation()
    case.file_claim(
        "bank",
        "c-bank",
        "Банк",
        CreditorKind.COMPETITIVE,
        make_amounts(Decimal(600)),
        date(2026, 3, 20),
        "кредит",
        secured=True,
        credit_agreement=True,
    )
    case.file_claim(
        "supplier",
        "c-sup",
        "Поставщик",
        CreditorKind.COMPETITIVE,
        make_amounts(Decimal(300), Decimal(0), Decimal(50)),
        date(2026, 3, 25),
        "поставка",
    )
    case.file_claim(
        "tax", "c-fns", "ФНС", CreditorKind.AUTHORIZED_BODY, make_amounts(Decimal(100)), date(2026, 4, 1), "налоги"
    )
    case.file_claim(
        "worker", "c-emp", "Работник", CreditorKind.EMPLOYEE, make_amounts(Decimal(40)), date(2026, 4, 1), "зарплата"
    )
    for claim_id in ("bank", "supplier", "tax", "worker"):
        case.rule_on_claim(claim_id, True, date(2026, 5, 12))
    return case


def scheduled_meeting(
    case: InsolvencyCase,
    meeting_id: str = "m1",
    first: bool = True,
    repeated_of: str | None = None,
    on: date = date(2026, 6, 15),
    question: Question = Question.ORDINARY,
) -> None:
    case.schedule_meeting(meeting_id, on, [AgendaItem("i1", question, "вопрос")], first=first, repeated_of=repeated_of)
    case.record_notice(meeting_id, NoticeMethod.EFRSB, date(2026, 5, 20), 3)
    case.record_notice(meeting_id, NoticeMethod.POST, date(2026, 5, 25), 3)
