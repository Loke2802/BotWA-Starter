"""Durable AI lane. Frozen DDL; no model imports during migrations."""

from alembic import op

revision = "20260920_0025"
down_revision = "20260916_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE ai_job (
	id UUID NOT NULL,
	receipt_id UUID NOT NULL,
	organization_id UUID NOT NULL,
	bot_id UUID NOT NULL,
	conversation_id UUID NOT NULL,
	configuration_id UUID NOT NULL,
	status VARCHAR(30) NOT NULL,
	sequence INTEGER NOT NULL,
	attempts INTEGER NOT NULL,
	token UUID,
	lease_until TIMESTAMP WITH TIME ZONE,
	available_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	sent_at TIMESTAMP WITH TIME ZONE,
	error_code VARCHAR(60),
	config_hash VARCHAR(64) NOT NULL,
	result_ciphertext TEXT,
	sources JSON NOT NULL,
	outbound_id UUID,
	CONSTRAINT pk_ai_job PRIMARY KEY (id),
	CONSTRAINT ck_ai_job_ai_job_status CHECK (status IN ('pending', 'running', 'retry', 'ready', 'sent', 'failed', 'cancelled', 'delivery_unknown', 'handoff')),
	CONSTRAINT ck_ai_job_ai_job_counters CHECK (attempts >= 0 AND sequence >= 0),
	CONSTRAINT uq_ai_job_receipt_id UNIQUE (receipt_id),
	CONSTRAINT fk_ai_job_receipt_id_inbound_message_receipt FOREIGN KEY(receipt_id) REFERENCES inbound_message_receipt (id),
	CONSTRAINT fk_ai_job_organization_id_organization FOREIGN KEY(organization_id) REFERENCES organization (id),
	CONSTRAINT fk_ai_job_bot_id_bot FOREIGN KEY(bot_id) REFERENCES bot (id),
	CONSTRAINT fk_ai_job_conversation_id_conversation FOREIGN KEY(conversation_id) REFERENCES conversation (id),
	CONSTRAINT fk_ai_job_configuration_id_whatsapp_channel_configuration FOREIGN KEY(configuration_id) REFERENCES whatsapp_channel_configuration (id),
	CONSTRAINT uq_ai_job_outbound_id UNIQUE (outbound_id),
	CONSTRAINT fk_ai_job_outbound_id_outbound_message_attempt FOREIGN KEY(outbound_id) REFERENCES outbound_message_attempt (id)
)
""")
    op.execute("""
CREATE TABLE ai_memory (
	conversation_id UUID NOT NULL,
	organization_id UUID NOT NULL,
	bot_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	ciphertext TEXT NOT NULL,
	CONSTRAINT pk_ai_memory PRIMARY KEY (conversation_id),
	CONSTRAINT fk_ai_memory_conversation_id_conversation FOREIGN KEY(conversation_id) REFERENCES conversation (id),
	CONSTRAINT fk_ai_memory_organization_id_organization FOREIGN KEY(organization_id) REFERENCES organization (id),
	CONSTRAINT fk_ai_memory_bot_id_bot FOREIGN KEY(bot_id) REFERENCES bot (id)
)
""")
    op.execute("""
CREATE TABLE ai_attempt (
	id UUID NOT NULL,
	job_id UUID NOT NULL,
	stage VARCHAR(20) NOT NULL,
	provider VARCHAR(20) NOT NULL,
	model VARCHAR(100) NOT NULL,
	parameters JSON NOT NULL,
	prompt_version VARCHAR(60) NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	duration_ms INTEGER,
	input_tokens INTEGER,
	output_tokens INTEGER,
	result VARCHAR(60) NOT NULL,
	CONSTRAINT pk_ai_attempt PRIMARY KEY (id),
	CONSTRAINT fk_ai_attempt_job_id_ai_job FOREIGN KEY(job_id) REFERENCES ai_job (id)
)
""")
    op.create_index("ix_ai_job_due", "ai_job", ["status", "available_at"])
    op.create_index(
        "ix_ai_job_scope", "ai_job", ["organization_id", "bot_id", "conversation_id"]
    )
    op.create_index("ix_ai_attempt_job_id", "ai_attempt", ["job_id"])


def downgrade() -> None:
    op.drop_table("ai_attempt")
    op.drop_table("ai_memory")
    op.drop_table("ai_job")
