"""Read-only schema review; emits proposals, never executes generated DDL."""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
from collections import Counter
from pathlib import Path

import app.infrastructure.models as models
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.infrastructure.database import Base
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import AddConstraint, CreateIndex


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = make_url(args.url)
    if (
        url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.get_backend_name() != "postgresql"
    ):
        parser.error("This rehearsal accepts only a local PostgreSQL URL")
    for module in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"{models.__name__}.{module.name}")
    engine = create_engine(url)
    with engine.connect() as connection:
        diffs = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    findings = []
    proposals = [
        "-- REVIEW ONLY. Not a migration; no statements have been applied.",
        "-- Reconcile names/definitions with historical migrations before executing.",
        "-- Existing indexes, constraints and JSONB data must be preserved.",
    ]
    for diff in diffs:
        if isinstance(diff, list):
            for item in diff:
                findings.append(
                    {
                        "operation": item[0],
                        "table": item[2],
                        "column": item[3],
                        "database_type": str(item[-2]),
                        "model_type": str(item[-1]),
                        "decision": "Align model to stored type; avoid data casts.",
                    }
                )
            continue
        operation, obj = diff[:2]
        table = getattr(getattr(obj, "table", None), "name", None)
        finding = {
            "operation": operation,
            "table": table,
            "name": str(getattr(obj, "name", "")),
            "definition": str(getattr(obj, "sqltext", "")),
            "columns": [c.name for c in getattr(obj, "columns", [])],
            "decision": "Preserve existing object; inspect semantic "
            "equivalence/name before changing.",
        }
        if operation in {"add_index", "add_constraint"}:
            ddl = CreateIndex(obj) if operation == "add_index" else AddConstraint(obj)
            finding["proposal"] = str(ddl.compile(dialect=engine.dialect))
            proposals.extend(
                [
                    f"-- {table}: {operation}; review equivalents and data first.",
                    finding["proposal"] + ";",
                ]
            )
        findings.append(finding)
    report = {
        "scope": "Local migrated PostgreSQL; all model modules loaded; "
        "read-only review",
        "count": len(findings),
        "by_operation": dict(Counter(f["operation"] for f in findings)),
        "crm_findings": [f for f in findings if str(f["table"]).startswith("crm_")],
        "findings": findings,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output.with_suffix(".sql").write_text(
        "\n".join(proposals) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in ["count", "by_operation", "crm_findings"]}))
    engine.dispose()


if __name__ == "__main__":
    main()
