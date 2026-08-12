"""Create PRD-019 billing and subscriptions tables.

Revision ID: 20260812_0020
Revises: 20260810_0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260812_0020"
down_revision = "20260810_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_account",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_customer_id", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','inactive')", name="billing_account_status"
        ),
        sa.CheckConstraint("version > 0", name="billing_account_version_positive"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )
    op.create_index(
        "uq_billing_account_provider_customer",
        "billing_account",
        ["provider", "provider_customer_id"],
        unique=True,
        postgresql_where=sa.text("provider_customer_id IS NOT NULL"),
    )
    op.create_table(
        "billing_price",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("plan_definition_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_price_id", sa.String(200), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("interval", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "amount_minor >= 0", name="billing_price_amount_nonnegative"
        ),
        sa.CheckConstraint(
            "length(currency) = 3", name="billing_price_currency_length"
        ),
        sa.CheckConstraint(
            "currency = upper(currency)", name="billing_price_currency_upper"
        ),
        sa.CheckConstraint(
            "interval IN ('monthly','annual')", name="billing_price_interval"
        ),
        sa.CheckConstraint(
            "status IN ('active','retired')", name="billing_price_status"
        ),
        sa.ForeignKeyConstraint(["plan_definition_id"], ["plan_definition.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_price_id"),
    )
    op.create_index(
        "ix_billing_price_plan_definition_id", "billing_price", ["plan_definition_id"]
    )
    op.create_table(
        "subscription",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("billing_account_id", sa.Uuid(), nullable=False),
        sa.Column("billing_price_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_subscription_id", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("provider_status", sa.String(80), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("grace_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_billing_price_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_change_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_state", sa.String(20), nullable=False),
        sa.Column("provider_sequence", sa.BigInteger(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_error_code", sa.String(80), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','active','past_due','suspended','canceled','expired')",
            name="subscription_status",
        ),
        sa.CheckConstraint(
            "payment_state IN ('unknown','pending','paid','failed')",
            name="subscription_payment_state",
        ),
        sa.CheckConstraint("version > 0", name="subscription_version_positive"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["billing_account_id"], ["billing_account.id"]),
        sa.ForeignKeyConstraint(["billing_price_id"], ["billing_price.id"]),
        sa.ForeignKeyConstraint(["pending_billing_price_id"], ["billing_price.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_subscription_one_current_per_org",
        "subscription",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('pending','active','past_due','suspended')"
        ),
    )
    op.create_index(
        "uq_subscription_provider_subscription",
        "subscription",
        ["provider", "provider_subscription_id"],
        unique=True,
        postgresql_where=sa.text("provider_subscription_id IS NOT NULL"),
    )
    op.create_index(
        "ix_subscription_org_updated", "subscription", ["organization_id", "updated_at"]
    )
    op.create_table(
        "billing_provider_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_event_id", sa.String(200), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("subscription_id", sa.Uuid(), nullable=True),
        sa.Column("provider_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("safe_error_code", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('received','processed','ignored','failed')",
            name="billing_provider_event_status",
        ),
        sa.CheckConstraint(
            "attempts > 0", name="billing_provider_event_attempts_positive"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscription.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_event_id"),
    )
    op.create_index(
        "ix_billing_event_status_received",
        "billing_provider_event",
        ["status", "received_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_billing_event_status_received", table_name="billing_provider_event"
    )
    op.drop_table("billing_provider_event")
    op.drop_index("ix_subscription_org_updated", table_name="subscription")
    op.drop_index("uq_subscription_provider_subscription", table_name="subscription")
    op.drop_index("uq_subscription_one_current_per_org", table_name="subscription")
    op.drop_table("subscription")
    op.drop_index("ix_billing_price_plan_definition_id", table_name="billing_price")
    op.drop_table("billing_price")
    op.drop_index("uq_billing_account_provider_customer", table_name="billing_account")
    op.drop_table("billing_account")
