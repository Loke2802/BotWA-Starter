"""Align historical model metadata without dropping or rewriting stored data.

Existing JSONB, unique/partial indexes, FKs and constraint names are preserved
in the models. Only missing nonunique indexes and two existing domain checks
are added here. Invalid legacy configuration aborts atomically; no auto-repair.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0028"
down_revision = "20261006_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM managed_automation_definition "
            "WHERE NOT (action_type = 'request_handoff'))"
        )
    ):
        raise RuntimeError(
            "Historical automation action is unsupported; review data before migration"
        )
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM managed_automation_definition "
            "WHERE NOT (trigger_type = 'conversation.inbound_received'))"
        )
    ):
        raise RuntimeError(
            "Historical automation trigger is unsupported; review data before migration"
        )
    op.create_check_constraint(
        op.f("ck_managed_automation_action_type"),
        "managed_automation_definition",
        "action_type = 'request_handoff'",
    )
    op.create_check_constraint(
        op.f("ck_managed_automation_trigger_type"),
        "managed_automation_definition",
        "trigger_type = 'conversation.inbound_received'",
    )
    op.create_index(
        "ix_contact_organization_id", "contact", ["organization_id"], unique=False
    )
    op.create_index("ix_conversation_bot_id", "conversation", ["bot_id"], unique=False)
    op.create_index(
        "ix_conversation_channel_configuration_id",
        "conversation",
        ["channel_configuration_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_external_customer_id",
        "conversation",
        ["external_customer_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_last_message_at",
        "conversation",
        ["last_message_at"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_management_status",
        "conversation",
        ["management_status"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_organization_id",
        "conversation",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_handoff_event_handoff_session_id",
        "handoff_event",
        ["handoff_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_handoff_event_organization_id",
        "handoff_event",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_handoff_session_bot_id", "handoff_session", ["bot_id"], unique=False
    )
    op.create_index(
        "ix_handoff_session_organization_id",
        "handoff_session",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_handoff_session_status", "handoff_session", ["status"], unique=False
    )
    op.create_index(
        "ix_managed_automation_definition_bot_id",
        "managed_automation_definition",
        ["bot_id"],
        unique=False,
    )
    op.create_index(
        "ix_managed_automation_definition_organization_id",
        "managed_automation_definition",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_managed_automation_event_receipt_bot_id",
        "managed_automation_event_receipt",
        ["bot_id"],
        unique=False,
    )
    op.create_index(
        "ix_managed_automation_event_receipt_organization_id",
        "managed_automation_event_receipt",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_managed_automation_execution_automation_definition_id",
        "managed_automation_execution",
        ["automation_definition_id"],
        unique=False,
    )
    op.create_index(
        "ix_managed_automation_execution_organization_id",
        "managed_automation_execution",
        ["organization_id"],
        unique=False,
    )
    op.create_index("ix_message_bot_id", "message", ["bot_id"], unique=False)
    op.create_index(
        "ix_message_channel_type", "message", ["channel_type"], unique=False
    )
    op.create_index("ix_message_direction", "message", ["direction"], unique=False)
    op.create_index("ix_message_occurred_at", "message", ["occurred_at"], unique=False)
    op.create_index(
        "ix_message_organization_id", "message", ["organization_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_message_organization_id", table_name="message")
    op.drop_index("ix_message_occurred_at", table_name="message")
    op.drop_index("ix_message_direction", table_name="message")
    op.drop_index("ix_message_channel_type", table_name="message")
    op.drop_index("ix_message_bot_id", table_name="message")
    op.drop_index(
        "ix_managed_automation_execution_organization_id",
        table_name="managed_automation_execution",
    )
    op.drop_index(
        "ix_managed_automation_execution_automation_definition_id",
        table_name="managed_automation_execution",
    )
    op.drop_index(
        "ix_managed_automation_event_receipt_organization_id",
        table_name="managed_automation_event_receipt",
    )
    op.drop_index(
        "ix_managed_automation_event_receipt_bot_id",
        table_name="managed_automation_event_receipt",
    )
    op.drop_index(
        "ix_managed_automation_definition_organization_id",
        table_name="managed_automation_definition",
    )
    op.drop_index(
        "ix_managed_automation_definition_bot_id",
        table_name="managed_automation_definition",
    )
    op.drop_index("ix_handoff_session_status", table_name="handoff_session")
    op.drop_index("ix_handoff_session_organization_id", table_name="handoff_session")
    op.drop_index("ix_handoff_session_bot_id", table_name="handoff_session")
    op.drop_index("ix_handoff_event_organization_id", table_name="handoff_event")
    op.drop_index("ix_handoff_event_handoff_session_id", table_name="handoff_event")
    op.drop_index("ix_conversation_organization_id", table_name="conversation")
    op.drop_index("ix_conversation_management_status", table_name="conversation")
    op.drop_index("ix_conversation_last_message_at", table_name="conversation")
    op.drop_index("ix_conversation_external_customer_id", table_name="conversation")
    op.drop_index("ix_conversation_channel_configuration_id", table_name="conversation")
    op.drop_index("ix_conversation_bot_id", table_name="conversation")
    op.drop_index("ix_contact_organization_id", table_name="contact")
    op.drop_constraint(
        op.f("ck_managed_automation_trigger_type"),
        "managed_automation_definition",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_managed_automation_action_type"),
        "managed_automation_definition",
        type_="check",
    )
