from dataclasses import dataclass

from insolvency_hub.domain.enums import DebtorKind, Phase, PublicationKind
from insolvency_hub.domain.terms import Unit

P = Phase


@dataclass(frozen=True, slots=True)
class Transition:
    source: Phase
    target: Phase
    basis: str


@dataclass(frozen=True, slots=True)
class Duration:
    amount: int
    unit: Unit
    basis: str
    extension: int | None = None


_LEGAL_ENTITY = (
    Transition(P.PETITION_ACCEPTED, P.OBSERVATION, "ст. 62 127-ФЗ"),
    Transition(P.PETITION_ACCEPTED, P.TERMINATED, "ст. 57 127-ФЗ"),
    Transition(P.OBSERVATION, P.FINANCIAL_RECOVERY, "ст. 75, 80 127-ФЗ"),
    Transition(P.OBSERVATION, P.EXTERNAL_MANAGEMENT, "ст. 75, 93 127-ФЗ"),
    Transition(P.OBSERVATION, P.BANKRUPTCY_PROCEEDINGS, "ст. 53, 75 127-ФЗ"),
    Transition(P.OBSERVATION, P.SETTLEMENT, "ст. 151, 159 127-ФЗ"),
    Transition(P.OBSERVATION, P.TERMINATED, "ст. 57 127-ФЗ"),
    Transition(P.FINANCIAL_RECOVERY, P.EXTERNAL_MANAGEMENT, "ст. 92 127-ФЗ"),
    Transition(P.FINANCIAL_RECOVERY, P.BANKRUPTCY_PROCEEDINGS, "ст. 87, 88 127-ФЗ"),
    Transition(P.FINANCIAL_RECOVERY, P.SETTLEMENT, "ст. 152, 159 127-ФЗ"),
    Transition(P.FINANCIAL_RECOVERY, P.TERMINATED, "ст. 57, 88 127-ФЗ"),
    Transition(P.EXTERNAL_MANAGEMENT, P.BANKRUPTCY_PROCEEDINGS, "ст. 119 127-ФЗ"),
    Transition(P.EXTERNAL_MANAGEMENT, P.SETTLEMENT, "ст. 153, 159 127-ФЗ"),
    Transition(P.EXTERNAL_MANAGEMENT, P.TERMINATED, "ст. 57, 119 127-ФЗ"),
    Transition(P.BANKRUPTCY_PROCEEDINGS, P.EXTERNAL_MANAGEMENT, "ст. 146 127-ФЗ"),
    Transition(P.BANKRUPTCY_PROCEEDINGS, P.SETTLEMENT, "ст. 154, 159 127-ФЗ"),
    Transition(P.BANKRUPTCY_PROCEEDINGS, P.COMPLETED, "ст. 149 127-ФЗ"),
    Transition(P.BANKRUPTCY_PROCEEDINGS, P.TERMINATED, "ст. 57 127-ФЗ"),
)

_CITIZEN = (
    Transition(P.PETITION_ACCEPTED, P.RESTRUCTURING, "ст. 213.6 127-ФЗ"),
    Transition(P.PETITION_ACCEPTED, P.PROPERTY_REALIZATION, "п. 8 ст. 213.6 127-ФЗ"),
    Transition(P.PETITION_ACCEPTED, P.TERMINATED, "ст. 57 127-ФЗ"),
    Transition(P.RESTRUCTURING, P.PROPERTY_REALIZATION, "ст. 213.24 127-ФЗ"),
    Transition(P.RESTRUCTURING, P.SETTLEMENT, "ст. 213.31 127-ФЗ"),
    Transition(P.RESTRUCTURING, P.COMPLETED, "п. 5 ст. 213.22 127-ФЗ"),
    Transition(P.RESTRUCTURING, P.TERMINATED, "ст. 57 127-ФЗ"),
    Transition(P.PROPERTY_REALIZATION, P.SETTLEMENT, "ст. 213.31 127-ФЗ"),
    Transition(P.PROPERTY_REALIZATION, P.COMPLETED, "ст. 213.28 127-ФЗ"),
    Transition(P.PROPERTY_REALIZATION, P.TERMINATED, "ст. 57 127-ФЗ"),
)

TRANSITIONS: dict[DebtorKind, dict[tuple[Phase, Phase], Transition]] = {
    DebtorKind.LEGAL_ENTITY: {(t.source, t.target): t for t in _LEGAL_ENTITY},
    DebtorKind.CITIZEN: {(t.source, t.target): t for t in _CITIZEN},
}

DURATIONS: dict[Phase, Duration] = {
    P.FINANCIAL_RECOVERY: Duration(24, Unit.MONTHS, "127-FZ:80.6"),
    P.EXTERNAL_MANAGEMENT: Duration(18, Unit.MONTHS, "127-FZ:93.2", extension=6),
    P.BANKRUPTCY_PROCEEDINGS: Duration(6, Unit.MONTHS, "127-FZ:124.2", extension=6),
    P.PROPERTY_REALIZATION: Duration(6, Unit.MONTHS, "127-FZ:213.24.2", extension=6),
}

PUBLICATION_FOR_PHASE: dict[Phase, PublicationKind] = {
    P.OBSERVATION: PublicationKind.OBSERVATION,
    P.FINANCIAL_RECOVERY: PublicationKind.FINANCIAL_RECOVERY,
    P.EXTERNAL_MANAGEMENT: PublicationKind.EXTERNAL_MANAGEMENT,
    P.BANKRUPTCY_PROCEEDINGS: PublicationKind.BANKRUPTCY_PROCEEDINGS,
    P.RESTRUCTURING: PublicationKind.RESTRUCTURING,
    P.PROPERTY_REALIZATION: PublicationKind.PROPERTY_REALIZATION,
}

CLAIM_PHASES = frozenset(PUBLICATION_FOR_PHASE)
MEETING_PHASES = frozenset(
    {
        P.OBSERVATION,
        P.FINANCIAL_RECOVERY,
        P.EXTERNAL_MANAGEMENT,
        P.BANKRUPTCY_PROCEEDINGS,
        P.RESTRUCTURING,
        P.PROPERTY_REALIZATION,
    }
)


def initial_phase() -> Phase:
    return P.PETITION_ACCEPTED


def find_transition(kind: DebtorKind, source: Phase, target: Phase) -> Transition | None:
    return TRANSITIONS[kind].get((source, target))


def allowed_targets(kind: DebtorKind, source: Phase) -> list[Phase]:
    return [t.target for (s, _), t in TRANSITIONS[kind].items() if s == source]
