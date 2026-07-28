"""create automation and integration tables

Revision ID: 20260728_0001
Revises: 20260722_0002
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260728_0001"
down_revision: str | None = "20260722_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_execution",
        sa.Column("execution_id", UUID, nullable=False),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("request_data", JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tasks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_tasks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_tasks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("result_data", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "execution_id",
            name=op.f("pk_automation_execution"),
        ),
    )
    op.create_table(
        "automation_task_execution",
        sa.Column("id", UUID, nullable=False),
        sa.Column("execution_id", UUID, nullable=False),
        sa.Column("task_id", UUID, nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("result_data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_automation_task_execution"),
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["automation_execution.execution_id"],
            name=op.f(
                "fk_automation_task_execution_execution_id_automation_execution"
            ),
        ),
    )
    op.create_table(
        "integration_event",
        sa.Column("id", UUID, nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("capability", sa.String(50), nullable=False),
        sa.Column("provider_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("request_id", UUID, nullable=False),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_event")),
    )
    op.create_index(
        op.f("ix_integration_event_event_type"),
        "integration_event",
        ["event_type"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_integration_event_event_type"),
        table_name="integration_event",
    )
    op.drop_table("integration_event")
    op.drop_table("automation_task_execution")
    op.drop_table("automation_execution")
