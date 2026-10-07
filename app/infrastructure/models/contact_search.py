"""Derived exact-search data. Identities remain encrypted; tokens are tenant HMACs."""

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class ContactSearchStateModel(Base):
    __tablename__ = "contact_search_state"
    __table_args__ = (
        ForeignKeyConstraint(
            ["contact_id", "organization_id"],
            ["contact.id", "contact.organization_id"],
            name="fk_contact_search_state_contact",
            ondelete="CASCADE",
        ),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    contact_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    key_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    identifier_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    registration_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)


class ContactSearchTokenModel(Base):
    __tablename__ = "contact_search_token"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contact_search_state.organization_id", "contact_search_state.contact_id"],
            name="fk_contact_search_token_state",
            ondelete="CASCADE",
        ),
        CheckConstraint("field IN ('phone', 'email')", name="contact_search_field"),
        Index("ix_contact_search_exact", "organization_id", "field", "digest"),
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    contact_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    field: Mapped[str] = mapped_column(String(5), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
