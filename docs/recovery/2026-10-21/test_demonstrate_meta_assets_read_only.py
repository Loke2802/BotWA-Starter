"""Offline tests: tenant asset matching, preflight gating and safe video output."""

import importlib.util
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper(monkeypatch):
    folder = Path(__file__).parent
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location(
        "video_b_assets", folder / "demonstrate_meta_assets_read_only.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_phone_rejects_other_assets_duplicates_and_wrong_display(helper):
    exact = {"id": helper.PHONE_ID, "display_phone_number": "+1 (555) 197-8260"}
    assert helper.exact_test_phone({"data": [exact]})
    assert not helper.exact_test_phone({"data": [exact, exact]})
    assert not helper.exact_test_phone({"data": [{**exact, "id": "other-tenant"}]})
    assert not helper.exact_test_phone(
        {"data": [{**exact, "display_phone_number": "+51 900000000"}]}
    )
    assert not helper.exact_test_phone({"error": {"message": "private"}})


@pytest.mark.parametrize(
    "channel_active,callback_matches", [(False, True), (True, False)]
)
def test_unverified_channel_or_callback_prevents_phone_request(
    helper, monkeypatch, channel_active, callback_matches
):
    state = SimpleNamespace(status="active", webhook_enabled=channel_active)
    monkeypatch.setattr(
        helper,
        "inspect_remote",
        lambda _: {
            "token": {"passed": True},
            "subscription": {
                "app_subscribed": True,
                "override_matches_staging_test": callback_matches,
            },
        },
    )
    monkeypatch.setattr(
        helper,
        "credentials",
        lambda _: pytest.fail("must not decrypt for phone request"),
    )
    assert helper.inspect_assets(state)["status"] == "video_b_checks_incomplete"


def test_phone_query_is_read_only_exact_scoped_and_output_hides_provider_data(
    helper, monkeypatch, capsys
):
    token = "synthetic-private-access-token"
    state = SimpleNamespace(status="active", webhook_enabled=True)
    monkeypatch.setattr(
        helper,
        "inspect_remote",
        lambda _: {
            "token": {"passed": True},
            "subscription": {
                "app_subscribed": True,
                "override_matches_staging_test": True,
            },
        },
    )
    monkeypatch.setattr(helper, "credentials", lambda _: (token, "secret", "verify"))
    monkeypatch.setattr(helper, "graph_version", lambda: "v26.0")
    monkeypatch.setattr(helper, "new_client", lambda: nullcontext(object()))
    calls = []

    def request(client, method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {
            "data": [
                {
                    "id": helper.PHONE_ID,
                    "display_phone_number": "+1 555-197-8260",
                    "unexpected_private_field": token,
                },
                {"id": "unrelated", "display_phone_number": "private-other-phone"},
            ]
        }, {"result": "ok"}

    monkeypatch.setattr(helper, "safe_request", request)
    report = helper.inspect_assets(state)
    assert report["status"] == "video_b_read_only_assets_verified"
    assert len(calls) == 1
    method, url, kwargs = calls[0]
    assert method == "GET"
    assert url == f"https://graph.facebook.com/v26.0/{helper.WABA_ID}/phone_numbers"
    assert token not in url
    assert kwargs["headers"]["Authorization"] == f"Bearer {token}"
    helper.display(report)
    output = capsys.readouterr().out + json.dumps(report)
    assert token not in output
    assert "private-other-phone" not in output
    assert "unexpected_private_field" not in output
    assert "Cambios: 0" in output
