"""Generate or verify BotWA's hashed pip lock files."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class LockTarget:
    output: Path
    extras: tuple[str, ...] = ()


TARGETS = (
    LockTarget(ROOT / "requirements" / "runtime.lock"),
    LockTarget(ROOT / "requirements" / "dev.lock", ("dev",)),
)


def _compile(target: LockTarget, output: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        "--generate-hashes",
        "--allow-unsafe",
        "--resolver=backtracking",
        "--strip-extras",
        "--no-emit-index-url",
        "--no-header",
        "--no-annotate",
        "--quiet",
        f"--output-file={output}",
    ]
    command.extend(f"--extra={extra}" for extra in target.extras)
    command.append(str(ROOT / "pyproject.toml"))
    subprocess.run(command, cwd=ROOT, check=True)


def generate() -> None:
    for target in TARGETS:
        target.output.parent.mkdir(parents=True, exist_ok=True)
        _compile(target, target.output)
        print(f"generated {target.output.relative_to(ROOT)}")


def check() -> int:
    failures: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="botwa-lock-check-") as temp_dir:
        temp_root = Path(temp_dir)
        for target in TARGETS:
            candidate = temp_root / target.output.name
            if not target.output.exists():
                failures.append(target.output)
                continue
            # pip-compile reuses compatible versions from an existing output.
            # Seed the candidate with the committed lock so a freshness check
            # detects source changes without turning every new PyPI release
            # into an unrelated lock drift failure.
            shutil.copyfile(target.output, candidate)
            _compile(target, candidate)
            if candidate.read_bytes() != target.output.read_bytes():
                failures.append(target.output)
    if failures:
        for path in failures:
            print(
                f"stale lock: {path.relative_to(ROOT)}; "
                "run `python scripts/lock_dependencies.py`",
                file=sys.stderr,
            )
        return 1
    print("dependency locks are current")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        return check()
    generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
