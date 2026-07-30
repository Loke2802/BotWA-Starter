"""extend conversations for multi-tenant administration

Revision ID: 20260730_0010
Revises: 20260730_0009
Create Date: 2026-07-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260730_0010"
down_revision: str | None = "20260730_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversation", sa.Column("organization_id", UUID, nullable=True))
    op.add_column("conversation", sa.Column("bot_id", UUID, nullable=True))
    op.add_column("conversation", sa.Column("channel_configuration_id", UUID, nullable=True))
    op.add_column("conversation", sa.Column("external_customer_id", sa.String(255), nullable=True))
    op.add_column("conversation", sa.Column("masked_customer_identifier", sa.String(255), nullable=True))
    op.add_column("conversation", sa.Column("management_status", sa.String(20), nullable=True))
    op.add_column("conversation", sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversation", sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversation", sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("conversation", sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("conversation", sa.Column("inbound_message_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("conversation", sa.Column("outbound_message_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("conversation", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(op.f("fk_conversation_organization_id_organization"), "conversation", "organization", ["organization_id"], ["id"])
    op.create_foreign_key(op.f("fk_conversation_bot_id_bot"), "conversation", "bot", ["bot_id"], ["id"])
    op.create_check_constraint("conversation_management_status", "conversation", "management_status IS NULL OR management_status IN ('open', 'closed', 'archived')")
    op.create_index("ix_conversation_organization_bot_status", "conversation", ["organization_id", "bot_id", "management_status"])
    op.create_index("ix_conversation_organization_bot_last_message", "conversation", ["organization_id", "bot_id", "last_message_at"])
    op.create_index("ix_conversation_external_customer", "conversation", ["organization_id", "bot_id", "channel", "external_customer_id"])
    op.create_index("uq_conversation_managed_identity", "conversation", ["organization_id", "bot_id", "channel", "external_customer_id"], unique=True, postgresql_where=sa.text("organization_id IS NOT NULL AND bot_id IS NOT NULL AND external_customer_id IS NOT NULL"), sqlite_where=sa.text("organization_id IS NOT NULL AND bot_id IS NOT NULL AND external_customer_id IS NOT NULL"))

    op.add_column("message", sa.Column("organization_id", UUID, nullable=True))
    op.add_column("message", sa.Column("bot_id", UUID, nullable=True))
    op.add_column("message", sa.Column("direction", sa.String(20), nullable=True))
    op.add_column("message", sa.Column("channel_type", sa.String(50), nullable=True))
    op.add_column("message", sa.Column("external_message_id", sa.String(255), nullable=True))
    op.add_column("message", sa.Column("provider_message_id", sa.String(255), nullable=True))
    op.add_column("message", sa.Column("message_type", sa.String(50), nullable=True))
    op.add_column("message", sa.Column("text_ciphertext", sa.Text(), nullable=True))
    op.add_column("message", sa.Column("delivery_status", sa.String(20), nullable=True))
    op.add_column("message", sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("message", sa.Column("inbound_receipt_id", UUID, nullable=True))
    op.add_column("message", sa.Column("outbound_attempt_id", UUID, nullable=True))
    op.add_column("message", sa.Column("metadata_data", sa.JSON(), nullable=True))
    op.create_foreign_key(op.f("fk_message_inbound_receipt_id_inbound_message_receipt"), "message", "inbound_message_receipt", ["inbound_receipt_id"], ["id"])
    op.create_foreign_key(op.f("fk_message_outbound_attempt_id_outbound_message_attempt"), "message", "outbound_message_attempt", ["outbound_attempt_id"], ["id"])
    op.create_check_constraint("message_management_direction", "message", "direction IS NULL OR direction IN ('inbound', 'outbound')")
    op.create_check_constraint("message_management_status", "message", "delivery_status IS NULL OR delivery_status IN ('received', 'processed', 'pending', 'sent', 'delivered', 'read', 'failed')")
    op.create_index("ix_message_conversation_occurred", "message", ["conversation_id", "occurred_at", "id"])
    op.create_index("ix_message_organization_bot", "message", ["organization_id", "bot_id"])
    op.create_index("uq_message_inbound_external", "message", ["channel_type", "external_message_id"], unique=True, postgresql_where=sa.text("direction = 'inbound' AND external_message_id IS NOT NULL"), sqlite_where=sa.text("direction = 'inbound' AND external_message_id IS NOT NULL"))
    op.create_index("uq_message_outbound_attempt", "message", ["outbound_attempt_id"], unique=True, postgresql_where=sa.text("outbound_attempt_id IS NOT NULL"), sqlite_where=sa.text("outbound_attempt_id IS NOT NULL"))


def downgrade() -> None:
    for name in ("uq_message_outbound_attempt", "uq_message_inbound_external", "ix_message_organization_bot", "ix_message_conversation_occurred"):
        op.drop_index(name, table_name="message")
    op.drop_constraint(op.f("ck_message_message_management_status"), "message", type_="check")
    op.drop_constraint(op.f("ck_message_message_management_direction"), "message", type_="check")
    op.drop_constraint(op.f("fk_message_outbound_attempt_id_outbound_message_attempt"), "message", type_="foreignkey")
    op.drop_constraint(op.f("fk_message_inbound_receipt_id_inbound_message_receipt"), "message", type_="foreignkey")
    for column in ("metadata_data", "outbound_attempt_id", "inbound_receipt_id", "occurred_at", "delivery_status", "text_ciphertext", "message_type", "provider_message_id", "external_message_id", "channel_type", "direction", "bot_id", "organization_id"):
        op.drop_column("message", column)
    for name in ("uq_conversation_managed_identity", "ix_conversation_external_customer", "ix_conversation_organization_bot_last_message", "ix_conversation_organization_bot_status"):
        op.drop_index(name, table_name="conversation")
    op.drop_constraint(op.f("ck_conversation_conversation_management_status"), "conversation", type_="check")
    op.drop_constraint(op.f("fk_conversation_bot_id_bot"), "conversation", type_="foreignkey")
    op.drop_constraint(op.f("fk_conversation_organization_id_organization"), "conversation", type_="foreignkey")
    for column in ("closed_at", "outbound_message_count", "inbound_message_count", "message_count", "last_outbound_at", "last_inbound_at", "last_message_at", "management_status", "masked_customer_identifier", "external_customer_id", "channel_configuration_id", "bot_id", "organization_id"):
        op.drop_column("conversation", column)
