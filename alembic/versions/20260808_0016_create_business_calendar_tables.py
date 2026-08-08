"""create business calendar tables

Revision ID: 20260808_0016
Revises: 20260807_0015
"""

import sqlalchemy as sa
from alembic import op

revision = "20260808_0016"
down_revision = "20260807_0015"
branch_labels = None
depends_on = None


def _calendar_tenant_fk(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", "calendar_id"],
        ["business_calendar.organization_id", "business_calendar.id"],
        name=name,
    )


def upgrade() -> None:
    op.create_table(
        "business_calendar",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid()),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("timezone", sa.String(100), nullable=False),
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
            name="business_calendar_status",
        ),
        sa.CheckConstraint("version > 0", name="business_calendar_version_positive"),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_business_calendar_org_id"
        ),
        sa.UniqueConstraint(
            "organization_id", "name", name="uq_business_calendar_org_name"
        ),
    )
    op.create_index(
        "ix_business_calendar_org_status",
        "business_calendar",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "ix_business_calendar_org_bot",
        "business_calendar",
        ["organization_id", "bot_id"],
    )
    op.create_index(
        "uq_business_calendar_active_org_default",
        "business_calendar",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND bot_id IS NULL"),
        sqlite_where=sa.text("status = 'active' AND bot_id IS NULL"),
    )
    op.create_index(
        "uq_business_calendar_active_org_bot",
        "business_calendar",
        ["organization_id", "bot_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND bot_id IS NOT NULL"),
        sqlite_where=sa.text("status = 'active' AND bot_id IS NOT NULL"),
    )

    op.create_table(
        "business_calendar_weekly_interval",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=False),
        sa.Column("end_minute", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        _calendar_tenant_fk("fk_business_weekly_interval_org_calendar"),
        sa.CheckConstraint(
            "weekday BETWEEN 1 AND 7", name="business_weekly_interval_weekday"
        ),
        sa.CheckConstraint(
            "start_minute >= 0 AND start_minute < 1440",
            name="business_weekly_interval_start",
        ),
        sa.CheckConstraint(
            "end_minute > 0 AND end_minute <= 1440",
            name="business_weekly_interval_end",
        ),
        sa.CheckConstraint(
            "start_minute < end_minute", name="business_weekly_interval_order"
        ),
        sa.UniqueConstraint(
            "calendar_id",
            "weekday",
            "start_minute",
            "end_minute",
            name="uq_business_weekly_interval",
        ),
    )
    op.create_index(
        "ix_business_weekly_interval_org_calendar_day",
        "business_calendar_weekly_interval",
        ["organization_id", "calendar_id", "weekday"],
    )

    op.create_table(
        "business_calendar_date_exception",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("intervals", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        _calendar_tenant_fk("fk_business_date_exception_org_calendar"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["app_user.id"]),
        sa.CheckConstraint(
            "mode IN "
            "('closed_all_day','open_all_day','replace','add_open','close_partial')",
            name="business_date_exception_mode",
        ),
        sa.CheckConstraint(
            "version > 0", name="business_date_exception_version_positive"
        ),
        sa.UniqueConstraint(
            "calendar_id", "local_date", name="uq_business_date_exception_date"
        ),
    )
    op.create_index(
        "ix_business_date_exception_org_calendar_date",
        "business_calendar_date_exception",
        ["organization_id", "calendar_id", "local_date"],
    )

    op.create_table(
        "business_calendar_holiday",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("intervals", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("external_reference_hash", sa.String(64)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        _calendar_tenant_fk("fk_business_holiday_org_calendar"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["app_user.id"]),
        sa.CheckConstraint(
            "scope IN ('full_day', 'partial')", name="business_holiday_scope"
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'external_import')",
            name="business_holiday_source",
        ),
        sa.CheckConstraint("version > 0", name="business_holiday_version_positive"),
        sa.UniqueConstraint(
            "calendar_id",
            "local_date",
            "name",
            name="uq_business_holiday_date_name",
        ),
    )
    op.create_index(
        "ix_business_holiday_org_calendar_date",
        "business_calendar_holiday",
        ["organization_id", "calendar_id", "local_date"],
    )
    op.create_index(
        "ix_business_holiday_external_hash",
        "business_calendar_holiday",
        ["organization_id", "external_reference_hash"],
    )

    op.create_table(
        "business_calendar_override",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("revoked_by_user_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        _calendar_tenant_fk("fk_business_override_org_calendar"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["app_user.id"]),
        sa.CheckConstraint(
            "decision IN ('open', 'closed')", name="business_override_decision"
        ),
        sa.CheckConstraint("version > 0", name="business_override_version_positive"),
        sa.CheckConstraint(
            "ends_at IS NULL OR starts_at < ends_at",
            name="business_override_window",
        ),
    )
    op.create_index(
        "ix_business_override_org_calendar_window",
        "business_calendar_override",
        ["organization_id", "calendar_id", "starts_at", "ends_at"],
    )
    op.create_index(
        "ix_business_override_active",
        "business_calendar_override",
        ["calendar_id", "revoked_at", "starts_at"],
    )

    op.create_table(
        "business_calendar_idempotency_receipt",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("command_type", sa.String(80), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("response_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_business_calendar_idempotency_org_key",
        ),
    )
    op.create_index(
        "ix_business_calendar_idempotency_resource",
        "business_calendar_idempotency_receipt",
        ["organization_id", "resource_type", "resource_id"],
    )

    op.create_table(
        "business_calendar_audit_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("previous_version", sa.Integer()),
        sa.Column("new_version", sa.Integer(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        _calendar_tenant_fk("fk_business_audit_org_calendar"),
        sa.ForeignKeyConstraint(["actor_id"], ["app_user.id"]),
    )
    op.create_index(
        "ix_business_audit_org_calendar_created",
        "business_calendar_audit_event",
        ["organization_id", "calendar_id", "created_at"],
    )
    op.create_index(
        "ix_business_audit_correlation",
        "business_calendar_audit_event",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_business_audit_correlation",
        table_name="business_calendar_audit_event",
    )
    op.drop_index(
        "ix_business_audit_org_calendar_created",
        table_name="business_calendar_audit_event",
    )
    op.drop_table("business_calendar_audit_event")
    op.drop_index(
        "ix_business_calendar_idempotency_resource",
        table_name="business_calendar_idempotency_receipt",
    )
    op.drop_table("business_calendar_idempotency_receipt")
    op.drop_index(
        "ix_business_override_active", table_name="business_calendar_override"
    )
    op.drop_index(
        "ix_business_override_org_calendar_window",
        table_name="business_calendar_override",
    )
    op.drop_table("business_calendar_override")
    op.drop_index(
        "ix_business_holiday_external_hash",
        table_name="business_calendar_holiday",
    )
    op.drop_index(
        "ix_business_holiday_org_calendar_date",
        table_name="business_calendar_holiday",
    )
    op.drop_table("business_calendar_holiday")
    op.drop_index(
        "ix_business_date_exception_org_calendar_date",
        table_name="business_calendar_date_exception",
    )
    op.drop_table("business_calendar_date_exception")
    op.drop_index(
        "ix_business_weekly_interval_org_calendar_day",
        table_name="business_calendar_weekly_interval",
    )
    op.drop_table("business_calendar_weekly_interval")
    op.drop_index(
        "uq_business_calendar_active_org_bot",
        table_name="business_calendar",
        if_exists=True,
    )
    op.drop_index(
        "uq_business_calendar_active_org_default",
        table_name="business_calendar",
        if_exists=True,
    )
    op.drop_index("ix_business_calendar_org_bot", table_name="business_calendar")
    op.drop_index("ix_business_calendar_org_status", table_name="business_calendar")
    op.drop_table("business_calendar")
