import argparse
from dataclasses import dataclass

import pytest
from app.infrastructure.settings import Settings
from app.observability.context import current_correlation_id
from app.operations import automation_worker, backfill_contacts, billing_due_transitions
from app.security.secret_cipher import EnvironmentSecretCipher


class RecordingLogger:
    def __init__(self) -> None:
        self.entries: list[dict[str, object]] = []

    def _record(self, event: str, fields: dict[str, object]) -> None:
        self.entries.append(
            {
                "event": event,
                "correlation_id": current_correlation_id(),
                **fields,
            }
        )

    def info(self, event: str, **fields: object) -> None:
        self._record(event, fields)

    def warning(self, event: str, **fields: object) -> None:
        self._record(event, fields)

    def error(self, event: str, **fields: object) -> None:
        self._record(event, fields)


class FakeSession:
    def __init__(self) -> None:
        self.closed = False
        self.rolled_back = False

    def close(self) -> None:
        self.closed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _events(logger: RecordingLogger, event: str) -> list[dict[str, object]]:
    return [entry for entry in logger.entries if entry["event"] == event]


def test_billing_command_disabled_run_has_safe_complete_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = RecordingLogger()
    monkeypatch.setattr(billing_due_transitions, "logger", logger)
    monkeypatch.setattr(
        billing_due_transitions,
        "get_settings",
        lambda: Settings(use_database=False, billing_enabled=False),
    )
    assert billing_due_transitions.run_batch() == 0
    assert len(_events(logger, "operation_started")) == 1
    completed = _events(logger, "operation_completed")[0]
    assert completed["examined"] == 0
    assert completed["retryable_failed"] == 0
    assert completed["correlation_id"] is not None
    assert current_correlation_id() is None


def test_billing_command_failure_is_safe_and_preserves_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = RecordingLogger()
    session = FakeSession()
    monkeypatch.setattr(billing_due_transitions, "logger", logger)
    monkeypatch.setattr(billing_due_transitions, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        billing_due_transitions,
        "get_settings",
        lambda: Settings(use_database=False, billing_enabled=True),
    )

    def fail_build(*_args: object) -> None:
        raise RuntimeError("private billing failure")

    monkeypatch.setattr(billing_due_transitions, "build_billing_service", fail_build)
    with pytest.raises(RuntimeError, match="private billing failure"):
        billing_due_transitions.run_batch()
    failed = _events(logger, "operation_failed")
    assert len(failed) == 1
    assert failed[0]["error_code"] == "UNEXPECTED_ERROR"
    assert "private billing failure" not in str(failed)
    assert session.closed


def test_contacts_backfill_command_reports_dry_run_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = RecordingLogger()
    session = FakeSession()

    class Metrics:
        def safe_dict(self) -> dict[str, int]:
            return {
                "scanned": 5,
                "linked": 2,
                "already_linked": 1,
                "skipped_missing_context": 1,
                "skipped_invalid_identity": 1,
                "failed": 0,
            }

    class Backfill:
        def __init__(self, *_args: object) -> None:
            return

        def run(self, **_kwargs: object) -> Metrics:
            return Metrics()

    monkeypatch.setattr(backfill_contacts, "logger", logger)
    monkeypatch.setattr(backfill_contacts, "configure_logging", lambda _level: None)
    monkeypatch.setattr(backfill_contacts, "SessionLocal", lambda: session)
    monkeypatch.setattr(backfill_contacts, "ContactBackfillService", Backfill)
    monkeypatch.setattr(
        backfill_contacts,
        "_args",
        lambda: argparse.Namespace(batch_size=10, organization_id=None, dry_run=True),
    )
    monkeypatch.setattr(
        backfill_contacts,
        "get_settings",
        lambda: Settings(
            use_database=False,
            contact_identity_hmac_key="identity-key-for-test",
        ),
    )
    monkeypatch.setattr(backfill_contacts, "ContactIdentityHasher", lambda *_: object())
    monkeypatch.setattr(
        EnvironmentSecretCipher,
        "from_settings",
        lambda _settings: object(),
    )
    monkeypatch.setattr(
        backfill_contacts, "ContactResolutionService", lambda *_: object()
    )
    monkeypatch.setattr(
        backfill_contacts, "SqlAlchemyContactRepository", lambda *_: object()
    )

    assert backfill_contacts.main() == 0
    completed = _events(logger, "operation_completed")[0]
    assert completed["processed"] == 5
    assert completed["updated"] == 2
    assert completed["skipped"] == 3
    assert completed["failed"] == 0
    assert completed["dry_run"] is True
    assert session.closed


def test_contacts_backfill_invalid_batch_preserves_exit_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = RecordingLogger()
    monkeypatch.setattr(backfill_contacts, "logger", logger)
    monkeypatch.setattr(backfill_contacts, "configure_logging", lambda _level: None)
    monkeypatch.setattr(
        backfill_contacts,
        "_args",
        lambda: argparse.Namespace(batch_size=0, organization_id=None, dry_run=False),
    )
    assert backfill_contacts.main() == 2
    assert _events(logger, "operation_failed")[0]["error_code"] == (
        "INVALID_BATCH_SIZE"
    )


@dataclass
class WorkerRow:
    status: str = "pending"


def test_automation_worker_emits_actual_batch_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = RecordingLogger()
    session = FakeSession()
    rows = [WorkerRow(), WorkerRow()]

    class Repository:
        def __init__(self, _session: object) -> None:
            return

        def claim(self, _owner: str, _batch_size: int, _lease: int) -> list[WorkerRow]:
            return rows

    class Service:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return

        def run(self, row: WorkerRow) -> None:
            row.status = "succeeded"

    monkeypatch.setattr(automation_worker, "logger", logger)
    monkeypatch.setattr(automation_worker, "SessionLocal", lambda: session)
    monkeypatch.setattr(automation_worker, "ManagedAutomationRepository", Repository)
    monkeypatch.setattr(automation_worker, "ManagedAutomationService", Service)
    monkeypatch.setattr(
        automation_worker, "SqlAlchemyAuditRepository", lambda *_: object()
    )
    monkeypatch.setattr(
        automation_worker, "SqlAlchemyPlanRepository", lambda *_: object()
    )
    monkeypatch.setattr(
        automation_worker, "PlanEnforcementService", lambda *_: object()
    )
    monkeypatch.setattr(
        automation_worker, "HumanHandoffRepository", lambda *_: object()
    )
    monkeypatch.setattr(automation_worker, "HumanHandoffService", lambda *_: object())

    assert automation_worker.run_batch(20) == 2
    completed = _events(logger, "operation_completed")[0]
    assert completed["claimed"] == 2
    assert completed["completed"] == 2
    assert completed["failed"] == 0
    assert completed["skipped"] == 0
    assert completed["correlation_id"] is not None
    assert session.closed
