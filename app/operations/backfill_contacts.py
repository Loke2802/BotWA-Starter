import argparse
import json
import sys
from uuid import UUID

from app.application.contacts.backfill import ContactBackfillService
from app.application.contacts.identity import ContactIdentityHasher
from app.application.contacts.service import ContactResolutionService
from app.domain.contacts.contracts import (
    ContactIdentityError,
    ContactIdentityNormalizer,
)
from app.infrastructure.database import SessionLocal
from app.infrastructure.repositories.contact_repository import (
    SqlAlchemyContactRepository,
)
from app.infrastructure.settings import get_settings
from app.security.secret_cipher import EnvironmentSecretCipher, SecretCipherError


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Contact links safely")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--organization-id", type=UUID)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    if not 1 <= args.batch_size <= 1000:
        print("invalid batch size", file=sys.stderr)
        return 2
    session = SessionLocal()
    try:
        settings = get_settings()
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
        print(json.dumps(metrics.safe_dict(), sort_keys=True))
        return 0
    except (ContactIdentityError, SecretCipherError):
        print("backfill configuration failed", file=sys.stderr)
        return 2
    except Exception:
        session.rollback()
        print("backfill failed", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
