"""Add tenant-scoped commercial profiles without changing existing contacts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "20260916_0023"
down_revision = "20260813_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("app_user") as batch:
        batch.create_unique_constraint(
            "uq_user_id_organization", ["id", "organization_id"]
        )
    with op.batch_alter_table("contact") as batch:
        batch.create_unique_constraint(
            "uq_contact_id_organization", ["id", "organization_id"]
        )
    op.create_table(
        "customer_profile",
        sa.ForeignKeyConstraint(
            ["assigned_user_id", "organization_id"],
            ["app_user.id", "app_user.organization_id"],
            name="fk_customer_profile_assignee_tenant",
        ),
        sa.CheckConstraint(
            "service_interest IN ('undecided','luri','site','marketing','other')",
            name="customer_service",
        ),
        sa.Column("contact_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("classification", sa.String(20), nullable=False),
        sa.Column("service_interest", sa.String(40), nullable=False),
        sa.Column(
            "assigned_user_id", sa.Uuid(), sa.ForeignKey("app_user.id"), nullable=True
        ),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("contact_id"),
        sa.ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_customer_profile_contact_tenant",
        ),
        sa.CheckConstraint(
            "classification IN ('lead','customer','inactive')",
            name="customer_classification",
        ),
        sa.CheckConstraint("version > 0", name="customer_version"),
    )
    op.create_index(
        "ix_customer_profile_org_follow_up",
        "customer_profile",
        ["organization_id", "next_follow_up_at"],
    )


def downgrade() -> None:
    op.drop_table("customer_profile")
    with op.batch_alter_table("app_user") as batch:
        batch.drop_constraint("uq_user_id_organization", type_="unique")
    with op.batch_alter_table("contact") as batch:
        batch.drop_constraint("uq_contact_id_organization", type_="unique")
