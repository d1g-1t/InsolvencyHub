from enum import StrEnum


class DebtorKind(StrEnum):
    LEGAL_ENTITY = "legal_entity"
    CITIZEN = "citizen"


class Phase(StrEnum):
    PETITION_ACCEPTED = "petition_accepted"
    OBSERVATION = "observation"
    FINANCIAL_RECOVERY = "financial_recovery"
    EXTERNAL_MANAGEMENT = "external_management"
    BANKRUPTCY_PROCEEDINGS = "bankruptcy_proceedings"
    RESTRUCTURING = "restructuring"
    PROPERTY_REALIZATION = "property_realization"
    SETTLEMENT = "settlement"
    TERMINATED = "terminated"
    COMPLETED = "completed"


TERMINAL_PHASES = frozenset({Phase.SETTLEMENT, Phase.TERMINATED, Phase.COMPLETED})


class CreditorKind(StrEnum):
    COMPETITIVE = "competitive"
    AUTHORIZED_BODY = "authorized_body"
    INJURY = "injury"
    ALIMONY = "alimony"
    EMPLOYEE = "employee"
    AUTHOR = "author"


class Queue(StrEnum):
    FIRST = "first"
    SECOND = "second"
    THIRD = "third"
    AFTER_THIRD = "after_third"


class AfterThirdBasis(StrEnum):
    INVALIDATED_TRANSACTION = "invalidated_transaction"
    EXCESS_SEVERANCE = "excess_severance"
    LATE_FILING = "late_filing"


class ClaimStatus(StrEnum):
    FILED = "filed"
    INCLUDED = "included"
    REJECTED = "rejected"
    EXCLUDED = "excluded"
    SATISFIED = "satisfied"


class CurrentPaymentOrder(StrEnum):
    PRIORITY_SAFETY = "priority_safety"
    FIRST = "first"
    SECOND = "second"
    THIRD = "third"
    FOURTH = "fourth"
    FIFTH = "fifth"


class Vote(StrEnum):
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"


class Question(StrEnum):
    ORDINARY = "ordinary"
    FINANCIAL_RECOVERY = "financial_recovery"
    REPAYMENT_SCHEDULE = "repayment_schedule"
    EXTERNAL_MANAGEMENT = "external_management"
    EXTERNAL_MANAGEMENT_PLAN = "external_management_plan"
    BANKRUPTCY_PETITION = "bankruptcy_petition"
    MANAGER_SELECTION = "manager_selection"
    MANAGER_REMOVAL = "manager_removal"
    CREDITORS_COMMITTEE = "creditors_committee"
    COMMITTEE_TERMINATION = "committee_termination"
    ADDITIONAL_AGENDA = "additional_agenda"
    SETTLEMENT = "settlement"
    TRANSITION_TO_EXTERNAL_MANAGEMENT = "transition_to_external_management"
    RESTRUCTURING_PLAN = "restructuring_plan"


class NoticeMethod(StrEnum):
    POST = "post"
    OTHER = "other"
    EFRSB = "efrsb"


class MeetingStatus(StrEnum):
    SCHEDULED = "scheduled"
    HELD = "held"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PublicationKind(StrEnum):
    OBSERVATION = "observation"
    BANKRUPTCY_PROCEEDINGS = "bankruptcy_proceedings"
    RESTRUCTURING = "restructuring"
    PROPERTY_REALIZATION = "property_realization"
    EXTERNAL_MANAGEMENT = "external_management"
    FINANCIAL_RECOVERY = "financial_recovery"
