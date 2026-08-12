import hashlib
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_non_user_audit, append_user_audit
from app.application.billing.metrics import BillingMetricsRegistry, billing_metrics
from app.application.plans.service import InternalPlanAssignmentService
from app.domain.access.contracts import Permission
from app.domain.audit.contracts import BillingMetadata
from app.domain.audit.ports import AuditWriter
from app.domain.billing.contracts import (
    BillingProvider,
    BillingStatusResponse,
    ChangePlanRequest,
    CheckoutCommand,
    CheckoutRequest,
    CheckoutResponse,
    NormalizedWebhook,
    ProviderEventReceipt,
    ProviderSubscriptionSnapshot,
)
from app.domain.billing.errors import (
    BillingDisabled,
    BillingFallbackNotConfigured,
    BillingForbidden,
    BillingNotConfigured,
    BillingPriceNotFound,
    BillingPriceUnavailable,
    BillingProviderUnavailable,
    BillingVersionConflict,
    BillingWebhookInvalid,
    InvalidBillingTransition,
    SubscriptionConflict,
    SubscriptionNotFound,
)
from app.domain.billing.ports import BillingProviderPort
from app.domain.user.contracts import User
from app.infrastructure.models.billing import (
    BillingPriceModel,
    BillingProviderEventModel,
    SubscriptionModel,
)
from app.infrastructure.repositories.billing_repository import BillingRepository
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from app.security.authorization import AuthorizationError, require_scoped_permission

TERMINAL_STATUSES = frozenset(("canceled", "expired"))


class BillingService:
    def __init__(
        self,
        repository: BillingRepository,
        plan_repository: SqlAlchemyPlanRepository,
        internal_plan_assignment: InternalPlanAssignmentService,
        provider: BillingProviderPort,
        session: Session,
        audit_writer: AuditWriter,
        *,
        enabled: bool,
        provider_name: BillingProvider,
        success_url: str,
        cancel_url: str,
        fallback_plan_code: str,
        freshness_seconds: int,
        metrics: BillingMetricsRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.plan_repository = plan_repository
        self.internal_plan_assignment = internal_plan_assignment
        self.provider = provider
        self.session = session
        self.audit_writer = audit_writer
        self.enabled = enabled
        self.provider_name = provider_name
        self.success_url = success_url
        self.cancel_url = cancel_url
        self.fallback_plan_code = fallback_plan_code.strip()
        self.freshness_seconds = freshness_seconds
        self.metrics = metrics or billing_metrics

    def get(self, organization_id: UUID, actor: User) -> BillingStatusResponse:
        self._authorize(actor, "billing.read", organization_id)
        assignment = self.plan_repository.get_assignment(organization_id)
        if assignment is None:
            raise BillingNotConfigured("organization plan is unavailable")
        plan = self.plan_repository.get_plan_by_id(assignment.plan_definition_id)
        if plan is None:
            raise BillingNotConfigured("organization plan is unavailable")
        subscription = self.repository.latest_subscription_model(organization_id)
        if subscription is None:
            return BillingStatusResponse(
                billing_enabled=self.enabled,
                status="not_configured" if self.enabled else "disabled",
                plan_code=plan.plan_code,
            )
        price = self.repository.price_model(subscription.billing_price_id)
        pending = (
            self.repository.price_model(subscription.pending_billing_price_id)
            if subscription.pending_billing_price_id is not None
            else None
        )
        now = datetime.now(UTC)
        last_synced = subscription.last_synced_at
        freshness = "unknown"
        if last_synced is not None:
            if last_synced.tzinfo is None:
                last_synced = last_synced.replace(tzinfo=UTC)
            freshness = (
                "fresh"
                if (now - last_synced).total_seconds() <= self.freshness_seconds
                else "stale"
            )
        return BillingStatusResponse(
            billing_enabled=self.enabled,
            status=subscription.status,
            plan_code=plan.plan_code,
            interval=self.repository.price(price).interval if price else None,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            payment_state=subscription.payment_state,
            pending_plan_code=(
                self.repository.plan_code_for_price(pending) if pending else None
            ),
            scheduled_change_at=subscription.scheduled_change_at,
            last_synced_at=last_synced,
            freshness=freshness,
            version=subscription.version,
        )

    def create_checkout(
        self,
        organization_id: UUID,
        request: CheckoutRequest,
        actor: User,
        idempotency_key: str,
    ) -> CheckoutResponse:
        self._require_enabled()
        self._authorize(actor, "billing.checkout", organization_id)
        if not idempotency_key.strip() or len(idempotency_key) > 200:
            raise SubscriptionConflict("invalid idempotency key")
        if not self.success_url.startswith(
            "https://"
        ) or not self.cancel_url.startswith("https://"):
            raise BillingNotConfigured("hosted checkout URLs are not configured")
        if not self.repository.lock_organization(organization_id):
            raise BillingNotConfigured("organization is unavailable")
        subscription_id = uuid5(
            NAMESPACE_URL, f"botwa:{organization_id}:billing:{idempotency_key}"
        )
        existing = self.repository.current_subscription_model(
            organization_id, lock=True
        )
        if existing is not None:
            if existing.id != subscription_id:
                raise SubscriptionConflict("current subscription already exists")
            existing_price = self.repository.price_model(existing.billing_price_id)
            if existing_price is None or existing_price.id != request.billing_price_id:
                raise SubscriptionConflict("idempotency key payload mismatch")
            price = self.repository.price(existing_price)
            result = self.provider.create_checkout(
                CheckoutCommand(
                    external_reference=str(existing.id),
                    provider_price_id=price.provider_price_id,
                    payer_email=actor.email,
                    success_url=self.success_url,
                    cancel_url=self.cancel_url,
                    idempotency_key=idempotency_key,
                )
            )
            return CheckoutResponse(
                checkout_url=result.checkout_url, subscription_id=existing.id
            )
        price_row = self._active_price(request.billing_price_id)
        price = self.repository.price(price_row)
        if price.provider != self.provider_name:
            raise BillingPriceUnavailable("billing price provider mismatch")
        now = datetime.now(UTC)
        account = self.repository.account_model(organization_id)
        if account is None:
            account = self.repository.create_account(
                organization_id, self.provider_name, now
            )
        subscription = SubscriptionModel(
            id=subscription_id,
            organization_id=organization_id,
            billing_account_id=account.id,
            billing_price_id=price.id,
            provider=self.provider_name,
            status="pending",
            provider_status="pending",
            cancel_at_period_end=False,
            payment_state="pending",
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.repository.add_subscription(subscription)
        try:
            result = self.provider.create_checkout(
                CheckoutCommand(
                    external_reference=str(subscription.id),
                    provider_price_id=price.provider_price_id,
                    payer_email=actor.email,
                    success_url=self.success_url,
                    cancel_url=self.cancel_url,
                    idempotency_key=idempotency_key,
                )
            )
            subscription.provider_subscription_id = result.provider_subscription_id
            subscription.provider_status = result.provider_status
            account.provider_customer_id = result.provider_customer_id
            append_user_audit(
                self.audit_writer,
                organization_id=organization_id,
                actor=actor,
                action="billing.checkout_created",
                resource_type="subscription",
                resource_id=subscription.id,
                metadata=BillingMetadata(
                    to_plan_code=price.plan_code, interval=price.interval
                ),
                occurred_at=now,
            )
            append_user_audit(
                self.audit_writer,
                organization_id=organization_id,
                actor=actor,
                action="subscription.created",
                resource_type="subscription",
                resource_id=subscription.id,
                metadata=BillingMetadata(
                    to_plan_code=price.plan_code, interval=price.interval
                ),
                occurred_at=now,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.metrics.record("billing_checkout_total", result="failed")
            raise
        self.metrics.record("billing_checkout_total", result="created")
        return CheckoutResponse(
            checkout_url=result.checkout_url, subscription_id=subscription.id
        )

    def request_plan_change(
        self, organization_id: UUID, request: ChangePlanRequest, actor: User
    ) -> BillingStatusResponse:
        self._require_enabled()
        self._authorize(actor, "billing.change_plan", organization_id)
        self._lock_organization(organization_id)
        subscription = self._current_locked(organization_id)
        if subscription.version != request.expected_version:
            raise BillingVersionConflict("subscription version conflict")
        if subscription.billing_price_id == request.billing_price_id:
            return self.get(organization_id, actor)
        target_row = self._active_price(request.billing_price_id)
        current_row = self.repository.price_model(subscription.billing_price_id)
        if current_row is None:
            raise BillingPriceNotFound("current billing price not found")
        target = self.repository.price(target_row)
        current = self.repository.price(current_row)
        if (
            target.provider != subscription.provider
            or target.currency != current.currency
        ):
            raise BillingPriceUnavailable("incompatible billing price")
        now = datetime.now(UTC)
        try:
            append_user_audit(
                self.audit_writer,
                organization_id=organization_id,
                actor=actor,
                action="subscription.plan_change_requested",
                resource_type="subscription",
                resource_id=subscription.id,
                metadata=BillingMetadata(
                    from_plan_code=current.plan_code,
                    to_plan_code=target.plan_code,
                    interval=target.interval,
                ),
                occurred_at=now,
            )
            if target.amount_minor <= current.amount_minor:
                subscription.pending_billing_price_id = target.id
                subscription.scheduled_change_at = subscription.current_period_end
                subscription.version += 1
                subscription.updated_at = now
            else:
                provider_id = self._provider_subscription_id(subscription)
                snapshot = self.provider.request_plan_change(
                    provider_id,
                    target.provider_price_id,
                    unit_amount_minor=target.amount_minor,
                    currency=target.currency,
                    current_interval=current.interval,
                    target_interval=target.interval,
                    idempotency_key=f"change-{subscription.id}-{subscription.version}",
                )
                self._verify_snapshot_binding(subscription, snapshot)
                subscription.pending_billing_price_id = target.id
                self._apply_snapshot(subscription, snapshot, now=now)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.metrics.record("billing_plan_changes_total", result="accepted")
        return self.get(organization_id, actor)

    def request_cancellation(
        self, organization_id: UUID, expected_version: int, actor: User
    ) -> BillingStatusResponse:
        self._require_enabled()
        self._authorize(actor, "billing.cancel", organization_id)
        self._lock_organization(organization_id)
        subscription = self._current_locked(organization_id)
        if subscription.version != expected_version:
            raise BillingVersionConflict("subscription version conflict")
        if subscription.cancel_at_period_end:
            return self.get(organization_id, actor)
        now = datetime.now(UTC)
        subscription.cancel_at_period_end = True
        subscription.scheduled_change_at = subscription.current_period_end
        subscription.version += 1
        subscription.updated_at = now
        try:
            append_user_audit(
                self.audit_writer,
                organization_id=organization_id,
                actor=actor,
                action="subscription.cancel_requested",
                resource_type="subscription",
                resource_id=subscription.id,
                metadata=BillingMetadata(cancel_at_period_end=True),
                occurred_at=now,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.metrics.record("billing_cancellations_total", result="scheduled")
        return self.get(organization_id, actor)

    def reconcile(self, organization_id: UUID, actor: User) -> BillingStatusResponse:
        self._require_enabled()
        self._authorize(actor, "billing.manage", organization_id)
        if actor.role != "platform_admin":
            raise BillingForbidden("billing reconcile denied")
        self._lock_organization(organization_id)
        subscription = self._current_locked(organization_id)
        provider_id = self._provider_subscription_id(subscription)
        try:
            if (
                subscription.cancel_at_period_end
                and subscription.current_period_end is not None
                and _aware(subscription.current_period_end) <= datetime.now(UTC)
            ):
                snapshot = self.provider.request_cancellation(
                    provider_id,
                    idempotency_key=f"cancel-{subscription.id}-{subscription.version}",
                )
            elif (
                subscription.pending_billing_price_id is not None
                and subscription.scheduled_change_at is not None
                and _aware(subscription.scheduled_change_at) <= datetime.now(UTC)
            ):
                pending = self.repository.price_model(
                    subscription.pending_billing_price_id
                )
                if pending is None:
                    raise BillingPriceNotFound("pending billing price not found")
                current_price = self.repository.price_model(
                    subscription.billing_price_id
                )
                if current_price is None:
                    raise BillingPriceNotFound("current billing price not found")
                snapshot = self.provider.request_plan_change(
                    provider_id,
                    pending.provider_price_id,
                    unit_amount_minor=pending.amount_minor,
                    currency=pending.currency,
                    current_interval=self.repository.price(current_price).interval,
                    target_interval=self.repository.price(pending).interval,
                    idempotency_key=(
                        f"scheduled-change-{subscription.id}-{subscription.version}"
                    ),
                )
            else:
                snapshot = self.provider.fetch_subscription(provider_id)
            self._verify_snapshot_binding(subscription, snapshot)
            changed = self._apply_snapshot(
                subscription, snapshot, now=datetime.now(UTC)
            )
            if changed:
                append_user_audit(
                    self.audit_writer,
                    organization_id=organization_id,
                    actor=actor,
                    action="subscription.reconciled",
                    resource_type="subscription",
                    resource_id=subscription.id,
                    metadata=BillingMetadata(),
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.metrics.record("billing_reconciliations_total", result="success")
        return self.get(organization_id, actor)

    def process_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
        query: dict[str, str],
    ) -> ProviderEventReceipt:
        if not self.enabled:
            return ProviderEventReceipt(duplicate=False, status="ignored")
        normalized = self.provider.verify_and_normalize_webhook(body, headers, query)
        existing = self.repository.event_model(self.provider_name, normalized.event_id)
        if existing is not None and existing.status in ("processed", "ignored"):
            self.metrics.record("billing_webhook_events_total", result="duplicate")
            return ProviderEventReceipt(duplicate=True, status=existing.status)
        event = existing or BillingProviderEventModel(
            provider=self.provider_name,
            provider_event_id=normalized.event_id,
            event_type=normalized.event_type,
            status="received",
            provider_created_at=normalized.provider_created_at,
            received_at=datetime.now(UTC),
            attempts=1,
            payload_hash=hashlib.sha256(body).hexdigest(),
        )
        if existing is None:
            try:
                self.repository.add_event(event)
            except IntegrityError:
                self.session.rollback()
                return ProviderEventReceipt(duplicate=True, status="processed")
        else:
            event.attempts += 1
            event.status = "received"
        try:
            self._process_normalized_event(event, normalized)
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            retry_event = self.repository.event_model(
                self.provider_name, normalized.event_id
            )
            if retry_event is None:
                retry_event = event
                self.session.add(retry_event)
            retry_event.status = "failed"
            retry_event.safe_error_code = _safe_error_code(exc)
            retry_event.processed_at = datetime.now(UTC)
            self.session.commit()
            self.metrics.record("billing_webhook_events_total", result="failed")
            raise
        self.metrics.record("billing_webhook_events_total", result=event.status)
        return ProviderEventReceipt(duplicate=False, status=event.status)

    def _process_normalized_event(
        self, event: BillingProviderEventModel, normalized: NormalizedWebhook
    ) -> None:
        if normalized.provider_subscription_id is None:
            event.status = "ignored"
            event.processed_at = datetime.now(UTC)
            return
        initial = self.repository.subscription_by_provider_id(
            self.provider_name, normalized.provider_subscription_id, lock=False
        )
        if initial is None:
            event.status = "ignored"
            event.safe_error_code = "BILLING_SUBSCRIPTION_NOT_FOUND"
            event.processed_at = datetime.now(UTC)
            return
        self._lock_organization(initial.organization_id)
        subscription = self.repository.subscription_by_provider_id(
            self.provider_name, normalized.provider_subscription_id, lock=True
        )
        if subscription is None:
            raise SubscriptionNotFound("subscription not found")
        snapshot = self.provider.fetch_subscription(normalized.provider_subscription_id)
        self._verify_snapshot_binding(subscription, snapshot)
        event.organization_id = subscription.organization_id
        event.subscription_id = subscription.id
        changed = self._apply_snapshot(subscription, snapshot, now=datetime.now(UTC))
        event.status = "processed" if changed else "ignored"
        event.safe_error_code = subscription.safe_error_code
        event.processed_at = datetime.now(UTC)

    def _apply_snapshot(
        self,
        subscription: SubscriptionModel,
        snapshot: ProviderSubscriptionSnapshot,
        *,
        now: datetime,
    ) -> bool:
        if (
            snapshot.provider_sequence is not None
            and subscription.provider_sequence is not None
            and snapshot.provider_sequence < subscription.provider_sequence
        ):
            return False
        old_status = subscription.status
        old_price_id = subscription.billing_price_id
        new_status = _internal_status(snapshot.status)
        if not _transition_allowed(old_status, new_status):
            raise InvalidBillingTransition("provider state regression rejected")
        target_row = None
        if subscription.pending_billing_price_id is not None:
            target_row = self.repository.price_model(
                subscription.pending_billing_price_id
            )
        elif new_status == "active" and old_status == "pending":
            target_row = self.repository.price_model(subscription.billing_price_id)
        material = any(
            (
                subscription.provider_status != snapshot.status,
                subscription.status != new_status,
                subscription.current_period_end != snapshot.current_period_end,
                subscription.payment_state != snapshot.payment_state,
                target_row is not None and target_row.id != old_price_id,
            )
        )
        subscription.provider_status = snapshot.status
        subscription.status = new_status
        subscription.current_period_start = snapshot.current_period_start
        subscription.current_period_end = snapshot.current_period_end
        subscription.payment_state = snapshot.payment_state
        subscription.provider_sequence = snapshot.provider_sequence
        subscription.last_synced_at = now
        subscription.updated_at = now
        if not material:
            return False
        subscription.version += 1
        if target_row is not None and new_status == "active":
            old_price = self.repository.price_model(old_price_id)
            old_plan = (
                self.repository.plan_code_for_price(old_price) if old_price else None
            )
            new_plan = self.repository.plan_code_for_price(target_row)
            subscription.billing_price_id = target_row.id
            subscription.pending_billing_price_id = None
            subscription.scheduled_change_at = None
            self.internal_plan_assignment.stage(
                subscription.organization_id,
                new_plan,
                assigned_by_user_id=None,
                organization_already_locked=True,
            )
            append_non_user_audit(
                self.audit_writer,
                organization_id=subscription.organization_id,
                actor_type="system",
                action=(
                    "subscription.activated"
                    if old_status == "pending"
                    else "subscription.plan_changed"
                ),
                resource_type="subscription",
                resource_id=subscription.id,
                metadata=BillingMetadata(
                    from_plan_code=old_plan,
                    to_plan_code=new_plan,
                    interval=self.repository.price(target_row).interval,
                ),
                occurred_at=now,
            )
        if new_status in TERMINAL_STATUSES or new_status == "suspended":
            if self.fallback_plan_code:
                self.internal_plan_assignment.stage(
                    subscription.organization_id,
                    self.fallback_plan_code,
                    assigned_by_user_id=None,
                    organization_already_locked=True,
                )
                subscription.safe_error_code = None
            else:
                subscription.safe_error_code = BillingFallbackNotConfigured.safe_code
            if new_status == "canceled":
                append_non_user_audit(
                    self.audit_writer,
                    organization_id=subscription.organization_id,
                    actor_type="system",
                    action="subscription.canceled",
                    resource_type="subscription",
                    resource_id=subscription.id,
                    metadata=BillingMetadata(cancel_at_period_end=True),
                    occurred_at=now,
                )
        return True

    def _active_price(self, price_id: UUID) -> BillingPriceModel:
        row = self.repository.price_model(price_id)
        if row is None:
            raise BillingPriceNotFound("billing price not found")
        if row.status != "active":
            raise BillingPriceUnavailable("billing price is retired")
        return row

    def _lock_organization(self, organization_id: UUID) -> None:
        if not self.repository.lock_organization(organization_id):
            raise BillingNotConfigured("organization is unavailable")

    def _current_locked(self, organization_id: UUID) -> SubscriptionModel:
        row = self.repository.current_subscription_model(organization_id, lock=True)
        if row is None:
            raise SubscriptionNotFound("subscription not found")
        return row

    @staticmethod
    def _provider_subscription_id(subscription: SubscriptionModel) -> str:
        if not subscription.provider_subscription_id:
            raise BillingProviderUnavailable("provider subscription is unresolved")
        return subscription.provider_subscription_id

    @staticmethod
    def _verify_snapshot_binding(
        subscription: SubscriptionModel, snapshot: ProviderSubscriptionSnapshot
    ) -> None:
        if snapshot.external_reference != str(subscription.id):
            raise BillingWebhookInvalid("provider subscription binding mismatch")

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise BillingDisabled("billing mutations are disabled")

    @staticmethod
    def _authorize(actor: User, permission: Permission, organization_id: UUID) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)
        except AuthorizationError as exc:
            raise BillingForbidden("billing access denied") from exc


def _internal_status(provider_status: str) -> str:
    normalized = provider_status.lower()
    mapped = {
        "pending": "pending",
        "authorized": "active",
        "active": "active",
        "past_due": "past_due",
        "paused": "suspended",
        "suspended": "suspended",
        "cancelled": "canceled",
        "canceled": "canceled",
        "expired": "expired",
    }.get(normalized)
    if mapped is None:
        raise InvalidBillingTransition("unknown provider subscription state")
    return mapped


def _transition_allowed(current: str, target: str) -> bool:
    allowed: dict[str, frozenset[str]] = {
        "pending": frozenset(("pending", "active", "canceled", "expired")),
        "active": frozenset(("active", "past_due", "suspended", "canceled", "expired")),
        "past_due": frozenset(
            ("active", "past_due", "suspended", "canceled", "expired")
        ),
        "suspended": frozenset(("active", "suspended", "canceled", "expired")),
        "canceled": frozenset(("canceled",)),
        "expired": frozenset(("expired",)),
    }
    return target in allowed.get(current, frozenset())


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _safe_error_code(exc: Exception) -> str:
    safe_code = getattr(exc, "safe_code", None)
    return str(safe_code) if safe_code else "BILLING_PROCESSING_FAILED"
