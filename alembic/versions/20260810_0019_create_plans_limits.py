"""Create PRD-018 plans and limits tables.

Revision ID: 20260810_0019
Revises: 20260808_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260810_0019"
down_revision = "20260808_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_PLAN_ID = "01800000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "plan_definition",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_code", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active','retired')", name="ck_plan_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_code", name="uq_plan_definition_plan_code"),
    )
    op.create_table(
        "organization_plan_assignment",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("plan_definition_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version > 0", name="ck_plan_assignment_version_positive"
        ),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["plan_definition_id"], ["plan_definition.id"]),
        sa.PrimaryKeyConstraint("organization_id"),
    )
    op.create_index(
        "ix_organization_plan_assignment_plan_definition_id",
        "organization_plan_assignment",
        ["plan_definition_id"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO plan_definition
                (id, plan_code, display_name, status, configuration,
                 created_at, updated_at)
            VALUES
                (CAST(:id AS uuid), 'default', 'Default', 'active',
                 CAST(:configuration AS jsonb), CURRENT_TIMESTAMP,
                 CURRENT_TIMESTAMP)
            """
        ).bindparams(
            id=DEFAULT_PLAN_ID,
            configuration='''{
              "features": {
                "analytics": true,
                "analytics_export": true,
                "audit": true,
                "integrations": true,
                "automations": true,
                "human_handoff": true,
                "business_calendar": true,
                "knowledge": true,
                "whatsapp_configuration": true
              },
              "limits": {
                "max_active_bots": {"kind": "unlimited"},
                "max_active_users": {"kind": "unlimited"},
                "max_integrations": {"kind": "unlimited"},
                "max_automations": {"kind": "unlimited"},
                "max_business_calendars": {"kind": "unlimited"},
                "max_whatsapp_configurations": {"kind": "unlimited"},
                "max_knowledge_entries": {"kind": "unlimited"}
              }
            }''',
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO organization_plan_assignment
                (organization_id, plan_definition_id, version,
                 assigned_by_user_id, created_at, updated_at)
            SELECT id, CAST(:plan_id AS uuid), 1, NULL,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM organization
            """
        ).bindparams(plan_id=DEFAULT_PLAN_ID)
    )
    op.create_index(
        "ix_prd018_bot_org_status", "bot", ["organization_id", "status"]
    )
    op.create_index(
        "ix_prd018_user_org_status", "app_user", ["organization_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_prd018_user_org_status", table_name="app_user")
    op.drop_index("ix_prd018_bot_org_status", table_name="bot")
    op.drop_table("organization_plan_assignment")
    op.drop_table("plan_definition")
