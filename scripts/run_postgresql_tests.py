"""Run every deterministic PostgreSQL suite from a restored Alembic head."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSTGRESQL_TESTS = (
    "tests/integration/test_prd012_postgresql_smoke.py",
    "tests/integration/test_prd012_worker_postgresql.py",
    "tests/integration/test_prd013_postgresql_smoke.py",
    "tests/integration/test_prd014_postgresql_dashboard.py",
    "tests/integration/test_prd015_postgresql.py",
    "tests/integration/test_prd016_postgresql_analytics.py",
    "tests/integration/test_prd017_postgresql_audit.py",
    "tests/integration/test_prd018_postgresql_plans_limits.py",
    "tests/integration/test_prd019_postgresql_billing.py",
    "tests/integration/test_prd020_postgresql_onboarding.py",
    "tests/integration/test_prd021_postgresql_security.py",
    "tests/integration/test_prd022_postgresql_observability.py",
    "tests/test_contacts_inbound.py::test_postgresql_contact_creation_race_creates_one_contact",
)


def _run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    tests = skipped = 0
    with tempfile.TemporaryDirectory(prefix="botwa-postgresql-junit-") as temp_dir:
        output_root = Path(temp_dir)
        for index, target in enumerate(POSTGRESQL_TESTS):
            _run(sys.executable, "-m", "alembic", "upgrade", "head")
            report = output_root / f"postgresql-{index}.xml"
            _run(
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                target,
                "-q",
                f"--junitxml={report}",
            )
            root = ET.parse(report).getroot()
            suites = [root] if root.tag == "testsuite" else list(root)
            tests += sum(int(suite.attrib.get("tests", "0")) for suite in suites)
            skipped += sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
    _run(sys.executable, "-m", "alembic", "upgrade", "head")
    if skipped:
        print(f"PostgreSQL gate rejected {skipped} skipped tests", file=sys.stderr)
        return 1
    print(f"PostgreSQL gate passed: {tests} tests, 0 skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
