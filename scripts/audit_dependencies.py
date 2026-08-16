"""Apply BotWA's actionable-vulnerability policy to a pip-audit JSON result."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parents[1]


class Vulnerability(TypedDict):
    id: str
    fix_versions: list[str]


class Dependency(TypedDict):
    name: str
    version: str
    vulns: list[Vulnerability]


class AuditReport(TypedDict):
    dependencies: list[Dependency]


def evaluate(report: AuditReport) -> int:
    actionable: list[str] = []
    unfixable: list[str] = []
    for dependency in report.get("dependencies", []):
        package = f"{dependency['name']}=={dependency['version']}"
        for vulnerability in dependency.get("vulns", []):
            item = f"{package} {vulnerability['id']}"
            if vulnerability.get("fix_versions"):
                actionable.append(item)
            else:
                unfixable.append(item)
    for item in sorted(unfixable):
        print(f"unfixed vulnerability (report and track): {item}")
    for item in sorted(actionable):
        print(f"actionable vulnerability: {item}", file=sys.stderr)
    return 1 if actionable else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "lock",
        nargs="?",
        type=Path,
        default=ROOT / "requirements" / "runtime.lock",
    )
    args = parser.parse_args()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "--requirement",
            str(args.lock),
            "--format=json",
            "--progress-spinner=off",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        report = cast(AuditReport, json.loads(completed.stdout))
    except json.JSONDecodeError:
        print("pip-audit did not return valid JSON", file=sys.stderr)
        return 2
    return evaluate(report)


if __name__ == "__main__":
    raise SystemExit(main())
