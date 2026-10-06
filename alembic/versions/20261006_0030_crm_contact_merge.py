"""Reviewed customer merges with preserved source identities."""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0030"
down_revision = "20261006_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_contact_merge",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_ciphertext", sa.Text(), nullable=False),
        sa.Column("review_token", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_id", name=op.f("pk_crm_contact_merge")),
        sa.ForeignKeyConstraint(
            ["source_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_crm_merge_source",
        ),
        sa.ForeignKeyConstraint(
            ["target_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_crm_merge_target",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app_user.id"],
            name=op.f("fk_crm_contact_merge_actor_user_id_app_user"),
        ),
        sa.CheckConstraint(
            "source_id <> target_id",
            name=op.f("ck_crm_contact_merge_crm_merge_distinct"),
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM crm_contact_merge)")):
        raise RuntimeError(
            "Merged customers exist; preserve the schema "
            "and roll back the application instead"
        )
    op.drop_table("crm_contact_merge")
