"""create integration management tables

Revision ID: 20260807_0015
Revises: 20260807_0014
"""

import sqlalchemy as sa
from alembic import op

revision = "20260807_0015"
down_revision = "20260807_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_connection",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid()),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("integration_type", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("health_status", sa.String(20), nullable=False),
        sa.Column("last_health_checked_at", sa.DateTime(timezone=True)),
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
            name="integration_connection_status",
        ),
        sa.CheckConstraint(
            "integration_type IN ('calendar', 'crm', 'erp', 'custom_api')",
            name="integration_connection_type",
        ),
        sa.CheckConstraint(
            "provider IN ('google_calendar')",
            name="integration_connection_provider",
        ),
        sa.CheckConstraint(
            "health_status IN "
            "('unknown', 'healthy', 'degraded', 'unreachable', 'auth_error')",
            name="integration_connection_health_status",
        ),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_integration_connection_org_name"
        ),
    )
    op.create_index(
        "ix_integration_connection_org_status",
        "integration_connection",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "ix_integration_connection_org_provider_status",
        "integration_connection",
        ["organization_id", "provider", "status"],
    )
    op.create_index(
        "ix_integration_connection_org_bot",
        "integration_connection",
        ["organization_id", "bot_id"],
    )

    op.create_table(
        "integration_credential",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("integration_connection_id", sa.Uuid(), nullable=False),
        sa.Column("credential_type", sa.String(50), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("key_version", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(
            ["integration_connection_id"], ["integration_connection.id"]
        ),
        sa.CheckConstraint(
            "credential_type = 'google_oauth_refresh'",
            name="integration_credential_type",
        ),
        sa.UniqueConstraint(
            "integration_connection_id",
            name="uq_integration_credential_connection",
        ),
    )
    op.create_index(
        "ix_integration_credential_org_connection",
        "integration_credential",
        ["organization_id", "integration_connection_id"],
    )

    op.create_table(
        "integration_health_check",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("integration_connection_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("safe_error_code", sa.String(80)),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(
            ["integration_connection_id"], ["integration_connection.id"]
        ),
        sa.CheckConstraint(
            "status IN "
            "('unknown', 'healthy', 'degraded', 'unreachable', 'auth_error')",
            name="integration_health_check_status",
        ),
        sa.CheckConstraint(
            "safe_error_code IS NULL OR safe_error_code IN "
            "('INTEGRATION_AUTH_REQUIRED','INTEGRATION_AUTH_FAILED',"
            "'INTEGRATION_UNREACHABLE','INTEGRATION_PROVIDER_ERROR',"
            "'INTEGRATION_CONFIGURATION_INVALID','INTEGRATION_NOT_ACTIVE',"
            "'INTEGRATION_CREDENTIAL_INVALID')",
            name="integration_health_check_safe_error",
        ),
    )
    op.create_index(
        "ix_integration_health_connection_checked",
        "integration_health_check",
        ["integration_connection_id", "checked_at"],
    )
    op.create_index(
        "ix_integration_health_org_checked",
        "integration_health_check",
        ["organization_id", "checked_at"],
    )

    op.create_table(
        "integration_oauth_state",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("integration_connection_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(
            ["integration_connection_id"], ["integration_connection.id"]
        ),
        sa.CheckConstraint(
            "provider = 'google_calendar'",
            name="integration_oauth_state_provider",
        ),
        sa.UniqueConstraint("nonce_hash", name="uq_integration_oauth_state_nonce"),
    )
    op.create_index(
        "ix_integration_oauth_state_org_integration",
        "integration_oauth_state",
        ["organization_id", "integration_connection_id"],
    )
    op.create_index(
        "ix_integration_oauth_state_expires",
        "integration_oauth_state",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_integration_oauth_state_expires", table_name="integration_oauth_state"
    )
    op.drop_index(
        "ix_integration_oauth_state_org_integration",
        table_name="integration_oauth_state",
    )
    op.drop_table("integration_oauth_state")
    op.drop_index(
        "ix_integration_health_org_checked", table_name="integration_health_check"
    )
    op.drop_index(
        "ix_integration_health_connection_checked",
        table_name="integration_health_check",
    )
    op.drop_table("integration_health_check")
    op.drop_index(
        "ix_integration_credential_org_connection",
        table_name="integration_credential",
    )
    op.drop_table("integration_credential")
    op.drop_index(
        "ix_integration_connection_org_bot", table_name="integration_connection"
    )
    op.drop_index(
        "ix_integration_connection_org_provider_status",
        table_name="integration_connection",
    )
    op.drop_index(
        "ix_integration_connection_org_status", table_name="integration_connection"
    )
    op.drop_table("integration_connection")
