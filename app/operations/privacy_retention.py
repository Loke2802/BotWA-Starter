"""Manual IA memory retention; no automatic scheduler or general recovery lane."""

import argparse
from uuid import UUID

from app.application.generative_ai.memory_retention import inspect_memory_retention
from app.infrastructure.database import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect expired IA memory by tenant/bot"
    )
    parser.add_argument("--organization-id", type=UUID, required=True)
    parser.add_argument("--bot-id", type=UUID, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--apply", action="store_true", help="Commit this bounded batch"
    )
    args = parser.parse_args()
    with SessionLocal() as session:
        result = inspect_memory_retention(
            session,
            args.organization_id,
            args.bot_id,
            limit=args.limit,
            apply=args.apply,
        )
        if args.apply:
            session.commit()
    print(
        f"eligible={result.eligible} cleared={result.cleared} "
        f"skipped_active={result.skipped_active}"
    )


if __name__ == "__main__":
    main()
