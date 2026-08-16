"""Validate security-critical PRD-023 repository workflow contracts."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
PINNED_ACTION = re.compile(r"^[^\s@]+@[0-9a-f]{40}$")
REQUIRED_JOBS = {"quality", "tests", "postgresql", "container-security"}


def validate() -> list[str]:
    errors: list[str] = []
    text = WORKFLOW.read_text(encoding="utf-8")
    document = yaml.load(text, Loader=yaml.BaseLoader)
    if not isinstance(document, dict):
        return ["CI workflow must be a YAML mapping"]
    triggers = document.get("on")
    if not isinstance(triggers, dict):
        errors.append("CI workflow must define structured triggers")
    else:
        if "pull_request_target" in triggers:
            errors.append("pull_request_target is forbidden")
        for required in ("pull_request", "push"):
            trigger = triggers.get(required)
            branches = trigger.get("branches") if isinstance(trigger, dict) else None
            if branches != ["master"]:
                errors.append(f"{required} must target only master")
    permissions = document.get("permissions")
    if permissions != {"contents": "read"}:
        errors.append("default workflow permissions must be contents: read")
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        errors.append("CI workflow must define jobs")
    elif not REQUIRED_JOBS.issubset(jobs):
        errors.append("CI workflow is missing stable required jobs")
    if "write-all" in text or "pull_request_target" in text:
        errors.append("forbidden workflow capability found")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("uses:"):
            reference = stripped.removeprefix("uses:").split("#", 1)[0].strip()
            if not PINNED_ACTION.fullmatch(reference):
                errors.append(f"action is not pinned to a full SHA: {reference}")
    return errors


def main() -> int:
    errors = validate()
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("CI contract validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
