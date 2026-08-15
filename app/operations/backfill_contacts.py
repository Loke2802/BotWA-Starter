import argparse
import json
import sys
from time import perf_counter
from uuid import UUID

import structlog

from app.application.contacts.backfill import ContactBackfillService
from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.service import ContactResolutionService
from app.domain.contacts.contracts import (
    ContactIdentityError,
    ContactIdentityNormalizer,
)
from app.infrastructure.database import SessionLocal
from app.infrastructure.logging import configure_logging
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.infrastructure.settings import get_settings
from app.observability.context import correlation_context
from app.security.secret_cipher import EnvironmentSecretCipher, SecretCipherError

logger = structlog.get_logger(__name__)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Contact links safely")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--organization-id", type=UUID)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    with correlation_context():
        started = perf_counter()
        logger.info("operation_started", operation="contacts_backfill")
        args = _args()
        if not 1 <= args.batch_size <= 1000:
            logger.warning(
                "operation_failed",
                operation="contacts_backfill",
                error_code="INVALID_BATCH_SIZE",
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            print("invalid batch size", file=sys.stderr)
            return 2
        session = SessionLocal()
        try:
            hasher = ContactIdentityHasher(
                settings.contact_identity_hmac_key, ContactIdentityNormalizer()
            )
            cipher = EnvironmentSecretCipher.from_settings(settings)
            resolver = ContactResolutionService(
                SqlAlchemyContactRepository(session), hasher, cipher, session
            )
            metrics = ContactBackfillService(session, resolver, hasher).run(
                batch_size=args.batch_size,
                organization_id=args.organization_id,
                dry_run=args.dry_run,
            )
            safe = metrics.safe_dict()
            logger.info(
                "operation_completed",
                operation="contacts_backfill",
                processed=safe["scanned"],
                updated=safe["linked"],
                skipped=(
                    safe["already_linked"]
                    + safe["skipped_missing_context"]
                    + safe["skipped_invalid_identity"]
                ),
                failed=safe["failed"],
                dry_run=args.dry_run,
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            print(json.dumps(safe, sort_keys=True))
            return 0
        except (ContactIdentityError, SecretCipherError):
            logger.warning(
                "operation_failed",
                operation="contacts_backfill",
                error_code="CONFIGURATION_ERROR",
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            print("backfill configuration failed", file=sys.stderr)
            return 2
        except Exception:
            session.rollback()
            logger.error(
                "operation_failed",
                operation="contacts_backfill",
                error_code="UNEXPECTED_ERROR",
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
            print("backfill failed", file=sys.stderr)
            return 1
        finally:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())
