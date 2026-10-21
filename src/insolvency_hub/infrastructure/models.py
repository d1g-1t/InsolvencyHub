from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

AMOUNT = Numeric(18, 2)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StoredEvent(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("aggregate_id", "version", name="uq_events_aggregate_version"),)

    position: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    aggregate_id: Mapped[str] = mapped_column(String(36), index=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(String(36))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutboxMessage(Base):
    __tablename__ = "outbox"
    __table_args__ = (Index("ix_outbox_pending", "id", postgresql_where="published_at IS NULL"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True)
    aggregate_id: Mapped[str] = mapped_column(String(36))
    organization_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class CaseView(Base):
    __tablename__ = "case_view"

    case_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    case_number: Mapped[str] = mapped_column(String(32))
    court: Mapped[str] = mapped_column(String(255))
    debtor_kind: Mapped[str] = mapped_column(String(16))
    debtor_name: Mapped[str] = mapped_column(String(255))
    debtor_inn: Mapped[str] = mapped_column(String(12))
    phase: Mapped[str] = mapped_column(String(32))
    phase_since: Mapped[date | None] = mapped_column(Date)
    manager_name: Mapped[str | None] = mapped_column(String(255))
    claims_count: Mapped[int] = mapped_column(Integer, default=0)
    registry_total: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))
    version: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimView(Base):
    __tablename__ = "claim_view"

    claim_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("case_view.case_id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    creditor_id: Mapped[str] = mapped_column(String(64))
    creditor_name: Mapped[str] = mapped_column(String(255))
    creditor_kind: Mapped[str] = mapped_column(String(32))
    queue: Mapped[str] = mapped_column(String(16))
    after_third_basis: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    secured: Mapped[bool] = mapped_column(Boolean)
    timely: Mapped[bool] = mapped_column(Boolean)
    filed_on: Mapped[date] = mapped_column(Date)
    ruling_date: Mapped[date | None] = mapped_column(Date)
    review_not_before: Mapped[date | None] = mapped_column(Date)
    filed_principal: Mapped[Decimal] = mapped_column(AMOUNT)
    filed_interest: Mapped[Decimal] = mapped_column(AMOUNT)
    filed_sanctions: Mapped[Decimal] = mapped_column(AMOUNT)
    included_principal: Mapped[Decimal | None] = mapped_column(AMOUNT)
    included_interest: Mapped[Decimal | None] = mapped_column(AMOUNT)
    included_sanctions: Mapped[Decimal | None] = mapped_column(AMOUNT)
    paid_total: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal("0"))


class MeetingView(Base):
    __tablename__ = "meeting_view"

    meeting_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("case_view.case_id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    meeting_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16))
    first: Mapped[bool] = mapped_column(Boolean)
    agenda: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    quorum: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
