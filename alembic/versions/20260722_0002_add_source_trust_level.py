"""add source_trust_level to knowledge_catalog_entry

Revision ID: 20260722_0002
Revises: 20260722_0001
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0002"
down_revision: str | None = "20260722_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_catalog_entry",
        sa.Column(
            "source_trust_level",
            sa.Float,
            nullable=False,
            server_default="1.0",
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_catalog_entry", "source_trust_level")
