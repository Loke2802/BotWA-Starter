"""add human reply idempotency

Revision ID: 20260730_0012
Revises: 20260730_0011
"""

import sqlalchemy as sa
from alembic import op

revision = "20260730_0012"
down_revision = "20260730_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbound_message_attempt",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.add_column("message", sa.Column("author_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_message_author_user_id_app_user",
        "message",
        "app_user",
        ["author_user_id"],
        ["id"],
    )
    op.create_index("ix_message_author_user_id", "message", ["author_user_id"])
    op.create_index(
        "ix_outbound_message_attempt_idempotency_key",
        "outbound_message_attempt",
        ["idempotency_key"],
    )
    op.create_unique_constraint(
        "uq_outbound_message_attempt_organization_idempotency",
        "outbound_message_attempt",
        ["organization_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_author_user_id", table_name="message")
    op.drop_constraint(
        "fk_message_author_user_id_app_user", "message", type_="foreignkey"
    )
    op.drop_column("message", "author_user_id")
    op.drop_constraint(
        "uq_outbound_message_attempt_organization_idempotency",
        "outbound_message_attempt",
        type_="unique",
    )
    op.drop_index(
        "ix_outbound_message_attempt_idempotency_key",
        table_name="outbound_message_attempt",
    )
    op.drop_column("outbound_message_attempt", "idempotency_key")
