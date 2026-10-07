"""Protected name grams and exact duplicate keys; no plaintext names."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class ContactNameStateModel(Base):
    __tablename__ = "contact_name_state"
    __table_args__ = (
        ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_contact_name_state_contact",
            ondelete="CASCADE",
        ),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    contact_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)


class ContactNameTokenModel(Base):
    __tablename__ = "contact_name_token"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contact_name_state.organization_id", "contact_name_state.contact_id"],
            name="fk_contact_name_token_state",
            ondelete="CASCADE",
        ),
        CheckConstraint("kind IN ('gram', 'exact')", name="contact_name_kind"),
        Index("ix_contact_name_lookup", "organization_id", "kind", "digest"),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    contact_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    kind: Mapped[str] = mapped_column(String(5), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
