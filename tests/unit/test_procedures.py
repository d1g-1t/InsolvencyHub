import pytest

from insolvency_hub.domain.enums import TERMINAL_PHASES, DebtorKind, Phase
from insolvency_hub.domain.procedures import (
    CLAIM_PHASES,
    DURATIONS,
    MEETING_PHASES,
    TRANSITIONS,
    allowed_targets,
    find_transition,
    initial_phase,
)
from insolvency_hub.domain.terms import Unit


def test_initial_phase() -> None:
    assert initial_phase() is Phase.PETITION_ACCEPTED


@pytest.mark.parametrize(
    ("kind", "source", "target", "allowed"),
    [
        (DebtorKind.LEGAL_ENTITY, Phase.PETITION_ACCEPTED, Phase.OBSERVATION, True),
        (DebtorKind.LEGAL_ENTITY, Phase.OBSERVATION, Phase.BANKRUPTCY_PROCEEDINGS, True),
        (DebtorKind.LEGAL_ENTITY, Phase.BANKRUPTCY_PROCEEDINGS, Phase.EXTERNAL_MANAGEMENT, True),
        (DebtorKind.LEGAL_ENTITY, Phase.PETITION_ACCEPTED, Phase.RESTRUCTURING, False),
        (DebtorKind.CITIZEN, Phase.PETITION_ACCEPTED, Phase.OBSERVATION, False),
        (DebtorKind.CITIZEN, Phase.RESTRUCTURING, Phase.PROPERTY_REALIZATION, True),
        (DebtorKind.CITIZEN, Phase.PROPERTY_REALIZATION, Phase.RESTRUCTURING, False),
    ],
)
def test_transitions(kind: DebtorKind, source: Phase, target: Phase, allowed: bool) -> None:
    assert (find_transition(kind, source, target) is not None) is allowed
    assert (target in allowed_targets(kind, source)) is allowed


def test_terminal_phases_have_no_exits() -> None:
    for kind in DebtorKind:
        for phase in TERMINAL_PHASES:
            assert allowed_targets(kind, phase) == []


def test_every_transition_has_basis() -> None:
    for table in TRANSITIONS.values():
        for transition in table.values():
            assert "127-ФЗ" in transition.basis


def test_durations() -> None:
    assert DURATIONS[Phase.FINANCIAL_RECOVERY].amount == 24
    assert DURATIONS[Phase.EXTERNAL_MANAGEMENT].amount == 18
    assert DURATIONS[Phase.EXTERNAL_MANAGEMENT].extension == 6
    assert DURATIONS[Phase.BANKRUPTCY_PROCEEDINGS].amount == 6
    assert DURATIONS[Phase.PROPERTY_REALIZATION].unit is Unit.MONTHS


def test_phase_sets() -> None:
    assert Phase.PETITION_ACCEPTED not in CLAIM_PHASES
    assert CLAIM_PHASES <= MEETING_PHASES
