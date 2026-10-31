"""Offline safety checks; synthetic inputs only, no database or provider calls."""

import importlib.util
import sys
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def loader():
    script = Path(__file__).with_name("load_meta_test_access_token.py")
    spec = importlib.util.spec_from_file_location("meta_token_loader", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tty(loader, monkeypatch):
    monkeypatch.setattr(
        loader,
        "sys",
        SimpleNamespace(
            stdin=SimpleNamespace(isatty=lambda: True),
            stderr=SimpleNamespace(isatty=lambda: True),
        ),
    )


def test_rejects_noninteractive_input_before_reading(loader, monkeypatch):
    monkeypatch.setattr(
        loader, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: False))
    )
    monkeypatch.setattr(loader.getpass, "getpass", lambda _: pytest.fail("read token"))
    with pytest.raises(SystemExit, match="Interactive terminal required"):
        loader.read_confirmed_token()


def test_never_falls_back_to_echoing_input(loader, tty, monkeypatch):
    def unsafe_getpass(_):
        warnings.warn("echo unavailable", loader.getpass.GetPassWarning, stacklevel=2)
        pytest.fail("echo fallback should be stopped")

    monkeypatch.setattr(loader.getpass, "getpass", unsafe_getpass)
    with pytest.raises(SystemExit, match="Hidden input unavailable"):
        loader.read_confirmed_token()


@pytest.mark.parametrize(
    "value",
    [
        "short",
        "x" * 4001,
        "x" * 20 + "\n",
        "á" * 25,
        "x" * 20 + "\x1b",
        "x" * 20 + "\x7f",
    ],
    ids=["too-short", "too-long", "newline", "non-ascii", "escape", "delete"],
)
def test_invalid_input_never_appears_in_error(loader, tty, monkeypatch, value):
    monkeypatch.setattr(loader.getpass, "getpass", lambda _: value)
    with pytest.raises(SystemExit) as exc:
        loader.read_confirmed_token()
    assert str(exc.value) == "Invalid token format; no changes"
    assert value not in str(exc.value)


def test_requires_exact_human_confirmation(loader, tty, monkeypatch):
    monkeypatch.setattr(
        loader.getpass, "getpass", lambda _: "synthetic-token-test-only"
    )
    monkeypatch.setattr("builtins.input", lambda _: "guardar")
    with pytest.raises(SystemExit, match="Cancelled; no changes"):
        loader.read_confirmed_token()


def test_returns_confirmed_input_without_printing_it(loader, tty, monkeypatch, capsys):
    value = "synthetic-token-test-only"
    monkeypatch.setattr(loader.getpass, "getpass", lambda _: value)
    monkeypatch.setattr("builtins.input", lambda _: "GUARDAR")
    assert loader.read_confirmed_token() == value
    captured = capsys.readouterr()
    assert value not in captured.out + captured.err


def test_cancellation_does_not_disclose_input(loader, tty, monkeypatch):
    def cancelled(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(loader.getpass, "getpass", cancelled)
    with pytest.raises(SystemExit, match="cancelled; no changes"):
        loader.read_confirmed_token()


def test_database_transaction_closed_during_input_and_revalidated(loader, monkeypatch):
    open_sessions = 0

    class FakeSession:
        def __enter__(self):
            nonlocal open_sessions
            open_sessions += 1
            return self

        def __exit__(self, *_):
            nonlocal open_sessions
            open_sessions -= 1

    original = datetime(2026, 10, 22, tzinfo=UTC)
    calls = []

    def validate(_, *, for_update=False):
        calls.append(for_update)
        return None, original + timedelta(seconds=int(for_update)), False

    def read_input():
        assert open_sessions == 0
        return "synthetic-token-test-only"

    monkeypatch.setattr(sys, "argv", ["loader", "--apply"])
    monkeypatch.setattr(loader, "SessionLocal", FakeSession)
    monkeypatch.setattr(loader, "validate_target", validate)
    monkeypatch.setattr(loader, "read_confirmed_token", read_input)
    monkeypatch.setattr(
        loader, "WhatsAppConfigurationService", lambda *_: pytest.fail("must not write")
    )
    with pytest.raises(SystemExit, match="Channel changed during input"):
        loader.main()
    assert calls == [False, True]
    assert open_sessions == 0


def test_existing_token_is_not_overwritten(loader, monkeypatch, capsys):
    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(sys, "argv", ["loader", "--apply"])
    monkeypatch.setattr(loader, "SessionLocal", FakeSession)
    monkeypatch.setattr(loader, "validate_target", lambda _: (None, None, True))
    monkeypatch.setattr(
        loader, "read_confirmed_token", lambda: pytest.fail("must not read")
    )
    loader.main()
    assert "access_token_already_configured_no_changes" in capsys.readouterr().out
