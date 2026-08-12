from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.infrastructure.database import Base


class BillingAccountModel(Base):
    __tablename__ = "billing_account"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','inactive')", name="billing_account_status"
        ),
        CheckConstraint("version > 0", name="billing_account_version_positive"),
        Index(
            "uq_billing_account_provider_customer",
            "provider",
            "provider_customer_id",
            unique=True,
            postgresql_where=text("provider_customer_id IS NOT NULL"),
            sqlite_where=text("provider_customer_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), unique=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_customer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class BillingPriceModel(Base):
    __tablename__ = "billing_price"
    __table_args__ = (
        CheckConstraint("amount_minor >= 0", name="billing_price_amount_nonnegative"),
        CheckConstraint("length(currency) = 3", name="billing_price_currency_length"),
        CheckConstraint(
            "currency = upper(currency)", name="billing_price_currency_upper"
        ),
        CheckConstraint(
            "interval IN ('monthly','annual')", name="billing_price_interval"
        ),
        CheckConstraint("status IN ('active','retired')", name="billing_price_status"),
        UniqueConstraint(
            "provider", "provider_price_id", name="uq_billing_price_provider_price"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    plan_definition_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("plan_definition.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_price_id: Mapped[str] = mapped_column(String(200), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    interval: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class SubscriptionModel(Base):
    __tablename__ = "subscription"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','active','past_due','suspended',"
            "'canceled','expired')",
            name="subscription_status",
        ),
        CheckConstraint(
            "payment_state IN ('unknown','pending','paid','failed')",
            name="subscription_payment_state",
        ),
        CheckConstraint("version > 0", name="subscription_version_positive"),
        Index(
            "uq_subscription_one_current_per_org",
            "organization_id",
            unique=True,
            postgresql_where=text(
                "status IN ('pending','active','past_due','suspended')"
            ),
            sqlite_where=text("status IN ('pending','active','past_due','suspended')"),
        ),
        Index(
            "uq_subscription_provider_subscription",
            "provider",
            "provider_subscription_id",
            unique=True,
            postgresql_where=text("provider_subscription_id IS NOT NULL"),
            sqlite_where=text("provider_subscription_id IS NOT NULL"),
        ),
        Index("ix_subscription_org_updated", "organization_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=False
    )
    billing_account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("billing_account.id"), nullable=False
    )
    billing_price_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("billing_price.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    grace_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pending_billing_price_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("billing_price.id"), nullable=True
    )
    scheduled_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown"
    )
    provider_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    safe_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class BillingProviderEventModel(Base):
    __tablename__ = "billing_provider_event"
    __table_args__ = (
        CheckConstraint(
            "status IN ('received','processed','ignored','failed')",
            name="billing_provider_event_status",
        ),
        CheckConstraint(
            "attempts > 0", name="billing_provider_event_attempts_positive"
        ),
        Index("ix_billing_event_status_received", "status", "received_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("organization.id"), nullable=True
    )
    subscription_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("subscription.id"), nullable=True
    )
    provider_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    safe_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
