"""Add protected partial-name and duplicate-name indexes without changing contacts."""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0032"
down_revision = "20261006_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_name_state",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("name_ciphertext", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "organization_id", "contact_id", name=op.f("pk_contact_name_state")
        ),
        sa.ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_contact_name_state_contact",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "contact_name_token",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(5), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "contact_id",
            "kind",
            "digest",
            name=op.f("pk_contact_name_token"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contact_name_state.organization_id", "contact_name_state.contact_id"],
            name="fk_contact_name_token_state",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('gram', 'exact')",
            name=op.f("ck_contact_name_token_contact_name_kind"),
        ),
    )
    op.create_index(
        "ix_contact_name_lookup",
        "contact_name_token",
        ["organization_id", "kind", "digest"],
    )


def downgrade() -> None:
    op.drop_table("contact_name_token")
    op.drop_table("contact_name_state")
