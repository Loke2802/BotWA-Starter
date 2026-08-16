import base64
from pathlib import Path
from threading import Event

import pytest
from app.api import routes
from app.infrastructure.settings import Environment, Settings
from app.main import create_app
from app.operations import automation_worker
from app.security.configuration import (
    SecurityConfigurationError,
    SecurityConfigurationValidator,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError
from scripts.audit_dependencies import AuditReport, evaluate
from scripts.run_postgresql_tests import POSTGRESQL_TESTS
from scripts.validate_ci_contract import validate

BUILD_SHA = "a1" * 20


def _safe_production_settings(**overrides: object) -> Settings:
    baseline = Settings(
        environment=Environment.PRODUCTION,
        build_sha=BUILD_SHA,
        auth_secret_key="auth-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ-secret",
        legacy_core_api_enabled=False,
        legacy_whatsapp_enabled=False,
        public_bootstrap_enabled=False,
        allowed_hosts=("api.example.com",),
        rate_limit_hmac_key="r" * 48,
        audit_cursor_signing_key="c" * 48,
        integration_oauth_state_secret="o" * 48,
        contact_identity_hmac_key="contact-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        whatsapp_secret_encryption_key=base64.urlsafe_b64encode(b"w" * 32).decode(),
        openapi_enabled=False,
    )
    return baseline.model_copy(update=overrides)


def test_build_sha_is_optional_locally_and_normalized_when_present() -> None:
    assert Settings(environment="development").build_sha is None
    assert Settings(environment="test", build_sha=BUILD_SHA.upper()).build_sha == (
        BUILD_SHA
    )


@pytest.mark.parametrize("invalid", ["short", "g" * 40, "a" * 39, "a" * 41])
def test_build_sha_rejects_malformed_values(invalid: str) -> None:
    with pytest.raises(ValidationError, match="40-character hexadecimal"):
        Settings(build_sha=invalid)


def test_production_requires_build_sha() -> None:
    with pytest.raises(SecurityConfigurationError, match="build_sha"):
        SecurityConfigurationValidator().validate(
            _safe_production_settings(build_sha=None)
        )
    SecurityConfigurationValidator().validate(_safe_production_settings())


def test_version_returns_only_safe_build_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(environment="test", use_database=False, build_sha=BUILD_SHA)
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    with TestClient(create_app()) as client:
        payload = client.get("/version").json()
    assert payload == {
        "app_name": "BotWA Starter",
        "api_version": "v1",
        "build_sha": BUILD_SHA,
    }
    assert "environment" not in payload
    assert "database" not in str(payload).lower()


def test_worker_shutdown_finishes_current_batch_and_stops_before_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = Event()
    calls: list[int] = []

    def batch(batch_size: int) -> int:
        calls.append(batch_size)
        stop_event.set()
        return 1

    monkeypatch.setattr(automation_worker, "run_batch", batch)
    automation_worker.run_worker(20, once=False, stop_event=stop_event)
    assert calls == [20]


def test_worker_idle_wait_is_interruptible(monkeypatch: pytest.MonkeyPatch) -> None:
    class RecordingEvent(Event):
        def __init__(self) -> None:
            super().__init__()
            self.waits: list[float] = []

        def is_set(self) -> bool:
            return bool(self.waits)

        def wait(self, timeout: float | None = None) -> bool:
            assert timeout is not None
            self.waits.append(timeout)
            return True

    stop_event = RecordingEvent()
    monkeypatch.setattr(automation_worker, "run_batch", lambda _batch_size: 0)
    automation_worker.run_worker(20, once=False, stop_event=stop_event)
    assert stop_event.waits == [1]


def test_ci_workflow_contract_is_valid() -> None:
    assert validate() == []


def test_postgresql_gate_covers_all_deterministic_database_tests() -> None:
    expected = {
        str(path).replace("\\", "/")
        for path in Path("tests/integration").glob("test_*.py")
        if "google_real" not in path.name
    }
    configured = {target.split("::", 1)[0] for target in POSTGRESQL_TESTS}
    assert expected <= configured
    assert "tests/integration/test_prd013_google_real_smoke.py" not in configured
    assert any("contact_creation_race" in target for target in POSTGRESQL_TESTS)


def test_dockerfile_is_reproducible_minimal_and_non_root() -> None:
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "python:3.13.15-slim@sha256:" in dockerfile
    assert " AS builder" in dockerfile
    assert " AS runtime" in dockerfile
    assert "pip install --require-hashes" in dockerfile
    assert "/opt/venv/lib/python3.13/site-packages/pip" in dockerfile
    assert "COPY . ." not in dockerfile
    assert "COPY --chown=10001:10001 app/ ./app/" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile and "/health/live" in dockerfile
    assert '"--workers", "1"' in dockerfile
    assert "alembic upgrade" not in dockerfile


def test_docker_context_excludes_sensitive_and_non_runtime_trees() -> None:
    ignored = set(Path(".dockerignore").read_text(encoding="utf-8").splitlines())
    assert {".env", ".env.*", ".git", ".github", "respaldos/"} <= ignored
    assert {"tests/", "docs/", ".venv", "*.zip"} <= ignored


def test_lock_files_are_exact_and_hashed() -> None:
    for path in (Path("requirements/runtime.lock"), Path("requirements/dev.lock")):
        content = path.read_text(encoding="utf-8")
        requirements = [
            line
            for line in content.splitlines()
            if line and not line[0].isspace() and not line.startswith("#")
        ]
        assert requirements
        assert all("==" in line for line in requirements)
        assert "--hash=sha256:" in content
        assert ">=" not in content


def test_runtime_lock_excludes_development_tooling() -> None:
    runtime = Path("requirements/runtime.lock").read_text(encoding="utf-8")
    assert "pytest==" not in runtime
    assert "pip-tools==" not in runtime
    assert "pip-audit==" not in runtime


def test_dependency_audit_policy_blocks_only_fixable_findings() -> None:
    report: AuditReport = {
        "dependencies": [
            {
                "name": "fixed-package",
                "version": "1.0",
                "vulns": [{"id": "CVE-1", "fix_versions": ["1.1"]}],
            },
            {
                "name": "unfixed-package",
                "version": "2.0",
                "vulns": [{"id": "CVE-2", "fix_versions": []}],
            },
        ]
    }
    assert evaluate(report) == 1
    report["dependencies"][0]["vulns"] = []
    assert evaluate(report) == 0
