"""create managed automation tables

Revision ID: 20260807_0014
Revises: 20260805_0013
"""

import sqlalchemy as sa
from alembic import op

revision = "20260807_0014"
down_revision = "20260805_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_automation_definition",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid()),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("trigger_type", sa.String(80), nullable=False),
        sa.Column("conditions_data", sa.JSON(), nullable=False),
        sa.Column("action_type", sa.String(80), nullable=False),
        sa.Column("action_data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("deactivated_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["bot_id"], ["bot.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["app_user.id"]),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'inactive', 'archived')",
            name="managed_automation_definition_status",
        ),
    )
    op.create_index(
        "ix_managed_automation_definition_org_status",
        "managed_automation_definition",
        ["organization_id", "status", "created_at", "id"],
    )
    op.create_index(
        "ix_managed_automation_definition_org_bot",
        "managed_automation_definition",
        ["organization_id", "bot_id"],
    )
    op.create_index(
        "ix_managed_automation_definition_org_trigger",
        "managed_automation_definition",
        ["organization_id", "trigger_type"],
    )
    op.create_table(
        "managed_automation_event_receipt",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("event_data", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("causation_id", sa.Uuid()),
        sa.Column("source_automation_id", sa.Uuid()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["bot_id"], ["bot.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "source_type",
            "source_event_id",
            name="uq_managed_automation_event_source",
        ),
    )
    op.create_index(
        "ix_managed_automation_event_org_created",
        "managed_automation_event_receipt",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_managed_automation_event_org_type",
        "managed_automation_event_receipt",
        ["organization_id", "event_type"],
    )
    op.create_index(
        "ix_managed_automation_event_source",
        "managed_automation_event_receipt",
        ["organization_id", "source_type", "source_event_id"],
    )
    op.create_table(
        "managed_automation_execution",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("automation_definition_id", sa.Uuid(), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("event_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("definition_snapshot", sa.JSON(), nullable=False),
        sa.Column("event_snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("safe_error_code", sa.String(100)),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("causation_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(
            ["automation_definition_id"], ["managed_automation_definition.id"]
        ),
        sa.ForeignKeyConstraint(
            ["event_receipt_id"], ["managed_automation_event_receipt.id"]
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','succeeded','failed','skipped','cancelled')",
            name="managed_automation_execution_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= 3",
            name="managed_automation_execution_attempt_count",
        ),
        sa.UniqueConstraint(
            "automation_definition_id",
            "definition_version",
            "event_receipt_id",
            name="uq_managed_automation_execution_event",
        ),
    )
    op.create_index(
        "ix_managed_automation_execution_claim",
        "managed_automation_execution",
        ["status", "available_at", "lease_expires_at"],
    )
    op.create_index(
        "ix_managed_automation_execution_org_status",
        "managed_automation_execution",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_managed_automation_execution_definition_created",
        "managed_automation_execution",
        ["automation_definition_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_managed_automation_execution_definition_created",
        table_name="managed_automation_execution",
    )
    op.drop_index(
        "ix_managed_automation_execution_org_status",
        table_name="managed_automation_execution",
    )
    op.drop_index(
        "ix_managed_automation_execution_claim",
        table_name="managed_automation_execution",
    )
    op.drop_table("managed_automation_execution")
    op.drop_index(
        "ix_managed_automation_event_source",
        table_name="managed_automation_event_receipt",
    )
    op.drop_index(
        "ix_managed_automation_event_org_type",
        table_name="managed_automation_event_receipt",
    )
    op.drop_index(
        "ix_managed_automation_event_org_created",
        table_name="managed_automation_event_receipt",
    )
    op.drop_table("managed_automation_event_receipt")
    op.drop_index(
        "ix_managed_automation_definition_org_trigger",
        table_name="managed_automation_definition",
    )
    op.drop_index(
        "ix_managed_automation_definition_org_bot",
        table_name="managed_automation_definition",
    )
    op.drop_index(
        "ix_managed_automation_definition_org_status",
        table_name="managed_automation_definition",
    )
    op.drop_table("managed_automation_definition")
