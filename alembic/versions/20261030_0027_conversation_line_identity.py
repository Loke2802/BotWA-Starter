"""Managed conversation identity includes the WhatsApp line; history is preserved."""

from alembic import op
import sqlalchemy as sa

revision = "20261030_0027"
down_revision = "20260921_0026"
branch_labels = None
depends_on = None

_MANAGED = "organization_id IS NOT NULL AND bot_id IS NOT NULL AND external_customer_id IS NOT NULL"


def _unique(name: str, columns: list[str], where: str) -> None:
    op.create_index(name, "conversation", columns, unique=True, postgresql_where=sa.text(where), sqlite_where=sa.text(where))


def upgrade() -> None:
    # Existing rows already satisfy the narrower old key, so both new keys hold.
    op.drop_index("uq_conversation_managed_identity", table_name="conversation")
    _unique(
        "uq_conversation_managed_line_identity",
        ["organization_id", "bot_id", "channel", "channel_configuration_id", "external_customer_id"],
        f"{_MANAGED} AND channel_configuration_id IS NOT NULL",
    )
    _unique(
        "uq_conversation_managed_unlined_identity",
        ["organization_id", "bot_id", "channel", "external_customer_id"],
        f"{_MANAGED} AND channel_configuration_id IS NULL",
    )


def downgrade() -> None:
    # Never merge or delete conversations: once one customer has a conversation
    # per line, the old per-bot key cannot hold and the downgrade must stop.
    connection = op.get_bind()
    if connection.execute(sa.text(f"SELECT 1 FROM conversation WHERE {_MANAGED} GROUP BY organization_id, bot_id, channel, external_customer_id HAVING count(*) > 1 LIMIT 1")).first():
        raise RuntimeError("Conversations exist per line; keep this revision")
    op.drop_index("uq_conversation_managed_unlined_identity", table_name="conversation")
    op.drop_index("uq_conversation_managed_line_identity", table_name="conversation")
    _unique("uq_conversation_managed_identity", ["organization_id", "bot_id", "channel", "external_customer_id"], _MANAGED)
