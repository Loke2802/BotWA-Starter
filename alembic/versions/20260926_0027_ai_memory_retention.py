"""Record AI memory activity for bounded retention; legacy age remains unknown."""

import sqlalchemy as sa
from alembic import op

revision = "20260926_0027"
down_revision = "20261030_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows cannot be safely assigned a fabricated last-update time.
    # NULL is handled as expired on the next access or supervised sweep.
    op.add_column("ai_memory", sa.Column("updated_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("ai_memory", "updated_at")
