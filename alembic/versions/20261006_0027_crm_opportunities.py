"""Conversation-linked commercial opportunities, actions and history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20261006_0027"
down_revision = "20260921_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversation") as batch:
        batch.create_unique_constraint(
            "uq_conversation_crm_contact", ["id", "organization_id", "contact_id"]
        )
    op.create_table(
        "crm_stage",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('open','won','lost')", name=op.f("ck_crm_stage_crm_stage_kind")
        ),
        sa.CheckConstraint(
            "position >= 0", name=op.f("ck_crm_stage_crm_stage_position")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_crm_stage_organization_id_organization"),
        ),
        sa.PrimaryKeyConstraint("organization_id", "code", name=op.f("pk_crm_stage")),
    )
    op.create_table(
        "crm_opportunity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("title_ciphertext", sa.Text(), nullable=False),
        sa.Column("need_ciphertext", sa.Text(), nullable=True),
        sa.Column("stage_code", sa.String(length=40), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=False),
        sa.Column("no_action_reason_ciphertext", sa.Text(), nullable=True),
        sa.Column("close_reason_ciphertext", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(amount IS NULL AND currency IS NULL) OR "
            "(amount IS NOT NULL AND currency IS NOT NULL)",
            name=op.f("ck_crm_opportunity_crm_opportunity_currency"),
        ),
        sa.CheckConstraint(
            "amount IS NULL OR amount >= 0",
            name=op.f("ck_crm_opportunity_crm_opportunity_amount"),
        ),
        sa.CheckConstraint(
            "version > 0", name=op.f("ck_crm_opportunity_crm_opportunity_version")
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id", "organization_id"],
            ["app_user.id", "app_user.organization_id"],
            name="fk_crm_opportunity_assignee",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_crm_opportunity_contact",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_crm_opportunity_created_by_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            name=op.f("fk_crm_opportunity_organization_id_organization"),
        ),
        sa.ForeignKeyConstraint(
            ["stage_code", "organization_id"],
            ["crm_stage.code", "crm_stage.organization_id"],
            name="fk_crm_opportunity_stage",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_opportunity")),
        sa.UniqueConstraint(
            "id", "organization_id", "contact_id", name="uq_crm_opportunity_contact"
        ),
        sa.UniqueConstraint("id", "organization_id", name="uq_crm_opportunity_tenant"),
        sa.UniqueConstraint(
            "organization_id",
            "created_by_user_id",
            "idempotency_key",
            name="uq_crm_opportunity_idempotency",
        ),
    )
    op.create_index(
        "ix_crm_opportunity_contact",
        "crm_opportunity",
        ["organization_id", "contact_id"],
        unique=False,
    )
    op.create_index(
        "ix_crm_opportunity_stage",
        "crm_opportunity",
        ["organization_id", "stage_code", "assigned_user_id"],
        unique=False,
    )
    op.create_table(
        "crm_activity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=False),
        sa.Column("description_ciphertext", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','completed','cancelled')",
            name=op.f("ck_crm_activity_crm_activity_status"),
        ),
        sa.CheckConstraint(
            "version > 0", name=op.f("ck_crm_activity_crm_activity_version")
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id", "organization_id"],
            ["app_user.id", "app_user.organization_id"],
            name="fk_crm_activity_assignee",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "organization_id"],
            ["crm_opportunity.id", "crm_opportunity.organization_id"],
            name="fk_crm_activity_opportunity",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crm_activity")),
        sa.UniqueConstraint(
            "opportunity_id", "version", name="uq_crm_activity_version"
        ),
    )
    op.create_index(
        "ix_crm_activity_due",
        "crm_activity",
        ["organization_id", "status", "due_at"],
        unique=False,
    )
    op.create_table(
        "crm_opportunity_conversation",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.id"],
            name=op.f("fk_crm_opportunity_conversation_actor_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id", "contact_id"],
            [
                "conversation.id",
                "conversation.organization_id",
                "conversation.contact_id",
            ],
            name="fk_crm_link_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "organization_id", "contact_id"],
            [
                "crm_opportunity.id",
                "crm_opportunity.organization_id",
                "crm_opportunity.contact_id",
            ],
            name="fk_crm_link_opportunity",
        ),
        sa.PrimaryKeyConstraint(
            "opportunity_id",
            "conversation_id",
            name=op.f("pk_crm_opportunity_conversation"),
        ),
    )
    op.create_table(
        "crm_opportunity_history",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_ciphertext", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version > 0", name=op.f("ck_crm_opportunity_history_crm_history_version")
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.id"],
            name=op.f("fk_crm_opportunity_history_actor_user_id_app_user"),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id", "organization_id"],
            ["crm_opportunity.id", "crm_opportunity.organization_id"],
            name="fk_crm_history_opportunity",
        ),
        sa.PrimaryKeyConstraint(
            "opportunity_id", "version", name=op.f("pk_crm_opportunity_history")
        ),
    )


def downgrade() -> None:
    # Refuse to destroy any commercial data, including initialized stage config.
    connection = op.get_bind()
    for table in ("crm_opportunity", "crm_stage"):
        if connection.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError(
                "CRM data exists; roll back the application, preserve the schema"
            )
    op.drop_table("crm_opportunity_history")
    op.drop_table("crm_opportunity_conversation")
    op.drop_table("crm_activity")
    op.drop_table("crm_opportunity")
    op.drop_table("crm_stage")
    with op.batch_alter_table("conversation") as batch:
        batch.drop_constraint("uq_conversation_crm_contact", type_="unique")
