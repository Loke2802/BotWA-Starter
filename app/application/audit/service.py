import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from app.application.audit.metrics import AuditMetricsRegistry
from app.application.plans.service import PlanEnforcementService
from app.domain.audit.contracts import (
    AuditAction,
    AuditCursor,
    AuditEventListResponse,
    AuditQuery,
    AuditResourceType,
)
from app.domain.audit.errors import (
    AuditForbidden,
    AuditInvalidCursor,
    AuditInvalidFilter,
    AuditInvalidRange,
    AuditRangeTooLarge,
)
from app.domain.audit.ports import AuditReader
from app.domain.user.contracts import User
from app.security.authorization import AuthorizationError, require_scoped_permission

MAX_RANGE = timedelta(days=366)
DEFAULT_RANGE = timedelta(days=30)
ACTION_ADAPTER: TypeAdapter[AuditAction] = TypeAdapter(AuditAction)
RESOURCE_TYPE_ADAPTER: TypeAdapter[AuditResourceType] = TypeAdapter(AuditResourceType)


class AuditCursorCodec:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def encode(self, cursor: AuditCursor) -> str:
        payload = json.dumps(
            cursor.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload + signature).decode("ascii").rstrip("=")

    def decode(self, value: str) -> AuditCursor:
        try:
            padded = value + "=" * (-len(value) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
            if len(decoded) <= hashlib.sha256().digest_size:
                raise ValueError
            payload = decoded[: -hashlib.sha256().digest_size]
            supplied = decoded[-hashlib.sha256().digest_size :]
            expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(supplied, expected):
                raise ValueError
            return AuditCursor.model_validate_json(payload)
        except (ValueError, UnicodeError, ValidationError, json.JSONDecodeError) as exc:
            raise AuditInvalidCursor("audit cursor is invalid") from exc


class AuditQueryService:
    def __init__(
        self,
        reader: AuditReader,
        *,
        cursor_codec: AuditCursorCodec,
        metrics: AuditMetricsRegistry | None = None,
        plan_enforcement: PlanEnforcementService,
    ) -> None:
        self.reader = reader
        self.cursor_codec = cursor_codec
        self.metrics = metrics or AuditMetricsRegistry()
        self.plan_enforcement = plan_enforcement

    def query(
        self,
        organization_id: UUID,
        actor: User,
        *,
        actor_user_id: UUID | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
        now: datetime | None = None,
    ) -> AuditEventListResponse:
        started = perf_counter()
        try:
            require_scoped_permission(actor, "audit.read", organization_id)
        except AuthorizationError as exc:
            self.metrics.record(
                "audit_query_requests_total", operation="query", result="forbidden"
            )
            raise AuditForbidden("audit access denied") from exc
        self.plan_enforcement.require_feature(organization_id, "audit")
        try:
            upper = self._aware(to or now or datetime.now(UTC))
            lower = self._aware(from_) if from_ is not None else upper - DEFAULT_RANGE
            if lower >= upper:
                raise AuditInvalidRange("audit range is invalid")
            if upper - lower > MAX_RANGE:
                raise AuditRangeTooLarge("audit range exceeds 366 days")
            if not 1 <= limit <= 200:
                raise AuditInvalidFilter("audit limit is invalid")
            parsed_action = self._action(action)
            parsed_resource = self._resource_type(resource_type)
            parsed_cursor = self.cursor_codec.decode(cursor) if cursor else None
            items, next_cursor = self.reader.page(
                AuditQuery(
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action=parsed_action,
                    resource_type=parsed_resource,
                    resource_id=resource_id,
                    from_=lower,
                    to=upper,
                    cursor=parsed_cursor,
                    limit=limit,
                )
            )
            result = AuditEventListResponse(
                items=items,
                next_cursor=(
                    self.cursor_codec.encode(next_cursor)
                    if next_cursor is not None
                    else None
                ),
            )
            self._metric("success", started)
            return result
        except Exception:
            self._metric("error", started)
            raise

    def _metric(self, result: str, started: float) -> None:
        elapsed = int((perf_counter() - started) * 1000)
        self.metrics.record(
            "audit_query_requests_total", operation="query", result=result
        )
        self.metrics.record(
            "audit_query_duration_seconds",
            operation="query",
            result=result,
            duration_ms=elapsed,
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise AuditInvalidRange("audit timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _action(value: str | None) -> AuditAction | None:
        if value is None:
            return None
        try:
            return ACTION_ADAPTER.validate_python(value)
        except ValidationError as exc:
            raise AuditInvalidFilter("audit action filter is invalid") from exc

    @staticmethod
    def _resource_type(value: str | None) -> AuditResourceType | None:
        if value is None:
            return None
        try:
            return RESOURCE_TYPE_ADAPTER.validate_python(value)
        except ValidationError as exc:
            raise AuditInvalidFilter("audit resource filter is invalid") from exc
