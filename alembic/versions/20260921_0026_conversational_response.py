"""Optional conversational checkpoints; existing jobs remain valid."""

from alembic import op
import sqlalchemy as sa

revision = "20260921_0026"
down_revision = "20260920_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("ai_attempt", "stage", type_=sa.String(32), existing_type=sa.String(20))
    op.create_table(
        "ai_response_checkpoint",
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("ai_job.id"), primary_key=True),
        sa.Column("context_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("schema_version", sa.String(10), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=True),
        sa.Column("memory_revision", sa.Integer(), nullable=False),
        sa.Column("committed_revision", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("reason_code", sa.String(60), nullable=True),
        sa.Column("reply_digest", sa.String(64), nullable=True),
        sa.Column("resumed_from", sa.String(32), nullable=True),
        sa.Column("response_revoked", sa.Boolean(), nullable=False),
        sa.CheckConstraint("memory_revision >= 0", name="ai_response_memory_revision"),
        sa.CheckConstraint("outcome IS NULL OR outcome IN ('approved', 'fallback')", name="ai_response_outcome"),
    )


def downgrade() -> None:
    # Keep stage width: narrowing would destroy audit rows for the 21-character
    # conversational_render stage. The old application accepts this wider field.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM ai_response_checkpoint c JOIN ai_job j ON j.id=c.job_id WHERE j.status IN ('pending','running','retry','ready') LIMIT 1")).first():
        raise RuntimeError("Drain conversational jobs before downgrade")
    op.drop_table("ai_response_checkpoint")
