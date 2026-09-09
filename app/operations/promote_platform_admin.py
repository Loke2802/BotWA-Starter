"""Safely promote an existing active user to the platform administrator role."""

import argparse
import json
import sys
from datetime import UTC, datetime

import structlog

from app.application.audit.writer import append_non_user_audit
from app.domain.audit.contracts import RoleAssignmentMetadata
from app.infrastructure.database import SessionLocal
from app.infrastructure.logging import configure_logging
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.settings import get_settings
from app.observability.context import correlation_context

logger = structlog.get_logger(__name__)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote an existing active user to platform_admin"
    )
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the promotion; without this flag the command is a dry run",
    )
    return parser.parse_args()


def promote(*, email: str, apply: bool) -> tuple[int, dict[str, object]]:
    normalized_email = email.strip().lower()
    if not normalized_email:
        return 2, {"status": "invalid_email"}

    session = SessionLocal()
    try:
        repository = UserRepository(session=session)
        model = repository.find_by_email(normalized_email)
        if model is None:
            return 2, {"status": "user_not_found"}
        if model.status != "active":
            return 2, {"status": "user_inactive", "user_id": str(model.id)}
        if model.role == "platform_admin":
            return 0, {
                "status": "already_platform_admin",
                "user_id": str(model.id),
                "organization_id": str(model.organization_id),
            }

        result: dict[str, object] = {
            "status": "would_promote" if not apply else "promoted",
            "user_id": str(model.id),
            "organization_id": str(model.organization_id),
            "previous_role": model.role,
        }
        if not apply:
            return 0, result

        previous_role = model.role
        now = datetime.now(UTC)
        model.role = "platform_admin"
        model.auth_version += 1
        model.updated_at = now
        repository.update(model)
        append_non_user_audit(
            SqlAlchemyAuditRepository(session),
            organization_id=model.organization_id,
            actor_type="system",
            action="user.role_changed",
            resource_type="user",
            resource_id=model.id,
            metadata=RoleAssignmentMetadata(
                from_role=previous_role,
                to_role="platform_admin",
            ),
            occurred_at=now,
        )
        session.commit()
        return 0, result
    except Exception:
        session.rollback()
        logger.error(
            "operation_failed",
            operation="promote_platform_admin",
            error_code="UNEXPECTED_ERROR",
        )
        return 1, {"status": "failed"}
    finally:
        session.close()


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    args = _args()
    with correlation_context():
        code, result = promote(email=args.email, apply=args.apply)
        output = sys.stderr if code else sys.stdout
        print(json.dumps(result, sort_keys=True), file=output)
        return code


if __name__ == "__main__":
    raise SystemExit(main())
