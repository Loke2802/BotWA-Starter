"""Validate the local gate's isolation, evidence and bounded process cleanup."""

import json
import os
import subprocess
import sys
from pathlib import Path
from time import sleep
from typing import Any

import pytest
from scripts import check_crm_local as gate


def test_environment_uses_sqlite_without_inherited_postgres_selectors() -> None:
    inherited = {
        "PATH": "keep-me",
        "BOTWA_DATABASE_URL": "postgresql://unrelated",
        "BOTWA_TEST_DATABASE_URL": "postgresql://unrelated",
        "BOTWA_PRD021_POSTGRES_URL": "postgresql://unrelated",
        "BOTWA_CRM_POSTGRES_URL": "postgresql://unrelated",
        "BOTWA_AI_ENABLED": "true",
    }
    clean = gate.test_environment(inherited)
    assert clean["PATH"] == "keep-me"
    assert clean["BOTWA_DATABASE_URL"] == "sqlite:///:memory:"
    assert clean["BOTWA_TEST_DATABASE_URL"] == "sqlite:///:memory:"
    assert clean["BOTWA_AI_ENABLED"] == "false"
    assert not any(key.endswith("_POSTGRES_URL") for key in clean)
    assert inherited["BOTWA_CRM_POSTGRES_URL"] == "postgresql://unrelated"


@pytest.mark.parametrize(
    "bindings",
    [
        [],
        [{"HostIp": "0.0.0.0", "HostPort": "15437"}],
        [{"HostIp": "127.0.0.1", "HostPort": "5432"}],
        [
            {"HostIp": "127.0.0.1", "HostPort": "15437"},
            {"HostIp": "::", "HostPort": "15437"},
        ],
    ],
)
def test_postgres_guard_rejects_nonlocal_bindings(
    bindings: list[dict[str, str]],
) -> None:
    with pytest.raises(ValueError):
        gate.validate_binding(
            {"NetworkSettings": {"Ports": {"5432/tcp": bindings}}}, 15437
        )


def test_postgres_guard_checks_scope_before_invoking_docker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("Docker must not be invoked outside the allowed scope")

    monkeypatch.setattr(subprocess, "run", unexpected)
    with pytest.raises(ValueError):
        gate.postgres_guard("production", 15437, "head")
    with pytest.raises(ValueError):
        gate.postgres_guard("luri-crm-local-recovery", 543, "head")


def test_evidence_stays_in_checkout_and_never_overwrites(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    for path in (Path("..") / "outside", Path(".git") / "logs", Path(".")):
        with pytest.raises(ValueError):
            gate.report_directory(path, root)
    first = gate.report_directory(Path("reports"), root)
    (first / "proof.txt").write_text("preserve", encoding="utf-8")
    second = gate.report_directory(Path("reports"), root)
    assert first != second
    assert (first / "proof.txt").read_text(encoding="utf-8") == "preserve"


def test_step_records_actual_exit_status_and_logs(tmp_path: Path) -> None:
    passed = gate.run_step(
        "ok",
        [sys.executable, "-c", "print('visible')"],
        dict(os.environ),
        tmp_path,
        15,
        root=tmp_path,
    )
    failed = gate.run_step(
        "bad",
        [
            sys.executable,
            "-c",
            "import sys; print('failure', file=sys.stderr); sys.exit(7)",
        ],
        dict(os.environ),
        tmp_path,
        15,
        root=tmp_path,
    )
    assert passed["status"] == "passed" and passed["returncode"] == 0
    assert "visible" in Path(passed["stdout"]).read_text(encoding="utf-8")
    assert failed["status"] == "failed" and failed["returncode"] == 7
    assert "failure" in Path(failed["stderr"]).read_text(encoding="utf-8")


def test_timeout_stops_owned_child_before_delayed_write(tmp_path: Path) -> None:
    late = tmp_path / "child-survived.txt"
    child = (
        "import time; from pathlib import Path; time.sleep(4); "
        "Path('child-survived.txt').write_text('alive')"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}]); "
        "print('parent-ready', flush=True); time.sleep(60)"
    )
    result = gate.run_step(
        "timeout",
        [sys.executable, "-c", parent],
        dict(os.environ),
        tmp_path,
        2,
        root=tmp_path,
    )
    assert result["status"] == "timed_out"
    assert "parent-ready" in Path(result["stdout"]).read_text(encoding="utf-8")
    sleep(4.5)
    assert not late.exists(), "A child process survived the parent's timeout"


def test_source_fingerprint_detects_changes_but_excludes_private_env(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("project", encoding="utf-8")
    (tmp_path / "alembic.ini").write_text("migration", encoding="utf-8")
    app = tmp_path / "app"
    app.mkdir()
    code = app / "sample.py"
    code.write_text("before", encoding="utf-8")
    before = gate.source_digest(tmp_path)
    (tmp_path / ".env").write_text("private", encoding="utf-8")
    assert gate.source_digest(tmp_path) == before
    code.write_text("after", encoding="utf-8")
    assert gate.source_digest(tmp_path) != before


def test_initial_fingerprint_failure_still_preserves_cli_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_directory = gate.report_directory

    def local_directory(destination: Path) -> Path:
        return original_directory(destination, tmp_path)

    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setattr(gate, "report_directory", local_directory)
    monkeypatch.setattr(sys, "argv", ["check_crm_local"])
    # Missing project configuration is an actual pre-check failure, before any
    # subprocess or PostgreSQL guard can run.
    with pytest.raises(SystemExit) as error:
        gate.main()
    assert error.value.code == 1
    reports = list((tmp_path / ".audit-results/crm-local").glob("*/quality.json"))
    assert len(reports) == 1
    proof = json.loads(reports[0].read_text(encoding="utf-8"))
    assert proof["status"] == "failed"
    assert proof["error_type"] == "FileNotFoundError"
    assert proof["source_sha256"] is None
    assert proof["steps"] == []
