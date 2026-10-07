"""Repeatable local gates; optional PostgreSQL is restricted to synthetic fixtures."""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]


def test_environment(inherited: dict[str, str]) -> dict[str, str]:
    # Historical optional selectors must never enable another database's cleanup.
    env = {
        key: value
        for key, value in inherited.items()
        if not (key.startswith("BOTWA_") and key.endswith("_POSTGRES_URL"))
    }
    env.update(
        BOTWA_DATABASE_URL="sqlite:///:memory:",
        BOTWA_TEST_DATABASE_URL="sqlite:///:memory:",
        BOTWA_USE_DATABASE="false",
        BOTWA_AI_ENABLED="false",
        PYTHONIOENCODING="utf-8",
        NO_COLOR="1",
    )
    return env


def source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = [root / "pyproject.toml", root / "alembic.ini"]
    for directory in ("app", "tests", "scripts", "alembic"):
        files.extend(
            path
            for path in (root / directory).rglob("*")
            if path.suffix in {".py", ".js", ".html", ".css"} and path.is_file()
        )
    for path in sorted(files):
        # Frame names and bytes, so concatenations of files cannot alias.
        name = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def migration_head() -> tuple[str, str]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    directory = ScriptDirectory.from_config(config)
    heads = directory.get_heads()
    if len(heads) != 1:
        raise ValueError("A single migration head is required")
    script = directory.get_revision(heads[0])
    assert script is not None
    return heads[0], Path(script.path).relative_to(ROOT).as_posix()


def validate_binding(info: dict[str, Any], port: int) -> None:
    bindings = info["NetworkSettings"]["Ports"].get("5432/tcp") or []
    if not bindings or any(
        value["HostIp"] != "127.0.0.1" or int(value["HostPort"]) != port
        for value in bindings
    ):
        raise ValueError("The synthetic PostgreSQL port must bind only to 127.0.0.1")


def postgres_guard(container: str, port: int, head: str) -> dict[str, Any]:
    if not re.fullmatch(r"luri-crm-local-[a-z0-9-]{1,63}", container):
        raise ValueError("Use an explicitly named luri-crm-local-* container")
    if not 1024 <= port <= 65535:
        raise ValueError("Use an unprivileged localhost port")
    result = subprocess.run(
        ["docker", "inspect", container],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if result.returncode:
        raise ValueError("The named synthetic container could not be inspected")
    validate_binding(json.loads(result.stdout)[0], port)
    schema = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            "botwa",
            "-d",
            "crm_local_test",
            "-At",
            "-c",
            "SELECT version_num FROM alembic_version;",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if schema.returncode or schema.stdout.strip() != head:
        raise ValueError("crm_local_test must already have the current migration head")
    return dict(
        container=container, port=port, database="crm_local_test", revision=head
    )


def stop_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        # A Windows venv launcher can have a Python child; killing only the
        # launcher would leave the actual test running beyond its timeout.
        result = subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        if result.returncode and process.poll() is None:
            raise RuntimeError("Could not stop the timed-out check's process tree")
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=15)


def run_step(
    name: str,
    command: list[str],
    env: dict[str, str],
    output: Path,
    timeout: float,
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    stdout, stderr = output / (name + ".stdout.txt"), output / (name + ".stderr.txt")
    started = perf_counter()
    state, code = "failed", None
    with stdout.open("wb") as out, stderr.open("wb") as err:
        try:
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW
            process = subprocess.Popen(
                command,
                cwd=root,
                env=env,
                stdout=out,
                stderr=err,
                start_new_session=sys.platform != "win32",
                creationflags=creationflags,
            )
            try:
                code = process.wait(timeout=timeout)
                state = "passed" if code == 0 else "failed"
            except subprocess.TimeoutExpired:
                state = "timed_out"
                stop_tree(process)
                code = process.returncode
        except OSError as exc:
            err.write((type(exc).__name__ + ": " + str(exc) + "\n").encode())
    return dict(
        name=name,
        status=state,
        returncode=code,
        seconds=round(perf_counter() - started, 3),
        command=["python" if value == sys.executable else value for value in command],
        stdout=str(stdout),
        stderr=str(stderr),
    )


def report_directory(destination: Path, root: Path = ROOT) -> Path:
    root = root.resolve()
    destination = (root / destination).resolve()
    if (
        not destination.is_relative_to(root)
        or destination == root
        or ".git" in destination.relative_to(root).parts
    ):
        raise ValueError("Evidence must stay in a subdirectory of this checkout")
    output = destination / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("crm", "all"), default="crm")
    parser.add_argument("--postgres", action="store_true")
    parser.add_argument("--container", default="luri-crm-local-recovery")
    parser.add_argument("--database-port", type=int, default=15437)
    parser.add_argument("--timeout", type=int, default=1200, help="Seconds per check")
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".audit-results/crm-local")
    )
    args = parser.parse_args()
    if not 60 <= args.timeout <= 3600:
        parser.error("Use 60..3600 seconds per bounded check")
    output = report_directory(args.output_dir)
    env = test_environment(dict(os.environ))
    proof: dict[str, Any] = dict(
        status="failed",
        environment="local SQLite and optional synthetic PostgreSQL",
        suite=args.suite,
        started_at=datetime.now(UTC).isoformat(),
        source_sha256=None,
        steps=[],
        browser_checks="separate, not executed by this CLI",
        deployment_performed=False,
    )
    try:
        before = source_digest(ROOT)
        proof["source_sha256"] = before
        head, migration = migration_head()
        proof["migration_head"] = head
        git = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        proof["git_commit_at_start"] = git.stdout.strip()
        commands = [
            ("ruff", ["ruff", "check", "app", "tests", "scripts", migration]),
            ("black", ["black", "--check", "app", "tests", "scripts", migration]),
            ("mypy-tests", ["mypy", "app", "tests", "--explicit-package-bases"]),
            ("mypy-scripts", ["mypy", "app", "scripts", "--explicit-package-bases"]),
            (
                "pytest",
                [
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    "--basetemp",
                    str(output / "pytest-temp"),
                    "-o",
                    "faulthandler_timeout=60",
                ]
                + (
                    []
                    if args.suite == "all"
                    else [
                        str(p.relative_to(ROOT))
                        for p in sorted((ROOT / "tests").glob("test_crm*.py"))
                    ]
                    + ["tests/test_portal_routes.py", "tests/test_auth_service.py"]
                ),
            ),
        ]
        for name, arguments in commands:
            print("CHECK " + name, flush=True)
            result = run_step(
                name, [sys.executable, "-m", *arguments], env, output, args.timeout
            )
            proof["steps"].append(result)
            print(
                f"{result['status'].upper()} {name} ({result['seconds']}s)", flush=True
            )
        if args.postgres:
            proof["postgres_guard"] = postgres_guard(
                args.container, args.database_port, head
            )
            pg_env = {
                **env,
                "BOTWA_CRM_POSTGRES_URL": (
                    f"postgresql+psycopg://botwa:crm_local_test@127.0.0.1:"
                    f"{args.database_port}/crm_local_test?connect_timeout=15"
                ),
            }
            print("CHECK pytest-postgres (synthetic fixtures only)", flush=True)
            proof["steps"].append(
                run_step(
                    "pytest-postgres",
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "-p",
                        "no:cacheprovider",
                        "--basetemp",
                        str(output / "postgres-temp"),
                        "tests/integration/test_crm_postgresql.py",
                        "tests/integration/test_crm_opportunities_postgresql.py",
                    ],
                    pg_env,
                    output,
                    args.timeout,
                )
            )
        proof["source_unchanged_during_checks"] = source_digest(ROOT) == before
        if proof["source_unchanged_during_checks"] and all(
            step["status"] == "passed" for step in proof["steps"]
        ):
            proof["status"] = "passed"
    except Exception as exc:
        proof.update(status="failed", error_type=type(exc).__name__, error=str(exc))
    finally:
        proof["finished_at"] = datetime.now(UTC).isoformat()
        (output / "quality.json").write_text(
            json.dumps(proof, indent=2) + "\n", encoding="utf-8"
        )
        print(
            proof["status"].upper() + " Evidence: " + str(output / "quality.json"),
            flush=True,
        )
    if proof["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
