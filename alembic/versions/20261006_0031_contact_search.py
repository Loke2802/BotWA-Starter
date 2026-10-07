"""Protected exact-search tokens; no changes to historical contact rows."""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0031"
down_revision = "20261006_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_search_state",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("channel_type", sa.String(50), nullable=False),
        sa.Column("identifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("registration_ciphertext", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "organization_id", "contact_id", name=op.f("pk_contact_search_state")
        ),
        sa.ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_contact_search_state_contact",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "contact_search_token",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(5), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "contact_id",
            "field",
            "digest",
            name=op.f("pk_contact_search_token"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contact_search_state.organization_id", "contact_search_state.contact_id"],
            name="fk_contact_search_token_state",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "field IN ('phone', 'email')",
            name=op.f("ck_contact_search_token_contact_search_field"),
        ),
    )
    op.create_index(
        "ix_contact_search_exact",
        "contact_search_token",
        ["organization_id", "field", "digest"],
    )


def downgrade() -> None:
    # Derived data can be regenerated. Contact records and histories are untouched.
    op.drop_table("contact_search_token")
    op.drop_table("contact_search_state")
