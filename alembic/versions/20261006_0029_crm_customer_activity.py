"""Append-only customer activities; preserves existing CRM and AI data."""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0029"
down_revision = "20261006_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_customer_activity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("description_ciphertext", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_customer_activity")),
        sa.ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_crm_journal_contact",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "organization_id", "contact_id"],
            [
                "crm_opportunity.id",
                "crm_opportunity.organization_id",
                "crm_opportunity.contact_id",
            ],
            name="fk_crm_journal_opportunity",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.id"],
            name="fk_crm_journal_actor",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "actor_user_id",
            "idempotency_key",
            name="uq_crm_journal_key",
        ),
        sa.CheckConstraint(
            "kind IN ('call','meeting','note')",
            name=op.f("ck_crm_customer_activity_crm_journal_kind"),
        ),
    )
    op.create_index(
        "ix_crm_journal_customer",
        "crm_customer_activity",
        ["organization_id", "contact_id", "occurred_at"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM crm_customer_activity)")
    ):
        raise RuntimeError(
            "Customer activities exist; preserve the schema "
            "and roll back the application instead"
        )
    op.drop_index("ix_crm_journal_customer", table_name="crm_customer_activity")
    op.drop_table("crm_customer_activity")
