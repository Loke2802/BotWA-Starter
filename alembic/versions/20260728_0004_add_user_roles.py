"""add user roles

Revision ID: 20260728_0004
Revises: 20260728_0003
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0004"
down_revision: str | None = "20260728_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column(
            "role",
            sa.String(50),
            nullable=False,
            server_default="viewer",
        ),
    )
    op.execute(
        """
        WITH ranked_users AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY organization_id
                    ORDER BY created_at ASC, id ASC
                ) AS position
            FROM app_user
        )
        UPDATE app_user
        SET role = CASE
            WHEN ranked_users.position = 1 THEN 'organization_owner'
            ELSE 'viewer'
        END
        FROM ranked_users
        WHERE app_user.id = ranked_users.id
        """
    )


def downgrade() -> None:
    op.drop_column("app_user", "role")
