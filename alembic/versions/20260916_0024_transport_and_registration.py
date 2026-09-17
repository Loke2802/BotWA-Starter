"""Durable transport ownership and independent registration evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260916_0024"
down_revision = "20260916_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Legacy attempts have no durable owner and may already have reached Meta.
    # They also lack a reliable notification discriminator. Preserve their
    # ciphertext for review instead of auto-replaying them under the new worker.
    op.execute(
        sa.text(
            "UPDATE outbound_message_attempt SET status = 'failed', "
            "last_error_code = 'LEGACY_DELIVERY_REVIEW', next_attempt_at = NULL "
            "WHERE status = 'pending'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE message SET delivery_status = 'failed' "
            "WHERE outbound_attempt_id IN "
            "(SELECT id FROM outbound_message_attempt "
            "WHERE last_error_code = 'LEGACY_DELIVERY_REVIEW')"
        )
    )
    op.add_column(
        "contact", sa.Column("registration_ciphertext", sa.Text(), nullable=True)
    )
    op.add_column(
        "inbound_message_receipt",
        sa.Column("payload_ciphertext", sa.Text(), nullable=True),
    )
    op.add_column(
        "inbound_message_receipt",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbound_message_attempt",
        sa.Column("delivery_token", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "outbound_message_attempt",
        sa.Column("delivery_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "outbound_message_attempt",
        sa.Column(
            "notification", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index(
        "ix_inbound_recovery", "inbound_message_receipt", ["status", "next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_inbound_recovery", table_name="inbound_message_receipt")
    for table, names in (
        (
            "outbound_message_attempt",
            ("notification", "delivery_started_at", "delivery_token"),
        ),
        ("inbound_message_receipt", ("next_attempt_at", "payload_ciphertext")),
        ("contact", ("registration_ciphertext",)),
    ):
        with op.batch_alter_table(table) as batch:
            for name in names:
                batch.drop_column(name)
