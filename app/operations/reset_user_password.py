"""Interactively reset an active user's password without exposing the secret."""

import argparse
import getpass
import json
import sys
from datetime import UTC, datetime

import structlog

from app.application.audit.writer import append_non_user_audit
from app.domain.audit.contracts import CredentialRotationMetadata
from app.domain.user.contracts import validate_email
from app.infrastructure.database import SessionLocal
from app.infrastructure.logging import configure_logging
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.user_repository import UserRepository
from app.infrastructure.settings import get_settings
from app.observability.context import correlation_context
from app.security.passwords import PasswordService

logger = structlog.get_logger(__name__)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactively reset an existing active user's password"
    )
    parser.add_argument("--email", required=True)
    return parser.parse_args()


def reset(
    *, email: str, new_password: str, confirmation: str
) -> tuple[int, dict[str, object]]:
    try:
        normalized_email = validate_email(email)
    except ValueError:
        return 2, {"status": "invalid_email"}

    if new_password != confirmation:
        return 2, {"status": "password_mismatch"}
    if len(new_password) < 12:
        return 2, {"status": "password_too_short", "minimum_length": 12}

    settings = get_settings()
    if len(new_password) > settings.auth_password_max_length:
        return 2, {
            "status": "password_too_long",
            "maximum_length": settings.auth_password_max_length,
        }

    session = SessionLocal()
    try:
        repository = UserRepository(session=session)
        model = repository.find_by_email(normalized_email)
        if model is None:
            return 2, {"status": "user_not_found"}
        if model.status != "active":
            return 2, {"status": "user_inactive", "user_id": str(model.id)}

        now = datetime.now(UTC)
        model.password_hash = PasswordService(
            max_length=settings.auth_password_max_length
        ).hash(new_password)
        model.auth_version += 1
        model.updated_at = now
        repository.update(model)
        append_non_user_audit(
            SqlAlchemyAuditRepository(session),
            organization_id=model.organization_id,
            actor_type="system",
            action="user.password_changed",
            resource_type="user",
            resource_id=model.id,
            metadata=CredentialRotationMetadata(),
            occurred_at=now,
        )
        session.commit()
        return 0, {"status": "password_reset", "user_id": str(model.id)}
    except Exception:
        session.rollback()
        logger.error(
            "operation_failed",
            operation="reset_user_password",
            error_code="UNEXPECTED_ERROR",
        )
        return 1, {"status": "failed"}
    finally:
        session.close()


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    args = _args()
    new_password = getpass.getpass("New password: ")
    confirmation = getpass.getpass("Confirm new password: ")
    with correlation_context():
        code, result = reset(
            email=args.email,
            new_password=new_password,
            confirmation=confirmation,
        )
        output = sys.stderr if code else sys.stdout
        print(json.dumps(result, sort_keys=True), file=output)
        return code


if __name__ == "__main__":
    raise SystemExit(main())
