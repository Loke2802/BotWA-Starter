"""create contact table

Revision ID: 20260805_0013
Revises: 20260730_0012
"""

import sqlalchemy as sa
from alembic import op

revision = "20260805_0013"
down_revision = "20260730_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("channel_type", sa.String(length=50), nullable=False),
        sa.Column("external_identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("external_identifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("normalized_identifier_version", sa.Integer(), nullable=False),
        sa.Column("display_name_ciphertext", sa.Text(), nullable=True),
        sa.Column("notes_ciphertext", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'archived')", name="contact_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["app_user.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "channel_type",
            "external_identifier_hash",
            name="uq_contact_organization_channel_identity",
        ),
    )
    op.create_index(
        "ix_contact_organization_status", "contact", ["organization_id", "status"]
    )
    op.add_column("conversation", sa.Column("contact_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_conversation_contact_id_contact",
        "conversation",
        "contact",
        ["contact_id"],
        ["id"],
    )
    op.create_index("ix_conversation_contact_id", "conversation", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_conversation_contact_id", table_name="conversation")
    op.drop_constraint(
        "fk_conversation_contact_id_contact", "conversation", type_="foreignkey"
    )
    op.drop_column("conversation", "contact_id")
    op.drop_index("ix_contact_organization_status", table_name="contact")
    op.drop_table("contact")
