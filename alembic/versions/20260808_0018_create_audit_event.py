"""Create the PRD-017 administrative audit ledger.

Revision ID: 20260808_0018
Revises: 20260808_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260808_0018"
down_revision = "20260808_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("correlation_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('user','system','automation')",
            name="ck_audit_event_actor_type",
        ),
        sa.CheckConstraint("result = 'success'", name="ck_audit_event_result"),
        sa.CheckConstraint(
            "(actor_type = 'user' AND actor_user_id IS NOT NULL "
            "AND actor_role IS NOT NULL) OR (actor_type IN "
            "('system','automation') AND actor_user_id IS NULL "
            "AND actor_role IS NULL)",
            name="ck_audit_event_actor_shape",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_event_org_occurred_id",
        "audit_event",
        ["organization_id", sa.text("occurred_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_audit_event_org_action_occurred",
        "audit_event",
        ["organization_id", "action", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_audit_event_org_actor_occurred",
        "audit_event",
        ["organization_id", "actor_user_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_audit_event_org_resource_occurred",
        "audit_event",
        [
            "organization_id",
            "resource_type",
            "resource_id",
            sa.text("occurred_at DESC"),
        ],
    )


def downgrade() -> None:
    op.drop_table("audit_event")
