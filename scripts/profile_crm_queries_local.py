"""Read-only SQL/decryption profile, restricted to synthetic localhost manifests."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from app.application.contacts.crm import CrmService
from app.application.contacts.identity import ContactIdentityHasher
from app.application.crm.duplicates import DuplicateService
from app.application.crm.service import OpportunityService
from app.domain.contacts.contracts import ContactIdentityNormalizer
from app.domain.user.contracts import User
from app.infrastructure.models.user import UserModel
from app.security.secret_cipher import SecretCipher
from scripts.rehearse_crm_concurrency_local import validate_source
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from tests.crm_opportunity_support import opportunity_service


class MeasuredCipher(SecretCipher):
    def __init__(self, delegate: SecretCipher) -> None:
        self.delegate = delegate
        self.reads = 0
        self.decrypt_seconds = 0.0

    def encrypt(self, value: str) -> str:
        return self.delegate.encrypt(value)

    def decrypt(self, value: str) -> str:
        started = perf_counter()
        result = self.delegate.decrypt(value)
        self.decrypt_seconds += perf_counter() - started
        self.reads += 1
        return result


def profile(
    manifest: dict[str, Any], source: dict[str, Any], port: int, repeats: int
) -> dict[str, Any]:
    validate_source(manifest, source)
    if not 1024 <= port <= 65535 or not 1 <= repeats <= 10:
        raise ValueError("Use a bounded localhost port and 1..10 repetitions")
    engine = create_engine(
        f"postgresql+psycopg://botwa:crm_local_test@127.0.0.1:{port}/"
        + manifest["databases"]["after"]
    )
    org = UUID(manifest["organization_id"])
    traces: list[tuple[str, Any, float]] = []

    def before_cursor(conn: Any, *_: Any) -> None:
        conn.info["crm_profile_started"] = perf_counter()

    def after_cursor(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: Any
    ) -> None:
        traces.append(
            (statement, params, perf_counter() - conn.info.pop("crm_profile_started"))
        )

    results = []
    try:
        with Session(engine) as session:
            row = session.scalar(
                select(UserModel).where(
                    UserModel.organization_id == org,
                    UserModel.email == manifest["accounts"]["organization_owner"],
                    UserModel.status == "active",
                )
            )
            assert row is not None and row.role == "organization_owner"
            actor = User(id=row.id, organization_id=org, email=row.email, role=row.role)
        event.listen(engine, "before_cursor_execute", before_cursor)
        event.listen(engine, "after_cursor_execute", after_cursor)
        for term in ("perez jose", "grupo marta", "co", "contacto", "duplicates"):
            for repeat in range(repeats):
                traces.clear()
                with Session(engine) as session:
                    commercial = opportunity_service(session)
                    cipher = MeasuredCipher(commercial.cipher)
                    started = perf_counter()
                    if term == "duplicates":
                        duplicates = DuplicateService(
                            OpportunityService(session, cipher, commercial.digest_key)
                        )
                        total = duplicates.candidates(org, actor, 1).total
                        assert total == source["search_runs"][-1]["duplicate_pairs"]
                    else:
                        crm = CrmService(
                            session,
                            cipher,
                            ContactIdentityHasher(
                                commercial.digest_key, ContactIdentityNormalizer()
                            ),
                        )
                        page = crm.list_customers(
                            org,
                            actor,
                            classification=None,
                            status="active",
                            due=False,
                            identifier=None,
                            page=1,
                            page_size=20,
                            search=term,
                        )
                        total = page.total
                        expected = (
                            2
                            if term == "perez jose"
                            else (
                                23
                                if term == "grupo marta"
                                else source["search_dataset"]["count"] - 25
                            )
                        )
                        assert total == expected, (term, total, expected)
                    seconds = perf_counter() - started
                captured = list(traces)
                event.remove(engine, "before_cursor_execute", before_cursor)
                event.remove(engine, "after_cursor_execute", after_cursor)
                plans = []
                if repeat == repeats - 1:
                    with engine.connect() as connection:
                        for sql, params, elapsed in captured:
                            if sql.lstrip().upper().startswith(("SELECT", "WITH")):
                                plan = connection.exec_driver_sql(
                                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql,
                                    params,
                                ).scalar_one()
                                plans.append(
                                    dict(
                                        sql_sha256=hashlib.sha256(
                                            sql.encode()
                                        ).hexdigest(),
                                        sql=sql[:4000],
                                        measured_seconds=round(elapsed, 6),
                                        plan=plan,
                                    )
                                )
                results.append(
                    dict(
                        term=term,
                        repetition=repeat + 1,
                        total=total,
                        seconds=round(seconds, 6),
                        sql_seconds=round(sum(t[2] for t in captured), 6),
                        sql_statements=len(captured),
                        decryptions=cipher.reads,
                        decrypt_seconds=round(cipher.decrypt_seconds, 6),
                        plans=plans,
                    )
                )
                event.listen(engine, "before_cursor_execute", before_cursor)
                event.listen(engine, "after_cursor_execute", after_cursor)
                print(
                    f"PROFILE {term}: {seconds:.3f}s, {cipher.reads} decryptions",
                    flush=True,
                )
    finally:
        engine.dispose()
    return dict(
        status="passed",
        environment="synthetic localhost PostgreSQL",
        database=manifest["databases"]["after"],
        measured_at=datetime.now(UTC).isoformat(),
        results=results,
        cache_note="Fresh SQLAlchemy sessions; PostgreSQL/OS buffers are not cleared",
        external_calls=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database-port", type=int, default=15437)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    proof = profile(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        json.loads(args.source_report.read_text(encoding="utf-8")),
        args.database_port,
        args.repeats,
    )
    args.output.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
