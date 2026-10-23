from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from insolvency_hub.domain.enums import (
    AfterThirdBasis,
    CreditorKind,
    CurrentPaymentOrder,
    DebtorKind,
    NoticeMethod,
    Phase,
    PublicationKind,
    Question,
    Queue,
    Vote,
)
from insolvency_hub.domain.terms import Direction, Unit

Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
Text = Annotated[str, Field(min_length=1, max_length=500)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(Model):
    email: Annotated[str, Field(min_length=3, max_length=255)]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    user_id: str
    organization_id: str
    role: str


class DebtorIn(Model):
    kind: DebtorKind
    name: Text
    inn: Annotated[str, Field(pattern=r"^\d{10}$|^\d{12}$")]
    ogrn: Annotated[str | None, Field(pattern=r"^\d{13}$|^\d{15}$")] = None


class CaseCreate(Model):
    case_number: Annotated[str, Field(min_length=5, max_length=32)]
    court: Text
    debtor: DebtorIn
    petition_received_on: date


class TransitionIn(Model):
    target: Phase
    court_act_date: date
    hearing_on: date | None = None


class PublicationIn(Model):
    kind: PublicationKind
    published_on: date


class ManagerIn(Model):
    full_name: Text
    sro: Text
    approved_on: date


class AmountsIn(Model):
    principal: Money
    interest: Money = Decimal("0")
    sanctions: Money = Decimal("0")


class ClaimCreate(Model):
    claim_id: Annotated[str | None, Field(max_length=36)] = None
    creditor_id: Annotated[str, Field(min_length=1, max_length=64)]
    creditor_name: Text
    creditor_kind: CreditorKind
    amounts: AmountsIn
    filed_on: date
    grounds: Text
    secured: bool = False
    credit_agreement: bool = False
    after_third_basis: AfterThirdBasis | None = None
    term_restored: bool = False


class ObjectionIn(Model):
    objector: Text
    reason: Text
    filed_on: date


class RulingIn(Model):
    included: bool
    ruling_date: date
    amounts: AmountsIn | None = None
    queue: Queue | None = None
    reason: Annotated[str | None, Field(max_length=500)] = None


class ExclusionIn(Model):
    ruling_date: date
    reason: Text


class PaymentIn(Model):
    amounts: AmountsIn
    paid_on: date


class CurrentPaymentIn(Model):
    payment_id: Annotated[str, Field(min_length=1, max_length=64)]
    order: CurrentPaymentOrder
    amount: Money
    due_date: date


class DistributionIn(Model):
    available: Money
    current_payments: list[CurrentPaymentIn] = Field(default_factory=list)


class CollateralIn(Model):
    proceeds: Money
    claim_id: Annotated[str | None, Field(max_length=36)] = None
    secured_debt: Money | None = None
    credit_agreement: bool = False
    first_second_unpaid: Money = Decimal("0")
    expenses_unpaid: Money = Decimal("0")


class AgendaItemIn(Model):
    item_id: Annotated[str | None, Field(max_length=36)] = None
    question: Question
    title: Text


class MeetingCreate(Model):
    meeting_id: Annotated[str | None, Field(max_length=36)] = None
    meeting_on: date
    agenda: Annotated[list[AgendaItemIn], Field(min_length=1, max_length=50)]
    first: bool = False
    repeated_of: str | None = None
    collateral_sale_refused: bool = False


class NoticeIn(Model):
    method: NoticeMethod
    sent_on: date
    recipients: Annotated[int, Field(ge=1, le=100_000)]


class ParticipantIn(Model):
    creditor_id: Annotated[str, Field(min_length=1, max_length=64)]


class BallotIn(Model):
    item_id: Annotated[str, Field(min_length=1, max_length=36)]
    creditor_id: Annotated[str, Field(min_length=1, max_length=64)]
    vote: Vote


class CancelIn(Model):
    reason: Text


class RequisitionIn(Model):
    requisition_id: Annotated[str | None, Field(max_length=36)] = None
    creditor_ids: Annotated[list[str], Field(max_length=1000)] = Field(default_factory=list)
    received_on: date
    agenda: Annotated[list[Text], Field(min_length=1, max_length=50)]
    by_committee: bool = False


class TermIn(Model):
    start: date
    amount: Annotated[int, Field(ge=0, le=3650)]
    unit: Unit
    direction: Direction = Direction.AFTER


class DebtIn(Model):
    amount: Money
    due_date: date


class PetitionCheckIn(Model):
    debtor_kind: DebtorKind
    filed_on: date
    debts: Annotated[list[DebtIn], Field(min_length=1, max_length=1000)]


class TermOut(BaseModel):
    code: str
    title: str
    start: date
    due: date
    nominal_due: date
    shifted: bool
    unit: Unit
    amount: int
    direction: Direction
    status: str
    calendar_verified: bool
    basis: list[str]


class CommandOut(BaseModel):
    case_id: str
    version: int
    phase: Phase
    events: list[str]
    data: dict[str, Any] = Field(default_factory=dict)
