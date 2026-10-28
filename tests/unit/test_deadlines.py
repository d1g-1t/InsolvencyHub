from datetime import date
from decimal import Decimal

from insolvency_hub.domain.case import InsolvencyCase, make_amounts
from insolvency_hub.domain.deadlines import case_terms
from insolvency_hub.domain.enums import CreditorKind, Phase, PublicationKind
from tests.factories import CITIZEN, in_observation, opened, scheduled_meeting, with_registry


def codes(case: InsolvencyCase) -> dict[str, date]:
    return {t.code: t.due for t in case_terms(case)}


def test_observation_terms() -> None:
    case = in_observation()
    case.file_claim("c", "k", "К", CreditorKind.COMPETITIVE, make_amounts(Decimal(1)), date(2026, 3, 20), "осн")
    terms = codes(case)
    assert terms["case_consideration"] == date(2026, 9, 2)
    assert terms["claims_first_meeting"] == date(2026, 4, 6)
    assert terms["first_meeting"] == date(2026, 8, 22)
    assert terms["claim_review:c"] == date(2026, 5, 6)
    assert list(terms.values()) == sorted(terms.values())


def test_meeting_terms_before_and_after() -> None:
    case = with_registry()
    scheduled_meeting(case)
    terms = codes(case)
    assert terms["notice_efrsb:m1"] == date(2026, 6, 1)
    assert terms["notice_other:m1"] == date(2026, 6, 5)
    case.register_participant("m1", "c-bank")
    case.conclude_meeting("m1")
    terms = codes(case)
    assert "first_meeting" not in terms
    assert terms["protocol_to_court:m1"] == date(2026, 6, 22)
    assert "notice_post:m1" not in terms


def test_requisition_term() -> None:
    case = with_registry()
    case.receive_requisition("r", ["c-sup"], date(2026, 6, 1), ["вопрос"])
    assert codes(case)["requisition_meeting:r"] == date(2026, 6, 22)


def test_bankruptcy_proceedings_terms() -> None:
    case = opened()
    case.change_phase(Phase.OBSERVATION, date(2026, 3, 2))
    case.change_phase(Phase.BANKRUPTCY_PROCEEDINGS, date(2026, 7, 1))
    case.record_publication(PublicationKind.BANKRUPTCY_PROCEEDINGS, date(2026, 7, 11))
    case.approve_manager("КУ", "СРО", date(2026, 7, 1))
    terms = codes(case)
    assert terms["bankruptcy_publication"] == date(2026, 7, 13)
    assert terms["registry_closing"] == date(2026, 9, 11)
    assert terms["bankruptcy_proceedings_ends"] == date(2027, 1, 11)


def test_citizen_terms() -> None:
    case = opened(CITIZEN)
    case.change_phase(Phase.RESTRUCTURING, date(2026, 3, 2))
    case.record_publication(PublicationKind.RESTRUCTURING, date(2026, 3, 5))
    case.file_claim("c", "k", "К", CreditorKind.COMPETITIVE, make_amounts(Decimal(1)), date(2026, 3, 20), "осн")
    terms = codes(case)
    assert terms["claims_restructuring"] == date(2026, 5, 5)
    assert terms["claim_review:c"] == date(2026, 6, 4)
    case.change_phase(Phase.PROPERTY_REALIZATION, date(2026, 7, 1))
    case.record_publication(PublicationKind.PROPERTY_REALIZATION, date(2026, 7, 4))
    terms = codes(case)
    assert terms["registry_closing"] == date(2026, 9, 4)
    assert terms["property_realization_ends"] == date(2027, 1, 11)
