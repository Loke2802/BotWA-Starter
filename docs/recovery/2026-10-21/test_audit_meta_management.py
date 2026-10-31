"""Offline management audit tests. No network or real credentials."""

import importlib.util
import json
from contextlib import nullcontext
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def helper(monkeypatch):
    folder = Path(__file__).parent
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location(
        "management_audit", folder / "audit_meta_management.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "graph_version", lambda: "v26.0")
    return module


def test_rejects_non_template_mutations_and_wrong_payload(helper):
    with pytest.raises(ValueError):
        helper.request(None, "POST", "/phone_numbers", ("token",), payload=helper.DEMO)
    with pytest.raises(ValueError):
        helper.request(
            None, "POST", "/message_templates", ("token",), payload={"name": "other"}
        )
    with pytest.raises(ValueError):
        helper.request(None, "GET", "/messages", ("token",))


def test_error_output_redacts_credentials_and_provider_urls(helper):
    secrets = (
        "synthetic-access-token",
        "synthetic-app-secret",
        "synthetic-verify-token",
    )
    body = {
        "error": {
            "code": 100,
            "error_subcode": 2388001,
            "message": " ".join(secrets)
            + " https://provider.invalid/?access_token=private",
            "error_user_title": "Test account limitation",
        }
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(400, json=body))
    ) as client:
        payload, result = helper.request(client, "GET", "", secrets)
    assert payload is None and result["http_status"] == 400
    assert result["error_subcode"] == 2388001
    rendered = json.dumps(result)
    assert all(secret not in rendered for secret in secrets)
    assert "provider.invalid" not in rendered


def test_single_post_and_readback_then_repeat_does_not_create(
    helper, monkeypatch, tmp_path
):
    calls = []
    stored = []

    def request(client, method, edge, secrets, **kwargs):
        calls.append(method)
        if method == "POST":
            assert edge == "/message_templates" and kwargs["payload"] == helper.DEMO
            stored.append({**helper.DEMO, "id": "12345", "status": "PENDING"})
            return {"id": "12345", "status": "PENDING"}, {
                "result": "ok",
                "http_status": 200,
            }
        return {"data": list(stored)}, {"result": "ok", "http_status": 200}

    monkeypatch.setattr(helper, "request", request)
    marker = tmp_path / "attempt.json"
    assert (
        helper.create_demo(None, ("fake",), marker)["status"]
        == "demo_created_and_readback_confirmed"
    )
    assert (
        helper.create_demo(None, ("fake",), marker)["status"]
        == "already_exists_no_post"
    )
    assert calls.count("POST") == 1
    assert "fake" not in marker.read_text()


def test_unknown_post_outcome_is_not_retried(helper, monkeypatch, tmp_path):
    calls = []

    def request(client, method, edge, secrets, **kwargs):
        calls.append(method)
        if method == "POST":
            return None, {"result": "request_failed_outcome_unknown_no_details"}
        return {"data": []}, {"result": "ok"}

    monkeypatch.setattr(helper, "request", request)
    marker = tmp_path / "attempt.json"
    assert (
        helper.create_demo(None, ("fake",), marker)["status"]
        == "creation_not_confirmed_no_retry"
    )
    assert (
        helper.create_demo(None, ("fake",), marker)["status"]
        == "previous_attempt_recorded_no_post"
    )
    assert calls.count("POST") == 1


def test_name_collision_and_failed_lookup_never_post(helper, monkeypatch, tmp_path):
    monkeypatch.setattr(
        helper,
        "lookup_demo",
        lambda *_: ({"data": [{**helper.DEMO, "components": []}]}, {"result": "ok"}),
    )
    monkeypatch.setattr(
        helper, "request", lambda *_args, **_kwargs: pytest.fail("must not post")
    )
    assert (
        helper.create_demo(None, ("fake",), tmp_path / "unused")["status"]
        == "name_collision_no_post"
    )
    monkeypatch.setattr(
        helper, "lookup_demo", lambda *_: (None, {"result": "provider_error"})
    )
    assert (
        helper.create_demo(None, ("fake",), tmp_path / "unused")["status"]
        == "lookup_failed_no_post"
    )


def test_default_audit_only_reads_and_omits_paging_credentials(helper, monkeypatch):
    monkeypatch.setattr(helper, "snapshot", lambda: object())
    monkeypatch.setattr(
        helper,
        "inspect_remote",
        lambda _: {
            "ready_to_connect": True,
            "token": {"passed": True},
            "subscription": {"override_matches_staging_test": True},
        },
    )
    monkeypatch.setattr(
        helper, "credentials", lambda _: ("fake-private-token", "secret", "verify")
    )
    monkeypatch.setattr(helper, "new_client", lambda: nullcontext(object()))
    calls = []

    def request(client, method, edge, secrets, **kwargs):
        calls.append(method)
        if edge == "":
            return {"id": helper.WABA_ID}, {"result": "ok", "http_status": 200}
        if edge == "/phone_numbers":
            return {
                "data": [
                    {
                        "id": "1354348231086256",
                        "display_phone_number": "+1 555-197-8260",
                    }
                ]
            }, {"result": "ok", "http_status": 200}
        return {
            "data": [
                {"id": "123", "name": "hello_world", "unexpected_secret": secrets[0]}
            ],
            "paging": {"next": "https://provider.invalid/?access_token=" + secrets[0]},
        }, {"result": "ok", "http_status": 200}

    monkeypatch.setattr(helper, "request", request)
    report = helper.audit()
    assert all(report["checks"].values())
    assert calls == ["GET", "GET", "GET"]
    assert report["creation"]["status"] == "not_requested"
    assert report["more_templates_not_followed"] is True
    output = json.dumps(report)
    assert "fake-private-token" not in output and "provider.invalid" not in output
