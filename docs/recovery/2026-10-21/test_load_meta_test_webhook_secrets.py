"""Offline tests using synthetic secrets only; no real DB/provider access."""

import importlib.util
import sys
import warnings
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

APP_SECRET = "a" * 32
VERIFY_TOKEN = "synthetic_verify_token_test_only_123456"


@pytest.fixture
def loader(monkeypatch):
    folder = Path(__file__).parent
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location(
        "webhook_secrets_loader", folder / "load_meta_test_webhook_secrets.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "sys",
        SimpleNamespace(
            stdin=SimpleNamespace(isatty=lambda: True),
            stderr=SimpleNamespace(isatty=lambda: True),
        ),
    )
    return module


def inputs(loader, monkeypatch, values, confirmation="GUARDAR"):
    sequence = iter(values)
    monkeypatch.setattr(loader.getpass, "getpass", lambda _: next(sequence))
    monkeypatch.setattr("builtins.input", lambda _: confirmation)


def test_hidden_entry_does_not_print_secrets(loader, monkeypatch, capsys):
    inputs(loader, monkeypatch, [APP_SECRET, VERIFY_TOKEN, VERIFY_TOKEN])
    assert loader.read_confirmed_secrets() == (APP_SECRET, VERIFY_TOKEN)
    captured = capsys.readouterr()
    assert APP_SECRET not in captured.out + captured.err
    assert VERIFY_TOKEN not in captured.out + captured.err


def test_non_tty_never_reads(loader, monkeypatch):
    monkeypatch.setattr(loader.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(loader.getpass, "getpass", lambda _: pytest.fail("read secret"))
    with pytest.raises(SystemExit, match="Interactive terminal required"):
        loader.read_confirmed_secrets()


def test_echo_fallback_is_blocked(loader, monkeypatch):
    def fallback(_):
        warnings.warn("echo unavailable", loader.getpass.GetPassWarning, stacklevel=2)
        pytest.fail("must not fall back to echo")

    monkeypatch.setattr(loader.getpass, "getpass", fallback)
    with pytest.raises(SystemExit, match="Hidden input unavailable"):
        loader.read_confirmed_secrets()


@pytest.mark.parametrize("value", ["short", "z" * 32, APP_SECRET + "\x1b"])
def test_invalid_app_secret_redacted(loader, monkeypatch, value):
    inputs(loader, monkeypatch, [value])
    with pytest.raises(SystemExit) as exc:
        loader.read_confirmed_secrets()
    assert str(exc.value) == "Invalid App Secret format; no changes"
    assert value not in str(exc.value)


@pytest.mark.parametrize(
    "value", ["short", "x" * 129, "x" * 31 + " ", VERIFY_TOKEN + "\x1b"]
)
def test_invalid_verify_token_redacted(loader, monkeypatch, value):
    inputs(loader, monkeypatch, [APP_SECRET, value])
    with pytest.raises(SystemExit) as exc:
        loader.read_confirmed_secrets()
    assert str(exc.value) == "Invalid verify token format; no changes"
    assert value not in str(exc.value)


def test_mismatched_confirmation_stops(loader, monkeypatch):
    inputs(loader, monkeypatch, [APP_SECRET, VERIFY_TOKEN, "different"])
    with pytest.raises(SystemExit, match="confirmation mismatch"):
        loader.read_confirmed_secrets()


def test_exact_human_confirmation_required(loader, monkeypatch):
    inputs(loader, monkeypatch, [APP_SECRET, VERIFY_TOKEN, VERIFY_TOKEN], "guardar")
    with pytest.raises(SystemExit, match="Cancelled"):
        loader.read_confirmed_secrets()


@pytest.fixture
def operation(loader, monkeypatch):
    state = SimpleNamespace(open_sessions=0, writes=[], input_calls=0)
    stamp = datetime.now(UTC)
    states = [(None, stamp, False, False), (None, stamp, False, False)]

    class FakeSession:
        def __enter__(self):
            state.open_sessions += 1
            return self

        def __exit__(self, *_):
            state.open_sessions -= 1

    monkeypatch.setattr(sys, "argv", ["loader", "--apply"])
    monkeypatch.setattr(loader, "SessionLocal", FakeSession)
    monkeypatch.setattr(loader, "inspect_target", lambda *a, **kw: states.pop(0))
    monkeypatch.setattr(loader, "correlation_context", nullcontext)

    def read():
        assert state.open_sessions == 0
        state.input_calls += 1
        return APP_SECRET, VERIFY_TOKEN

    monkeypatch.setattr(loader, "read_confirmed_secrets", read)
    for name in (
        "SqlAlchemyWhatsAppConfigurationRepository",
        "BotRepository",
        "OrganizationRepository",
        "SqlAlchemyPlanRepository",
        "SqlAlchemyAuditRepository",
        "PlanEnforcementService",
    ):
        monkeypatch.setattr(loader, name, lambda _: None)
    monkeypatch.setattr(loader, "get_settings", lambda: None)
    monkeypatch.setattr(
        loader, "EnvironmentSecretCipher", SimpleNamespace(from_settings=lambda _: None)
    )

    def rotate(*args):
        request = args[-2]
        assert request.access_token is None
        assert request.app_secret == APP_SECRET
        assert request.verify_token == VERIFY_TOKEN
        state.writes.append(True)
        return SimpleNamespace(
            id=loader.CONFIGURATION_ID,
            access_token_configured=True,
            app_secret_configured=True,
            verify_token_configured=True,
            status="draft",
            webhook_enabled=False,
        )

    monkeypatch.setattr(
        loader,
        "WhatsAppConfigurationService",
        lambda *a: SimpleNamespace(rotate_secrets=rotate),
    )
    return state, states, stamp


def test_transaction_closed_during_entry_and_existing_token_preserved(
    loader, operation, capsys
):
    state, _, _ = operation
    loader.main()
    assert state.writes == [True]
    out = capsys.readouterr().out
    assert "test_webhook_secrets_saved_encrypted" in out
    assert APP_SECRET not in out and VERIFY_TOKEN not in out


def test_concurrent_change_aborts_without_write(loader, operation):
    state, states, stamp = operation
    states[1] = (None, stamp + timedelta(seconds=1), False, False)
    with pytest.raises(SystemExit, match="Channel changed"):
        loader.main()
    assert not state.writes


@pytest.mark.parametrize("existing", [(True, True), (True, False), (False, True)])
def test_never_overwrites_or_reads_input_when_secret_exists(
    loader, operation, existing
):
    state, states, stamp = operation
    states[0] = (None, stamp, *existing)
    loader.main()
    assert state.input_calls == 0
    assert not state.writes
