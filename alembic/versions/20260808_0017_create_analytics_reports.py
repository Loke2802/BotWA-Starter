"""Create PRD-016 historical analytics sources and daily projection.

Revision ID: 20260808_0017
Revises: 20260808_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260808_0017"
down_revision = "20260808_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_management_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "from_status IN ('open','closed','archived')",
            name="ck_conversation_management_event_conversation_management_event_from_status",
        ),
        sa.CheckConstraint(
            "to_status IN ('open','closed','archived')",
            name="ck_conversation_management_event_conversation_management_event_to_status",
        ),
        sa.CheckConstraint(
            "actor_type IN ('user','system','automation')",
            name="ck_conversation_management_event_conversation_management_event_actor_type",
        ),
        sa.ForeignKeyConstraint(["bot_id"], ["bot.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_management_event_org_occurred",
        "conversation_management_event",
        ["organization_id", "occurred_at"],
    )
    op.create_index(
        "ix_conversation_management_event_org_bot_occurred",
        "conversation_management_event",
        ["organization_id", "bot_id", "occurred_at"],
    )
    op.create_index(
        "ix_conversation_management_event_conversation_occurred",
        "conversation_management_event",
        ["conversation_id", "occurred_at"],
    )

    op.create_table(
        "handoff_cycle",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("handoff_session_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_type", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "resolution_type IS NULL OR resolution_type IN ('resolved','returned_to_bot')",
            name="ck_handoff_cycle_handoff_cycle_resolution_type",
        ),
        sa.CheckConstraint(
            "activated_at IS NULL OR activated_at >= requested_at",
            name="ck_handoff_cycle_handoff_cycle_activated_after_request",
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= requested_at",
            name="ck_handoff_cycle_handoff_cycle_resolved_after_request",
        ),
        sa.ForeignKeyConstraint(["bot_id"], ["bot.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
        sa.ForeignKeyConstraint(["handoff_session_id"], ["handoff_session.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_handoff_cycle_org_requested",
        "handoff_cycle",
        ["organization_id", "requested_at"],
    )
    op.create_index(
        "ix_handoff_cycle_org_bot_requested",
        "handoff_cycle",
        ["organization_id", "bot_id", "requested_at"],
    )
    op.create_index(
        "ix_handoff_cycle_org_resolved",
        "handoff_cycle",
        ["organization_id", "resolved_at"],
    )
    op.create_index(
        "uq_handoff_cycle_open_session",
        "handoff_cycle",
        ["handoff_session_id"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
        sqlite_where=sa.text("resolved_at IS NULL"),
    )

    op.create_table(
        "analytics_daily_summary",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=True),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        *[
            sa.Column(name, sa.BigInteger(), nullable=False, server_default="0")
            for name in (
                "conversations_started",
                "conversations_closed",
                "handoffs_created",
                "handoffs_resolved",
                "handoff_resolution_seconds_sum",
                "handoff_resolution_count",
                "automation_executions_created",
                "automation_succeeded",
                "automation_failed",
                "automation_skipped",
                "automation_cancelled",
                "contacts_created",
            )
        ],
        sa.Column("source_watermark_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "conversations_started >= 0 AND conversations_closed >= 0 AND handoffs_created >= 0 AND handoffs_resolved >= 0 AND handoff_resolution_seconds_sum >= 0 AND handoff_resolution_count >= 0 AND automation_executions_created >= 0 AND automation_succeeded >= 0 AND automation_failed >= 0 AND automation_skipped >= 0 AND automation_cancelled >= 0 AND contacts_created >= 0",
            name="ck_analytics_daily_summary_analytics_daily_summary_nonnegative",
        ),
        sa.ForeignKeyConstraint(["bot_id"], ["bot.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analytics_daily_summary_org_date",
        "analytics_daily_summary",
        ["organization_id", "local_date"],
    )
    op.create_index(
        "ix_analytics_daily_summary_org_bot_date",
        "analytics_daily_summary",
        ["organization_id", "bot_id", "local_date"],
    )
    op.create_index(
        "uq_analytics_daily_summary_bot",
        "analytics_daily_summary",
        ["organization_id", "bot_id", "local_date"],
        unique=True,
        postgresql_where=sa.text("bot_id IS NOT NULL"),
        sqlite_where=sa.text("bot_id IS NOT NULL"),
    )
    op.create_index(
        "uq_analytics_daily_summary_organization",
        "analytics_daily_summary",
        ["organization_id", "local_date"],
        unique=True,
        postgresql_where=sa.text("bot_id IS NULL"),
        sqlite_where=sa.text("bot_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("analytics_daily_summary")
    op.drop_table("handoff_cycle")
    op.drop_table("conversation_management_event")
