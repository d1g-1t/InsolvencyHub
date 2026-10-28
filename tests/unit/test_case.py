from datetime import date
from decimal import Decimal

import pytest

from insolvency_hub.domain.case import AgendaItem, Debtor, InsolvencyCase, make_amounts
from insolvency_hub.domain.enums import (
    AfterThirdBasis,
    ClaimStatus,
    CreditorKind,
    DebtorKind,
    MeetingStatus,
    NoticeMethod,
    Phase,
    PublicationKind,
    Question,
    Queue,
    Vote,
)
from insolvency_hub.domain.errors import NotFound, TransitionNotAllowed, ValidationFailed
from tests.factories import CITIZEN, LEGAL, ORG, in_observation, opened, scheduled_meeting, with_registry

D = Decimal


def replay(case: InsolvencyCase) -> InsolvencyCase:
    return InsolvencyCase.rehydrate(case.case_id, case.pending)


def test_open_validates_identifiers() -> None:
    with pytest.raises(ValidationFailed):
        InsolvencyCase("x").open(
            ORG,
            "А00-1/2026",
            "суд",
            Debtor(DebtorKind.LEGAL_ENTITY, "ООО", "0000000019", "1000000000010"),
            date(2026, 1, 1),
        )
    with pytest.raises(ValidationFailed):
        InsolvencyCase("x").open(
            ORG, "А00-1/2026", "суд", Debtor(DebtorKind.LEGAL_ENTITY, "ООО", "0000000018", None), date(2026, 1, 1)
        )
    with pytest.raises(ValidationFailed):
        InsolvencyCase("x").open(
            ORG, "А00-1/2026", "суд", Debtor(DebtorKind.CITIZEN, "Г", "000000000184", "1000000000011"), date(2026, 1, 1)
        )
    with pytest.raises(ValidationFailed):
        InsolvencyCase("x").open(ORG, "1/2026", "суд", LEGAL, date(2026, 1, 1))
    case = opened()
    with pytest.raises(TransitionNotAllowed):
        case.open(ORG, "А00-1/2026", "суд", LEGAL, date(2026, 1, 1))


def test_unopened_case_rejects_commands() -> None:
    case = InsolvencyCase("x")
    with pytest.raises(NotFound):
        case.record_publication(PublicationKind.OBSERVATION, date(2026, 1, 1))
    with pytest.raises(NotFound):
        _ = case.debtor_kind


def test_phase_changes_follow_statute() -> None:
    case = opened()
    with pytest.raises(TransitionNotAllowed) as error:
        case.change_phase(Phase.RESTRUCTURING, date(2026, 3, 1))
    assert error.value.basis == "127-FZ:27"
    case.change_phase(Phase.OBSERVATION, date(2026, 3, 2), hearing_on=date(2026, 9, 1))
    with pytest.raises(ValidationFailed):
        case.change_phase(Phase.BANKRUPTCY_PROCEEDINGS, date(2026, 3, 1))
    with pytest.raises(ValidationFailed):
        case.change_phase(Phase.BANKRUPTCY_PROCEEDINGS, date(2026, 9, 1), hearing_on=date(2026, 9, 1))
    case.change_phase(Phase.BANKRUPTCY_PROCEEDINGS, date(2026, 9, 1))
    case.change_phase(Phase.COMPLETED, date(2027, 3, 1))
    with pytest.raises(TransitionNotAllowed):
        case.approve_manager("А", "СРО", date(2027, 3, 2))
    assert [h["phase"] for h in case.phase_history] == [
        "petition_accepted",
        "observation",
        "bankruptcy_proceedings",
        "completed",
    ]
    assert replay(case).phase is Phase.COMPLETED


def test_citizen_transition_basis() -> None:
    case = opened(CITIZEN)
    with pytest.raises(TransitionNotAllowed) as error:
        case.change_phase(Phase.OBSERVATION, date(2026, 3, 1))
    assert error.value.basis == "127-FZ:213.2"


def test_publication_and_manager() -> None:
    case = opened()
    with pytest.raises(TransitionNotAllowed):
        case.approve_manager("А", "СРО", date(2026, 3, 2))
    with pytest.raises(ValidationFailed):
        case.record_publication(PublicationKind.OBSERVATION, date(2026, 3, 7))
    case.change_phase(Phase.OBSERVATION, date(2026, 3, 2))
    with pytest.raises(ValidationFailed):
        case.record_publication(PublicationKind.BANKRUPTCY_PROCEEDINGS, date(2026, 3, 7))
    with pytest.raises(ValidationFailed):
        case.record_publication(PublicationKind.OBSERVATION, date(2026, 3, 1))
    case.record_publication(PublicationKind.OBSERVATION, date(2026, 3, 7))
    with pytest.raises(ValidationFailed):
        case.record_publication(PublicationKind.OBSERVATION, date(2026, 3, 8))
    case.approve_manager("Управляющий", "СРО", date(2026, 3, 2))
    restored = replay(case)
    assert restored.manager is not None
    assert restored.manager["full_name"] == "Управляющий"
    assert restored.publications[PublicationKind.OBSERVATION] == date(2026, 3, 7)


def test_claim_filing_rules() -> None:
    case = opened()
    with pytest.raises(TransitionNotAllowed):
        case.file_claim("c", "k", "К", CreditorKind.COMPETITIVE, make_amounts(D(1)), date(2026, 3, 1), "осн")
    case = in_observation()
    case.file_claim("c", "k", "К", CreditorKind.COMPETITIVE, make_amounts(D(1)), date(2026, 3, 10), "осн")
    with pytest.raises(ValidationFailed):
        case.file_claim("c", "k", "К", CreditorKind.COMPETITIVE, make_amounts(D(1)), date(2026, 3, 10), "осн")
    with pytest.raises(ValidationFailed):
        case.file_claim("d", "k", "К", CreditorKind.COMPETITIVE, make_amounts(D(1)), date(2026, 3, 1), "осн")
    with pytest.raises(ValidationFailed):
        case.file_claim(
            "d", "k", "К", CreditorKind.EMPLOYEE, make_amounts(D(1)), date(2026, 3, 10), "осн", secured=True
        )
    with pytest.raises(ValidationFailed):
        case.file_claim(
            "d", "k", "К", CreditorKind.COMPETITIVE, make_amounts(D(1)), date(2026, 3, 10), "осн", credit_agreement=True
        )
    with pytest.raises(ValidationFailed):
        make_amounts(D(0))
    claim = case.claims["c"]
    assert claim.timely
    assert claim.review_not_before == date(2026, 5, 6)
    assert claim.closing_date == date(2026, 4, 6)
    assert claim.queue is Queue.THIRD


def test_ruling_rules_and_deferred_claims() -> None:
    case = in_observation()
    case.file_claim(
        "ok", "k1", "К1", CreditorKind.COMPETITIVE, make_amounts(D(100), D(10), D(5)), date(2026, 3, 20), "осн"
    )
    case.file_claim("late", "k2", "К2", CreditorKind.COMPETITIVE, make_amounts(D(50)), date(2026, 4, 20), "осн")
    with pytest.raises(ValidationFailed) as early:
        case.rule_on_claim("ok", True, date(2026, 5, 5))
    assert early.value.basis == "127-FZ:71.2"
    with pytest.raises(ValidationFailed):
        case.rule_on_claim("ok", True, date(2026, 3, 1))
    with pytest.raises(ValidationFailed):
        case.rule_on_claim("ok", True, date(2026, 5, 6), make_amounts(D(200)))
    with pytest.raises(TransitionNotAllowed) as deferred:
        case.rule_on_claim("late", True, date(2026, 6, 1))
    assert deferred.value.basis == "127-FZ:71.7"
    case.object_to_claim("ok", "К2", "размер", date(2026, 4, 1))
    case.rule_on_claim("ok", True, date(2026, 5, 6), make_amounts(D(100), D(10)))
    with pytest.raises(TransitionNotAllowed):
        case.rule_on_claim("ok", False, date(2026, 5, 7))
    with pytest.raises(TransitionNotAllowed):
        case.object_to_claim("ok", "К2", "поздно", date(2026, 5, 7))
    with pytest.raises(NotFound):
        case.rule_on_claim("missing", True, date(2026, 5, 7))
    claim = replay(case).claims["ok"]
    assert claim.status is ClaimStatus.INCLUDED
    assert claim.included is not None
    assert claim.included.sanctions == D(0)
    assert claim.objections[0]["objector"] == "К2"
    case.change_phase(Phase.BANKRUPTCY_PROCEEDINGS, date(2026, 7, 1))
    case.rule_on_claim("late", False, date(2026, 7, 2), reason="не доказано")
    assert case.claims["late"].status is ClaimStatus.REJECTED


def test_payments_exclusion_and_sanctions_order() -> None:
    case = with_registry()
    with pytest.raises(ValidationFailed) as error:
        case.record_payment("supplier", make_amounts(D(100), D(0), D(10)), date(2026, 6, 1))
    assert error.value.basis == "127-FZ:137.3"
    with pytest.raises(ValidationFailed):
        case.record_payment("supplier", make_amounts(D(301)), date(2026, 6, 1))
    case.record_payment("supplier", make_amounts(D(300)), date(2026, 6, 1))
    case.record_payment("supplier", make_amounts(D(0), D(0), D(50)), date(2026, 6, 2))
    assert case.claims["supplier"].status is ClaimStatus.SATISFIED
    with pytest.raises(TransitionNotAllowed):
        case.record_payment("supplier", make_amounts(D(1)), date(2026, 6, 3))
    with pytest.raises(ValidationFailed):
        case.exclude_claim("tax", date(2026, 5, 1), "ошибка")
    case.exclude_claim("tax", date(2026, 6, 1), "погашено третьим лицом")
    with pytest.raises(TransitionNotAllowed):
        case.exclude_claim("tax", date(2026, 6, 2), "повторно")
    tax = replay(case).claims["tax"]
    assert tax.status is ClaimStatus.EXCLUDED
    assert tax.in_registry_on(date(2026, 5, 31))
    assert not tax.in_registry_on(date(2026, 6, 1))


def test_after_third_basis_and_late_filing_in_bankruptcy() -> None:
    case = opened()
    case.change_phase(Phase.OBSERVATION, date(2026, 3, 2))
    case.change_phase(Phase.BANKRUPTCY_PROCEEDINGS, date(2026, 6, 1))
    case.record_publication(PublicationKind.BANKRUPTCY_PROCEEDINGS, date(2026, 6, 6))
    case.file_claim("late", "k", "К", CreditorKind.COMPETITIVE, make_amounts(D(10)), date(2026, 8, 7), "осн")
    case.file_claim(
        "void",
        "k2",
        "К2",
        CreditorKind.COMPETITIVE,
        make_amounts(D(10)),
        date(2026, 7, 1),
        "осн",
        after_third=AfterThirdBasis.INVALIDATED_TRANSACTION,
    )
    assert case.claims["late"].queue is Queue.AFTER_THIRD
    assert case.claims["late"].after_third_basis is AfterThirdBasis.LATE_FILING
    assert case.claims["void"].after_third_basis is AfterThirdBasis.INVALIDATED_TRANSACTION


def test_meeting_full_cycle() -> None:
    case = with_registry()
    scheduled_meeting(case, question=Question.ORDINARY)
    meeting = case.meetings["m1"]
    assert meeting.properly_notified
    assert case.meeting_weights(meeting) == {"c-bank": D(600), "c-sup": D(300), "c-fns": D(100)}
    with pytest.raises(ValidationFailed):
        case.register_participant("m1", "c-unknown")
    with pytest.raises(ValidationFailed):
        case.cast_ballot("m1", "i1", "c-bank", Vote.FOR)
    case.register_participant("m1", "c-emp")
    with pytest.raises(ValidationFailed):
        case.cast_ballot("m1", "i1", "c-emp", Vote.FOR)
    case.register_participant("m1", "c-bank")
    with pytest.raises(ValidationFailed):
        case.register_participant("m1", "c-bank")
    case.cast_ballot("m1", "i1", "c-bank", Vote.FOR)
    with pytest.raises(ValidationFailed):
        case.cast_ballot("m1", "i1", "c-bank", Vote.AGAINST)
    with pytest.raises(NotFound):
        case.cast_ballot("m1", "nope", "c-bank", Vote.FOR)
    case.conclude_meeting("m1")
    held = replay(case).meetings["m1"]
    assert held.status is MeetingStatus.HELD
    assert held.quorum is not None
    assert held.quorum["reached"]
    assert held.results[0]["adopted"]
    with pytest.raises(TransitionNotAllowed):
        case.record_notice("m1", NoticeMethod.POST, date(2026, 6, 1), 1)
    with pytest.raises(ValidationFailed):
        case.schedule_meeting("m2", date(2026, 7, 1), [AgendaItem("i", Question.ORDINARY, "в")], first=True)


def test_failed_meeting_and_repeated_quorum() -> None:
    case = with_registry()
    scheduled_meeting(case, first=False)
    case.register_participant("m1", "c-sup")
    case.conclude_meeting("m1")
    assert case.meetings["m1"].status is MeetingStatus.FAILED
    assert case.meetings["m1"].quorum is not None
    assert case.meetings["m1"].quorum["present_votes"] == "300.00"
    assert case.meetings["m1"].results == []
    with pytest.raises(ValidationFailed):
        case.schedule_meeting("m3", date(2026, 7, 1), [AgendaItem("i", Question.ORDINARY, "в")], repeated_of="nope")
    scheduled_meeting(case, "m2", first=False, repeated_of="m1", on=date(2026, 7, 1))
    case.register_participant("m2", "c-sup")
    case.register_participant("m2", "c-fns")
    case.conclude_meeting("m2")
    assert case.meetings["m2"].status is MeetingStatus.HELD
    assert case.meetings["m2"].quorum is not None
    assert case.meetings["m2"].quorum["threshold_percent"] == 30


def test_meeting_validation_and_cancel() -> None:
    case = opened()
    with pytest.raises(TransitionNotAllowed):
        case.schedule_meeting("m", date(2026, 6, 1), [AgendaItem("i", Question.ORDINARY, "в")])
    case = with_registry()
    with pytest.raises(ValidationFailed):
        case.schedule_meeting("m", date(2026, 6, 1), [])
    with pytest.raises(ValidationFailed):
        case.schedule_meeting(
            "m", date(2026, 6, 1), [AgendaItem("i", Question.ORDINARY, "a"), AgendaItem("i", Question.ORDINARY, "b")]
        )
    case.schedule_meeting("m", date(2026, 6, 1), [AgendaItem("i", Question.ORDINARY, "a")])
    with pytest.raises(ValidationFailed):
        case.schedule_meeting("m", date(2026, 6, 1), [AgendaItem("i", Question.ORDINARY, "a")])
    with pytest.raises(ValidationFailed):
        case.record_notice("m", NoticeMethod.POST, date(2026, 5, 1), 0)
    case.record_notice("m", NoticeMethod.POST, date(2026, 5, 30), 2)
    assert not case.meetings["m"].properly_notified
    case.cancel_meeting("m", "перенос")
    assert replay(case).meetings["m"].status is MeetingStatus.CANCELLED
    with pytest.raises(NotFound):
        case.cancel_meeting("zzz", "нет")


def test_secured_creditor_cannot_vote_on_ordinary_question_in_bankruptcy() -> None:
    case = with_registry()
    case.change_phase(Phase.BANKRUPTCY_PROCEEDINGS, date(2026, 7, 1))
    case.schedule_meeting(
        "m",
        date(2026, 8, 1),
        [AgendaItem("i1", Question.ORDINARY, "отчет"), AgendaItem("i2", Question.MANAGER_SELECTION, "АУ")],
    )
    case.register_participant("m", "c-bank")
    with pytest.raises(ValidationFailed) as error:
        case.cast_ballot("m", "i1", "c-bank", Vote.FOR)
    assert error.value.basis == "127-FZ:12.1.secured"
    case.cast_ballot("m", "i2", "c-bank", Vote.FOR)


def test_requisitions() -> None:
    case = opened()
    with pytest.raises(TransitionNotAllowed):
        case.receive_requisition("r", ["c-sup"], date(2026, 6, 1), ["вопрос"])
    case = with_registry()
    with pytest.raises(ValidationFailed):
        case.receive_requisition("r", ["c-sup"], date(2026, 6, 1), [])
    case.receive_requisition("r", ["c-sup"], date(2026, 6, 1), ["отстранение"])
    with pytest.raises(ValidationFailed):
        case.receive_requisition("r", ["c-sup"], date(2026, 6, 1), ["снова"])
    case.receive_requisition("r2", ["nobody"], date(2026, 6, 1), ["вопрос"])
    restored = replay(case)
    assert restored.requisitions["r"].valid
    assert restored.requisitions["r"].hold_by == date(2026, 6, 22)
    assert not restored.requisitions["r2"].valid


def test_rehydrate_reproduces_state_and_version() -> None:
    case = with_registry()
    scheduled_meeting(case)
    restored = replay(case)
    assert restored.version == case.version == len(case.pending)
    assert restored.claims.keys() == case.claims.keys()
    assert restored.organization_id == ORG
