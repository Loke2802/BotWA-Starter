"""Supervised contact retention / verified data-subject request (local operator)."""

import argparse
import json
from dataclasses import asdict
from uuid import UUID

from app.application.privacy_erasure import erase_contact
from app.infrastructure.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", type=UUID, required=True)
    parser.add_argument("--bot-id", type=UUID, required=True)
    parser.add_argument("--contact-id", type=UUID, required=True)
    parser.add_argument("--mode", choices=("retention", "request"), default="retention")
    parser.add_argument("--max-rows", type=int, default=10000)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-fingerprint")
    args = parser.parse_args()
    with SessionLocal() as session:
        result = erase_contact(
            session,
            args.organization_id,
            args.bot_id,
            args.contact_id,
            mode=args.mode,
            max_rows=args.max_rows,
            apply=args.apply,
            expected_fingerprint=args.expected_fingerprint,
        )
        if result.applied:
            session.commit()
        else:
            session.rollback()
    print(json.dumps(asdict(result), sort_keys=True))
    if result.blockers:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
