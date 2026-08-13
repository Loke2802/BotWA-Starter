"""Create PRD-021 security rate-limit persistence.

Revision ID: 20260813_0022
Revises: 20260813_0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260813_0022"
down_revision = "20260813_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_rate_limit_bucket",
        sa.Column("scope", sa.String(40), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count > 0", name="security_rate_limit_count_positive"
        ),
        sa.PrimaryKeyConstraint("scope", "key_hash", "window_started_at"),
    )
    op.create_index(
        "ix_security_rate_limit_bucket_updated_at",
        "security_rate_limit_bucket",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_security_rate_limit_bucket_updated_at",
        table_name="security_rate_limit_bucket",
    )
    op.drop_table("security_rate_limit_bucket")
