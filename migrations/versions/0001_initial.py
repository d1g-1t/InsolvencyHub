from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "case_view",
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("case_number", sa.String(length=32), nullable=False),
        sa.Column("court", sa.String(length=255), nullable=False),
        sa.Column("debtor_kind", sa.String(length=16), nullable=False),
        sa.Column("debtor_name", sa.String(length=255), nullable=False),
        sa.Column("debtor_inn", sa.String(length=12), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("phase_since", sa.Date(), nullable=True),
        sa.Column("manager_name", sa.String(length=255), nullable=True),
        sa.Column("claims_count", sa.Integer(), nullable=False),
        sa.Column("registry_total", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("case_id", name=op.f("pk_case_view")),
    )
    op.create_index(op.f("ix_case_view_organization_id"), "case_view", ["organization_id"], unique=False)
    op.create_table(
        "events",
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("position", name=op.f("pk_events")),
        sa.UniqueConstraint("aggregate_id", "version", name="uq_events_aggregate_version"),
        sa.UniqueConstraint("event_id", name=op.f("uq_events_event_id")),
    )
    op.create_index(op.f("ix_events_aggregate_id"), "events", ["aggregate_id"], unique=False)
    op.create_index(op.f("ix_events_organization_id"), "events", ["organization_id"], unique=False)
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
        sa.UniqueConstraint("event_id", name=op.f("uq_outbox_event_id")),
    )
    op.create_index("ix_outbox_pending", "outbox", ["id"], unique=False, postgresql_where="published_at IS NULL")
    op.create_table(
        "claim_view",
        sa.Column("claim_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("creditor_id", sa.String(length=64), nullable=False),
        sa.Column("creditor_name", sa.String(length=255), nullable=False),
        sa.Column("creditor_kind", sa.String(length=32), nullable=False),
        sa.Column("queue", sa.String(length=16), nullable=False),
        sa.Column("after_third_basis", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("secured", sa.Boolean(), nullable=False),
        sa.Column("timely", sa.Boolean(), nullable=False),
        sa.Column("filed_on", sa.Date(), nullable=False),
        sa.Column("ruling_date", sa.Date(), nullable=True),
        sa.Column("review_not_before", sa.Date(), nullable=True),
        sa.Column("filed_principal", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("filed_interest", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("filed_sanctions", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("included_principal", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("included_interest", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("included_sanctions", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("paid_total", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["case_view.case_id"], name=op.f("fk_claim_view_case_id_case_view"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("claim_id", name=op.f("pk_claim_view")),
    )
    op.create_index(op.f("ix_claim_view_case_id"), "claim_view", ["case_id"], unique=False)
    op.create_index(op.f("ix_claim_view_organization_id"), "claim_view", ["organization_id"], unique=False)
    op.create_table(
        "meeting_view",
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("meeting_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("first", sa.Boolean(), nullable=False),
        sa.Column("agenda", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quorum", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"], ["case_view.case_id"], name=op.f("fk_meeting_view_case_id_case_view"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("meeting_id", name=op.f("pk_meeting_view")),
    )
    op.create_index(op.f("ix_meeting_view_case_id"), "meeting_view", ["case_id"], unique=False)
    op.create_index(op.f("ix_meeting_view_organization_id"), "meeting_view", ["organization_id"], unique=False)
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], name=op.f("fk_users_organization_id_organizations")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_organization_id"), "users", ["organization_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_table("users")
    op.drop_index(op.f("ix_meeting_view_organization_id"), table_name="meeting_view")
    op.drop_index(op.f("ix_meeting_view_case_id"), table_name="meeting_view")
    op.drop_table("meeting_view")
    op.drop_index(op.f("ix_claim_view_organization_id"), table_name="claim_view")
    op.drop_index(op.f("ix_claim_view_case_id"), table_name="claim_view")
    op.drop_table("claim_view")
    op.drop_index("ix_outbox_pending", table_name="outbox", postgresql_where="published_at IS NULL")
    op.drop_table("outbox")
    op.drop_table("organizations")
    op.drop_index(op.f("ix_events_organization_id"), table_name="events")
    op.drop_index(op.f("ix_events_aggregate_id"), table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_case_view_organization_id"), table_name="case_view")
    op.drop_table("case_view")
