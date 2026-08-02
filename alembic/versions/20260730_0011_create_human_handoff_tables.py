"""create human handoff tables

Revision ID: 20260730_0011
Revises: 20260730_0010
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_0011"
down_revision = "20260730_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "handoff_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('bot_active', 'waiting_human', 'human_active', 'resolved')",
            name="handoff_session_status",
        ),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["bot_id"], ["bot.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", name="uq_handoff_session_conversation"),
    )
    op.create_index(
        "ix_handoff_session_org_status_activity",
        "handoff_session",
        ["organization_id", "status", "last_activity_at"],
    )
    op.create_index(
        "ix_handoff_session_assigned_user_id", "handoff_session", ["assigned_user_id"]
    )
    op.create_table(
        "handoff_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("handoff_session_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["handoff_session_id"], ["handoff_session.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_handoff_event_session_created",
        "handoff_event",
        ["handoff_session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_handoff_event_session_created", table_name="handoff_event")
    op.drop_table("handoff_event")
    op.drop_index("ix_handoff_session_assigned_user_id", table_name="handoff_session")
    op.drop_index(
        "ix_handoff_session_org_status_activity", table_name="handoff_session"
    )
    op.drop_table("handoff_session")
