import asyncio
import os
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from insolvency_hub.application.cases import CaseService
from insolvency_hub.core.security import Principal, Role, hash_password
from insolvency_hub.domain.case import AgendaItem, Debtor, make_amounts
from insolvency_hub.domain.enums import (
    CreditorKind,
    DebtorKind,
    NoticeMethod,
    Phase,
    PublicationKind,
    Question,
    Vote,
)
from insolvency_hub.infrastructure.db import make_engine, make_session_factory
from insolvency_hub.infrastructure.models import Organization, User

ORGANIZATION_ID = "00000000-0000-4000-8000-000000000001"
USERS = (
    ("admin@demo.invalid", "Демо Администратор", Role.ADMIN),
    ("manager@demo.invalid", "Демо Управляющий", Role.MANAGER),
    ("creditor@demo.invalid", "Демо Кредитор", Role.CREDITOR),
    ("auditor@demo.invalid", "Демо Аудитор", Role.AUDITOR),
)


async def seed() -> None:
    password = os.environ.get("IH_DEMO_PASSWORD", "demo-password")
    engine = make_engine(null_pool=True)
    sessions = make_session_factory(engine)
    async with sessions() as session:
        if await session.get(Organization, ORGANIZATION_ID) is not None:
            print("demo data already present")
            await engine.dispose()
            return
        session.add(Organization(id=ORGANIZATION_ID, name="Демо-офис арбитражного управляющего"))
        await session.flush()
        for email, name, role in USERS:
            session.add(
                User(
                    id=str(uuid.uuid4()),
                    organization_id=ORGANIZATION_ID,
                    email=email,
                    password_hash=hash_password(password),
                    full_name=name,
                    role=role.value,
                )
            )
        await session.commit()
        manager_id = await session.scalar(select(User.id).where(User.email == "manager@demo.invalid"))
        if manager_id is None:
            raise RuntimeError("manager user was not created")
        principal = Principal(manager_id, ORGANIZATION_ID, Role.MANAGER)
        service = CaseService(session)
        debtor = Debtor(DebtorKind.LEGAL_ENTITY, "ООО «Вымышленный Завод»", "0000000018", "1000000000010")
        case = await service.open_case(
            principal, "А00-101/2026", "Демонстрационный арбитражный суд", debtor, date(2026, 2, 2)
        )
        await service.execute(
            case.case_id,
            principal,
            None,
            lambda c: (
                c.change_phase(Phase.OBSERVATION, date(2026, 3, 2), hearing_on=date(2026, 9, 1)),
                c.record_publication(PublicationKind.OBSERVATION, date(2026, 3, 7)),
                c.approve_manager("Управляющий Демо Д.Д.", "Демонстрационная СРО", date(2026, 3, 2)),
                c.file_claim(
                    "demo-claim-bank",
                    "creditor-bank",
                    "АО «Вымышленный Банк»",
                    CreditorKind.COMPETITIVE,
                    make_amounts(Decimal("12000000"), Decimal("800000"), Decimal("350000")),
                    date(2026, 3, 20),
                    "кредитный договор",
                    secured=True,
                    credit_agreement=True,
                ),
                c.file_claim(
                    "demo-claim-supplier",
                    "creditor-supplier",
                    "ООО «Пример Поставок»",
                    CreditorKind.COMPETITIVE,
                    make_amounts(Decimal("4500000"), Decimal("0"), Decimal("120000")),
                    date(2026, 3, 25),
                    "договор поставки",
                ),
                c.file_claim(
                    "demo-claim-tax",
                    "creditor-fns",
                    "Уполномоченный орган (демо)",
                    CreditorKind.AUTHORIZED_BODY,
                    make_amounts(Decimal("1750000"), Decimal("0"), Decimal("90000")),
                    date(2026, 4, 1),
                    "обязательные платежи",
                ),
                c.file_claim(
                    "demo-claim-late",
                    "creditor-late",
                    "ИП Пример (демо)",
                    CreditorKind.COMPETITIVE,
                    make_amounts(Decimal("300000")),
                    date(2026, 4, 20),
                    "договор подряда",
                ),
            ),
        )
        await service.execute(
            case.case_id,
            principal,
            None,
            lambda c: (
                c.object_to_claim(
                    "demo-claim-supplier", "АО «Вымышленный Банк»", "оспаривается размер неустойки", date(2026, 4, 10)
                ),
                c.rule_on_claim("demo-claim-bank", True, date(2026, 5, 6)),
                c.rule_on_claim(
                    "demo-claim-supplier",
                    True,
                    date(2026, 5, 6),
                    make_amounts(Decimal("4500000"), Decimal("0"), Decimal("60000")),
                ),
                c.rule_on_claim("demo-claim-tax", True, date(2026, 5, 12)),
            ),
        )
        meeting_id = "demo-meeting-first"
        await service.execute(
            case.case_id,
            principal,
            None,
            lambda c: (
                c.schedule_meeting(
                    meeting_id,
                    date(2026, 6, 15),
                    [
                        AgendaItem("item-1", Question.ORDINARY, "Отчет временного управляющего"),
                        AgendaItem(
                            "item-2", Question.BANKRUPTCY_PETITION, "Ходатайство о признании должника банкротом"
                        ),
                    ],
                    first=True,
                ),
                c.record_notice(meeting_id, NoticeMethod.EFRSB, date(2026, 5, 25), 3),
                c.record_notice(meeting_id, NoticeMethod.POST, date(2026, 5, 27), 3),
            ),
        )
        await service.execute(
            case.case_id,
            principal,
            None,
            lambda c: (
                c.register_participant(meeting_id, "creditor-bank"),
                c.register_participant(meeting_id, "creditor-supplier"),
                c.cast_ballot(meeting_id, "item-1", "creditor-bank", Vote.FOR),
                c.cast_ballot(meeting_id, "item-1", "creditor-supplier", Vote.FOR),
                c.cast_ballot(meeting_id, "item-2", "creditor-supplier", Vote.FOR),
                c.conclude_meeting(meeting_id),
            ),
        )
        print(f"demo case {case.case_id}; users: {', '.join(u[0] for u in USERS)}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
