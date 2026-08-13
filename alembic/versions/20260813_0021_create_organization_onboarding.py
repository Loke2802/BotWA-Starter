"""Create PRD-020 organization onboarding workflow table.

Revision ID: 20260813_0021
Revises: 20260812_0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260813_0021"
down_revision = "20260812_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organization_onboarding",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('in_progress','completed')",
            name="organization_onboarding_status",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="organization_onboarding_version_positive",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL "
            "AND completed_by_user_id IS NOT NULL) OR "
            "(status = 'in_progress' AND completed_at IS NULL "
            "AND completed_by_user_id IS NULL)",
            name="organization_onboarding_completion_shape",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="organization_onboarding_completion_order",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("organization_id"),
    )


def downgrade() -> None:
    op.drop_table("organization_onboarding")
