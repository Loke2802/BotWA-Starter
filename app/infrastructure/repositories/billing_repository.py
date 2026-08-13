from datetime import UTC, datetime
from uuid import UUID

from pydantic import TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.billing.contracts import (
    BillingAccount,
    BillingAccountStatus,
    BillingDueTransitionCandidate,
    BillingInterval,
    BillingPrice,
    BillingPriceStatus,
    BillingProvider,
    PaymentState,
    Subscription,
    SubscriptionStatus,
)
from app.infrastructure.models.billing import (
    BillingAccountModel,
    BillingPriceModel,
    BillingProviderEventModel,
    SubscriptionModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import PlanDefinitionModel

PROVIDER: TypeAdapter[BillingProvider] = TypeAdapter(BillingProvider)
ACCOUNT_STATUS: TypeAdapter[BillingAccountStatus] = TypeAdapter(BillingAccountStatus)
PRICE_STATUS: TypeAdapter[BillingPriceStatus] = TypeAdapter(BillingPriceStatus)
INTERVAL: TypeAdapter[BillingInterval] = TypeAdapter(BillingInterval)
SUBSCRIPTION_STATUS: TypeAdapter[SubscriptionStatus] = TypeAdapter(SubscriptionStatus)
PAYMENT_STATE: TypeAdapter[PaymentState] = TypeAdapter(PaymentState)


class BillingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_organization(self, organization_id: UUID) -> bool:
        statement = (
            select(OrganizationModel.id)
            .where(OrganizationModel.id == organization_id)
            .with_for_update()
        )
        return self.session.execute(statement).scalar_one_or_none() is not None

    def account_model(self, organization_id: UUID) -> BillingAccountModel | None:
        return self.session.scalars(
            select(BillingAccountModel).where(
                BillingAccountModel.organization_id == organization_id
            )
        ).first()

    def create_account(
        self, organization_id: UUID, provider: BillingProvider, now: datetime
    ) -> BillingAccountModel:
        row = BillingAccountModel(
            organization_id=organization_id,
            provider=provider,
            status="active",
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def price_model(self, price_id: UUID) -> BillingPriceModel | None:
        return self.session.get(BillingPriceModel, price_id)

    def price_by_provider_id(
        self, provider: BillingProvider, provider_price_id: str
    ) -> BillingPriceModel | None:
        return self.session.scalars(
            select(BillingPriceModel).where(
                BillingPriceModel.provider == provider,
                BillingPriceModel.provider_price_id == provider_price_id,
            )
        ).first()

    def current_subscription_model(
        self, organization_id: UUID, *, lock: bool = False
    ) -> SubscriptionModel | None:
        statement = select(SubscriptionModel).where(
            SubscriptionModel.organization_id == organization_id,
            SubscriptionModel.status.in_(
                ("pending", "active", "past_due", "suspended")
            ),
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalars(statement).first()

    def subscription_model(
        self, subscription_id: UUID, organization_id: UUID, *, lock: bool = False
    ) -> SubscriptionModel | None:
        statement = select(SubscriptionModel).where(
            SubscriptionModel.id == subscription_id,
            SubscriptionModel.organization_id == organization_id,
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalars(statement).first()

    def due_transition_candidates(
        self, now: datetime, *, limit: int
    ) -> list[BillingDueTransitionCandidate]:
        rows = self.session.execute(
            select(
                SubscriptionModel.id,
                SubscriptionModel.organization_id,
                SubscriptionModel.cancel_at_period_end,
            )
            .where(
                SubscriptionModel.scheduled_change_at.is_not(None),
                SubscriptionModel.scheduled_change_at <= now,
                or_(
                    SubscriptionModel.cancel_at_period_end.is_(True),
                    SubscriptionModel.pending_billing_price_id.is_not(None),
                ),
            )
            .order_by(SubscriptionModel.scheduled_change_at, SubscriptionModel.id)
            .limit(limit)
        ).all()
        return [
            BillingDueTransitionCandidate(
                subscription_id=row.id,
                organization_id=row.organization_id,
                operation="cancellation" if row.cancel_at_period_end else "downgrade",
            )
            for row in rows
        ]

    def latest_subscription_model(
        self, organization_id: UUID
    ) -> SubscriptionModel | None:
        return self.session.scalars(
            select(SubscriptionModel)
            .where(SubscriptionModel.organization_id == organization_id)
            .order_by(SubscriptionModel.updated_at.desc(), SubscriptionModel.id.desc())
        ).first()

    def subscription_by_provider_id(
        self, provider: BillingProvider, provider_subscription_id: str, *, lock: bool
    ) -> SubscriptionModel | None:
        statement = select(SubscriptionModel).where(
            SubscriptionModel.provider == provider,
            SubscriptionModel.provider_subscription_id == provider_subscription_id,
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalars(statement).first()

    def add_subscription(self, row: SubscriptionModel) -> None:
        self.session.add(row)
        self.session.flush()

    def event_model(
        self, provider: BillingProvider, event_id: str
    ) -> BillingProviderEventModel | None:
        return self.session.scalars(
            select(BillingProviderEventModel).where(
                BillingProviderEventModel.provider == provider,
                BillingProviderEventModel.provider_event_id == event_id,
            )
        ).first()

    def add_event(self, row: BillingProviderEventModel) -> None:
        self.session.add(row)
        self.session.flush()

    def plan_code_for_price(self, row: BillingPriceModel) -> str:
        value = self.session.scalar(
            select(PlanDefinitionModel.plan_code).where(
                PlanDefinitionModel.id == row.plan_definition_id
            )
        )
        if value is None:
            raise LookupError("billing price plan is unavailable")
        return value

    @staticmethod
    def account(row: BillingAccountModel) -> BillingAccount:
        return BillingAccount(
            id=row.id,
            organization_id=row.organization_id,
            provider=PROVIDER.validate_python(row.provider),
            provider_customer_id=row.provider_customer_id,
            status=ACCOUNT_STATUS.validate_python(row.status),
            version=row.version,
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )

    def price(self, row: BillingPriceModel) -> BillingPrice:
        return BillingPrice(
            id=row.id,
            plan_definition_id=row.plan_definition_id,
            plan_code=self.plan_code_for_price(row),
            provider=PROVIDER.validate_python(row.provider),
            provider_price_id=row.provider_price_id,
            amount_minor=row.amount_minor,
            currency=row.currency,
            interval=INTERVAL.validate_python(row.interval),
            status=PRICE_STATUS.validate_python(row.status),
        )

    @staticmethod
    def subscription(row: SubscriptionModel) -> Subscription:
        return Subscription(
            id=row.id,
            organization_id=row.organization_id,
            billing_account_id=row.billing_account_id,
            billing_price_id=row.billing_price_id,
            provider=PROVIDER.validate_python(row.provider),
            provider_subscription_id=row.provider_subscription_id,
            status=SUBSCRIPTION_STATUS.validate_python(row.status),
            provider_status=row.provider_status,
            current_period_start=_aware_or_none(row.current_period_start),
            current_period_end=_aware_or_none(row.current_period_end),
            cancel_at_period_end=row.cancel_at_period_end,
            grace_until=_aware_or_none(row.grace_until),
            pending_billing_price_id=row.pending_billing_price_id,
            scheduled_change_at=_aware_or_none(row.scheduled_change_at),
            payment_state=PAYMENT_STATE.validate_python(row.payment_state),
            provider_sequence=row.provider_sequence,
            last_synced_at=_aware_or_none(row.last_synced_at),
            version=row.version,
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _aware_or_none(value: datetime | None) -> datetime | None:
    return _aware(value) if value is not None else None
