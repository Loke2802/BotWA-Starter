"""Offline safety checks; synthetic passwords only, no staging writes."""

import importlib.util
import io
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper(monkeypatch):
    folder = Path(__file__).parent
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location(
        "reviewer_setup", folder / "create_meta_reviewer.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_report(helper):
    return {
        "email": helper.REVIEW_EMAIL,
        "organization_id": str(helper.ORGANIZATION_ID),
        "ai_enabled": False,
        "transport": "disabled",
        "owner_role": "organization_owner",
        "candidate_role": "operator",
        "existing_accounts": [],
        "counts_in_organization": dict(helper.EXPECTED_COUNTS),
        "conversation_identity_counts": {"other_bot": 0, "other_customer": 0},
        "contacts_without_owner_test_conversation": 0,
        "active_users": 1,
        "user_limit": {"kind": "unlimited"},
    }


def test_exact_scope_and_capacity(helper):
    report = safe_report(helper)
    assert helper.validate_scope(report) == "ready_for_private_reviewer_setup"
    for key, value in [
        ("email", "other@example.invalid"),
        ("ai_enabled", True),
        ("transport", "meta"),
        ("active_users", 2),
        ("user_limit", {"kind": "limited", "value": 1}),
    ]:
        with pytest.raises(ValueError):
            helper.validate_scope({**report, key: value})
    with pytest.raises(ValueError):
        helper.validate_scope(
            {
                **report,
                "conversation_identity_counts": {"other_bot": 1, "other_customer": 0},
            }
        )


def test_existing_account_no_overwrite_and_wrong_role_rejected(helper):
    report = safe_report(helper)
    row = {"same_organization": True, "role": "operator", "status": "active"}
    report["existing_accounts"] = [row]
    assert helper.validate_scope(report) == "reviewer_already_exists_no_changes"
    report["existing_accounts"] = [{**row, "role": "organization_owner"}]
    with pytest.raises(ValueError):
        helper.validate_scope(report)


def test_non_tty_and_visible_fallback_never_accept_password(helper, monkeypatch):
    monkeypatch.setattr(helper, "sys", SimpleNamespace(stdin=io.StringIO()))
    with pytest.raises(ValueError):
        helper.read_password(12, 128)
    monkeypatch.setattr(
        helper, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
    )

    def visible_fallback(_):
        warnings.warn("echo fallback", helper.getpass.GetPassWarning, stacklevel=2)
        pytest.fail("visible input must not be reached")

    monkeypatch.setattr(helper.getpass, "getpass", visible_fallback)
    with pytest.raises(helper.getpass.GetPassWarning):
        helper.read_password(12, 128)


def test_password_confirmation_and_explicit_commit(helper, monkeypatch):
    monkeypatch.setattr(
        helper, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
    )
    password = "synthetic-test-password"
    monkeypatch.setattr(helper.getpass, "getpass", lambda _: password)
    monkeypatch.setattr("builtins.input", lambda _: "CANCELAR")
    with pytest.raises(ValueError):
        helper.read_password(12, 128)
    monkeypatch.setattr("builtins.input", lambda _: "CREAR REVISION")
    assert helper.read_password(12, 128) == password


def test_read_only_mode_never_reads_password_or_writes(helper, monkeypatch, capsys):
    monkeypatch.setattr(helper, "inspect", lambda: safe_report(helper))
    monkeypatch.setattr(helper, "read_password", lambda *_: pytest.fail("no password"))
    monkeypatch.setattr(helper, "SessionLocal", lambda: pytest.fail("no write session"))
    helper.main()
    assert '"account_created": false' in capsys.readouterr().out


def test_mismatch_can_be_corrected_without_printing_passwords(
    helper, monkeypatch, capsys
):
    monkeypatch.setattr(
        helper, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
    )
    values = [
        "synthetic-private-A",
        "synthetic-private-B",
        "synthetic-private-correct",
        "synthetic-private-correct",
    ]
    inputs = iter(values)
    monkeypatch.setattr(helper.getpass, "getpass", lambda _: next(inputs))
    monkeypatch.setattr("builtins.input", lambda _: "CREAR REVISION")
    assert helper.read_password(12, 128) == values[-1]
    output = capsys.readouterr().out
    assert "no coinciden" in output
    assert all(password not in output for password in values)


def test_invalid_length_stops_after_three_attempts(helper, monkeypatch, capsys):
    monkeypatch.setattr(
        helper, "sys", SimpleNamespace(stdin=SimpleNamespace(isatty=lambda: True))
    )
    calls = []

    def hidden_input(_):
        calls.append(1)
        return "short"

    monkeypatch.setattr(helper.getpass, "getpass", hidden_input)
    monkeypatch.setattr(
        "builtins.input", lambda _: pytest.fail("no commit confirmation")
    )
    with pytest.raises(ValueError, match="attempts exhausted"):
        helper.read_password(12, 128)
    assert len(calls) == 6
    output = capsys.readouterr().out
    assert "Longitud no valida" in output and "short" not in output


def test_changed_scope_after_password_stops_before_write(helper, monkeypatch, capsys):
    first = safe_report(helper)
    changed = {**first, "active_users": 2}
    reports = iter([first, changed])
    monkeypatch.setattr(helper, "inspect", lambda: next(reports))
    monkeypatch.setattr(
        helper,
        "get_settings",
        lambda: SimpleNamespace(
            auth_password_min_length=12, auth_password_max_length=128
        ),
    )
    password = "synthetic-test-password"
    monkeypatch.setattr(helper, "read_password", lambda *_: password)
    monkeypatch.setattr(helper, "SessionLocal", lambda: pytest.fail("no write session"))
    with pytest.raises(ValueError):
        helper.main(apply=True)
    assert password not in capsys.readouterr().out
